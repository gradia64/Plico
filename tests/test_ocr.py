"""OCR: reading a picture of words, and the layer that makes it real text.

Tesseract is a hard dependency of the *feature* and a soft one of the app:
when the engine or its language data are missing the dialog says so, and
nothing here pretends otherwise. The tests skip in that case, which is honest
about the machine rather than about the code.
"""

import time

import pymupdf
import pytest
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication, QDialog

from plico.main_window import MainWindow
from plico.model import (
    AddRedaction,
    DocumentModel,
    OcrPage,
    RedactionRect,
    default_language,
    save_as,
)
from plico.model.ocr import tessdata_dir
from plico.widgets.ocr import OcrDialog

WORDS = "SEGRETO"


def _scan_of(path: str, text: str = WORDS, rotation: int = 0) -> None:
    """A page that is a PICTURE of a word: exactly what a scanner produces.

    The word is drawn on a throw-away page and rendered to a picture; only
    the picture goes into the document. The content stream therefore holds no
    text at all, so a test cannot pass by finding text that was never read --
    and that is the case OCR exists for.
    """
    with pymupdf.open() as source:
        drawn = source.new_page(width=595, height=842)
        drawn.insert_text((100, 100), text, fontsize=28)
        picture = drawn.get_pixmap(dpi=300)
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=picture.tobytes("png"))
        if rotation:
            page.set_rotation(rotation)
        doc.save(path)


def _rendered(path: str) -> bytes:
    with pymupdf.open(path) as doc:
        return doc[0].get_pixmap(dpi=72).tobytes("png")


@pytest.fixture
def language(monkeypatch) -> str:
    """The languages this machine has, and point the model at them.

    Not what is installed on the developer's box: the directory the app
    itself would look in, so the test also proves the lookup works.
    """
    directory = tessdata_dir()
    if directory is None:
        pytest.skip("no Tesseract language data installed")
    monkeypatch.setenv("PLICO_TESSDATA", directory)
    text = default_language()
    if not text:
        pytest.skip("no Tesseract language data installed")
    return text


# --------------------------------------------------------------------- #
#  Recognition
# --------------------------------------------------------------------- #

def test_ocr_reads_the_word_in_the_picture(tmp_path, language) -> None:
    path = str(tmp_path / "scansione.pdf")
    _scan_of(path)
    model = DocumentModel()
    model.open(path)

    words = model.ocr_page(0, language)

    assert [word.text for word in words] == [WORDS]


def test_the_word_lands_where_the_picture_shows_it(tmp_path, language) -> None:
    """The layer has to sit ON the words, not near them."""
    path = str(tmp_path / "scansione.pdf")
    _scan_of(path)
    model = DocumentModel()
    model.open(path)

    x0, y0, x1, y1 = model.ocr_page(0, language)[0].rect

    # Drawn at 100, 100 with 28pt type: a box that starts further right, or
    # is too narrow to hold the word, means the coordinates were taken in the
    # wrong space.
    assert 90 < x0 < 115
    assert 60 < y0 < 100
    assert x1 - x0 > 90
    assert y1 > y0


def _words_on(path, rotation: int, language: str) -> list:
    _scan_of(str(path), rotation=rotation)
    model = DocumentModel()
    model.open(str(path))
    words = model.ocr_page(0, language)
    # The source is only read, never written: the rotation of the file on
    # disk is what it was, whatever the handle had to do to read it.
    with pymupdf.open(str(path)) as doc:
        assert doc[0].rotation == rotation
    return words


@pytest.mark.parametrize("degrees", [90, 180, 270])
def test_the_box_does_not_depend_on_the_rotation(tmp_path, language, degrees) -> None:
    """``/Rotate`` is display metadata, so the words keep one box.

    Everything in Plico -- redactions, text edits, these words -- lives in the
    unrotated space. Reading a rotated page and getting the box of a
    *different* orientation would put the layer on the scan sideways.
    """
    upright = _words_on(tmp_path / "dritta.pdf", 0, language)
    turned = _words_on(tmp_path / f"ruotata{degrees}.pdf", degrees, language)

    assert turned == upright


