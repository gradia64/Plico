"""Redactions are seen before the save, and confirmed before they are burnt.

A user marked two words, saw nothing change, saved, reopened the file and only
then found out the words were gone. These tests pin the three answers: the
page (and its thumbnail) shows the marks applied as soon as no mark tool is
on, the title and a message say what is waiting, and the write asks first.
The OCR run, which ended in the status bar alone, now says so over the page.
"""

import time

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from plico.main_window import MainWindow
from plico.model.commands import AddRedaction
from plico.model.redact import RedactionRect, redacted_copy
from plico.rendering import RenderRequest, RenderWorker
from plico.widgets.thumbnail_bar import THUMB_ZOOM, thumb_key

pytestmark = pytest.mark.usefixtures("qapp")

SECRET = (60.0, 50.0, 400.0, 90.0)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def windows(qapp):
    created: list[MainWindow] = []

    def factory() -> MainWindow:
        mw = MainWindow()
        created.append(mw)
        return mw

    yield factory
    for mw in created:
        mw.shutdown_worker()
        mw.deleteLater()
    qapp.processEvents()


def _pdf(path, pages: int = 2) -> str:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"SEGRETO {i + 1}", fontsize=24)
        page.insert_text((72, 300), "resta", fontsize=24)
    doc.save(str(path))
    doc.close()
    return str(path)


def _pump(seconds: float = 0.6) -> None:
    app = QApplication.instance()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def _mark(mw: MainWindow, index: int = 0) -> RedactionRect:
    rect = RedactionRect(*SECRET)
    mw._undo_stack.push(AddRedaction(mw._doc_model, index, rect))
    return rect


def _dark_pixels(image, rect, zoom: float = 1.0) -> int:
    x0, y0, x1, y1 = (int(v * zoom) for v in rect)
    return sum(
        1
        for x in range(x0, x1, 2)
        for y in range(y0, y1, 2)
        if image.pixelColor(x, y).lightness() < 128
    )


# -- the preview itself ------------------------------------------------- #


def test_redacted_copy_leaves_the_source_alone(tmp_path):
    path = _pdf(tmp_path / "a.pdf")
    with pymupdf.open(path) as doc:
        with redacted_copy(doc, 0, (RedactionRect(*SECRET),)) as copy:
            assert "SEGRETO" not in copy[0].get_text()
            assert "resta" in copy[0].get_text()
        assert "SEGRETO" in doc[0].get_text()


def test_worker_renders_the_page_as_saved(tmp_path):
    path = _pdf(tmp_path / "a.pdf")
    worker = RenderWorker()
    images = {}
    worker.rendered.connect(lambda key, image: images.__setitem__(key, image))
    marks = (RedactionRect(*SECRET),)

    plain = ("page", 0, 0, 0, 1.0, 1.0, ())
    burnt = ("page", 0, 0, 0, 1.0, 1.0, marks)
    worker._render(RenderRequest(plain, path, 0, 1.0, 0))
    worker._render(RenderRequest(burnt, path, 0, 1.0, 0, marks))

    assert _dark_pixels(images[plain], SECRET) > 0
    assert _dark_pixels(images[burnt], SECRET) == 0
    # The rest of the page is untouched.
    below = (60.0, 270.0, 200.0, 310.0)
    assert _dark_pixels(images[burnt], below) == _dark_pixels(images[plain], below) > 0


def test_the_view_asks_for_the_preview_only_without_a_mark_tool(windows, tmp_path):
    mw = windows()
    mw.open_document(_pdf(tmp_path / "a.pdf"))
    _pump()
    rect = _mark(mw)
    _pump()
    canvas = mw._page_view._canvases[0]
    assert canvas.current_key[-1] == (rect,), "senza strumento: pagina come salvata"

    mw._redact_act.setChecked(True)
    mw._on_redaction_toggled(True)
    _pump()
    assert canvas.current_key[-1] == (), "con lo strumento: la pagina vera, sotto i segni"

    mw._redact_act.setChecked(False)
    mw._on_redaction_toggled(False)
    _pump()
    assert canvas.current_key[-1] == (rect,)


def test_an_undo_with_no_tool_on_takes_the_preview_back(windows, tmp_path):
    mw = windows()
    mw.open_document(_pdf(tmp_path / "a.pdf"))
    _pump()
    _mark(mw)
    _pump()
    mw._undo_stack.undo()
    _pump()
    assert mw._page_view._canvases[0].current_key[-1] == ()


