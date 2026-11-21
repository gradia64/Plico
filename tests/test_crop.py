"""Modifica → Ritaglia margini: the visible part of a page, kept until saving."""

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from plico.main_window import MainWindow
from plico.model import AddRedaction, CropPages, DocumentModel, RotatePage, save_as
from plico.model.crop import MIN_VISIBLE, crop_from_margins, margins_of
from plico.model.redact import RedactionRect, map_point
from plico.rendering.worker import RenderRequest, RenderWorker
from plico.widgets.crop import MM, CropDialog


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


def _pdf(path: str, rotate: int = 0, cropbox: pymupdf.Rect | None = None, pages: int = 2) -> None:
    with pymupdf.open() as doc:
        for _ in range(pages):
            page = doc.new_page(width=600, height=800)
            page.insert_text((150, 200), "DENTRO", fontsize=20)
            page.insert_text((150, 700), "FUORI", fontsize=20)
            if cropbox is not None:
                page.set_cropbox(cropbox)
            page.set_rotation(rotate)
        doc.save(path)


# -- geometry ---------------------------------------------------------------


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_margins_round_trip_whatever_the_rotation(rotation) -> None:
    margins = (10.0, 20.0, 30.0, 40.0)
    crop = crop_from_margins(margins, 600, 800, rotation)
    assert crop is not None
    assert margins_of(crop, 600, 800, rotation) == pytest.approx(margins)
    assert crop_from_margins((0, 0, 0, 0), 600, 800, rotation) is None


def test_a_crop_always_leaves_something() -> None:
    crop = crop_from_margins((500.0, 0.0, 500.0, 0.0), 600, 800, 0)
    assert crop is not None and crop.y1 - crop.y0 == pytest.approx(MIN_VISIBLE)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_the_view_shows_only_the_crop(qapp, tmp_path, rotation) -> None:
    path = str(tmp_path / "doc.pdf")
    _pdf(path, rotate=rotation)
    model = DocumentModel()
    model.open(path)
    item = model.pages[0]
    item.crop = RedactionRect(100, 150, 400, 300)
    width, height = item.oriented_size
    assert {round(width), round(height)} == {300, 150}
    # The crop's corners land on the corners of the view, and come back.
    corners = [map_point(x, y, item.view_matrix()) for x, y in ((100, 150), (400, 300))]
    xs = sorted(round(x) for x, _ in corners)
    ys = sorted(round(y) for _, y in corners)
    assert xs == [0, round(width)] and ys == [0, round(height)]
    back = map_point(*map_point(250, 200, item.view_matrix()), item.page_matrix())
    assert back == pytest.approx((250, 200))


# -- save -------------------------------------------------------------------


@pytest.mark.parametrize("rotate", [0, 90])
def test_the_crop_becomes_the_crop_box(qapp, tmp_path, rotate) -> None:
    path = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf(path, rotate=rotate)
    model = DocumentModel()
    model.open(path)
    with pymupdf.open(path) as doc:
        word = doc[0].search_for("DENTRO")[0]
    crop = RedactionRect(100, 150, 400, 300)
    CropPages(model, [0], [crop]).redo()
    # A redaction made in page space before the crop lands where it was drawn.
    AddRedaction(model, 0, RedactionRect(word.x0, word.y0, word.x1, word.y1)).redo()
    RotatePage(model, 1, 90).redo()
    save_as(model, out)
    with pymupdf.open(out) as doc:
        assert (round(doc[0].cropbox.width), round(doc[0].cropbox.height)) == (300, 150)
        assert doc[0].search_for("DENTRO") == []
        # Hidden, not deleted: the text outside the crop is still in the file.
        doc[0].set_cropbox(doc[0].mediabox)
        assert doc[0].search_for("FUORI")
        assert doc[1].cropbox == doc[1].mediabox