def test_ocr_leaves_the_real_words_alone(tmp_path, language) -> None:
    """MuPDF answers with the content-stream words as well as Tesseract's.

    Writing those again would make every copied line read twice and every
    search return each word two times, so only what is left after the real
    words is worth writing.
    """
    path = str(tmp_path / "testo.pdf")
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 100), WORDS, fontsize=20)
        doc.save(path)
    model = DocumentModel()
    model.open(path)

    assert model.ocr_page(0, language) == []


# --------------------------------------------------------------------- #
#  The command and the materialised file
# --------------------------------------------------------------------- #

def test_undo_takes_the_reading_back(tmp_path, language) -> None:
    path = str(tmp_path / "scansione.pdf")
    _scan_of(path)
    model = DocumentModel()
    model.open(path)
    words = model.ocr_page(0, language)
    stack = QUndoStack()

    command = OcrPage(model, 0, words)
    stack.push(command)

    assert command.text() == "Riconosci testo su pagina 1"
    assert model.pages[0].ocr_words == words
    stack.undo()
    assert model.pages[0].ocr_words == []
    stack.redo()
    assert model.pages[0].ocr_words == words


def test_reading_the_same_page_again_replaces_the_words(tmp_path, language) -> None:
    """A second pass is a correction, not a pile: undo goes back one pass."""
    path = str(tmp_path / "scansione.pdf")
    _scan_of(path)
    model = DocumentModel()
    model.open(path)
    words = model.ocr_page(0, language)
    stack = QUndoStack()
    stack.push(OcrPage(model, 0, words))

    stack.push(OcrPage(model, 0, words[:1]))

    assert model.pages[0].ocr_words == words[:1]
    stack.undo()
    assert model.pages[0].ocr_words == words


def test_saving_writes_the_layer_without_changing_the_picture(tmp_path, language) -> None:
    path = str(tmp_path / "scansione.pdf")
    out = str(tmp_path / "salvato.pdf")
    _scan_of(path)
    model = DocumentModel()
    model.open(path)
    before = _rendered(path)
    stack = QUndoStack()
    stack.push(OcrPage(model, 0, model.ocr_page(0, language)))

    save_as(model, out)

    with pymupdf.open(out) as doc:
        assert doc[0].get_text().strip() == WORDS
    # Invisible: not merely "hard to see". A printed page must come out of the
    # printer without the layer on it.
    assert _rendered(out) == before


def test_a_redaction_over_a_recognised_word_really_deletes_it(tmp_path, language) -> None:
    """The layer is real text, and that is the point of the order in save.py.

    A redaction drawn afterwards must take the word with it: leaving it there,
    invisible but perfectly extractable, is the only outcome worse than not
    having read the page at all.
    """
    path = str(tmp_path / "scansione.pdf")
    out = str(tmp_path / "salvato.pdf")
    _scan_of(path)
    model = DocumentModel()
    model.open(path)
    before = _rendered(path)
    stack = QUndoStack()
    words = model.ocr_page(0, language)
    stack.push(OcrPage(model, 0, words))
    stack.push(AddRedaction(model, 0, RedactionRect.from_corners(*words[0].rect)))

    save_as(model, out)

    with pymupdf.open(out) as doc:
        assert doc[0].get_text().strip() == ""
        assert doc[0].search_for(WORDS) == []
    # And the picture is gone with it: the scan of the word is blanked.
    assert _rendered(out) != before


# --------------------------------------------------------------------- #
#  The window: one operation, one undo step
# --------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    """A real MainWindow, shut down for sure."""
    mw = MainWindow()
    yield mw
    mw.shutdown_worker()
    mw.deleteLater()
    qapp.processEvents()


