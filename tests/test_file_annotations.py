"""The annotations already in a PDF: taken off, notes rewritten, all undoable."""

import pymupdf
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from plico.main_window import MainWindow
from plico.model import (
    AddRedaction,
    Annotation,
    DocumentModel,
    EditFileNote,
    MoveAnnotation,
    MoveFileAnnotation,
    RecolorAnnotation,
    RecolorFileAnnotation,
    RemoveFileAnnotation,
    ResizeFileAnnotation,
    RotatePage,
    save_as,
)
from plico.model.annotate import (
    HIGHLIGHT,
    INK,
    MAX_FILE_ANNOTATIONS,
    NOTE,
    FileAnnotationEdit,
    apply_file_changes,
    read_file_annotations,
)
from plico.model.redact import RedactionRect
from plico.rendering.worker import RenderRequest, RenderWorker
from plico.widgets.page_view import MIN_ANNOTATION_SIZE


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
        apply_file_changes(page, [(square, FileAnnotationEdit(removed=True))])
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
    worker._render(
        RenderRequest(("hidden",), path, 0, 1.0, 0, edits=((square, FileAnnotationEdit(removed=True)),))
    )
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
    drawn = ((square, FileAnnotationEdit(removed=True)),)
    assert drawn in [key[-2] for key in (canvas.pending_key, canvas.current_key) if key]
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
    edit, _color, remove = menu.actions()
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


# -- colour, position and FreeText -------------------------------------------

FREE = pymupdf.Rect(300, 400, 500, 450)
INK_POINTS = [(320, 600), (380, 650), (420, 620)]


def _shapes(path: str, rotate: int = 0) -> None:
    """A square, a FreeText, a stroke and a stamp."""
    with pymupdf.open() as doc:
        page = doc.new_page()
        square = page.add_rect_annot(SQUARE)
        square.set_colors(stroke=(0, 0, 1))
        square.set_border(width=4)
        square.update()
        page.add_freetext_annot(FREE, "testo libero", fontsize=12, text_color=(0, 0, 0))
        page.add_ink_annot([INK_POINTS])
        page.add_stamp_annot(pymupdf.Rect(100, 650, 250, 700), stamp=0)
        page.set_rotation(rotate)
        doc.save(path)


def test_reading_knows_colours_and_what_can_change(tmp_path) -> None:
    path = str(tmp_path / "shapes.pdf")
    _shapes(path)
    with pymupdf.open(path) as doc:
        square, free, ink, stamp = read_file_annotations(doc[0])
    assert square.color == (0.0, 0.0, 1.0) and square.colorable and square.movable
    assert free.color == (0.0, 0.0, 0.0) and free.has_text and not free.is_note
    assert ink.movable and ink.colorable
    assert stamp.movable and not stamp.colorable and stamp.color is None


@pytest.mark.parametrize("rotate", [0, 90])
def test_moves_colours_and_words_reach_the_saved_file(qapp, tmp_path, rotate) -> None:
    path = str(tmp_path / "shapes.pdf")
    out = str(tmp_path / "out.pdf")
    _shapes(path, rotate)
    model = DocumentModel()
    model.open(path)
    square, free, ink, stamp = model.pages[0].file_annotations
    MoveFileAnnotation(model, 0, square, 30, 40).redo()
    MoveFileAnnotation(model, 0, square, 10, 0).redo()  # two moves add up
    RecolorFileAnnotation(model, 0, square, (1.0, 0.0, 0.0)).redo()
    EditFileNote(model, 0, free, "parole nuove").redo()
    RecolorFileAnnotation(model, 0, free, (1.0, 0.0, 0.0)).redo()
    MoveFileAnnotation(model, 0, ink, -20, 10).redo()
    MoveFileAnnotation(model, 0, stamp, 0, -50).redo()
    RotatePage(model, 0, 90).redo()
    save_as(model, out)
    with pymupdf.open(out) as doc:
        page = doc[0]
        saved_square, saved_free, saved_ink, saved_stamp = page.annots()
        moved = square.rect
        assert tuple(saved_square.rect) == pytest.approx(
            (moved.x0 + 40, moved.y0 + 40, moved.x1 + 40, moved.y1 + 40), abs=0.6
        )
        assert saved_square.colors["stroke"] == pytest.approx([1.0, 0.0, 0.0])
        assert saved_free.info["content"] == "parole nuove"
        assert doc.xref_get_key(saved_free.xref, "DA")[1].startswith("1 0 0 rg")
        assert saved_ink.vertices[0][0] == pytest.approx((300, 610), abs=0.01)
        assert saved_stamp.rect.y0 == pytest.approx(stamp.rect.y0 - 50, abs=0.01)


