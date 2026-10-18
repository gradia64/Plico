"""Minimal text editing: replace the text of one span, keeping its look.

A *span* is the unit MuPDF reports in ``get_text("dict")``: a run of text on
one line in one font, size and colour. It is the right unit for a minimal
edit -- a block is a whole paragraph over several lines, and a word has no
style of its own -- and it carries everything needed to write the
replacement where the original was: baseline origin, font, size, colour.

Everything here is in PAGE space (unrotated PDF points), like redactions:
``get_text("dict")``, ``add_redact_annot()`` and ``TextWriter`` all use it,
so a page with its own /Rotate needs no conversion at all.

The edit happens in two steps, and both are destructive only on the page
they are given:

1. the original text is removed from the content stream with a redaction
   that touches ONLY text -- no fill, no image or line-art damage -- so the
   background, table borders and the neighbouring spans survive;
2. the new text is written with a :class:`pymupdf.TextWriter` at the original
   baseline, in the best font available (see :func:`check_edit`).

What a minimal edit deliberately does not do: reflow, multi-line text,
vertical text, or Type3 fonts. Those are refused with a message, never
attempted badly.

Nothing here opens a file: the caller hands over a live page, opened with
:func:`plico.model.document.open_for_reading` when it is a source, so an
encrypted PDF needs no special case.
"""

import functools
import subprocess
from dataclasses import dataclass

import pymupdf
from PySide6.QtCore import QCoreApplication

# get_text("dict") span flags
_ITALIC = 1 << 1
_SERIF = 1 << 2
_MONO = 1 << 3
_BOLD = 1 << 4

# A longer text is shrunk to fit down to this scale and refused below it:
# squeezed past ~80% it no longer looks like the paragraph around it.
MIN_SCALE = 0.8

# The right margin assumed when nothing on the page bounds a span sooner.
_PAGE_MARGIN = 36.0

# Font sources, in order of preference; also what the caller is told.
FROM_DOCUMENT = "documento"
FROM_SYSTEM = "sistema"
FROM_FALLBACK = "riserva"


@dataclass(frozen=True)
class TextSpan:
    """One span of a source page, as it was when the user picked it.

    Frozen and self-contained: everything the save needs is captured here,
    so materialising the edit never has to find the span again.
    """

    text: str
    bbox: tuple[float, float, float, float]   # page space
    origin: tuple[float, float]                # baseline start, page space
    font: str                                  # PostScript name, no subset tag
    size: float
    color: int                                 # 0xRRGGBB
    flags: int
    horizontal: bool
    type3: bool
    # Free width to the right of the span before the next text or vertical
    # rule: how far a longer replacement may grow.
    room: float

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]


@dataclass(frozen=True)
class TextEdit:
    """A replacement planned for one span of a virtual page.

    State of the page, like a redaction: nothing is written until the
    document is materialised. The span is the identity -- there is at most
    one edit per span, so editing the same words twice replaces the first
    edit instead of stacking two texts on top of each other.
    """

    span: TextSpan
    new_text: str


@dataclass(frozen=True)
class FontChoice:
    """How a replacement will be written."""

    font_name: str
    source: str        # FROM_DOCUMENT, FROM_SYSTEM or FROM_FALLBACK
    scale: float       # 1.0 = the original size


def _room(page: pymupdf.Page, spans: list[dict], rect: pymupdf.Rect) -> float:
    """Free width to the right of *rect*: up to the next text OR vertical rule.

    The next span of the same line is not enough. A table cell is a block of
    its own, so the neighbouring cell's text and the border between the two
    are invisible to the line -- the prototype let a longer text run straight
    through both.
    """
    # The page edge in PAGE space. ``page.rect`` is already turned by /Rotate,
    # so on a quarter-turned A4 it is 842 wide while the spans live in a space
    # 595 wide, and a longer text was let run 210 points off the page.
    right = (page.rect * page.derotation_matrix).x1 - _PAGE_MARGIN
    for other in spans:
        o = pymupdf.Rect(other["bbox"])
        if o.x0 >= rect.x1 - 0.5 and o.y0 < rect.y1 and o.y1 > rect.y0:
            right = min(right, o.x0)
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                a, b = item[1], item[2]
                if abs(a.x - b.x) >= 0.5:
                    continue
                x, top, bottom = a.x, min(a.y, b.y), max(a.y, b.y)
            elif item[0] == "re":
                # A thin rectangle is how many producers draw a rule.
                r = item[1]
                if r.width > 2:
                    continue
                x, top, bottom = r.x0, r.y0, r.y1
            else:
                continue
            if x >= rect.x1 - 0.5 and top < rect.y1 and bottom > rect.y0:
                right = min(right, x)
    return max(0.0, float(right - rect.x1) - 1.0)


