"""End-to-end tests: open a PDF, manipulate it, save and verify the result.

These drive the real MainWindow (offscreen) including its render thread, then
assert on the materialised PDF. A fixture guarantees every window is closed,
so a failing assertion can never leave a QThread running.
"""

import os
import time

import fitz
import pytest
from PySide6.QtWidgets import QApplication

from plico.main_window import MainWindow

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def windows(qapp):
    """Factory that tracks every MainWindow and shuts them down for sure."""
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


def _make_pdf(path: str, pages: int = 5, text: str = "Pagina") -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} {i + 1}", fontsize=24)
    doc.save(path)
    doc.close()


def _pump(seconds: float = 0.6) -> None:
    """Let queued worker signals be delivered to the GUI thread."""
    app = QApplication.instance()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def _open(mw: MainWindow, pdf: str) -> None:
    """Open a document through the same entry point the menu uses."""
    mw.open_document(pdf)
    _pump()


def test_open_renders_pages(windows, tmp_path):
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=5)

    mw = windows()
    _open(mw, pdf)

    # Model and view agree
    assert mw._doc_model.page_count == 5
    assert len(mw._page_view._canvases) == 5
    # Native page geometry arrived from the worker
    assert mw._sizes_pt and mw._sizes_pt[0][0] > 0

    # The first page got a real pixmap, not the grey placeholder
    first = mw._page_view._canvases[0]
    pix = first.label.pixmap()
    assert not pix.isNull()
    assert pix.width() > 0 and pix.height() > 0
    assert first.label.text() == ""


def test_thumbnails_render(windows, tmp_path):
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=3)

    mw = windows()
    _open(mw, pdf)
    _pump()

    assert mw._thumb_bar._model.rowCount() == 3
    # At least one thumbnail landed in the shared cache
    assert len(mw._thumbnail_cache) >= 1
    key = next(iter(mw._thumbnail_cache))
    assert key[0] == "thumb"


def test_rotate_changes_geometry_and_saved_rotation(windows, tmp_path):
    pdf = str(tmp_path / "in.pdf")
    out = str(tmp_path / "out.pdf")
    _make_pdf(pdf, pages=3)

    mw = windows()
    _open(mw, pdf)

    first = mw._page_view._canvases[0]
    w_before, h_before = first.width_pt, first.height_pt
    assert (w_before, h_before) == (595.0, 842.0)   # A4 portrait

    mw._thumb_bar.set_current_row(0)
    mw._rotate_cw_clicked()
    _pump()

    first = mw._page_view._canvases[0]
    assert first.item.rotation == 90
    # 90° rotation swaps the displayed footprint
    assert (first.width_pt, first.height_pt) == (h_before, w_before)

    # And the canvas label was actually re-measured (landscape now)
    assert first.label.width() > first.label.height()

    from plico.model import save_as

    save_as(mw._doc_model, out)
    with fitz.open(out) as d:
        assert d.page_count == 3
        assert d[0].rotation == 90      # rotated page
        assert d[1].rotation == 0       # untouched page


def test_rotate_is_undoable(windows, tmp_path):
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=2)

    mw = windows()
    _open(mw, pdf)

    mw._thumb_bar.set_current_row(0)
    mw._rotate_cw_clicked()
    assert mw._doc_model.pages[0].rotation == 90

    mw._undo_stack.undo()
    _pump(0.2)
    assert mw._doc_model.pages[0].rotation == 0
    assert mw._page_view._canvases[0].height_pt > mw._page_view._canvases[0].width_pt


def test_delete_page_and_undo(windows, tmp_path):
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=4)

    mw = windows()
    _open(mw, pdf)

    mw._thumb_bar.set_current_row(1)
    mw._delete_page()
    _pump()

    assert mw._doc_model.page_count == 3
    # The deleted page was source_index 1; survivors keep their identity
    assert [p.source_index for p in mw._doc_model.pages] == [0, 2, 3]
    assert len(mw._page_view._canvases) == 3

    mw._undo_stack.undo()
    _pump()
    assert [p.source_index for p in mw._doc_model.pages] == [0, 1, 2, 3]
    assert len(mw._page_view._canvases) == 4


def test_move_page_command(windows, tmp_path):
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=3)

    mw = windows()
    _open(mw, pdf)

    from plico.model import MovePage

    mw._undo_stack.push(MovePage(mw._doc_model, 0, 2))
    assert [p.source_index for p in mw._doc_model.pages] == [1, 2, 0]

    mw._undo_stack.undo()
    assert [p.source_index for p in mw._doc_model.pages] == [0, 1, 2]


def test_drag_drop_becomes_a_command(windows, tmp_path):
    """The thumbnail bar must request a move, never reorder itself."""
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=3)

    mw = windows()
    _open(mw, pdf)

    seen: list[tuple[int, int]] = []
    mw._thumb_bar.move_requested.connect(lambda a, b: seen.append((a, b)))

    mw._thumb_bar.set_current_row(0)
    mw._move_page(0, 2)
    _pump(0.2)

    assert [p.source_index for p in mw._doc_model.pages] == [1, 2, 0]
    assert mw._undo_stack.count() == 1
    # Model and view stayed in sync
    assert [c.item.source_index for c in mw._page_view._canvases] == [1, 2, 0]


