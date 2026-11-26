"""The annotations already in a PDF: taken off, notes rewritten, all undoable."""

import pymupdf
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from plico.main_window import MainWindow
from plico.model import (
    AddRedaction,
    DocumentModel,
    EditFileNote,
    RemoveFileAnnotation,
    RotatePage,
    save_as,
)
from plico.model.annotate import (
    HIGHLIGHT,
    MAX_FILE_ANNOTATIONS,
    NOTE,
    apply_file_changes,
    read_file_annotations,
)
from plico.model.redact import RedactionRect
from plico.rendering.worker import RenderRequest, RenderWorker


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    mw = MainWindow()
    mw.resize(900, 700)
    yield mw
    mw.shutdown_worker()
    mw.deleteLater()
    qapp.processEvents()


HIGHLIGHTED = pymupdf.Rect(100, 132, 260, 156)
NOTE_AT = (400, 100)
SQUARE = pymupdf.Rect(100, 400, 250, 500)


def _pdf(path: str, rotate: int = 0) -> None:
    """A page with a highlight, a note, a square, a link and a form field."""
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((100, 150), "SEGRETO parola", fontsize=20)
        page.add_highlight_annot(HIGHLIGHTED)
        page.add_text_annot(NOTE_AT, "nota del file")
        square = page.add_rect_annot(SQUARE)
        square.set_colors(stroke=(0, 0, 1))
        square.set_border(width=4)
        square.update()
        page.insert_link(
            {"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(10, 10, 60, 30), "uri": "https://example.org"}
        )
        widget = pymupdf.Widget()
        widget.field_name = "nome"
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.rect = pymupdf.Rect(100, 600, 300, 620)
        page.add_widget(widget)
        page.set_rotation(rotate)
        doc.save(path)


def _annots(path: str) -> list[tuple[str, str]]:
    with pymupdf.open(path) as doc:
        return [(a.type[1], a.info.get("content", "")) for a in doc[0].annots()]


def _extras(path: str) -> tuple[int, list[str]]:
    """Links and fields of the first page: never the annotations' business."""
    with pymupdf.open(path) as doc:
        page = doc[0]
        return len(page.get_links()), [w.field_name for w in page.widgets()]


# -- model ------------------------------------------------------------------


def test_reading_describes_what_a_reader_sees(tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    _pdf(path)
    with pymupdf.open(path) as doc:
        found = read_file_annotations(doc[0])
    assert [a.subtype for a in found] == ["Highlight", "Text", "Square"]
    assert [a.index for a in found] == [0, 1, 2]
    highlight, note, square = found
    assert highlight.parts and highlight.hit(150, 144)
    assert not highlight.hit(150, 300)
    assert note.is_note and note.text == "nota del file"
    assert note.hit(NOTE_AT[0] + 5, NOTE_AT[1] + 5)
    assert square.hit(175, 450) and not square.is_note


def test_a_crowded_page_is_shown_but_not_described(tmp_path) -> None:
    path = str(tmp_path / "crowded.pdf")
    with pymupdf.open() as doc:
        page = doc.new_page()
        for i in range(MAX_FILE_ANNOTATIONS + 1):
            page.add_rect_annot(pymupdf.Rect(i % 500, 0, i % 500 + 5, 5))
        doc.save(path)
    with pymupdf.open(path) as doc:
        assert read_file_annotations(doc[0]) == []


@pytest.mark.parametrize("rotate", [0, 90, 270])
def test_taking_off_and_rewriting_reach_the_saved_file(qapp, tmp_path, rotate) -> None:
    path = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf(path, rotate)
    model = DocumentModel()
    model.open(path)
    highlight, note, _square = model.pages[0].file_annotations
    RemoveFileAnnotation(model, 0, highlight).redo()
    EditFileNote(model, 0, note, "riscritta").redo()
    # A user rotation on top: the note's box moves with it, the match must not.
    RotatePage(model, 0, 90).redo()
    save_as(model, out)
    assert _annots(out) == [("Text", "riscritta"), ("Square", "")]
    assert _extras(out) == (1, ["nome"])
    assert _annots(path) == [("Highlight", ""), ("Text", "nota del file"), ("Square", "")]


def test_undo_puts_back_what_the_file_had(qapp, tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    _pdf(path)
    model = DocumentModel()
    model.open(path)
    item = model.pages[0]
    _highlight, note, square = item.file_annotations
    rewrite = EditFileNote(model, 0, note, "prima")
    rewrite.redo()
    remove = RemoveFileAnnotation(model, 0, note)
    remove.redo()
    assert item.file_annotations_shown() == [_highlight, square]
    assert item.hidden_annotations == (note,)
    remove.undo()
    assert item.note_text(note) == "prima", "undo goes back to the rewritten note"
    rewrite.undo()
    assert item.file_annotation_changes == {}
    assert item.note_text(note) == "nota del file"


def test_a_redaction_still_takes_what_it_touches(qapp, tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf(path)
    model = DocumentModel()
    model.open(path)
    _highlight, note, _square = model.pages[0].file_annotations
    EditFileNote(model, 0, note, "riscritta").redo()
    x, y = NOTE_AT
    AddRedaction(model, 0, RedactionRect(x - 5, y - 5, x + 30, y + 30)).redo()
    save_as(model, out)
    assert [kind for kind, _ in _annots(out)] == ["Highlight", "Square"]


def test_changes_find_the_annotation_by_its_box_when_the_order_moved(tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    _pdf(path)
    with pymupdf.open(path) as doc:
        page = doc[0]
        *_, square = read_file_annotations(page)
        page.delete_annot(next(page.annots()))  # the copy lost its first annotation
        apply_file_changes(page, [square], {square.index: None})
        assert [a.type[1] for a in page.annots()] == ["Text"]


# -- preview ----------------------------------------------------------------


def _blue(image, rect: pymupdf.Rect) -> int:
    count = 0
    for y in range(int(rect.y0), int(rect.y1)):
        for x in range(int(rect.x0), int(rect.x1)):
            colour = image.pixelColor(x, y)
            if colour.blue() > 150 and colour.red() < 100:
                count += 1
    return count


def test_the_preview_leaves_out_what_was_taken_off(qapp, tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    _pdf(path)
    model = DocumentModel()
    model.open(path)
    square = model.pages[0].file_annotations[2]
    worker = RenderWorker()
    images: dict[str, object] = {}
    worker.rendered.connect(lambda key, image: images.__setitem__(key[0], image))
    worker._render(RenderRequest(("shown",), path, 0, 1.0, 0))
    worker._render(RenderRequest(("hidden",), path, 0, 1.0, 0, hidden=(square,)))
    worker.shutdown()
    assert _blue(images["shown"], SQUARE) > 100
    assert _blue(images["hidden"], SQUARE) == 0
    assert _annots(path)[2] == ("Square", ""), "the source is not touched"


# -- window -----------------------------------------------------------------


def _event(kind: QEvent.Type, pos: QPointF) -> QMouseEvent:
    return QMouseEvent(
        kind, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _click(label, point: QPointF) -> None:
    label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, point))
    label.mouseReleaseEvent(_event(QEvent.Type.MouseButtonRelease, point))


def _open(window, tmp_path):
    path = str(tmp_path / "doc.pdf")
    _pdf(path)
    assert window.open_path(path)
    return path, window._page_view._canvases[0]


def _centre(canvas, rect: RedactionRect) -> QPointF:
    return canvas.label._to_pixels(rect).center()


def test_a_click_with_a_tool_takes_off_an_annotation_of_the_file(window, qapp, tmp_path) -> None:
    _, canvas = _open(window, tmp_path)
    item = window._doc_model.pages[0]
    square = item.file_annotations[2]
    window._annotate_acts[HIGHLIGHT].trigger()
    _click(canvas.label, _centre(canvas, square.rect))
    assert item.hidden_annotations == (square,)
    assert window.is_modified()
    assert canvas.label.file_annotation_at(_centre(canvas, square.rect)) is None
    assert canvas.pending_key[-2] == (square,) or canvas.current_key[-2] == (square,)
    window._undo_stack.undo()
    assert item.hidden_annotations == ()


def test_the_menu_rewrites_a_note_and_takes_one_off(window, qapp, tmp_path, monkeypatch) -> None:
    _, canvas = _open(window, tmp_path)
    item = window._doc_model.pages[0]
    note = item.file_annotations[1]
    point = _centre(canvas, note.rect)
    assert canvas.label._note_text_at(point) == "nota del file"
    asked: list[str] = []

    def answer(text: str = "") -> str:
        asked.append(text)
        return "nuove parole"

    monkeypatch.setattr(window._page_view, "ask_note_text", answer)
    menu = canvas.label.annotation_menu(point)
    assert menu is not None
    edit, remove = menu.actions()
    edit.trigger()
    assert asked == ["nota del file"], "the dialog starts from what the note says"
    assert item.note_text(note) == "nuove parole"
    assert canvas.label._note_text_at(point) == "nuove parole"
    remove.trigger()
    assert item.hidden_annotations == (note,)
    assert window._undo_stack.count() == 2
    assert canvas.label.annotation_menu(QPointF(5, 5)) is None, "nothing there, no menu"


def test_the_menu_also_rewrites_a_note_made_in_plico(window, qapp, tmp_path, monkeypatch) -> None:
    _, canvas = _open(window, tmp_path)
    window._annotate_acts[NOTE].trigger()
    monkeypatch.setattr(window._page_view, "ask_note_text", lambda text="": "prima")
    _click(canvas.label, QPointF(300, 300))
    window._leave_tools()
    [mine] = window._doc_model.pages[0].annotations
    monkeypatch.setattr(window._page_view, "ask_note_text", lambda text="": text + " e dopo")
    menu = canvas.label.annotation_menu(QPointF(300, 300))
    menu.actions()[0].trigger()
    [edited] = window._doc_model.pages[0].annotations
    assert edited.text == "prima e dopo" and edited.at == mine.at
    window._undo_stack.undo()
    assert window._doc_model.pages[0].annotations == [mine]