def test_undo_takes_a_move_back_one_step_at_a_time(qapp, tmp_path) -> None:
    path = str(tmp_path / "shapes.pdf")
    _shapes(path)
    model = DocumentModel()
    model.open(path)
    item = model.pages[0]
    square = item.file_annotations[0]
    first = MoveFileAnnotation(model, 0, square, 30, 40)
    first.redo()
    second = RecolorFileAnnotation(model, 0, square, (1.0, 0.0, 0.0))
    second.redo()
    r = square.rect
    moved = RedactionRect(r.x0 + 30, r.y0 + 40, r.x1 + 30, r.y1 + 40)
    assert item.file_edit(square) == FileAnnotationEdit(color=(1.0, 0.0, 0.0), box=moved)
    second.undo()
    assert item.file_edit(square) == FileAnnotationEdit(box=moved)
    first.undo()
    assert item.file_annotation_changes == {}, "back to the file: nothing recorded"


def test_the_preview_shows_a_moved_annotation_where_it_went(qapp, tmp_path) -> None:
    path = str(tmp_path / "shapes.pdf")
    _shapes(path)
    model = DocumentModel()
    model.open(path)
    square = model.pages[0].file_annotations[0]
    worker = RenderWorker()
    images: dict[str, object] = {}
    worker.rendered.connect(lambda key, image: images.__setitem__(key[0], image))
    r = square.rect
    edit = FileAnnotationEdit(box=RedactionRect(r.x0, r.y0 + 150, r.x1, r.y1 + 150))
    worker._render(RenderRequest(("moved",), path, 0, 1.0, 0, edits=((square, edit),)))
    worker.shutdown()
    assert _blue(images["moved"], SQUARE) == 0
    assert _blue(images["moved"], SQUARE + (0, 150, 0, 150)) > 100


def test_plico_annotations_take_a_colour_and_move(qapp, tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf(path)
    model = DocumentModel()
    model.open(path)
    note = Annotation(NOTE, at=(300, 300), text="qui")
    model.pages[0].annotations.append(note)
    MoveAnnotation(model, 0, note, 20, 30).redo()
    [moved] = model.pages[0].annotations
    assert moved.at == (320, 330) and not Annotation(HIGHLIGHT).movable
    RecolorAnnotation(model, 0, moved, (0.0, 0.5, 0.0)).redo()
    [tinted] = model.pages[0].annotations
    assert tinted.color == (0.0, 0.5, 0.0) and tinted.at == (320, 330)
    save_as(model, out)
    with pymupdf.open(out) as doc:
        page = doc[0]  # alive: an annotation does not keep its page
        mine = list(page.annots())[-1]
        assert mine.colors["stroke"] == pytest.approx([0.0, 0.5, 0.0])
        assert mine.rect.x0 == pytest.approx(320 - 8, abs=1)


def _drag(label, points: list[QPointF]) -> None:
    label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, points[0]))
    for point in points[1:]:
        label.mouseMoveEvent(_event(QEvent.Type.MouseMove, point))
    label.mouseReleaseEvent(_event(QEvent.Type.MouseButtonRelease, points[-1]))


def test_dragging_moves_an_annotation_and_stays_on_the_page(window, qapp, tmp_path) -> None:
    path = str(tmp_path / "shapes.pdf")
    _shapes(path)
    assert window.open_path(path)
    canvas = window._page_view._canvases[0]
    item = window._doc_model.pages[0]
    square = item.file_annotations[0]
    start = _centre(canvas, square.rect)
    _click(canvas.label, start)
    assert item.file_annotation_changes == {}, "a click does not move it"
    label = canvas.label
    label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, start))
    label.mouseMoveEvent(_event(QEvent.Type.MouseMove, start + QPointF(15, 0)))
    label.grab()  # the outline of where it will land is painted
    label.mouseReleaseEvent(_event(QEvent.Type.MouseButtonRelease, start + QPointF(30, 20)))
    box = item.file_box(square)
    dx, dy = box.x0 - square.rect.x0, box.y0 - square.rect.y0
    scale = canvas.label._scale()
    assert dx == pytest.approx(30 / scale, abs=0.5) and dy == pytest.approx(20 / scale, abs=0.5)
    assert canvas.label.file_annotation_at(start + QPointF(30, 20)) == square
    assert window._undo_stack.count() == 1
    # Far off the page: it stops at the edge.
    moved = _centre(canvas, RedactionRect(
        square.rect.x0 + dx, square.rect.y0 + dy, square.rect.x1 + dx, square.rect.y1 + dy
    ))
    _drag(canvas.label, [moved, moved - QPointF(5000, 0)])
    assert item.file_box(square).x0 == pytest.approx(0, abs=0.01)
    window._undo_stack.undo()
    window._undo_stack.undo()
    assert item.file_annotation_changes == {}


