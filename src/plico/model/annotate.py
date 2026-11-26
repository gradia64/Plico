"""Annotations made in Plico: highlight, underline, strike out, notes, ink.

An annotation is state of the virtual page, like a redaction: nothing is
written into the PDF until the document is saved, so every one of them can be
undone. They live in PAGE space (unrotated PDF points), the space
``Page.add_highlight_annot()`` and its siblings expect -- measured on a page
with ``/Rotate 90``: the highlight lands on the word only when it is given the
unrotated rectangle, exactly like a redaction (see ``redact.py``).

Those already in the file are part of the source page, and its picture: they
are described once, when the file is opened (:class:`FileAnnotation`), and
the page remembers what the user did to them -- taken off, or a note given
new words. The source stays untouched; the save applies the changes to the
copy of the page (:func:`apply_file_changes`), and the preview to a copy of
its own.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

import pymupdf

from .redact import RedactionRect

HIGHLIGHT = "highlight"
UNDERLINE = "underline"
STRIKEOUT = "strikeout"
NOTE = "note"
INK = "ink"

# Markup follows the words of the text; the other two are placed by hand.
MARKUP = (HIGHLIGHT, UNDERLINE, STRIKEOUT)
KINDS = (*MARKUP, NOTE, INK)

# One colour per kind, as RGB in 0..1: the usual ones of PDF readers, so the
# file reads the same in Okular or Acrobat.
Color = tuple[float, float, float]

COLORS: dict[str, Color] = {
    HIGHLIGHT: (1.0, 0.85, 0.0),
    UNDERLINE: (0.12, 0.53, 0.9),
    STRIKEOUT: (0.86, 0.18, 0.18),
    NOTE: (1.0, 0.85, 0.0),
    INK: (0.86, 0.18, 0.18),
}

# The pen of a freehand line, in points.
INK_WIDTH = 2.0
# Size of a note's icon on the page, in points: the one PyMuPDF draws.
NOTE_SIZE = 16.0
# Limits on what a single annotation may carry: a stroke is sampled from the
# mouse, and a note is typed. Neither should be able to grow a save without
# bound.
MAX_INK_POINTS = 5000
MAX_NOTE_TEXT = 10_000
# Annotations of the file described per page, at most: a page past this is
# shown as it is, its annotations not editable -- the file is untrusted, and
# every one of them is a box to test under each click.
MAX_FILE_ANNOTATIONS = 1000
# Not annotations to the reader: a link is the text it sits on, a widget a
# form field (the form panel's), a popup the window of a note, which goes
# when its note goes.
_NOT_EDITABLE = frozenset(
    (pymupdf.PDF_ANNOT_LINK, pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_WIDGET)  # type: ignore[attr-defined]
)


@dataclass(frozen=True)
class Annotation:
    """One annotation, in page space.

    Frozen and compared by value, like :class:`RedactionRect`: the undo
    commands find it again in the page's list by equality.
    """

    kind: str
    # Markup: one rectangle per line of text covered.
    rects: tuple[RedactionRect, ...] = ()
    # Ink: one stroke, as the points the mouse went through.
    points: tuple[tuple[float, float], ...] = ()
    # Note: the centre of its icon, and what it says.
    at: tuple[float, float] = (0.0, 0.0)
    text: str = ""
    # A colour the user chose instead of the kind's own (RGB in 0..1).
    tint: Color | None = None

    @property
    def color(self) -> Color:
        return self.tint or COLORS[self.kind]

    @property
    def movable(self) -> bool:
        """Markup belongs to the words under it; notes and strokes can move."""
        return self.kind not in MARKUP

    def moved(self, dx: float, dy: float) -> Annotation:
        """The same annotation *dx*, *dy* points further on the page."""
        return replace(
            self,
            points=tuple((x + dx, y + dy) for x, y in self.points),
            at=(self.at[0] + dx, self.at[1] + dy),
        )

    def bounds(self) -> RedactionRect:
        """The page-space box the annotation occupies (to find it under a click)."""
        if self.kind in MARKUP and self.rects:
            return RedactionRect(
                min(r.x0 for r in self.rects),
                min(r.y0 for r in self.rects),
                max(r.x1 for r in self.rects),
                max(r.y1 for r in self.rects),
            )
        if self.kind == INK and self.points:
            pad = INK_WIDTH * 2
            xs = [x for x, _ in self.points]
            ys = [y for _, y in self.points]
            return RedactionRect(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
        x, y = self.at
        half = NOTE_SIZE / 2
        return RedactionRect(x - half, y - half, x + half, y + half)

    def hit(self, x: float, y: float, slop: float = 0.0) -> bool:
        """Whether the page-space point (*x*, *y*) falls on the annotation.

        Markup answers for its own lines, not for the box around them: two
        lines highlighted at the ends of a paragraph do not own the middle.
        A stroke answers within *slop* of the line it draws.
        """
        if self.kind in MARKUP:
            return any(r.x0 <= x <= r.x1 and r.y0 <= y <= r.y1 for r in self.rects)
        if self.kind == INK:
            reach = max(slop, INK_WIDTH)
            pts = self.points
            if len(pts) == 1:
                return _distance(x, y, pts[0], pts[0]) <= reach
            return any(_distance(x, y, a, b) <= reach for a, b in itertools.pairwise(pts))
        box = self.bounds()
        return box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1


def _distance(x: float, y: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance from (*x*, *y*) to the segment *a*–*b*."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length))
    px, py = ax + t * dx, ay + t * dy
    return float(((x - px) ** 2 + (y - py) ** 2) ** 0.5)


def lines_of(words: Sequence[RedactionRect]) -> tuple[RedactionRect, ...]:
    """The words covered, joined into one rectangle per line.

    A highlight made of one box per word leaves a gap at every space, which
    no reader draws; PDF markup is one quadrilateral per line. Two words are
    on the same line when their boxes overlap vertically for at least half
    the height of the smaller one.
    """
    lines: list[RedactionRect] = []
    for word in sorted(words, key=lambda w: ((w.y0 + w.y1) / 2, w.x0)):
        if lines:
            last = lines[-1]
            overlap = min(last.y1, word.y1) - max(last.y0, word.y0)
            smaller = min(last.y1 - last.y0, word.y1 - word.y0)
            if smaller > 0 and overlap >= smaller / 2:
                lines[-1] = RedactionRect(
                    min(last.x0, word.x0),
                    min(last.y0, word.y0),
                    max(last.x1, word.x1),
                    max(last.y1, word.y1),
                )
                continue
        lines.append(RedactionRect(word.x0, word.y0, word.x1, word.y1))
    return tuple(lines)


def write_annotations(page: pymupdf.Page, annotations: Sequence[Annotation]) -> None:
    """Write *annotations* into *page*, as real PDF annotations.

    Runs BEFORE the redactions of the same page: a redaction deletes every
    annotation it touches (see ``burn_redactions``), and a note written over
    erased words must go with them rather than survive on top.
    """
    for annotation in annotations:
        annot = _add(page, annotation)
        if annot is None:
            continue
        annot.set_colors(stroke=annotation.color)
        if annotation.kind == HIGHLIGHT:
            annot.set_opacity(0.5)
        annot.set_info(title="Plico")
        annot.update()


def _add(page: pymupdf.Page, annotation: Annotation) -> pymupdf.Annot | None:
    if annotation.kind in MARKUP:
        if not annotation.rects:
            return None
        quads = [pymupdf.Rect(*rect.as_tuple()).quad for rect in annotation.rects]
        if annotation.kind == HIGHLIGHT:
            return page.add_highlight_annot(quads=quads)
        if annotation.kind == UNDERLINE:
            return page.add_underline_annot(quads=quads)
        return page.add_strikeout_annot(quads=quads)
    if annotation.kind == INK:
        if len(annotation.points) < 2:
            return None
        annot = page.add_ink_annot([list(annotation.points)])
        annot.set_border(width=INK_WIDTH)
        return annot
    if annotation.kind == NOTE:
        # PyMuPDF puts the icon's corner on the point, and which corner
        # depends on the page's /Rotate (it keeps the icon upright). Placing
        # it once and moving the point by what was missed centres it on the
        # click whatever the rotation.
        x, y = annotation.at
        probe = page.add_text_annot((x, y), "", icon="Note")
        centre = (probe.rect.x0 + probe.rect.x1) / 2, (probe.rect.y0 + probe.rect.y1) / 2
        page.delete_annot(probe)
        point = (2 * x - centre[0], 2 * y - centre[1])
        return page.add_text_annot(point, annotation.text, icon="Note")
    return None


@dataclass(frozen=True)
class FileAnnotation:
    """An annotation already in the source page, as read when the file opened.

    *index* is its place among ``page.annots()`` of the source page: copying a
    page keeps that order (measured), so it finds the annotation again in
    the copy the save and the preview work on. *subtype* is checked there
    too. Everything is in page space, as ``Annot.rect`` reports it -- for a
    note, where its icon is drawn.
    """

    index: int
    subtype: str
    rect: RedactionRect
    # Markup: one box per quadrilateral, so the middle of a paragraph
    # highlighted at both ends is not part of it.
    parts: tuple[RedactionRect, ...] = ()
    text: str = ""
    # What it is drawn in now, if PyMuPDF can redraw it in another colour.
    color: Color | None = None

    @property
    def is_note(self) -> bool:
        return self.subtype == "Text"

    @property
    def has_text(self) -> bool:
        """A note's words are in its popup, a FreeText's on the page."""
        return self.subtype in _WITH_TEXT

    @property
    def movable(self) -> bool:
        return self.subtype not in _MARKUP_SUBTYPES

    @property
    def colorable(self) -> bool:
        return self.subtype in _COLORABLE

    def hit(self, x: float, y: float, offset: tuple[float, float] = (0.0, 0.0)) -> bool:
        """Whether (*x*, *y*) falls on it, once moved by *offset*."""
        x, y = x - offset[0], y - offset[1]
        boxes = self.parts or (self.rect,)
        return any(r.x0 <= x <= r.x1 and r.y0 <= y <= r.y1 for r in boxes)


@dataclass(frozen=True)
class FileAnnotationEdit:
    """What the user did to one annotation of the file. The default: nothing."""

    removed: bool = False
    # New words for a note or a FreeText.
    text: str | None = None
    color: Color | None = None
    # How far it was moved, in page points.
    offset: tuple[float, float] = (0.0, 0.0)

    @property
    def unchanged(self) -> bool:
        return self == FileAnnotationEdit()


_MARKUP_SUBTYPES = frozenset(("Highlight", "Underline", "StrikeOut", "Squiggly"))
_WITH_TEXT = frozenset(("Text", "FreeText"))
# What PyMuPDF redraws in a new colour (measured): a stamp or an attachment
# keeps an appearance of its own, which a redraw would throw away.
_COLORABLE = frozenset(
    ("Text", "FreeText", "Square", "Circle", "Line", "Polygon", "PolyLine", "Ink")
) | _MARKUP_SUBTYPES


def read_file_annotations(page: pymupdf.Page) -> list[FileAnnotation]:
    """Describe the annotations of *page* a reader sees (not links or fields)."""
    entries = [entry for entry in page.annot_xrefs() if entry[1] not in _NOT_EDITABLE]
    if not entries or len(entries) > MAX_FILE_ANNOTATIONS:
        return []
    described = (_describe_safely(index, annot) for index, annot in enumerate(page.annots()))
    return [annotation for annotation in described if annotation is not None]


def _describe_safely(index: int, annot: pymupdf.Annot) -> FileAnnotation | None:
    """Like :func:`_describe`; a malformed annotation is left alone, not a
    reason to refuse the file."""
    try:
        return _describe(index, annot)
    except Exception:  # noqa: BLE001
        return None


def _describe(index: int, annot: pymupdf.Annot) -> FileAnnotation:
    rect = RedactionRect.from_corners(*annot.rect)
    parts: tuple[RedactionRect, ...] = ()
    if annot.type[0] in _QUAD_KINDS and annot.vertices:
        points = annot.vertices
        parts = tuple(
            RedactionRect.from_corners(
                min(p[0] for p in quad), min(p[1] for p in quad),
                max(p[0] for p in quad), max(p[1] for p in quad),
            )
            for quad in (points[i : i + 4] for i in range(0, len(points) - 3, 4))
        )
    text = (annot.info.get("content") or "")[:MAX_NOTE_TEXT]
    subtype = annot.type[1]
    return FileAnnotation(index, subtype, rect, parts, text, _color_of(annot, subtype))


def _color_of(annot: pymupdf.Annot, subtype: str) -> Color | None:
    """The colour it is drawn in: a FreeText's is its text's, in /DA."""
    if subtype not in _COLORABLE:
        return None
    if subtype == "FreeText":
        kind, value = annot.parent.parent.xref_get_key(annot.xref, "DA")
        found = _DA_RGB.search(value) if kind == "string" else None
        values = [float(v) for v in found.groups()] if found else []
    else:
        values = [float(v) for v in annot.colors.get("stroke") or ()]
    return (values[0], values[1], values[2]) if len(values) == 3 else None


_DA_RGB = re.compile(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg")
_NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
# Where an annotation keeps its coordinates, in pairs: moving it is adding
# the same step to every pair, without redrawing it.
_POSITIONS = ("Rect", "InkList", "L", "Vertices", "CL")


_QUAD_KINDS = frozenset(
    (
        pymupdf.PDF_ANNOT_HIGHLIGHT,  # type: ignore[attr-defined]
        pymupdf.PDF_ANNOT_UNDERLINE,  # type: ignore[attr-defined]
        pymupdf.PDF_ANNOT_STRIKE_OUT,  # type: ignore[attr-defined]
        pymupdf.PDF_ANNOT_SQUIGGLY,  # type: ignore[attr-defined]
    )
)


def apply_file_changes(
    page: pymupdf.Page,
    edits: Sequence[tuple[FileAnnotation, FileAnnotationEdit]],
) -> None:
    """Do to the copy *page* what the user did to the file's annotations.

    Found first and changed afterwards: deleting shifts the indices of the
    ones after.
    """
    present = list(page.annots())
    targets: list[tuple[pymupdf.Annot, FileAnnotation, FileAnnotationEdit]] = []
    for annotation, edit in edits:
        annot = _find(present, annotation)
        if annot is not None and not edit.unchanged:
            targets.append((annot, annotation, edit))
    for annot, annotation, edit in targets:
        if edit.removed:
            page.delete_annot(annot)
            continue
        if edit.offset != (0.0, 0.0) and annotation.movable:
            _shift(page.parent, annot.xref, *edit.offset)
        redraw = False
        if edit.text is not None and annotation.has_text:
            annot.set_info(content=edit.text)
            if annotation.subtype == "FreeText":
                # Readers draw the rich text when there is one, and it still
                # says the old words.
                page.parent.xref_set_key(annot.xref, "RC", "null")
            redraw = True
        if edit.color is not None and annotation.colorable:
            if annotation.subtype == "FreeText":
                annot.update(text_color=edit.color)
                redraw = False
            else:
                annot.set_colors(stroke=edit.color)
                redraw = True
        if redraw:
            annot.update()


def _shift(doc: pymupdf.Document, xref: int, dx: float, dy: float) -> None:
    """Move an annotation by (*dx*, *dy*) page points, as it is drawn.

    Its appearance is drawn into /Rect, so moving the numbers moves the
    picture as it is -- a stamp keeps its image, a box its border (measured,
    also on turned pages, where PyMuPDF's ``set_rect`` grows a bordered box
    and lands a note elsewhere). PDF space grows upwards: down the page is
    minus.
    """
    for key in _POSITIONS:
        kind, value = doc.xref_get_key(xref, key)
        if kind != "array":
            continue
        position = 0

        def step(match: re.Match[str]) -> str:
            nonlocal position
            moved = float(match.group()) + (dx if position % 2 == 0 else -dy)
            position += 1
            return f"{moved:.4f}"

        doc.xref_set_key(xref, key, _NUMBER.sub(step, value))


def _find(present: list[pymupdf.Annot], annotation: FileAnnotation) -> pymupdf.Annot | None:
    """*annotation* among the annotations of a copy of its page.

    By position, if the subtype agrees; otherwise the one of that subtype
    whose box matches. A note is matched on its type alone at its position:
    PyMuPDF reports its box where the icon is drawn, and that moves with the
    rotation the save gives the page.
    """
    if annotation.index < len(present):
        annot = present[annotation.index]
        if annot.type[1] == annotation.subtype:
            return annot
    for annot in present:
        if annot.type[1] == annotation.subtype and _close(annot.rect, annotation.rect):
            return annot
    return None


def _close(rect: pymupdf.Rect, box: RedactionRect, tolerance: float = 1.0) -> bool:
    found = (rect.x0, rect.y0, rect.x1, rect.y1)
    return all(abs(a - b) <= tolerance for a, b in zip(found, box.as_tuple(), strict=True))