def test_the_thumbnail_follows_the_marks(windows, tmp_path):
    mw = windows()
    mw.open_document(_pdf(tmp_path / "a.pdf"))
    _pump()
    before = thumb_key(mw._doc_model.pages[0], THUMB_ZOOM, 1.0)
    rect = _mark(mw)
    after = thumb_key(mw._doc_model.pages[0], THUMB_ZOOM, 1.0)
    assert before != after and after[-1] == (rect,)
    assert before not in mw._thumbnail_cache, "la miniatura senza il segno non serve più"


# -- saying it ----------------------------------------------------------- #


def test_the_title_counts_what_waits_for_a_save(windows, tmp_path):
    mw = windows()
    path = _pdf(tmp_path / "a.pdf")
    mw.open_document(path)
    _pump()
    _mark(mw, 0)
    assert "una cancellazione da applicare" in mw.windowTitle()
    _mark(mw, 1)
    assert "2 cancellazioni da applicare" in mw.windowTitle()

    assert mw._save_to(str(tmp_path / "copia.pdf"))
    assert "da applicare" not in mw.windowTitle(), "nella copia ci sono già"


def test_a_drawn_zone_is_announced_over_the_page(windows, tmp_path):
    mw = windows()
    mw.open_document(_pdf(tmp_path / "a.pdf"))
    _pump()
    mw._add_redaction(0, RedactionRect(*SECRET))
    assert mw._toast.isVisibleTo(mw)
    assert "al salvataggio" in mw._toast.text()
    assert mw._status.text() == mw._toast.text()


def test_leaving_the_tool_announces_the_preview(windows, tmp_path):
    mw = windows()
    mw.open_document(_pdf(tmp_path / "a.pdf"))
    _pump()
    mw._redact_act.setChecked(True)
    mw._on_redaction_toggled(True)
    mw._add_redaction(0, RedactionRect(*SECRET))
    mw._toast.hide()

    mw._leave_tools()

    assert mw._toast.isVisibleTo(mw)
    assert "Anteprima" in mw._toast.text()


def test_the_ocr_outcome_is_announced_over_the_page(windows, tmp_path):
    mw = windows()
    mw.open_document(_pdf(tmp_path / "a.pdf"))
    _pump()
    mw._install_ocr({0: []})
    assert mw._toast.isVisibleTo(mw)
    assert mw._toast.text() == "Nessun testo riconosciuto nelle pagine scelte."


# -- asking before the write -------------------------------------------- #


def test_the_save_asks_with_the_numbers_and_can_be_refused(windows, tmp_path, monkeypatch):
    mw = windows()
    mw.open_document(_pdf(tmp_path / "a.pdf", pages=3))
    _pump()
    _mark(mw, 0)
    _mark(mw, 2)
    asked: list[str] = []
    monkeypatch.setattr(MainWindow, "_ask_to_burn", lambda self, text: asked.append(text) or False)
    out = tmp_path / "out.pdf"

    assert not mw._save_to(str(out))

    assert not out.exists(), "rifiutato: niente file"
    assert len(asked) == 1
    assert "2 zone" in asked[0] and "1, 3" in asked[0]
    assert sum(len(item.redactions) for item in mw._doc_model.pages) == 2


def test_marks_already_in_the_target_are_not_asked_again(windows, tmp_path, monkeypatch):
    mw = windows()
    mw.open_document(_pdf(tmp_path / "a.pdf"))
    _pump()
    _mark(mw, 0)
    asked: list[str] = []
    monkeypatch.setattr(MainWindow, "_ask_to_burn", lambda self, text: asked.append(text) or True)
    target = str(tmp_path / "copia.pdf")

    assert mw._save_to(target)
    assert mw._save_to(target)
    assert len(asked) == 1, "lo stesso file ha già quella cancellazione"

    assert mw._save_to(str(tmp_path / "altro.pdf"))
    assert len(asked) == 2, "un file nuovo la riceve di nuovo, e va chiesto"
    with pymupdf.open(target) as doc:
        assert "SEGRETO" not in doc[0].get_text()


def test_nothing_is_asked_without_marks(windows, tmp_path, monkeypatch):
    mw = windows()
    mw.open_document(_pdf(tmp_path / "a.pdf"))
    _pump()
    asked: list[str] = []
    monkeypatch.setattr(MainWindow, "_ask_to_burn", lambda self, text: asked.append(text) or True)
    assert mw._save_to(str(tmp_path / "copia.pdf"))
    assert asked == []


def test_the_search_speaks_in_the_singular_when_it_should(windows, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    mw = windows()
    mw.open_document(_pdf(tmp_path / "a.pdf"))
    _pump()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("SEGRETO 2", True)))
    mw._redact_text()
    assert mw._toast.text().startswith("Un'occorrenza di «SEGRETO 2» segnata a pagina 2")
    assert not mw._redact_act.isChecked() and mw._page_view.redaction_preview()
