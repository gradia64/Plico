"""Annota: highlight, underline, strike out, notes and ink, written on save."""

import pymupdf
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from plico.main_window import MainWindow
from plico.model import (
    AddAnnotation,
    AddRedaction,
    Annotation,
    DocumentModel,
    DuplicatePage,
    RemoveAnnotation,
    RotatePage,
    save_as,
)
from plico.model.annotate import HIGHLIGHT, INK, NOTE, STRIKEOUT, UNDERLINE, lines_of
from plico.model.redact import RedactionRect


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


def _pdf(path: str, rotate: int = 0) -> None:
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((100, 150), "SEGRETO parola", fontsize=20)
        page.insert_text((100, 300), "seconda riga", fontsize=20)
        page.set_rotation(rotate)
        doc.save(path)


def _word(path: str, text: str) -> RedactionRect:
    with pymupdf.open(path) as doc:
        box = doc[0].search_for(text)[0]
    return RedactionRect(box.x0, box.y0, box.x1, box.y1)


def _annots(path: str) -> list[tuple[str, pymupdf.Rect, str]]:
    with pymupdf.open(path) as doc:
        page = doc[0]
        return [(a.type[1], a.rect, a.info.get("content", "")) for a in page.annots()]


def _event(kind: QEvent.Type, pos: QPointF) -> QMouseEvent:
    return QMouseEvent(
        kind, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _drag(label, points: list[QPointF]) -> None:
    label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, points[0]))
    for point in points[1:]:
        label.mouseMoveEvent(_event(QEvent.Type.MouseMove, point))
    label.mouseReleaseEvent(_event(QEvent.Type.MouseButtonRelease, points[-1]))


# -- geometry ---------------------------------------------------------------


def test_words_join_into_one_rectangle_per_line() -> None:
    words = [
        RedactionRect(100, 130, 150, 155),
        RedactionRect(160, 128, 220, 156),
        RedactionRect(100, 280, 180, 305),
    ]
    assert lines_of(words) == (
        RedactionRect(100, 128, 220, 156),
        RedactionRect(100, 280, 180, 305),
    )


def test_an_annotation_answers_only_where_it_is() -> None:
    markup = Annotation(HIGHLIGHT, rects=(RedactionRect(0, 0, 10, 10), RedactionRect(0, 50, 10, 60)))
    assert markup.hit(5, 5) and markup.hit(5, 55) and not markup.hit(5, 30)
    ink = Annotation(INK, points=((0.0, 0.0), (100.0, 0.0)))
    assert ink.hit(50, 1.5) and not ink.hit(50, 20)
    note = Annotation(NOTE, at=(100.0, 100.0), text="x")
    assert note.hit(105, 95) and not note.hit(120, 100)


# -- save -------------------------------------------------------------------


@pytest.mark.parametrize("rotate", [0, 90])
def test_every_kind_is_written_where_it_was_made(qapp, tmp_path, rotate) -> None:
    path = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf(path, rotate)
    word = _word(path, "SEGRETO")
    second = _word(path, "seconda")
    model = DocumentModel()
    model.open(path)
    for annotation in (
        Annotation(HIGHLIGHT, rects=(word,)),
        Annotation(UNDERLINE, rects=(second,)),
        Annotation(STRIKEOUT, rects=(second,)),
        Annotation(NOTE, at=(400.0, 500.0), text="Da rivedere"),
        Annotation(INK, points=((50.0, 600.0), (150.0, 650.0), (200.0, 600.0))),
    ):
        AddAnnotation(model, 0, annotation).redo()
    # A user rotation on top must not move anything: page space is page space.
    RotatePage(model, 0, 90).redo()
    save_as(model, out)
    found = {kind: (rect, content) for kind, rect, content in _annots(out)}
    assert set(found) == {"Highlight", "Underline", "StrikeOut", "Text", "Ink"}
    assert found["Highlight"][0].intersects(pymupdf.Rect(*word.as_tuple()))
    assert found["Underline"][0].intersects(pymupdf.Rect(*second.as_tuple()))
    note = found["Text"][0]
    assert abs((note.x0 + note.x1) / 2 - 400) < 1 and abs((note.y0 + note.y1) / 2 - 500) < 1
    assert found["Text"][1] == "Da rivedere"
    assert found["Ink"][0].contains(pymupdf.Point(150, 640))