def test_the_menu_recolours_and_rewrites_a_freetext(window, qapp, tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "shapes.pdf")
    _shapes(path)
    assert window.open_path(path)
    canvas = window._page_view._canvases[0]
    item = window._doc_model.pages[0]
    square, free, _ink, stamp = item.file_annotations
    asked: list[object] = []

    def colour(start):
        asked.append(start)
        return (0.0, 0.6, 0.0)

    monkeypatch.setattr(window._page_view, "ask_color", colour)
    monkeypatch.setattr(window._page_view, "ask_annotation_text", lambda text: text + " e altre")
    menu = canvas.label.annotation_menu(_centre(canvas, square.rect))
    assert [a.text() for a in menu.actions()] == ["&Colore…", "&Togli annotazione"]
    menu.actions()[0].trigger()
    assert asked == [(0.0, 0.0, 1.0)], "the dialog starts from its own colour"
    assert item.file_edit(square).color == (0.0, 0.6, 0.0)
    menu = canvas.label.annotation_menu(_centre(canvas, free.rect))
    assert [a.text() for a in menu.actions()] == ["Modifica t&esto…", "&Colore…", "&Togli annotazione"]
    menu.actions()[0].trigger()
    assert item.note_text(free) == "testo libero e altre"
    menu = canvas.label.annotation_menu(_centre(canvas, stamp.rect))
    assert [a.text() for a in menu.actions()] == ["&Togli annotazione"], "a stamp keeps its look"


# -- size -------------------------------------------------------------------


def test_reading_knows_what_can_take_another_size(tmp_path) -> None:
    path = str(tmp_path / "shapes.pdf")
    _shapes(path)
    with pymupdf.open(path) as doc:
        square, free, ink, stamp = read_file_annotations(doc[0])
    assert square.resizable and free.resizable and ink.resizable and stamp.resizable
    path = str(tmp_path / "doc.pdf")
    _pdf(path)
    with pymupdf.open(path) as doc:
        highlight, note, _square = read_file_annotations(doc[0])
    assert not highlight.resizable and not note.resizable
    assert Annotation(INK).resizable and not Annotation(NOTE).resizable


def _drawn(page: pymupdf.Page, clip: pymupdf.Rect) -> pymupdf.Rect | None:
    """The box of what is drawn inside *clip*, in page space."""
    pix = page.get_pixmap(clip=clip * page.rotation_matrix, alpha=False)
    xs, ys = [], []
    for y in range(pix.height):
        for x in range(pix.width):
            if min(pix.pixel(x, y)) < 200:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    at = (clip * page.rotation_matrix).tl
    seen = pymupdf.Rect(min(xs) + at.x, min(ys) + at.y, max(xs) + 1 + at.x, max(ys) + 1 + at.y)
    return seen * page.derotation_matrix


@pytest.mark.parametrize("rotate", [0, 90])
def test_a_new_size_reaches_the_saved_file(qapp, tmp_path, rotate) -> None:
    path = str(tmp_path / "shapes.pdf")
    out = str(tmp_path / "out.pdf")
    _shapes(path, rotate)
    model = DocumentModel()
    model.open(path)
    square, free, ink, _stamp = model.pages[0].file_annotations
    bigger = RedactionRect(square.rect.x0, square.rect.y0, square.rect.x1 + 100, square.rect.y1 + 50)
    ResizeFileAnnotation(model, 0, square, bigger).redo()
    wider = RedactionRect(free.rect.x0 - 100, free.rect.y0, free.rect.x1, free.rect.y1 + 40)
    ResizeFileAnnotation(model, 0, free, wider).redo()
    half = RedactionRect(ink.rect.x0, ink.rect.y0, (ink.rect.x0 + ink.rect.x1) / 2, ink.rect.y1)
    ResizeFileAnnotation(model, 0, ink, half).redo()
    MoveFileAnnotation(model, 0, square, 0, 20).redo()  # a move keeps the new size
    save_as(model, out)
    with pymupdf.open(out) as doc:
        page = doc[0]
        saved_square, saved_free, saved_ink, _stamp = page.annots()
        assert tuple(saved_square.rect) == pytest.approx(
            (bigger.x0, bigger.y0 + 20, bigger.x1, bigger.y1 + 20), abs=0.6
        )
        # Redrawn, not stretched: the border keeps its width.
        assert saved_square.border["width"] == pytest.approx(4)
        assert tuple(saved_free.rect) == pytest.approx(wider.as_tuple(), abs=0.6)
        assert saved_free.info["content"] == "testo libero"
        xs = [x for x, _ in saved_ink.vertices[0]]
        assert max(xs) - min(xs) == pytest.approx((INK_POINTS[2][0] - INK_POINTS[0][0]) / 2, abs=4)