def _font_key(name: str) -> str:
    """Compare font names the way they actually differ between APIs.

    ``get_fonts()`` and ``get_text("dict")`` spell the same font differently
    -- "ABCDEF+Nimbus Roman Regular" against "NimbusRoman-Regular" -- so the
    subset tag, spaces, hyphens and case are all dropped.
    """
    return "".join(c for c in name.split("+")[-1] if c not in " -_").lower()


def _type3_fonts(page: pymupdf.Page) -> set[str]:
    return {_font_key(f[3]) for f in page.get_fonts() if f[2] == "Type3"}


# How far outside a span's box a click still picks it, in points. A span's
# box is tight around the glyphs, so the gap between two lines, or a click a
# hair to the left of the first letter, would otherwise find nothing at all --
# and "nothing happens" is what the user then sees.
HIT_TOLERANCE = 3.0


def span_at(page: pymupdf.Page, x: float, y: float) -> TextSpan | None:
    """The span under the page-space point (*x*, *y*), or ``None``.

    A span that contains the point wins; otherwise the nearest one within
    :data:`HIT_TOLERANCE` points.
    """
    blocks = page.get_text("dict")["blocks"]
    every = [
        span
        for block in blocks
        for line in block.get("lines", ())
        for span in line["spans"]
        if span["text"].strip()
    ]
    best: tuple[float, dict, dict] | None = None
    for block in blocks:
        for line in block.get("lines", ()):
            for span in line["spans"]:
                if not span["text"].strip():
                    continue
                rect = pymupdf.Rect(span["bbox"])
                # Distance from the point to the box: 0 inside it.
                dx = max(rect.x0 - x, 0.0, x - rect.x1)
                dy = max(rect.y0 - y, 0.0, y - rect.y1)
                distance = (dx * dx + dy * dy) ** 0.5
                if distance <= HIT_TOLERANCE and (best is None or distance < best[0]):
                    best = (distance, span, line)
    if best is None:
        return None
    _, span, line = best
    rect = pymupdf.Rect(span["bbox"])
    font = span["font"]
    return TextSpan(
        text=span["text"],
        bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
        origin=(span["origin"][0], span["origin"][1]),
        font=font,
        size=span["size"],
        color=span["color"],
        flags=span["flags"],
        horizontal=tuple(line["dir"]) == (1.0, 0.0),
        # MuPDF names a Type3 span "Type3 (xref)" when the font has no name
        # of its own.
        type3=font.startswith("Type3") or _font_key(font) in _type3_fonts(page),
        room=_room(page, every, rect),
    )


def _embedded_font(page: pymupdf.Page, name: str) -> pymupdf.Font | None:
    """The span's own font program, if the document embeds a usable one.

    Usable is rarer than it sounds: office producers embed glyph-indexed
    subsets with no character map, so ``has_glyph`` answers no for every
    character and :func:`_covers` moves on to the next source.
    """
    for xref, _ext, ftype, basefont, *_ in page.get_fonts():
        if _font_key(basefont) != _font_key(name) or ftype == "Type3":
            continue
        _, ext, _, buffer = page.parent.extract_font(xref)
        if ext in ("n/a", "") or not buffer:
            return None
        try:
            return pymupdf.Font(fontbuffer=buffer)
        except Exception:  # noqa: BLE001 -- a damaged program is just unusable
            return None
    return None


