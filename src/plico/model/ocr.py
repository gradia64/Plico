"""Read the text of a scanned page, and write it back invisibly.

A scan is a picture of words: the page carries no text at all, so nothing on
it can be selected, searched or redacted by word. Tesseract turns that picture
back into words with a position, and Plico keeps them on the page item -- like
a redaction, they are state of the virtual page, and they reach the file only
when the document is saved, as an invisible text layer under the image.

Two behaviours of PyMuPDF's OCR decide the shape of this module, both
measured:

* the raster is built from the page AS DISPLAYED, so a quarter turn of
  ``/Rotate`` lays the words sideways in it and Tesseract answers ``DIOZ``
  where the page says ``SCANSIONE``. The rotation is therefore taken off for
  the duration of the call and put back afterwards -- on our own read-only
  handle, which is never saved;
* with the rotation off, the rectangles come back in the page's unrotated
  space, which is exactly where a redaction and a text span live, so nothing
  has to be converted anywhere.

What the words are worth is a different question, and only the user can answer
it: the layer sits under the picture and changes neither the picture nor what
the page looks like.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import pymupdf
from PySide6.QtCore import QCoreApplication, QLocale

# 300 dpi is the resolution Tesseract's own documentation recommends for
# scanned office documents, and its cost here is small: a full A4 page of text
# takes half a second (measured), so a 30-page scan is some fifteen seconds --
# which is why recognition runs in the thread pool and not on the GUI thread.
DEFAULT_DPI = 300

# PDF render mode 3: the text joins the page but is never painted. This is what
# makes the layer invisible while staying selectable and searchable.
INVISIBLE = 3

# Where a distribution puts the language data of Tesseract. Plico's own copy
# (and the Flatpak build's) is added in front of these, see tessdata_dir().
_TESSDATA_DIRS = (
    "/app/share/tessdata",
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tesseract-ocr/4.00/tessdata",
    "/usr/local/share/tessdata",
    "/usr/share/tessdata",
)

# Tesseract's code for each language Plico speaks. The document is most likely
# in the user's own language, and together with English -- the numbers,
# addresses and borrowed words of any office document -- it reads better than
# either alone.
_TESSERACT = {
    QLocale.Language.Italian: "ita",
    QLocale.Language.English: "eng",
    QLocale.Language.Spanish: "spa",
    QLocale.Language.French: "fra",
    QLocale.Language.German: "deu",
}


def user_tessdata_dir() -> str:
    """Where Plico's own language data belongs, honouring ``$XDG_DATA_HOME``.

    The place to point a user at: it needs no root, and the Flatpak build has
    no way to write anywhere else either.
    """
    base = os.environ.get("XDG_DATA_HOME") or "~/.local/share"
    return os.path.expanduser(os.path.join(base, "plico", "tessdata"))


@dataclass(frozen=True)
class OcrWord:
    """One word Tesseract read, and where it found it.

    The rectangle is in PAGE space -- the unrotated PDF points a redaction
    lives in -- never in screen coordinates.
    """

    text: str
    rect: tuple[float, float, float, float]

    @property
    def size(self) -> float:
        """Font size to write the word with, taken from the height of its box.

        An approximation, and it can afford to be one: the layer is invisible,
        so all that matters is that the letters cover the ink they stand for,
        which is what a reader highlights when the text is selected.
        """
        return max(self.rect[3] - self.rect[1], 1.0)

    @property
    def baseline(self) -> float:
        """Where the baseline goes: above the bottom of the box, by a descender."""
        return self.rect[3] - self.size * 0.2


def tessdata_dir() -> str | None:
    """The directory the language data is read from, or ``None`` if there is none.

    ``$PLICO_TESSDATA`` wins, so the choice can be made without touching code.
    A directory only counts if it actually holds language data:
    ``/usr/share/tesseract-ocr/5/tessdata`` exists on a bare Debian system and
    is empty, and answering with it would send Tesseract looking for files it
    will not find.
    """
    candidates = [user_tessdata_dir(), *_TESSDATA_DIRS]
    if override := os.environ.get("PLICO_TESSDATA"):
        candidates.insert(0, override)
    for candidate in candidates:
        directory = os.path.expanduser(candidate)
        if languages(directory):
            return directory
    return None


def languages(directory: str | None = None) -> list[str]:
    """The language codes installed in *directory* (default: the chosen one).

    ``osd`` is Tesseract's orientation data, not a language a page can be read
    with, so it is left out.
    """
    path = tessdata_dir() if directory is None else directory
    if not path:
        return []
    try:
        names = os.listdir(path)
    except OSError:
        return []
    suffix = ".traineddata"
    return sorted(
        name[: -len(suffix)]
        for name in names
        if name.endswith(suffix) and name != f"osd{suffix}"
    )


def default_language(locale: QLocale | None = None) -> str:
    """The best language to read the user's documents with, out of what is there.

    The language of *locale* (the default one: the interface's) together
    with English when both are installed, then either alone, then whatever
    else there is: refusing to read a page because the ideal data is missing
    would be worse than reading it imperfectly. A language Plico does not
    speak gets English, like its interface does.

    The default locale, not the system's: a language chosen in «Impostazioni»
    is set as the default, and an interface in German on an Italian system
    proposed Italian for the documents (reported by a review).
    """
    locale = QLocale() if locale is None else locale
    own = _TESSERACT.get(locale.language(), "eng")
    available = languages()
    preferred = [code for code in dict.fromkeys((own, "eng")) if code in available]
    if preferred:
        return "+".join(preferred)
    return available[0] if available else "eng"


_reason: str | None = None
_asked = False


def unavailable_reason() -> str | None:
    """``None`` when OCR can run, otherwise why it cannot, for the user.

    The answer comes from a real recognition on a page made of a single
    picture, and it is remembered: nothing cheaper tells the whole truth, and
    the truth has two halves -- the language data being installed, and MuPDF
    finding the Tesseract library when the call is made. The check is not run
    at startup, only when the tool is asked for.
    """
    global _asked, _reason
    if not _asked:
        _asked = True
        _reason = _check()
    return _reason


def _check() -> str | None:
    directory = tessdata_dir()
    if directory is None:
        return QCoreApplication.translate(
            "Ocr",
            "Manca il dato di lingua di Tesseract (un file .traineddata).\n"
            "Si possono installare i pacchetti tesseract-ocr-ita e tesseract-ocr-eng, "
            "oppure copiare i file in {0}.",
        ).format(user_tessdata_dir())
    # A picture, and not a line of text: on a page that already has text MuPDF
    # answers from the content stream alone, which would make this check pass
    # on a system where Tesseract cannot be loaded at all.
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 24, 12))
    pixmap.set_rect(pixmap.irect, (255, 255, 255))
    try:
        with pymupdf.open() as doc:
            page = doc.new_page(width=24, height=12)
            page.insert_image(page.rect, stream=pixmap.tobytes("png"))
            _run(page, default_language(), 72, directory)
    except Exception as error:  # noqa: BLE001
        return QCoreApplication.translate("Ocr", "Tesseract non è utilizzabile: {0}").format(error)
    return None


def recognise(page: pymupdf.Page, language: str, dpi: int = DEFAULT_DPI) -> list[OcrWord]:
    """Read *page* with Tesseract, in PAGE space.

    The page is opened read-only by the caller, and its /Rotate is put back
    before returning: whoever asked gets the page it lent, unchanged.
    """
    directory = tessdata_dir()
    if directory is None:
        raise RuntimeError(
            unavailable_reason() or QCoreApplication.translate("Ocr", "Manca il dato di lingua di Tesseract.")
        )
    rotation = page.rotation
    if rotation:
        page.set_rotation(0)
    try:
        # Both the box and the text page belong to the page as it is now --
        # unrotated -- so the clamp below is in the space of the rectangles.
        box = page.rect
        # MuPDF answers with the words of the content stream as well, so a
        # page that is half text and half scan would get its real text
        # written twice -- and then read twice, copied twice, found twice.
        # Only what is left of the page after the real words is OCR material.
        already = [pymupdf.Rect(w[:4]) for w in page.get_text("words")]
        words = []
        for x0, y0, x1, y1, text, *_ in _run(page, language, dpi, directory).extractWORDS():
            if not text.strip():
                continue
            rect = pymupdf.Rect(x0, y0, x1, y1) & box
            if rect.is_empty or rect.width <= 0 or rect.height <= 0:
                continue
            middle = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
            if any(other.contains(middle) for other in already):
                continue
            words.append(OcrWord(text, (rect.x0, rect.y0, rect.x1, rect.y1)))
        return words
    finally:
        if rotation:
            page.set_rotation(rotation)


def _run(page: pymupdf.Page, language: str, dpi: int, directory: str) -> pymupdf.TextPage:
    """The one call to Tesseract, and the one that can raise.

    Cast because PyMuPDF's stub for it is bare: the answer is a TextPage, and
    the dictionary-based extraction below is the only thing asked of it.
    """
    return cast(
        pymupdf.TextPage,
        page.get_textpage_ocr(language=language, dpi=dpi, tessdata=directory),
    )


def write_layer(page: pymupdf.Page, words: Sequence[OcrWord]) -> None:
    """Write *words* onto *page* as an invisible text layer.

    One ``insert_text`` per word, in page space: that is where ``insert_text``
    writes even on a page with a /Rotate left on (measured), which matters
    because the layer has to sit under the picture the user sees.

    The font is one of the Base-14 on purpose. It is never embedded, so making
    a scan searchable costs no bytes at all -- and since the layer is
    invisible, the only thing that can be wrong about it is where the letters
    are.
    """
    for word in words:
        page.insert_text(
            (word.rect[0], word.baseline),
            word.text,
            fontname="helv",
            fontsize=word.size,
            render_mode=INVISIBLE,
        )