def test_a_page_that_already_had_a_crop_box(qapp, tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf(path, cropbox=pymupdf.Rect(50, 50, 550, 750))
    model = DocumentModel()
    model.open(path)
    with pymupdf.open(path) as doc:
        word = doc[0].search_for("DENTRO")[0]  # relative to the old box
    crop = RedactionRect(word.x0 - 10, word.y0 - 10, word.x1 + 10, word.y1 + 10)
    CropPages(model, [0], [crop]).redo()
    save_as(model, out)
    with pymupdf.open(out) as doc:
        found = doc[0].search_for("DENTRO")
        assert found and abs(found[0].x0 - 10) < 1 and abs(found[0].y0 - 10) < 1


def test_the_content_is_found(qapp, tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    _pdf(path, rotate=90)
    model = DocumentModel()
    model.open(path)
    box = model.content_box(0)
    with pymupdf.open(path) as doc:
        inside = doc[0].search_for("DENTRO")[0]
        outside = doc[0].search_for("FUORI")[0]
    assert box is not None
    # The ink, not the font's box around it: search_for adds the ascender.
    for word in (inside, outside):
        assert box.x0 <= word.x0 + 3 and box.y0 <= word.y0 + 3
        assert word.x1 - 3 <= box.x1 and word.y1 - 3 <= box.y1
    assert box.x0 > 100 and box.y1 < 760


def test_the_worker_renders_only_the_crop(qapp, tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    _pdf(path, rotate=90)
    worker = RenderWorker()
    seen = []
    worker.rendered.connect(lambda key, image: seen.append(image))
    crop = RedactionRect(100, 150, 400, 300)
    for user in (0, 90):
        worker._render(RenderRequest(("page", user), path, 0, 1.0, user, (), crop))
    sizes = [(image.width(), image.height()) for image in seen]
    assert sizes == [(150, 300), (300, 150)]


# -- window -----------------------------------------------------------------


def test_the_dialog_crops_one_page_or_all(window, qapp, tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "doc.pdf")
    _pdf(path, pages=3)
    assert window.open_path(path)
    window._thumb_bar.set_current_row(1)
    canvas = window._page_view._canvases[1]
    full = (canvas.width_pt, canvas.height_pt)

    def answer(margins, every):
        def run(dialog):
            dialog.set_margins_mm(*margins)
            dialog.choose_all_pages(every)
            return True
        monkeypatch.setattr(window, "_run_crop_dialog", run)

    answer((10, 0, 20, 0), False)
    window._crop_pages()
    pages = window._doc_model.pages
    assert pages[0].crop is None and pages[2].crop is None
    assert pages[1].crop == pytest.approx(RedactionRect(0, 10 * MM, 600, 800 - 20 * MM))
    assert window._page_view._canvases[1].height_pt == pytest.approx(full[1] - 30 * MM)
    assert window.is_modified()

    answer((0, 0, 0, 0), True)  # «Nessun margine» on every page
    window._crop_pages()
    assert all(page.crop is None for page in pages)
    window._undo_stack.undo()
    assert pages[1].crop is not None
    window._undo_stack.undo()
    assert pages[1].crop is None and not window.is_modified()


def test_detect_fills_the_margins(window, qapp, tmp_path) -> None:
    path = str(tmp_path / "doc.pdf")
    _pdf(path)
    assert window.open_path(path)
    item = window._doc_model.pages[0]

    def detect():
        box = window._doc_model.content_box(0)
        return margins_of(box, *item.unrotated_size, item.total_rotation)

    dialog = CropDialog((0, 0, 0, 0), 2, detect, window)
    dialog._fill_from_content()
    top, right, bottom, left = dialog.margins()
    assert top > 100 and left > 100 and bottom > 50 and right > 100
    dialog.deleteLater()


def test_a_cropped_first_page_keeps_the_thumbnail_rows(window, qapp, tmp_path) -> None:
    # The bar measures the first row for all: a strip there collapsed them all.
    path = str(tmp_path / "doc.pdf")
    _pdf(path, pages=3)
    assert window.open_path(path)
    bar = window._thumb_bar
    before = bar.model().data(bar.model().index(0, 0), 13)  # SizeHintRole
    window._undo_stack.push(
        CropPages(window._doc_model, [0], [RedactionRect(0, 0, 600, 40)])
    )
    assert bar.model().data(bar.model().index(0, 0), 13) == before
    assert before.height() > 100