@functools.lru_cache(maxsize=64)
def _system_font_path(postscript_name: str) -> str | None:
    """Where the installed font with this PostScript name lives, if anywhere.

    The font a document was made with (Liberation, DejaVu, Noto, Open
    Sans...) is often installed even when its embedded subset is useless.
    ``fc-match`` always answers with *something*, so the name it returns is
    checked. Cached: the answer does not change while Plico runs, and the
    lookup is a subprocess.
    """
    try:
        found = subprocess.run(
            ["fc-match", "-f", "%{postscriptname}|%{file}", f":postscriptname={postscript_name}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    name, _, path = found.partition("|")
    return path if name == postscript_name and path else None


def _system_font(name: str) -> pymupdf.Font | None:
    path = _system_font_path(name)
    if path is None:
        return None
    try:
        return pymupdf.Font(fontfile=path)
    except Exception:  # noqa: BLE001 -- unreadable file: try the next source
        return None


def _fallback_font(flags: int) -> pymupdf.Font:
    """A built-in look-alike chosen from the span's flags."""
    bold, italic = bool(flags & _BOLD), bool(flags & _ITALIC)
    if flags & _MONO:
        family = ("cour", "cobo", "coit", "cobi")
    elif flags & _SERIF:
        family = ("tiro", "tibo", "tiit", "tibi")
    else:
        family = ("helv", "hebo", "heit", "hebi")
    return pymupdf.Font(family[bold + 2 * italic])


def _covers(font: pymupdf.Font, text: str) -> bool:
    return all(c == " " or font.has_glyph(ord(c)) for c in text)


def _resolve(page: pymupdf.Page, span: TextSpan, new_text: str) -> tuple[pymupdf.Font, FontChoice]:
    """Pick the font and size for *new_text*, or explain why it cannot be done."""
    if not span.horizontal:
        raise ValueError(QCoreApplication.translate("TextEdit", "Si può modificare solo testo orizzontale."))
    if span.type3:
        # Type3 glyphs are drawings: the colour lives inside each glyph (the
        # span reports black), and redacting them leaves visible remnants.
        raise ValueError(
            QCoreApplication.translate("TextEdit", "Questo testo usa un font Type3 e non si può modificare.")
        )

    candidates = (
        (lambda: _embedded_font(page, span.font), FROM_DOCUMENT),
        (lambda: _system_font(span.font), FROM_SYSTEM),
        (lambda: _fallback_font(span.flags), FROM_FALLBACK),
    )
    for load, source in candidates:
        font = load()
        if font is not None and _covers(font, new_text):
            break
    else:
        raise ValueError(
            QCoreApplication.translate("TextEdit", "Nessun font disponibile contiene questi caratteri.")
        )

    needed = font.text_length(new_text, fontsize=span.size)
    available = span.width + span.room
    scale = min(1.0, available / needed) if needed > 0 else 1.0
    if scale < MIN_SCALE:
        raise ValueError(
            QCoreApplication.translate(
                "TextEdit", "Il testo nuovo non ci sta: andrebbe rimpicciolito al {0}%."
            ).format(round(scale * 100))
        )
    return font, FontChoice(font_name=font.name, source=source, scale=scale)


def check_edit(page: pymupdf.Page, span: TextSpan, new_text: str) -> FontChoice:
    """Whether *new_text* can replace *span* on *page*, without touching it.

    Meant for the moment the user confirms the edit: a replacement that
    cannot be written must be refused there, not discovered at save time.
    Raises :class:`ValueError` with a message for the user.
    """
    return _resolve(page, span, new_text)[1]


def _removal_band(span: TextSpan) -> pymupdf.Rect:
    """Where the old text is redacted: a band across the line, not its box.

    MuPDF deletes every glyph whose box touches the redaction, and a glyph
    box runs from ascender to descender. The span's own box therefore reaches
    into the lines above and below at ordinary single spacing, and redacting
    it took letters off both (measured at 1.0, 1.15 and 1.2 leading, with
    Helvetica and Times). Every glyph of the span crosses the band between
    half and a fifth of the size above the baseline; no glyph of another
    line does.
    """
    baseline = span.origin[1]
    return pymupdf.Rect(
        span.bbox[0], baseline - 0.5 * span.size, span.bbox[2], baseline - 0.2 * span.size
    )


def apply_edit(page: pymupdf.Page, span: TextSpan, new_text: str) -> FontChoice:
    """Replace *span*'s text on *page* with *new_text*.

    *page* is the page being materialised, never a source. Raises
    :class:`ValueError` (and leaves the page alone) when the edit cannot be
    written. The font is embedded whole: the caller should run
    ``doc.subset_fonts()`` before saving, or a single edit in a system font
    adds a couple of hundred kilobytes to the file.
    """
    font, choice = _resolve(page, span, new_text)

    # Remove ONLY the text: no fill (fill=None paints nothing -- measured on
    # a shaded cell, the background stays) and no image or line-art damage
    # (borders and shading stay).
    page.add_redact_annot(_removal_band(span), fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,  # type: ignore[attr-defined]
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,  # type: ignore[attr-defined]
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,  # type: ignore[attr-defined]
    )

    if new_text:
        color = span.color
        writer = pymupdf.TextWriter(
            page.rect,
            color=((color >> 16) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255),
        )
        writer.append(span.origin, new_text, font=font, fontsize=span.size * choice.scale)
        writer.write_text(page)
    return choice