def test_a_redaction_takes_the_annotations_it_touches(qapp, tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf(path)
    word = _word(path, "SEGRETO")
    model = DocumentModel()
    model.open(path)
    AddAnnotation(model, 0, Annotation(HIGHLIGHT, rects=(word,))).redo()
    AddAnnotation(model, 0, Annotation(NOTE, at=(word.x0 + 5, word.y0 + 5), text="SEGRETO")).redo()
    AddAnnotation(model, 0, Annotation(NOTE, at=(400.0, 600.0), text="resta")).redo()
    AddRedaction(model, 0, word).redo()
    save_as(model, out)
    assert [(kind, content) for kind, _, content in _annots(out)] == [("Text", "resta")]


def test_commands_undo_and_duplicates_are_independent(qapp, tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    _pdf(path)
    model = DocumentModel()
    model.open(path)
    first = Annotation(NOTE, at=(100.0, 100.0), text="uno")
    second = Annotation(NOTE, at=(200.0, 200.0), text="due")
    add = [AddAnnotation(model, 0, first), AddAnnotation(model, 0, second)]
    for command in add:
        command.redo()
    remove = RemoveAnnotation(model, 0, first)
    remove.redo()
    assert model.pages[0].annotations == [second]
    remove.undo()
    assert model.pages[0].annotations == [first, second]
    DuplicatePage(model, 0).redo()
    model.pages[1].annotations.clear()
    assert len(model.pages[0].annotations) == 2
    for command in reversed(add):
        command.undo()
    assert model.pages[0].annotations == []


# -- window -----------------------------------------------------------------


def _open(window, tmp_path) -> tuple[str, object]:
    path = str(tmp_path / "doc.pdf")
    _pdf(path)
    assert window.open_path(path)
    canvas = window._page_view._canvases[0]
    return path, canvas


def test_the_tools_are_one_at_a_time(window, qapp, tmp_path) -> None:
    _open(window, tmp_path)
    acts = window._annotate_acts
    acts[HIGHLIGHT].trigger()
    assert window._page_view.annotation_tool() == HIGHLIGHT
    acts[INK].trigger()
    assert window._page_view.annotation_tool() == INK
    assert not acts[HIGHLIGHT].isChecked()
    window._redact_act.trigger()
    assert window._page_view.annotation_tool() is None and not acts[INK].isChecked()
    acts[NOTE].trigger()
    assert not window._redact_act.isChecked() and not window._page_view.redaction_mode()
    window._leave_tools()
    assert window._page_view.annotation_tool() is None and not acts[NOTE].isChecked()


def test_dragging_highlights_and_a_click_takes_it_back(window, qapp, tmp_path) -> None:
    path, canvas = _open(window, tmp_path)
    window._annotate_acts[HIGHLIGHT].trigger()
    word = canvas.label._to_pixels(_word(path, "SEGRETO"))
    _drag(canvas.label, [word.topLeft() + QPointF(1, 1), word.bottomRight() - QPointF(1, 1)])
    [annotation] = window._doc_model.pages[0].annotations
    assert annotation.kind == HIGHLIGHT and len(annotation.rects) == 1
    assert window.is_modified()
    _drag(canvas.label, [word.center()])
    assert window._doc_model.pages[0].annotations == []
    window._undo_stack.undo()
    assert window._doc_model.pages[0].annotations == [annotation]


def test_a_stroke_and_a_note_with_the_mouse(window, qapp, tmp_path, monkeypatch) -> None:
    _, canvas = _open(window, tmp_path)
    window._annotate_acts[INK].trigger()
    _drag(canvas.label, [QPointF(40, 400), QPointF(60, 420), QPointF(90, 410)])
    [stroke] = window._doc_model.pages[0].annotations
    assert stroke.kind == INK and len(stroke.points) == 3
    window._annotate_acts[NOTE].trigger()
    monkeypatch.setattr(window._page_view, "ask_note_text", lambda: None)
    _drag(canvas.label, [QPointF(300, 300)])  # cancelled: nothing added
    assert len(window._doc_model.pages[0].annotations) == 1
    monkeypatch.setattr(window._page_view, "ask_note_text", lambda: "Controllare")
    _drag(canvas.label, [QPointF(300, 300)])
    note = window._doc_model.pages[0].annotations[-1]
    assert note.kind == NOTE and note.text == "Controllare"
    assert canvas.label.annotation_at(QPointF(300, 300)) == note
    assert window._undo_stack.count() == 2