def test_save_preserves_base_rotation(windows, tmp_path):
    """A page with an existing /Rotate keeps it after an unrelated save."""
    pdf = str(tmp_path / "rotated.pdf")
    out = str(tmp_path / "out.pdf")

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Base 90", fontsize=12)
    # Set /Rotate before the first save: a document cannot be written back
    # onto the file it was opened from (PyMuPDF raises), so the rotation has
    # to be baked in at creation time.
    doc[0].set_rotation(90)
    doc.save(pdf)
    doc.close()

    mw = windows()
    mw._doc_model.open(pdf)

    item = mw._doc_model.pages[0]
    assert item.base_rotation == 90
    assert item.total_rotation == 90
    assert item.rotation == 0        # user offset untouched

    from plico.model import save_as

    save_as(mw._doc_model, out)
    with fitz.open(out) as d:
        assert d[0].rotation == 90


def test_save_over_the_original_file(windows, tmp_path):
    """Saving onto the open file must work and must not corrupt it."""
    pdf = str(tmp_path / "inplace.pdf")
    _make_pdf(pdf, pages=2)

    mw = windows()
    _open(mw, pdf)
    mw._thumb_bar.set_current_row(0)
    mw._delete_page()
    assert mw._doc_model.page_count == 1

    from plico.model import save_as

    save_as(mw._doc_model, pdf)         # same path as the source

    with fitz.open(pdf) as d:
        assert d.page_count == 1
    # No temporary files left behind next to the target.
    leftovers = [p for p in os.listdir(tmp_path) if p.endswith(".tmp")]
    assert leftovers == []


def test_compression_flags_reduce_size(tmp_path):
    """garbage=4 + deflate should not inflate a simple document."""
    from plico.model import save_as

    pdf = str(tmp_path / "in.pdf")
    out = str(tmp_path / "out.pdf")
    _make_pdf(pdf, pages=3)

    mw = MainWindow()
    try:
        mw._doc_model.open(pdf)
        save_as(mw._doc_model, out)
    finally:
        mw.shutdown_worker()

    with fitz.open(out) as d:
        assert d.page_count == 3
        assert d[0].get_text().strip() == "Pagina 1"

def test_large_document_stays_responsive(windows, tmp_path):
    """Acceptance criterion: a 300-page PDF must open without blocking.

    The point is not that it is fast, but that opening does not do 300
    pages' worth of work up front: only the pages in view are rendered, and
    thumbnails load lazily as the user scrolls.
    """
    pdf = str(tmp_path / "big.pdf")
    _make_pdf(pdf, pages=300)

    mw = windows()
    requested = []
    mw._worker.render_requested.connect(lambda req: requested.append(req.key))

    started = time.monotonic()
    mw.open_document(pdf)
    open_seconds = time.monotonic() - started

    assert open_seconds < 2.0, f"opening blocked the UI for {open_seconds:.2f}s"
    assert mw._doc_model.page_count == 300

    page_keys = [k for k in requested if k[0] == "page"]
    # A window shows a handful of pages, not all 300.
    assert len(page_keys) < 30, f"requested {len(page_keys)} page renders up front"

    _pump(0.8)
    page_keys = [k for k in requested if k[0] == "page"]
    assert len(page_keys) < 60, f"rendered {len(page_keys)} pages for one screen"


def test_second_document_does_not_reuse_first_render(windows, tmp_path):
    """Caches are keyed by source_index, so they MUST be flushed per document."""
    first_pdf = str(tmp_path / "first.pdf")
    second_pdf = str(tmp_path / "second.pdf")
    _make_pdf(first_pdf, pages=1, text="AAAA")
    _make_pdf(second_pdf, pages=1, text="BBBB")

    mw = windows()
    seen: list[tuple] = []
    mw._worker.rendered.connect(lambda key, img: seen.append((key, img.copy())))

    _open(mw, first_pdf)
    first = [img for key, img in seen if key[0] == "page"]
    assert first, "first document produced no page render"

    seen.clear()
    _open(mw, second_pdf)
    second = [img for key, img in seen if key[0] == "page"]
    assert second, "second document produced no page render"

    def digest(img) -> bytes:
        return bytes(img.constBits())

    assert digest(first[0]) != digest(second[0]), (
        "the second document reused the first document's cached pixmap"
    )


def test_application_quit_stops_the_worker_thread(windows, tmp_path):
    """Quitting the app (not just closing the window) must stop the thread.

    A QThread still running when it is destroyed aborts the whole process,
    so shutdown is hooked to QApplication.aboutToQuit and not only to
    MainWindow.closeEvent.
    """
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)

    mw = windows()
    _open(mw, pdf)
    assert mw._thread.isRunning()

    QApplication.instance().aboutToQuit.emit()

    assert not mw._thread.isRunning(), "the render thread survived app quit"