def test_a_stamp_is_stretched_with_its_picture(qapp, tmp_path) -> None:
    path = str(tmp_path / "shapes.pdf")
    out = str(tmp_path / "out.pdf")
    _shapes(path)
    model = DocumentModel()
    model.open(path)
    stamp = model.pages[0].file_annotations[3]
    r = stamp.rect
    taller = RedactionRect(r.x0, r.y0 - 40, r.x1 + 60, r.y1)
    ResizeFileAnnotation(model, 0, stamp, taller).redo()
    save_as(model, out)
    with pymupdf.open(out) as doc:
        page = doc[0]
        drawn = _drawn(page, pymupdf.Rect(0, 560, 316, 760))  # the stroke is right of it
    assert drawn is not None
    assert drawn.width == pytest.approx(taller.width, abs=4)
    assert drawn.height == pytest.approx(taller.height, abs=4)


def test_a_plico_stroke_stretches_into_its_new_box(qapp) -> None:
    stroke = Annotation(INK, points=((100.0, 100.0), (200.0, 150.0)))
    box = stroke.bounds()
    double = RedactionRect(box.x0, box.y0, box.x0 + box.width * 2, box.y1)
    stretched = stroke.resized(double)
    assert stretched.bounds().as_tuple() == pytest.approx(double.as_tuple(), abs=0.05)


def _corner(canvas, x: float, y: float) -> QPointF:
    return canvas.label._page_transform().map(QPointF(x, y))


def test_a_corner_handle_stretches_and_a_note_has_none(window, qapp, tmp_path) -> None:
    path = str(tmp_path / "shapes.pdf")
    _shapes(path)
    assert window.open_path(path)
    canvas = window._page_view._canvases[0]
    label = canvas.label
    item = window._doc_model.pages[0]
    square = item.file_annotations[0]
    r = square.rect
    corner = _corner(canvas, r.x1, r.y1)
    label.mouseMoveEvent(_event(QEvent.Type.MouseMove, corner))
    assert label._hover == square
    assert label.cursor().shape() == Qt.CursorShape.SizeFDiagCursor
    label.grab()  # the handles are painted
    _drag(label, [corner, corner + QPointF(20, 10), corner + QPointF(40, 30)])
    box = item.file_box(square)
    assert (box.x0, box.y0) == pytest.approx((r.x0, r.y0), abs=0.01), "the opposite corner stays"
    scale = label._scale()
    assert box.x1 == pytest.approx(r.x1 + 40 / scale, abs=0.5)
    assert box.y1 == pytest.approx(r.y1 + 30 / scale, abs=0.5)
    label.mouseMoveEvent(_event(QEvent.Type.MouseMove, _centre(canvas, box)))
    assert label.cursor().shape() == Qt.CursorShape.SizeAllCursor, "inside: a move"
    # Shrunk past the opposite corner: never below the smallest size.
    top_left = _corner(canvas, box.x0, box.y0)
    end = _corner(canvas, box.x1, box.y1)
    _drag(label, [end, top_left])
    small = item.file_box(square)
    assert small.width == pytest.approx(MIN_ANNOTATION_SIZE, abs=0.05)
    assert window._undo_stack.count() == 2


def test_a_note_moves_but_does_not_stretch(window, qapp, tmp_path) -> None:
    _, canvas = _open(window, tmp_path)
    item = window._doc_model.pages[0]
    note = item.file_annotations[1]
    corner = _corner(canvas, note.rect.x1, note.rect.y1)
    assert canvas.label._corner_at(note, corner) is None