def _pump(seconds: float = 0.6) -> None:
    """Let queued worker signals be delivered to the GUI thread."""
    app = QApplication.instance()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def test_recognising_from_the_window_is_one_undo_step(
    window, tmp_path, language, monkeypatch
) -> None:
    """The pages are read in the pool, the commands are pushed here.

    One macro, not one step per page: the user asked for one operation, and
    undoing a 40-page scan forty times is not an undo.
    """
    path = str(tmp_path / "scansione.pdf")
    _scan_of(path)
    window.open_document(path)
    _pump()
    monkeypatch.setattr(OcrDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    window._ocr_pages()

    assert window._undo_stack.count() == 1
    assert window._undo_stack.undoText() == "Riconosci testo su una pagina"
    assert [word.text for word in window._doc_model.pages[0].ocr_words] == [WORDS]
    assert window._status.text() == "Riconosciuto testo su una pagina."


def test_a_page_without_text_is_not_a_modification(window, tmp_path, language, monkeypatch) -> None:
    """Reading a born-digital page finds nothing, so nothing changes.

    An undo step that writes no layer would mark the document modified and
    make the window ask whether to save -- for no change at all.
    """
    path = str(tmp_path / "testo.pdf")
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 100), WORDS, fontsize=20)
        doc.save(path)
    window.open_document(path)
    _pump()
    monkeypatch.setattr(OcrDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    window._ocr_pages()

    assert window._undo_stack.count() == 0
    assert window._undo_stack.isClean()
    assert window._status.text() == "Nessun testo riconosciuto nelle pagine scelte."


def test_the_window_is_locked_from_the_moment_the_task_starts(
    window, tmp_path, language, monkeypatch
) -> None:
    """The progress dialog is what keeps the page list still under the task,
    and it used to appear only after half a second: until then the window
    still took a Del or a drag while the pool was reading the pages."""
    from PySide6.QtCore import QThreadPool

    path = str(tmp_path / "scansione.pdf")
    _scan_of(path)
    window.open_document(path)
    monkeypatch.setattr(OcrDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    seen: list[object] = []
    start = QThreadPool.start

    def watched(pool, task, *args):
        seen.append(QApplication.activeModalWidget())
        start(pool, task, *args)

    monkeypatch.setattr(QThreadPool, "start", watched)
    try:
        window._ocr_pages()
    finally:
        monkeypatch.setattr(QThreadPool, "start", start)

    assert seen and seen[0] is not None, "nessuna finestra modale mentre il task parte"


# --------------------------------------------------------------------- #
#  The language proposed follows the user's
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("it_IT", "ita+eng"),
        ("de_DE", "deu+eng"),
        ("fr_FR", "fra+eng"),
        ("es_ES", "spa+eng"),
        ("en_GB", "eng"),
        ("pt_BR", "eng"),
    ],
)
def test_the_proposed_language_is_the_user_s_plus_english(
    tmp_path, monkeypatch, locale, expected
) -> None:
    """It used to be Italian and English for everybody."""
    from PySide6.QtCore import QLocale

    for code in ("ita", "eng", "deu", "fra", "spa"):
        (tmp_path / f"{code}.traineddata").write_bytes(b"")
    monkeypatch.setenv("PLICO_TESSDATA", str(tmp_path))

    assert default_language(QLocale(locale)) == expected


def test_without_the_user_s_language_english_alone(tmp_path, monkeypatch) -> None:
    from PySide6.QtCore import QLocale

    (tmp_path / "eng.traineddata").write_bytes(b"")
    monkeypatch.setenv("PLICO_TESSDATA", str(tmp_path))

    assert default_language(QLocale("de_DE")) == "eng"


def test_languages_are_named_in_their_own_language() -> None:
    from plico.widgets.ocr import language_name

    assert language_name("deu") == "Deutsch"
    assert language_name("fra") == "Français"
    assert language_name("swe") == "Svenska", "la tabella non c'e`: risponde Qt"
    assert language_name("xyz") == "xyz"


def test_the_proposed_language_follows_the_one_chosen_in_the_settings(
    tmp_path, monkeypatch
) -> None:
    """Review 2026-10-19 (G-03): German chosen, Italian system, Italian proposed."""
    from PySide6.QtCore import QLocale

    for code in ("ita", "eng", "deu"):
        (tmp_path / f"{code}.traineddata").write_bytes(b"")
    monkeypatch.setenv("PLICO_TESSDATA", str(tmp_path))
    before = QLocale()
    try:
        QLocale.setDefault(QLocale("de_DE"))  # what apply_language("de") does
        assert default_language() == "deu+eng"
    finally:
        QLocale.setDefault(before)
