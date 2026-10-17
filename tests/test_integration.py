"""End-to-end tests: open a PDF, manipulate it, save and verify the result.

These drive the real MainWindow (offscreen) including its render thread, then
assert on the materialised PDF. A fixture guarantees every window is closed,
so a failing assertion can never leave a QThread running.
"""

import os
import pathlib
import time
from unittest import mock

import pymupdf
import pytest
from PySide6.QtCore import QEvent, QPointF, QSettings, Qt, QThreadPool
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QImage, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
)

import plico.main_window
from plico.main_window import MainWindow
from plico.model import LEVELS_BY_KEY
from plico.model.commands import DeletePage, RotatePage
from plico.model.redact import RedactionRect, map_rect, rotation_matrix
from plico.model.save import save_as
from plico.widgets.thumbnail_bar import (
    THUMB_ZOOM,
    ThumbnailBar,
    ThumbnailCache,
    thumb_key,
)

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


def _make_pdf(
    path: str,
    pages: int = 5,
    text: str = "Pagina",
    size: tuple[float, float] | None = None,
) -> None:
    """Write a small PDF; *size* allows a mixed-orientation document."""
    doc = pymupdf.open()
    width, height = size if size else (595.0, 842.0)
    for i in range(pages):
        page = doc.new_page(width=width, height=height)
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
    # Native page geometry was read from the model
    assert mw._doc_model.page_sizes and mw._doc_model.page_sizes[0][0] > 0

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
    assert (w_before, h_before) == (595.0, 842.0)  # A4 portrait

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
    with pymupdf.open(out) as d:
        assert d.page_count == 3
        assert d[0].rotation == 90  # rotated page
        assert d[1].rotation == 0  # untouched page


def test_page_with_base_rotation_is_not_rotated_twice(windows, tmp_path):
    """A page carrying its own /Rotate must be shown as it really is.

    MuPDF applies the page's /Rotate both when rendering and when reporting
    ``page.rect``, so the renderer may only add the USER's offset. Passing the
    composite rotation rotates such a page a second time: it comes out
    portrait and upside down. Base-rotated pages are common (scans, phone
    exports, anything a viewer has "fixed" by writing /Rotate), which is why
    this needs a regression test of its own.
    """
    pdf = str(tmp_path / "base90.pdf")
    out = str(tmp_path / "base90-out.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # stored portrait...
    page.insert_text((72, 72), "BASE90", fontsize=24)
    page.set_rotation(90)  # ...but flagged as rotated 90
    doc.save(pdf)
    doc.close()

    mw = windows()
    _open(mw, pdf)

    assert mw._doc_model.pages[0].base_rotation == 90
    assert mw._doc_model.pages[0].rotation == 0  # the user rotated nothing

    first = mw._page_view._canvases[0]
    # Landscape, the way every other PDF viewer shows it.
    assert (first.width_pt, first.height_pt) == (842.0, 595.0)
    pix = first.label.pixmap()
    assert not pix.isNull()
    assert pix.width() > pix.height()  # NOT portrait: no double rotation

    # The user's own 90° must compose with the base one, not replace it.
    mw._thumb_bar.set_current_row(0)
    mw._rotate_cw_clicked()
    _pump()
    first = mw._page_view._canvases[0]
    assert (first.width_pt, first.height_pt) == (595.0, 842.0)

    save_as(mw._doc_model, out)
    with pymupdf.open(out) as d:
        assert d[0].rotation == 180  # 90 base + 90 user


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

    doc = pymupdf.open()
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
    assert item.rotation == 0  # user offset untouched

    from plico.model import save_as

    save_as(mw._doc_model, out)
    with pymupdf.open(out) as d:
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

    save_as(mw._doc_model, pdf)  # same path as the source

    with pymupdf.open(pdf) as d:
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

    with pymupdf.open(out) as d:
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
    """Render keys embed the source identity, so caches MUST still be flushed.

    Two different files both have a page 0; without the flush the second
    document would be served the first document's pixmap from cache.
    """
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


def test_all_window_shortcuts_are_valid(windows):
    """A mistyped key name parses to an EMPTY sequence and silently
    disables the shortcut.  'Canc' (Italian for Del) did exactly that:
    QKeySequence('Canc').toString() == '' while non-empty checks pass.
    """
    mw = windows()
    actions = [a for a in mw.findChildren(QAction) if not a.shortcut().isEmpty()]

    assert actions, "no window action exposes a shortcut at all"
    broken = [a.text() for a in actions if not a.shortcut().toString()]
    assert not broken, f"shortcuts that do not round-trip: {broken}"


def test_actions_carry_theme_icons_no_bundled_assets(windows):
    """KDE touches: icons come from the Breeze theme, never from the app.

    On a headless container no icon theme is installed, so fromTheme()
    legitimately returns a null icon and _act() skips it rather than
    painting an empty square; in that case there is nothing to assert.
    """
    wanted = ("object-rotate-right", "object-rotate-left")
    if not any(QIcon.hasThemeIcon(name) for name in wanted):
        pytest.skip(f"no icon theme provides {wanted} here (Qt theme: {QIcon.themeName()!r})")

    mw = windows()
    for action in mw.findChildren(QAction):
        if action.text() in ("Ruota a destra", "Ruota a sinistra"):
            assert not action.icon().isNull(), f"{action.text()} has no theme icon"


def test_package_ships_no_icon_assets():
    """The 'zero assets to package' requirement, verified on disk."""
    pkg = pathlib.Path(plico.main_window.__file__).parent
    icons = [
        f
        for f in pkg.rglob("*")
        if f.suffix.lower() in (".png", ".svg", ".ico", ".xpm") and f.is_file()
    ]
    assert not icons, f"bundled icon assets defeat the theme-icon approach: {icons}"


def test_zoom_and_geometry_round_trip_through_settings(qapp, tmp_path, monkeypatch):
    """QSettings must survive a restart: close the window, reopen, same zoom.

    _settings is redirected to a throwaway INI so the test never touches the
    developer's real configuration.
    """
    ini = str(tmp_path / "plico.ini")
    monkeypatch.setattr(
        MainWindow,
        "_settings",
        lambda self: QSettings(ini, QSettings.Format.IniFormat),
    )

    first = MainWindow()
    first._page_view.set_zoom(1.5)
    first.resize(1000, 700)
    first.close()  # closeEvent -> _save_settings
    first.deleteLater()

    stored = QSettings(ini, QSettings.Format.IniFormat)
    assert float(stored.value("view/zoom")) == pytest.approx(1.5)
    blob = stored.value("window/geometry")
    assert blob is not None and not blob.isEmpty(), "geometry was never written"

    # restoreGeometry() clamps to the available screen (the offscreen
    # platform is 800px wide), so assert on round-trip *stability* rather
    # than on the raw pixel size.
    second = MainWindow()
    try:
        assert second._page_view.zoom() == pytest.approx(1.5)
        restored = second.saveGeometry()
        assert not restored.isEmpty()
        third = MainWindow()
        try:
            assert third.saveGeometry() == restored
        finally:
            third.shutdown_worker()
            third.deleteLater()
    finally:
        second.shutdown_worker()
        second.deleteLater()


def test_file_menu_exposes_every_expected_action(windows):
    """Guards the menu against an action being dropped by a careless edit."""
    mw = windows()
    texts = {a.text() for a in mw.findChildren(QAction)}

    expected = {
        "A&pri…",
        "&Salva",
        "Salva con &nome…",
        "&Unisci PDF…",
        "&Estrai pagine…",
        "&Esci",
        "Annulla",
        "Ripeti",
        "Elimina pagina",
        "Adatta alla &larghezza",
        "Zoom a&vanti",
        "Zoom &indietro",
    }
    assert expected <= texts, f"missing menu actions: {expected - texts}"


def test_no_two_actions_share_a_shortcut(windows):
    mw = windows()
    seen: dict[str, str] = {}
    for action in mw.findChildren(QAction):
        if action.shortcut().isEmpty():
            continue
        key = action.shortcut().toString()
        # Undo/redo live on the QUndoStack, so ignore obviously distinct
        # duplicates only if they are the same action text.
        if key in seen and seen[key] != action.text():
            raise AssertionError(f"shortcut {key} used by both {seen[key]!r} and {action.text()!r}")
        seen[key] = action.text()


def test_extract_action_writes_a_subset_without_touching_the_source(
    qapp, tmp_path, monkeypatch, windows
):
    """Drives the real menu handler with the dialogs stubbed out."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=5)
    out = str(tmp_path / "out.pdf")

    mw = windows()
    _open(mw, pdf)
    mw._doc_model.pages[1].rotation = 90

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("2-3", True)))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))

    mw._extract_pages()

    with pymupdf.open(out) as doc:
        assert doc.page_count == 2
        assert doc[0].rotation == 90  # page 2 of the source
    with pymupdf.open(pdf) as doc:
        assert doc.page_count == 5, "extracting must not modify the source"


def test_extract_rejects_a_bad_page_spec_without_writing(qapp, tmp_path, monkeypatch, windows):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=5)
    out = str(tmp_path / "out.pdf")

    mw = windows()
    _open(mw, pdf)

    # A modal QMessageBox would block forever offscreen, so capture it.
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda _parent, _title, text, *a, **k: warnings.append(text)),
    )

    calls: list[str] = []
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("99", True)))
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (calls.append("asked"), (out, ""))[1]),
    )

    mw._extract_pages()

    assert calls == [], "a file dialog must not open for an invalid range"
    assert not os.path.exists(out)
    assert warnings and "99" in warnings[0], f"the user must be told why: {warnings}"


# --------------------------------------------------------------------- #
#  Unire (merge): a second source document, never a second copy
# --------------------------------------------------------------------- #

def test_merge_appends_a_second_source(windows, tmp_path):
    """Unire must grow the page list without copying anything anywhere."""
    pdf_a = str(tmp_path / "a.pdf")
    pdf_b = str(tmp_path / "b.pdf")
    _make_pdf(pdf_a, pages=5, text="A")
    _make_pdf(pdf_b, pages=3, text="B")

    mw = windows()
    _open(mw, pdf_a)
    mw._doc_model.append_document(pdf_b)

    assert mw._doc_model.page_count == 8
    assert len(mw._doc_model.sources) == 2
    # Page sizes are stored per virtual page, so the appended ones are aligned
    assert len(mw._doc_model.page_sizes) == 8
    # The appended pages know which document they belong to
    assert [p.source_id for p in mw._doc_model.pages] == [0] * 5 + [1] * 3
    # ...and both sources still resolve to their own path
    assert mw._doc_model.source_for(mw._doc_model.pages[0]) == pdf_a
    assert mw._doc_model.source_for(mw._doc_model.pages[7]) == pdf_b

    # The view rebuilt itself from the model, with no manual refresh
    assert len(mw._page_view._canvases) == 8
    assert mw._thumb_bar._model.rowCount() == 8


def test_merged_page_identity_does_not_collide(windows, tmp_path):
    """Both sources contain a page 0; they must remain distinct pages."""
    pdf_a = str(tmp_path / "a.pdf")
    pdf_b = str(tmp_path / "b.pdf")
    _make_pdf(pdf_a, pages=2, text="A")
    _make_pdf(pdf_b, pages=2, text="B")

    mw = windows()
    _open(mw, pdf_a)
    mw._doc_model.append_document(pdf_b)

    # Row 0 and row 2 both have source_index 0 but different source_id
    first, third = mw._doc_model.pages[0], mw._doc_model.pages[2]
    assert first.source_index == third.source_index == 0
    assert first.source_id != third.source_id

    view = mw._page_view
    assert len(view._by_page) == 4, "colliding source_index would collapse two pages"
    assert view._identity(first) != view._identity(third)


def test_merged_document_renders_and_saves_every_source(windows, tmp_path):
    """Both the render thread and the writer must reach the second PDF."""
    pdf_a = str(tmp_path / "a.pdf")
    pdf_b = str(tmp_path / "b.pdf")
    _make_pdf(pdf_a, pages=5, text="A")
    _make_pdf(pdf_b, pages=3, text="B")

    mw = windows()
    # A real window: the scrollbar only has a range once the scroll area has
    # been laid out, so an unshown window cannot scroll to a page.
    mw.resize(1024, 768)
    mw.show()
    _open(mw, pdf_a)
    mw._doc_model.append_document(pdf_b)
    _pump(0.3)

    # Pages render lazily, so the merged page only appears once it is on
    # screen: scroll to it exactly as the user would.
    view = mw._page_view
    assert view.verticalScrollBar().maximum() > 0, "the window must be scrollable"
    view.ensure_page_visible(5)
    _pump(1.5)

    appended = view._by_page[(1, 0)]
    assert appended.label.pixmap().width() > 0, "a merged page must render"

    out = str(tmp_path / "merged.pdf")
    save_as(mw._doc_model, out)
    with pymupdf.open(out) as doc:
        assert doc.page_count == 8
        # Page 5 is the first page of the second document
        assert "B" in doc[5].get_text()
        assert "A" in doc[0].get_text()


def test_merge_respects_rotation_of_both_sources(windows, tmp_path):
    """A rotation applied to a merged page must survive the save."""
    pdf_a = str(tmp_path / "a.pdf")
    pdf_b = str(tmp_path / "b.pdf")
    _make_pdf(pdf_a, pages=2, text="A")
    _make_pdf(pdf_b, pages=2, text="B")

    mw = windows()
    _open(mw, pdf_a)
    mw._doc_model.append_document(pdf_b)

    row = 2  # first page of the second source
    mw._undo_stack.push(RotatePage(mw._doc_model, row, 90))
    mw._undo_stack.push(DeletePage(mw._doc_model, 0))  # drop a page from source A

    out = str(tmp_path / "rotated.pdf")
    save_as(mw._doc_model, out)
    with pymupdf.open(out) as doc:
        assert doc.page_count == 3
        # Deleting row 0 leaves A2 first, then the two pages of B
        assert "A 2" in doc[0].get_text()
        assert "B" in doc[1].get_text()
        assert doc[1].rotation == 90, "rotation of a merged page must be written"
        assert doc[0].rotation == 0


def test_merge_action_reads_a_second_file_and_saves_both(
    qapp, tmp_path, monkeypatch, windows
):
    """Drives the real menu handler with the file dialog stubbed out."""
    pdf_a = str(tmp_path / "a.pdf")
    pdf_b = str(tmp_path / "b.pdf")
    _make_pdf(pdf_a, pages=2, text="A")
    _make_pdf(pdf_b, pages=2, text="B")
    out = str(tmp_path / "merged.pdf")

    mw = windows()
    _open(mw, pdf_a)

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (pdf_b, "")))
    mw._merge_file()

    assert mw._doc_model.page_count == 4
    assert len(mw._doc_model.sources) == 2
    assert "Unite 2" in mw._status.text()

    save_as(mw._doc_model, out)
    with pymupdf.open(out) as doc:
        assert doc.page_count == 4
        assert "A 1" in doc[0].get_text()
        assert "B 1" in doc[2].get_text()
        assert "B 2" in doc[3].get_text()
    # Merging is additive and never rewrites the documents being read
    with pymupdf.open(pdf_a) as doc:
        assert doc.page_count == 2
    with pymupdf.open(pdf_b) as doc:
        assert doc.page_count == 2


def test_merge_without_a_document_warns_instead_of_crashing(
    qapp, tmp_path, monkeypatch, windows
):
    """No document open: the action must refuse, not raise."""
    mw = windows()
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2]))
    )
    opened = []
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: opened.append(a) or ("", ""))
    )

    mw._merge_file()

    assert warnings, "the user must be told there is nothing to merge into"
    assert opened == [], "no file dialog without an open document"


def test_merge_reveals_the_appended_pages_in_a_real_window(windows, tmp_path):
    """The merged pages must actually reach the viewport, not just the model.

    Regression guard: the scroll target is computed from our own layout, and
    the scrollbar range is only final after Qt's own layout pass. Clamping to
    a not-yet-grown range used to stop the view short of the merged pages.
    """
    pdf_a = str(tmp_path / "a.pdf")
    pdf_b = str(tmp_path / "b.pdf")
    _make_pdf(pdf_a, pages=3, text="A")                      # portrait
    _make_pdf(pdf_b, pages=2, text="B", size=(842.0, 595.0))  # landscape

    mw = windows()
    mw.resize(1000, 700)
    mw.show()
    _open(mw, pdf_a)
    mw._doc_model.append_document(pdf_b)
    _pump(0.5)

    view = mw._page_view
    assert view.verticalScrollBar().maximum() > 0, "the window must be scrollable"
    view.ensure_page_visible(3)   # first merged page
    _pump(1.5)

    first, last = view._visible_range()
    assert first <= 3 < last, (
        f"merged page 3 is not in view: range is ({first}, {last}), "
        f"scroll is {view.verticalScrollBar().value()}"
    )
    merged = view._by_page[(1, 0)]
    assert not merged.label.pixmap().isNull(), "the merged page must be rendered"
    # Landscape source appended to a portrait one: the box must be landscape.
    assert merged.width_pt > merged.height_pt


def test_open_path_reports_a_broken_file_instead_of_raising(
    qapp, tmp_path, monkeypatch, windows
):
    """The command line must fail like the dialog does, never crash on startup.

    The .desktop file hands the document over as an argument, so a corrupted
    file is now reachable before the window is even up: the failure has to be
    a message box, not a traceback out of main().
    """
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a PDF at all\n")
    errors = []
    monkeypatch.setattr(
        QMessageBox, "critical", staticmethod(lambda *a, **k: errors.append(a[2]))
    )

    mw = windows()

    assert mw.open_path(str(broken)) is False
    assert errors, "a damaged PDF must be reported to the user"
    assert mw._doc_model.page_count == 0


def test_open_path_and_merge_path_drive_the_command_line(tmp_path, windows):
    """`plico a.pdf b.pdf` opens the first document and appends the rest."""
    pdf_a = str(tmp_path / "a.pdf")
    pdf_b = str(tmp_path / "b.pdf")
    _make_pdf(pdf_a, pages=2, text="A")
    _make_pdf(pdf_b, pages=3, text="B")

    mw = windows()

    assert mw.open_path(pdf_a) is True
    assert mw._doc_model.page_count == 2

    # No dialog is involved on this path.
    mw.merge_path(pdf_b)

    assert mw._doc_model.page_count == 5
    assert len(mw._doc_model.sources) == 2
    assert mw._doc_model.pages[2].source_id != mw._doc_model.pages[0].source_id


# --------------------------------------------------------------------------- #
#  Regressions from the second review round
# --------------------------------------------------------------------------- #

def test_drop_target_row_maps_both_directions():
    """The drop destination is an index in the list WITHOUT the dragged row.

    MovePage pops and then inserts, so when the target sits after the dragged
    row its position shifts by one. Without the fix, dragging a page downwards
    onto the UPPER half of X still left it after X.
    """
    # On [A B C D], I drag A (row 0) onto C (row 2):
    assert ThumbnailBar.drop_target_row(0, 2, below=False) == 1  # above C → [B A C D]
    assert ThumbnailBar.drop_target_row(0, 2, below=True) == 2   # below C → [B C A D]
    # I drag D (row 3) upwards, onto B (row 1):
    assert ThumbnailBar.drop_target_row(3, 1, below=False) == 1  # above B → [A D B C]
    assert ThumbnailBar.drop_target_row(3, 1, below=True) == 2   # below B → [A B D C]


def test_drop_target_row_agrees_with_the_move_command(windows, tmp_path):
    """The mapping is correct only if MovePage really produces that order."""
    pdf = str(tmp_path / "four.pdf")
    _make_pdf(pdf, pages=4, text="P")

    mw = windows()
    _open(mw, pdf)

    to_row = ThumbnailBar.drop_target_row(0, 2, below=False)
    mw._move_page(0, to_row)

    assert [p.source_index for p in mw._doc_model.pages] == [1, 0, 2, 3]


def test_selection_survives_a_delete(windows, tmp_path):
    """After a delete the selection must not die.

    beginResetModel/endResetModel resets currentIndex: without the restore
    Ctrl+R read -1 and did nothing until the user clicked again.
    """
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=5)

    mw = windows()
    _open(mw, pdf)
    mw._thumb_bar.set_current_row(3)
    assert mw._thumb_bar.current_row() == 3

    mw._delete_page()  # deletes row 3

    row = mw._thumb_bar.current_row()
    assert row >= 0, "la selezione è andata persa dopo il delete"

    # ...and now the command really acts on that row.
    mw._rotate_selected(90)
    assert mw._doc_model.pages[row].rotation == 90


def test_rotation_drops_the_stale_thumbnail_of_that_page(windows, tmp_path):
    """The key embeds the rotation: the previous entry is unreachable.

    Without the discard, every rotation left an orphan image in the LRU.
    """
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=3)

    mw = windows()
    _open(mw, pdf)

    old_key = thumb_key(mw._doc_model.pages[0], THUMB_ZOOM, 1.0)
    other_key = thumb_key(mw._doc_model.pages[1], THUMB_ZOOM, 1.0)
    blank = QImage(4, 4, QImage.Format.Format_RGB888)
    mw._thumbnail_cache[old_key] = blank
    mw._thumbnail_cache[other_key] = blank

    mw._thumb_bar.set_current_row(0)
    mw._rotate_selected(90)

    assert old_key not in mw._thumbnail_cache, "miniatura stantia non scartata"
    assert other_key in mw._thumbnail_cache, "scartata la miniatura di un'altra pagina"


def test_thumbnail_requests_are_not_duplicated(windows, tmp_path):
    """Scrolling must not fill the worker queue with duplicate requests.

    Observed on `_pending` rather than on the signal: a Python callable
    connected to a signal of a QObject living in another thread is
    delivered QUEUED, so a spy in the GUI thread would not see it.
    """
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=30)

    mw = windows()
    _open(mw, pdf)

    # Put the bar back into the "nothing cached, nothing in flight" state.
    mw._thumbnail_cache.clear()
    mw._thumb_bar._pending.clear()

    mw._thumb_bar.refresh()
    in_flight = dict(mw._thumb_bar._pending)
    assert in_flight, "la barra non ha chiesto nessuna miniatura"

    mw._thumb_bar.refresh()
    mw._thumb_bar.refresh()

    assert mw._thumb_bar._pending == in_flight, "richieste duplicate in volo"


def test_late_render_for_a_key_nobody_asked_is_dropped(windows, tmp_path):
    """The result of a document we no longer show must not go into the cache.

    Keys restart from source_id 0 on every open: without the `_pending`
    filter the thumbnail of the old file would land on the new one's row.
    """
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=3)

    mw = windows()
    _open(mw, pdf)

    mw._thumbnail_cache.clear()
    mw._thumb_bar._pending.clear()
    orphan = ("thumb", 0, 0, 0, THUMB_ZOOM, 1.0)
    mw._thumb_bar._on_rendered(orphan, QImage(4, 4, QImage.Format.Format_RGB888))

    assert orphan not in mw._thumbnail_cache


def test_failed_thumbnail_render_clears_pending(windows, tmp_path):
    """A failed request must be retryable, not stay hanging."""
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=3)

    mw = windows()
    _open(mw, pdf)

    mw._thumbnail_cache.clear()
    mw._thumb_bar._pending.clear()
    mw._thumb_bar.refresh()
    assert mw._thumb_bar._pending, "niente in volo: il test non prova nulla"

    for key in list(mw._thumb_bar._pending):
        mw._thumb_bar._on_render_failed(key)

    assert mw._thumb_bar._pending == {}


def test_thumbnail_cache_is_lru_not_fifo():
    """`get` must refresh the recency, or the cache is FIFO in disguise."""
    cache = ThumbnailCache(maxsize=2)
    cache["a"] = 1
    cache["b"] = 2

    assert cache.get("a") == 1  # "a" goes back to the front
    cache["c"] = 3              # must evict "b", not "a"

    assert "a" in cache
    assert "b" not in cache


def test_the_page_cache_frees_the_bytes_it_replaced(windows):
    """Putting the same key back must not count the same bytes twice.

    A page can be put back into the cache with the same key (a render retried
    after an error, a screen change): the bytes of the replaced pixmap must be
    returned to the budget, otherwise more than due is evicted.
    """
    mw = windows()
    view = mw._page_view
    key = ("page", 0, 0, 0, 1.0, 1.0)

    view._cache_put(key, QPixmap(100, 100))
    assert view._cache_bytes == 100 * 100 * 4

    view._cache_put(key, QPixmap(50, 50))
    assert view._cache_bytes == 50 * 50 * 4, "i byte della pixmap sostituita"
    assert len(view._cache) == 1

    # And the same key must not stay twice in the queue.
    assert list(view._cache) == [key]


def test_saving_over_the_open_file_makes_the_worker_forget_it(windows, tmp_path):
    """After a save that overwrites the source the handle is stale.

    save_as() uses os.replace(): the inode changes, but the worker would keep
    the old document open, so reopening the same file would render the
    previous content.
    """
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=4, text="Prima")

    mw = windows()
    _open(mw, pdf)
    previous = mw._worker._docs.get(pdf)
    assert previous is not None, "il worker non ha aperto la sorgente"

    mw._delete_page()
    with mock.patch.object(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (pdf, ""))
    ):
        mw._save_file_as()
    _pump()

    # The file is re-opened, so the worker may well hold a handle again --
    # just never the one it had before the save.
    assert previous.is_closed, "il worker tiene ancora il documento sovrascritto"
    assert mw._worker._docs.get(pdf) is not previous
    with pymupdf.open(pdf) as doc:
        assert doc.page_count == 4 - 1


def _three_pages(path: str, base: int = 0) -> None:
    """Three A4 pages with the text «PAGINA n» and a starting /Rotate of *base*."""
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"PAGINA {i + 1}", fontsize=24)
        page.set_rotation(base)
    doc.save(path)
    doc.close()


def _content(path: str) -> list[tuple[str, int]]:
    with pymupdf.open(path) as doc:
        return [(page.get_text().strip(), page.rotation) for page in doc]


@pytest.mark.parametrize("base", [0, 90])
def test_saving_over_the_open_file_then_saving_again_keeps_every_page(
    windows, tmp_path, base
):
    """Saving over the open file and then continuing must not lose pages.

    It was the bug: after os.replace() the PageItem still described the OLD
    file (page numbers, /Rotate, sizes), while on disk there was the
    materialized document. The second save lost a page and its rotation,
    and the view rendered the wrong pages rotating them twice. With base=90
    the starting /Rotate is checked too (§4).
    """
    pdf = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "di-nuovo.pdf")
    _three_pages(pdf, base)

    mw = windows()
    # Shown, so that scrolling a page into view really renders it.
    mw.resize(1000, 700)
    mw.show()
    _open(mw, pdf)
    mw._thumb_bar.set_current_row(0)
    mw._delete_page()
    mw._thumb_bar.set_current_row(0)
    mw._rotate_cw_clicked()
    _pump()

    with mock.patch.object(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (pdf, ""))
    ):
        mw._save_file_as()
    _pump()

    rotated = (base + 90) % 360
    assert _content(pdf) == [("PAGINA 2", rotated), ("PAGINA 3", base)]

    # The model now describes the file on disk, not the one it replaced.
    model = mw._doc_model
    assert model.sources == [pdf]
    assert [(p.source_index, p.base_rotation, p.rotation) for p in model.pages] == [
        (0, rotated, 0),
        (1, base, 0),
    ]
    # What is on disk cannot be undone: an undo stack that still offered the
    # old commands would mutate items that no longer exist.
    assert mw._undo_stack.count() == 0

    # The view shows the right pages, each rotated exactly once.
    canvases = mw._page_view._canvases
    assert len(canvases) == 2
    for index, (canvas, degrees) in enumerate(zip(canvases, (rotated, base), strict=True)):
        # Only what is on screen gets rendered: bring each page into view.
        mw._page_view.ensure_page_visible(index)
        _pump()
        pix = canvas.label.pixmap()
        assert not pix.isNull(), "la pagina non è stata resa dopo il salvataggio"
        horizontal = degrees % 180 == 90
        assert (pix.width() > pix.height()) == horizontal

    save_as(model, out)
    assert _content(out) == [("PAGINA 2", rotated), ("PAGINA 3", base)]


# --------------------------------------------------------------------- #
#  Salva compresso: the same menu entry, the same document as before
# --------------------------------------------------------------------- #

def _fragmented(path: str, pages: int = 20) -> None:
    """A PDF in the shape real PDFs arrive in: many pages, many streams.

    ``insert_text`` creates one object per call, so the document carries
    hundreds of tiny content streams. That is the case in which the
    compression really has something to do.
    """
    with pymupdf.open() as doc:
        for i in range(pages):
            page = doc.new_page(width=595, height=842)
            for k in range(40):
                page.insert_text(
                    (60, 60 + k * 18),
                    f"Paragrafo {k} della pagina {i + 1}: contenuto ripetuto per occupare spazio.",
                    fontsize=10,
                )
        doc.save(path, deflate=True)


def _chosen_level(monkeypatch, key: str = "light", accepted: bool = True) -> None:
    """Replaces the level dialog with an immediate answer."""

    class _Dialogo:
        def __init__(self, parent=None) -> None:
            self.level = LEVELS_BY_KEY[key]

        def exec(self) -> object:
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(plico.main_window, "CompressionDialog", _Dialogo)


def _wait_for_compression() -> None:
    """Waits for the thread pool, then delivers the queued signals to the GUI.

    The compression runs on a QRunnable: ``finished`` reaches the window as a
    queued connection, so an event loop round is needed too.
    """
    QThreadPool.globalInstance().waitForDone()
    _pump()


def test_the_compressed_entry_is_in_the_file_menu(windows):
    """The menu entry exists, in the position where the user looks for it."""
    mw = windows()
    entries = [action.text().replace("&", "") for action in mw.menuBar().actions()[0].menu().actions()]
    assert "Salva compresso…" in entries


def test_the_proposed_name_sits_next_to_the_original(windows, tmp_path):
    pdf = str(tmp_path / "relazione.pdf")
    _make_pdf(pdf, pages=2)

    mw = windows()
    _open(mw, pdf)

    assert mw._proposed_compressed_path() == str(tmp_path / "relazione-compresso.pdf")


def test_compress_writes_a_smaller_copy_and_leaves_the_source_alone(
    qapp, tmp_path, monkeypatch, windows
):
    """Walks the whole menu entry, with fake dialogs."""
    pdf = str(tmp_path / "doc.pdf")
    _fragmented(pdf)
    out = str(tmp_path / "doc-compresso.pdf")
    before = os.path.getsize(pdf)

    mw = windows()
    _open(mw, pdf)

    messaggi: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda _parent, _title, text, *a, **k: messaggi.append(text)),
    )
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    _chosen_level(monkeypatch, "light")

    mw._compress_file()
    _wait_for_compression()

    assert os.path.getsize(out) < before * 0.5, "il file compresso non e` piu` piccolo"
    with pymupdf.open(out) as doc:
        assert doc.page_count == 20
        assert "della pagina 1" in doc[0].get_text()
    assert os.path.getsize(pdf) == before, "la sorgente non si tocca"
    assert messaggi and "Prima:" in messaggi[0], f"il guadagno va raccontato: {messaggi}"
    assert mw._progress is None, "il dialogo di avanzamento deve sparire"
    assert mw._compression_task is None


def test_compress_writes_the_virtual_document(qapp, tmp_path, monkeypatch, windows):
    """The compressed file honours deletions and rotations too."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=5)
    out = str(tmp_path / "out.pdf")

    mw = windows()
    _open(mw, pdf)
    DeletePage(mw._doc_model, 0).redo()
    RotatePage(mw._doc_model, 0, 90).redo()

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    _chosen_level(monkeypatch, "light")

    mw._compress_file()
    _wait_for_compression()

    with pymupdf.open(out) as doc:
        assert doc.page_count == 4
        assert doc[0].rotation == 90


def test_compress_can_be_cancelled_at_the_level_dialog(qapp, tmp_path, monkeypatch, windows):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    out = str(tmp_path / "out.pdf")

    mw = windows()
    _open(mw, pdf)

    calls: list[str] = []
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (calls.append("chiesto"), (out, ""))[1]),
    )
    _chosen_level(monkeypatch, "light", accepted=False)

    mw._compress_file()

    assert calls == [], "annullare il livello non deve chiedere un file"
    assert not os.path.exists(out)


def test_compress_without_a_document_warns(qapp, monkeypatch, windows):
    mw = windows()

    avvisi: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda _parent, _title, text, *a, **k: avvisi.append(text)),
    )
    opened_files: list[str] = []
    monkeypatch.setattr(plico.main_window, "CompressionDialog", lambda *a, **k: opened_files.append("x"))

    mw._compress_file()

    assert opened_files == [], "senza documento non si sceglie nemmeno il livello"
    assert avvisi and "Nessun documento" in avvisi[0]


def test_compressing_over_the_open_file_evicts_the_stale_handle(
    qapp, tmp_path, monkeypatch, windows
):
    """As with save_as: os.replace() changes the inode under the worker's feet."""
    pdf = str(tmp_path / "doc.pdf")
    _fragmented(pdf, pages=6)

    mw = windows()
    _open(mw, pdf)
    previous = mw._worker._docs.get(pdf)
    assert previous is not None, "il worker non ha aperto la sorgente"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (pdf, "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    _chosen_level(monkeypatch, "light")

    mw._compress_file()
    _wait_for_compression()

    assert previous.is_closed, "il worker tiene ancora il documento sovrascritto"
    assert mw._worker._docs.get(pdf) is not previous
    with pymupdf.open(pdf) as doc:
        assert doc.page_count == 6


def test_compressing_over_the_open_file_reopens_the_document(
    qapp, tmp_path, monkeypatch, windows
):
    """The same bug as the save, from the «Salva compresso» entry."""
    pdf = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "di-nuovo.pdf")
    _three_pages(pdf)

    mw = windows()
    _open(mw, pdf)
    mw._thumb_bar.set_current_row(0)
    mw._delete_page()
    mw._thumb_bar.set_current_row(0)
    mw._rotate_cw_clicked()

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (pdf, "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    _chosen_level(monkeypatch, "light")

    mw._compress_file()
    _wait_for_compression()

    assert [(p.source_index, p.base_rotation, p.rotation) for p in mw._doc_model.pages] == [
        (0, 90, 0),
        (1, 0, 0),
    ]
    assert mw._undo_stack.count() == 0
    save_as(mw._doc_model, out)
    assert _content(out) == [("PAGINA 2", 90), ("PAGINA 3", 0)]


def test_extract_over_the_open_file_is_refused(qapp, tmp_path, monkeypatch, windows):
    """Extracting over the open document is refused, the file stays as it was."""
    pdf = str(tmp_path / "doc.pdf")
    _three_pages(pdf)

    mw = windows()
    _open(mw, pdf)

    messaggi: list[str] = []
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("1", True)))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (pdf, "")))
    monkeypatch.setattr(
        QMessageBox, "critical", staticmethod(lambda *a, **k: messaggi.append(a[2]))
    )

    mw._extract_pages()

    assert messaggi, "il rifiuto deve arrivare all'utente"
    assert len(_content(pdf)) == 3
    assert mw._doc_model.page_count == 3


def test_a_failed_compression_arrives_as_a_message(qapp, tmp_path, monkeypatch, windows):
    """An error in the worker thread must reach the user, not vanish."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    # A directory that does not exist: the temporary cannot even be created.
    out = str(tmp_path / "inesistente" / "out.pdf")

    mw = windows()
    _open(mw, pdf)

    errors: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda _parent, _title, text, *a, **k: errors.append(text)),
    )
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    _chosen_level(monkeypatch, "light")

    mw._compress_file()
    _wait_for_compression()

    assert errors and "Impossibile comprimere" in errors[0], errors
    assert mw._progress is None, "anche fallendo, il dialogo di avanzamento deve sparire"


# --------------------------------------------------------------------- #
#  Redazione: the mode, the drag and the full round
# --------------------------------------------------------------------- #

def _pdf_da_redigere(path: str) -> None:
    """Two well-separated words: one to remove, one to find again."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 100), "SEGRETO", fontsize=20)
        page.insert_text((100, 700), "PUBBLICO", fontsize=20)
        doc.save(path)


def _event(kind: QEvent.Type, pos: tuple[int, int]) -> QMouseEvent:
    # The form with global position is the only one Qt 6 does not flag as
    # deprecated; the local position is the one the label reads.
    point = QPointF(*pos)
    return QMouseEvent(
        kind,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _drag(label, start: tuple[int, int], end: tuple[int, int]) -> None:
    """A real drag: press, move, release.

    QtTest is not available in this PySide6 installation, so the events are
    built by hand and delivered to the same label that would receive them
    from the user. With ``da == a`` it becomes a plain click.
    """
    label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, start))
    if end != start:
        label.mouseMoveEvent(_event(QEvent.Type.MouseMove, end))
    label.mouseReleaseEvent(_event(QEvent.Type.MouseButtonRelease, end))


def _pixel_for(canvas, pdf: str, word: str) -> tuple[tuple[int, int], tuple[int, int]]:
    """Where *word* is on the screen, computed without using the view.

    Its purpose is not to ask PageView where it put the word and then check
    that it put it there: it starts from PyMuPDF's ``search_for`` and applies the
    same matrix MuPDF uses (fixed by tests/test_redact.py).
    """
    with pymupdf.open(pdf) as doc:
        box = doc[0].search_for(word)[0]
    rect = RedactionRect.from_corners(box.x0, box.y0, box.x1, box.y1)
    width, height = canvas.item.unrotated_size
    in_view = map_rect(rect, rotation_matrix(width, height, canvas.item.total_rotation))
    return (
        (int(in_view.x0 * canvas.scale), int(in_view.y0 * canvas.scale)),
        (int(in_view.x1 * canvas.scale), int(in_view.y1 * canvas.scale)),
    )


def test_redaction_is_a_mode_in_the_edit_menu(windows):
    mw = windows()
    entries = {
        action.text().replace("&", ""): action
        for action in mw.menuBar().actions()[1].menu().actions()
    }
    assert "Cancella zona" in entries, sorted(entries)
    assert entries["Cancella zona"].isCheckable(), "e` una modalita`, non un comando secco"
    assert entries["Cancella zona"].shortcut().toString() == "Ctrl+Shift+X"


def test_redaction_without_a_document_warns(qapp, monkeypatch, windows):
    mw = windows()

    avvisi: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda _parent, _title, text, *a, **k: avvisi.append(text)),
    )

    mw._redact_act.trigger()

    assert avvisi and "Nessun documento" in avvisi[0]
    assert not mw._redact_act.isChecked(), "la spunta deve tornare indietro"
    assert not mw._page_view.redaction_mode()


def test_redaction_mode_turns_on_and_off(qapp, tmp_path, windows):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    mw = windows()
    _open(mw, pdf)

    mw._redact_act.trigger()
    assert mw._redact_act.isChecked()
    assert mw._page_view.redaction_mode()

    mw._redact_act.trigger()
    assert not mw._redact_act.isChecked()
    assert not mw._page_view.redaction_mode()


def test_esc_leaves_redaction(qapp, tmp_path, windows):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=1)
    mw = windows()
    _open(mw, pdf)

    mw._redact_act.trigger()
    assert mw._page_view.redaction_mode()

    mw._escape_act.trigger()

    assert not mw._redact_act.isChecked()
    assert not mw._page_view.redaction_mode()


def test_opening_another_document_turns_redaction_off(qapp, tmp_path, windows):
    """Otherwise the first drag would mark a page never seen."""
    first = str(tmp_path / "primo.pdf")
    second = str(tmp_path / "secondo.pdf")
    _make_pdf(first, pages=1)
    _make_pdf(second, pages=1)

    mw = windows()
    _open(mw, first)
    mw._redact_act.trigger()
    assert mw._page_view.redaction_mode()

    _open(mw, second)

    assert not mw._redact_act.isChecked()
    assert not mw._page_view.redaction_mode()


def test_dragging_on_the_page_creates_a_redaction(qapp, tmp_path, windows):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=1)
    mw = windows()
    _open(mw, pdf)

    mw._redact_act.trigger()
    canvas = mw._page_view._canvases[0]

    _drag(canvas.label, (20, 20), (120, 80))
    _pump(0.1)

    redactions = mw._doc_model.pages[0].redactions
    assert len(redactions) == 1, "il trascinamento non ha lasciato una redazione"
    rect = redactions[0]
    width, height = mw._doc_model.pages[0].unrotated_size
    assert 0.0 <= rect.x0 < rect.x1 <= width
    assert 0.0 <= rect.y0 < rect.y1 <= height
    assert mw._undo_stack.count() == 1
    assert mw._undo_stack.undoText() == "Cancella zona su pagina 1"


def test_undoing_the_command_removes_the_redaction(qapp, tmp_path, windows):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=1)
    mw = windows()
    _open(mw, pdf)

    mw._redact_act.trigger()
    canvas = mw._page_view._canvases[0]
    _drag(canvas.label, (20, 20), (120, 80))
    assert len(mw._doc_model.pages[0].redactions) == 1

    mw._undo_stack.undo()

    assert mw._doc_model.pages[0].redactions == []

    mw._undo_stack.redo()
    assert len(mw._doc_model.pages[0].redactions) == 1


def test_a_click_on_a_mark_removes_it(qapp, tmp_path, windows):
    """A plain click is the way to take back a wrong rectangle."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=1)
    mw = windows()
    _open(mw, pdf)

    mw._redact_act.trigger()
    canvas = mw._page_view._canvases[0]
    _drag(canvas.label, (20, 20), (120, 80))
    assert len(mw._doc_model.pages[0].redactions) == 1

    # A click in the middle of the zone just drawn.
    _drag(canvas.label, (70, 50), (70, 50))
    _pump(0.1)

    assert mw._doc_model.pages[0].redactions == []
    assert mw._undo_stack.undoText() == "Ripristina zona su pagina 1"


def test_from_the_drag_to_the_file_the_text_disappears(qapp, tmp_path, monkeypatch, windows):
    """The full round: draw on the word, save, the word is no longer there."""
    pdf = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_da_redigere(pdf)

    mw = windows()
    _open(mw, pdf)

    mw._redact_act.trigger()
    canvas = mw._page_view._canvases[0]
    da, a = _pixel_for(canvas, pdf, "SEGRETO")
    _drag(canvas.label, da, a)
    assert len(mw._doc_model.pages[0].redactions) == 1

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    mw._save_file_as()
    _pump()

    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
    assert "SEGRETO" not in text, "il giro completo non ha rimosso il testo"
    assert "PUBBLICO" in text, "la redazione ha portato via anche il resto"


def test_the_drag_also_holds_with_a_rotated_page(qapp, tmp_path, monkeypatch, windows):
    """Where the rectangle can end up in the wrong place: a rotated page."""
    pdf = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_da_redigere(pdf)

    mw = windows()
    _open(mw, pdf)
    mw._doc_model.pages[0].rotation = 90
    mw._page_view.refresh_geometry()

    mw._redact_act.trigger()
    canvas = mw._page_view._canvases[0]
    assert canvas.item.total_rotation == 90
    da, a = _pixel_for(canvas, pdf, "SEGRETO")
    _drag(canvas.label, da, a)

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    mw._save_file_as()
    _pump()

    with pymupdf.open(out) as doc:
        assert doc[0].rotation == 90
        text = doc[0].get_text()
    assert "SEGRETO" not in text, "ruotando, il rettangolo e` finito altrove"
    assert "PUBBLICO" in text


# --------------------------------------------------------------------- #
#  AcroForm form: the panel, the click on the page and the save
# --------------------------------------------------------------------- #

def _add_field(page, name: str, kind: int, rect, value=None) -> None:
    """A field on the test form. The page must be alive."""
    widget = pymupdf.Widget()
    widget.field_name = name
    widget.field_type = kind
    widget.rect = pymupdf.Rect(*rect)
    if value is not None:
        widget.field_value = value
    page.add_widget(widget)
    widget.update()


def _form_pdf(path: str, pages: int = 1) -> None:
    """A form with a text field and a checkbox, on the last page."""
    with pymupdf.open() as doc:
        for _ in range(max(0, pages - 1)):
            doc.new_page(width=595, height=842)
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 60), "Modulo", fontsize=16)
        _add_field(
            page, "nome", pymupdf.PDF_WIDGET_TYPE_TEXT, (72, 100, 300, 128), "vecchio"
        )
        _add_field(page, "accetto", pymupdf.PDF_WIDGET_TYPE_CHECKBOX, (72, 140, 92, 160))
        doc.save(path, garbage=4, deflate=True)


def _file_values(path: str) -> dict[str, str]:
    with pymupdf.open(path) as doc:
        page = doc[0]
        return {w.field_name or "": w.field_value or "" for w in page.widgets() or ()}


def _editor_di(mw: MainWindow, name: str):
    """The editor the panel built for *nome*."""
    return mw._form_panel._editors[name]


def _type_in_panel(mw: MainWindow, name: str, value: str) -> None:
    """Simulates typing in the panel.

    QtTest does not exist in this installation, so for the text field the
    value is put into the editor and the same signal Qt emits while typing is
    emitted. Checkbox and combo box emit on their own, so there it is enough
    to act.
    """
    editor = _editor_di(mw, name)
    if isinstance(editor, QCheckBox):
        editor.setChecked(value not in ("", "Off"))
        return
    if isinstance(editor, QComboBox):
        editor.setCurrentText(value)
        return
    assert isinstance(editor, QLineEdit), editor
    editor.setText(value)
    editor.textEdited.emit(value)


def test_the_panel_shows_the_page_fields(qapp, tmp_path, windows):
    pdf = str(tmp_path / "modulo.pdf")
    _form_pdf(pdf)

    mw = windows()
    _open(mw, pdf)

    pannello = mw._form_panel
    assert pannello.page() == 0
    assert set(pannello._editors) == {"nome", "accetto"}
    assert _editor_di(mw, "nome").text() == "vecchio"
    assert not _editor_di(mw, "accetto").isChecked()


def test_without_a_document_the_panel_is_empty(qapp, windows):
    mw = windows()
    assert mw._form_panel._editors == {}


def test_the_panel_follows_the_selected_page(qapp, tmp_path, windows):
    """Fields live on one page: changing page changes them."""
    pdf = str(tmp_path / "due.pdf")
    _form_pdf(pdf, pages=2)

    mw = windows()
    _open(mw, pdf)
    assert mw._form_panel._editors == {}, "la prima pagina non ha campi"

    mw._thumb_bar.set_current_row(1)
    _pump()

    assert set(mw._form_panel._editors) == {"nome", "accetto"}


def test_typing_in_the_panel_becomes_a_command_and_reaches_the_file(
    qapp, tmp_path, monkeypatch, windows
):
    pdf = str(tmp_path / "modulo.pdf")
    out = str(tmp_path / "out.pdf")
    _form_pdf(pdf)

    mw = windows()
    _open(mw, pdf)

    _type_in_panel(mw, "nome", "Anna")

    assert mw._doc_model.pages[0].form_values["nome"] == "Anna"
    assert mw._undo_stack.count() == 1
    assert mw._undo_stack.undoText() == "Campo «nome» su pagina 1"

    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, ""))
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    mw._save_file_as()
    _pump()

    assert _file_values(out)["nome"] == "Anna"
    assert _file_values(pdf)["nome"] == "vecchio", "la sorgente non si tocca"


def test_undo_removes_the_panel_edit(qapp, tmp_path, windows):
    pdf = str(tmp_path / "modulo.pdf")
    _form_pdf(pdf)

    mw = windows()
    _open(mw, pdf)
    _type_in_panel(mw, "nome", "Anna")

    mw._undo_stack.undo()

    assert "nome" not in mw._doc_model.pages[0].form_values


def test_the_panel_checkbox_records_the_state(qapp, tmp_path, windows):
    pdf = str(tmp_path / "modulo.pdf")
    _form_pdf(pdf)

    mw = windows()
    _open(mw, pdf)

    _type_in_panel(mw, "accetto", "Yes")
    assert mw._doc_model.pages[0].form_values["accetto"] == "Yes"

    mw._undo_stack.undo()
    assert "accetto" not in mw._doc_model.pages[0].form_values


def test_a_click_on_the_page_selects_the_field(qapp, tmp_path, windows):
    """The click does not fill in: it tells the panel which field is being looked at."""
    pdf = str(tmp_path / "modulo.pdf")
    _form_pdf(pdf)

    mw = windows()
    _open(mw, pdf)

    canvas = mw._page_view._canvases[0]
    field = next(c for c in canvas.item.form_fields if c.name == "nome")
    inside = (
        int((field.rect[0] + field.rect[2]) / 2 * canvas.scale),
        int((field.rect[1] + field.rect[3]) / 2 * canvas.scale),
    )
    _drag(canvas.label, inside, inside)  # da == a: a plain click

    assert mw._page_view.selected_field() == (0, "nome")
    assert mw._form_panel.focusWidget() is not None


def test_a_click_outside_the_fields_selects_nothing(qapp, tmp_path, windows):
    pdf = str(tmp_path / "modulo.pdf")
    _form_pdf(pdf)

    mw = windows()
    _open(mw, pdf)

    canvas = mw._page_view._canvases[0]
    _drag(canvas.label, (5, 700), (5, 700))

    assert mw._page_view.selected_field() is None


def test_the_drawn_value_comes_from_the_model(qapp, tmp_path, windows):
    """The preview on the page must follow the model, not the file."""
    pdf = str(tmp_path / "modulo.pdf")
    _form_pdf(pdf)

    mw = windows()
    _open(mw, pdf)

    canvas = mw._page_view._canvases[0]
    field = next(c for c in canvas.item.form_fields if c.name == "nome")
    assert canvas.label._value_shown(canvas.item, field) == "vecchio"

    _type_in_panel(mw, "nome", "Anna")

    assert canvas.label._value_shown(canvas.item, field) == "Anna"
    assert field.value == "vecchio", "il descrittore resta quello del file"


# --------------------------------------------------------------------- #
#  Redigi testo: search for a word and mark it everywhere
# --------------------------------------------------------------------- #


def _search(mw, monkeypatch, text: str, conferma: bool = True) -> None:
    """Fakes the search dialog and triggers the menu action."""
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: (text, conferma))
    )
    mw._redact_text()


def test_the_redact_text_entry_is_in_the_edit_menu(windows) -> None:
    """The action exists, it is in Modifica and carries its shortcut."""
    mw = windows()
    modifica = next(a.menu() for a in mw.menuBar().actions() if "Modifica" in a.text())
    assert modifica is not None
    action = next(
        a for a in modifica.actions() if a.text().replace("&", "") == "Cancella parola…"
    )
    assert action.shortcut().toString() == "Ctrl+Shift+F"


def test_redact_text_marks_every_occurrence_in_one_step(
    windows, monkeypatch, tmp_path
) -> None:
    """Three marked pages must cost ONE Annulla, not three."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    mw = windows()
    _open(mw, pdf)

    _search(mw, monkeypatch, "Pagina")

    assert mw._undo_stack.count() == 1, "una macro, non un comando per pagina"
    assert mw._undo_stack.undoText() == "Cancella «Pagina»"
    assert sum(len(item.redactions) for item in mw._doc_model.pages) == 3
    assert mw._redact_act.isChecked(), "le tacche vanno mostrate, non solo messe"

    mw._undo_stack.undo()
    assert all(not item.redactions for item in mw._doc_model.pages)


def test_redact_text_saves_a_file_without_the_word(
    windows, monkeypatch, tmp_path
) -> None:
    """From the menu to the disk: the searched word is no longer in the file."""
    pdf = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _make_pdf(pdf, pages=2)
    mw = windows()
    _open(mw, pdf)

    _search(mw, monkeypatch, "Pagina")
    save_as(mw._doc_model, out)

    with pymupdf.open(out) as doc:
        assert doc.page_count == 2
        for page in doc:
            assert "Pagina" not in page.get_text()

    with pymupdf.open(pdf) as doc:
        assert "Pagina 1" in doc[0].get_text(), "la sorgente resta com'era"


def test_redact_text_cancelled_marks_nothing(windows, monkeypatch, tmp_path) -> None:
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=2)
    mw = windows()
    _open(mw, pdf)

    _search(mw, monkeypatch, "Pagina", conferma=False)

    assert mw._undo_stack.count() == 0
    assert all(not item.redactions for item in mw._doc_model.pages)


def test_redact_text_without_occurrences_says_so(windows, monkeypatch, tmp_path) -> None:
    """No command, no mark, and the status tells it."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=2)
    mw = windows()
    _open(mw, pdf)

    _search(mw, monkeypatch, "INESISTENTE")

    assert mw._undo_stack.count() == 0
    assert "Nessuna occorrenza" in mw._status.text()


def test_redact_text_without_a_document_warns(windows, monkeypatch) -> None:
    """With nothing open it warns, and the dialog does not even open."""
    avvisi: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: avvisi.append(a[2]))
    )

    def _never(*a, **k):
        raise AssertionError("il dialogo non deve aprirsi")

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(_never))
    mw = windows()

    mw._redact_text()

    assert avvisi and "Nessun documento" in avvisi[0]


def test_the_search_does_not_mark_the_same_spot_twice(
    windows, monkeypatch, tmp_path
) -> None:
    """The second search finds nothing more, and creates no command."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=1)
    mw = windows()
    _open(mw, pdf)

    _search(mw, monkeypatch, "Pagina")
    assert sum(len(item.redactions) for item in mw._doc_model.pages) == 1

    _search(mw, monkeypatch, "Pagina")

    assert sum(len(item.redactions) for item in mw._doc_model.pages) == 1
    assert mw._undo_stack.count() == 1, "la seconda ricerca non crea un comando"
    assert "Nessuna occorrenza" in mw._status.text()


# --------------------------------------------------------------------- #
#  Unsaved changes: Salva, the [*] in the title, the question before losing them
# --------------------------------------------------------------------- #

def _answer(monkeypatch, bottone) -> list[str]:
    """Answers QMessageBox.question with *bottone*, recording the questions."""
    domande: list[str] = []

    def rispondi(*args, **kwargs):
        domande.append(args[2])
        return bottone

    monkeypatch.setattr(QMessageBox, "question", staticmethod(rispondi))
    return domande


def _close_window(mw: MainWindow) -> bool:
    """Delivers a real QCloseEvent and says whether the window accepted it."""
    event = QCloseEvent()
    mw.closeEvent(event)
    return event.isAccepted()


def test_a_fresh_document_is_not_modified(windows, tmp_path, monkeypatch):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=2)
    mw = windows()
    _open(mw, pdf)
    domande = _answer(monkeypatch, QMessageBox.StandardButton.Cancel)

    assert not mw.is_modified()
    assert not mw.isWindowModified()
    assert mw.windowTitle() == "doc.pdf[*]"
    assert _close_window(mw), "niente da perdere: la finestra si chiude senza chiedere"
    assert domande == []


def test_an_edit_marks_the_title_and_undo_clears_it(windows, tmp_path):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=2)
    mw = windows()
    _open(mw, pdf)

    mw._thumb_bar.set_current_row(0)
    mw._rotate_cw_clicked()
    assert mw.is_modified() and mw.isWindowModified()

    mw._undo_stack.undo()
    assert not mw.is_modified(), "tornati al documento salvato: niente da salvare"
    assert not mw.isWindowModified()


def test_closing_with_changes_can_be_cancelled(windows, tmp_path, monkeypatch):
    """Annulla: the window stays open, the change stays in the model."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    mw = windows()
    _open(mw, pdf)
    mw._delete_page()
    domande = _answer(monkeypatch, QMessageBox.StandardButton.Cancel)

    assert not _close_window(mw)
    assert len(domande) == 1 and "doc.pdf" in domande[0]
    assert mw._doc_model.page_count == 2
    assert mw._thread.isRunning(), "una chiusura annullata non ferma il worker"


def test_closing_with_changes_can_discard_them(windows, tmp_path, monkeypatch):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    mw = windows()
    _open(mw, pdf)
    mw._delete_page()
    _answer(monkeypatch, QMessageBox.StandardButton.Discard)

    assert _close_window(mw)
    with pymupdf.open(pdf) as doc:
        assert doc.page_count == 3, "«Non salvare» non scrive niente"


def test_closing_with_changes_can_save_them(windows, tmp_path, monkeypatch):
    """«Salva» goes through Ctrl+S: it writes to the open file, without asking where."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    mw = windows()
    _open(mw, pdf)
    mw._delete_page()
    _answer(monkeypatch, QMessageBox.StandardButton.Save)

    def _never(*a, **k):
        raise AssertionError("Salva non deve chiedere il nome del file")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(_never))

    assert _close_window(mw)
    with pymupdf.open(pdf) as doc:
        assert doc.page_count == 2


def test_a_failed_save_keeps_the_window_open(windows, tmp_path, monkeypatch):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    mw = windows()
    _open(mw, pdf)
    mw._delete_page()
    _answer(monkeypatch, QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    def _guasto(*a, **k):
        raise OSError("disco pieno")

    monkeypatch.setattr(plico.main_window, "save_as", _guasto)

    assert not _close_window(mw), "il salvataggio è fallito: le modifiche ci sono ancora"
    assert mw.is_modified()


def test_save_as_moves_the_target_and_keeps_the_undo_history(windows, tmp_path, monkeypatch):
    """After «Salva con nome» Ctrl+S writes there, and undo still works."""
    pdf = str(tmp_path / "doc.pdf")
    altro = str(tmp_path / "altro.pdf")
    _make_pdf(pdf, pages=3)
    mw = windows()
    _open(mw, pdf)
    mw._delete_page()

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (altro, "")))
    assert mw._save_file_as()
    assert not mw.is_modified()
    assert mw.windowTitle() == "altro.pdf[*]"
    assert mw._undo_stack.canUndo(), "le sorgenti non sono cambiate: l'annulla resta"

    mw._thumb_bar.set_current_row(0)
    mw._delete_page()
    assert mw.is_modified()
    assert mw._save_file()
    with pymupdf.open(altro) as doc:
        assert doc.page_count == 1
    with pymupdf.open(pdf) as doc:
        assert doc.page_count == 3, "Ctrl+S scrive sull'ultimo «Salva con nome»"


def test_a_merge_counts_as_a_change(windows, tmp_path, monkeypatch):
    """Unire does not go through the undo stack, but must be saved all the same."""
    pdf = str(tmp_path / "doc.pdf")
    second = str(tmp_path / "secondo.pdf")
    _make_pdf(pdf, pages=2)
    _make_pdf(second, pages=2)
    mw = windows()
    _open(mw, pdf)
    mw.merge_path(second)
    domande = _answer(monkeypatch, QMessageBox.StandardButton.Cancel)

    assert mw.is_modified() and mw.isWindowModified()
    assert not _close_window(mw)
    assert len(domande) == 1


def test_opening_another_file_asks_first(windows, tmp_path, monkeypatch):
    """The question comes before the dialog: Annulla does not even show the file picker."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    mw = windows()
    _open(mw, pdf)
    mw._delete_page()
    domande = _answer(monkeypatch, QMessageBox.StandardButton.Cancel)

    def _never(*a, **k):
        raise AssertionError("con Annulla il dialogo di apertura non deve comparire")

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(_never))

    mw._open_file()
    assert len(domande) == 1
    assert mw._doc_model.page_count == 2


# --------------------------------------------------------------------------- #
#  Encrypted documents: the password dialog
# --------------------------------------------------------------------------- #


def _encrypted_pdf(
    path: str, password: str = "segreta", pages: int = 2, text: str = "Pagina"
) -> str:
    """*pages* pages with something on them, locked with *password*."""
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"{text} {i + 1}", fontsize=24)
    doc.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="proprietario",
        user_pw=password,
    )
    doc.close()
    return path


def _answers(monkeypatch, *replies: str) -> list[str]:
    """Answer the password dialog with *replies*, and return the labels shown."""
    asked: list[str] = []
    queue = iter(replies)

    def get_text(parent, title, label, *args, **kwargs):
        asked.append(label)
        return (next(queue), True)

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(get_text))
    return asked


def test_opening_an_encrypted_file_asks_for_the_password(windows, tmp_path, monkeypatch):
    """The dialog names the file, and the answer unlocks it everywhere."""
    pdf = _encrypted_pdf(str(tmp_path / "cifrato.pdf"))
    asked = _answers(monkeypatch, "segreta")

    mw = windows()
    assert mw.open_path(pdf) is True

    assert mw._doc_model.page_count == 2
    assert len(asked) == 1 and "cifrato.pdf" in asked[0]
    # The render thread opens the file on its own: it needs the password too.
    assert mw._worker._passwords[pdf] == "segreta"


def test_the_page_of_an_encrypted_file_is_rendered(windows, tmp_path, monkeypatch):
    """A request sent while the file was still locked would stay unanswered.

    The view holds its requests back until the worker has the password; this
    is what checks that the hold is released, because the pixels have to
    arrive on their own.
    """
    pdf = _encrypted_pdf(str(tmp_path / "cifrato.pdf"), pages=1, text="PUBBLICO")
    _answers(monkeypatch, "segreta")

    mw = windows()
    assert mw.open_path(pdf) is True
    _pump()

    pixmap = mw._page_view._canvases[0].label.pixmap()
    assert not pixmap.isNull()
    image = pixmap.toImage()
    assert any(
        image.pixel(x, y) != image.pixel(0, 0)
        for y in range(0, 150, 3)
        for x in range(0, 300, 3)
    ), "la pagina decifrata e` rimasta vuota"


def test_a_wrong_password_is_asked_again(windows, tmp_path, monkeypatch):
    pdf = _encrypted_pdf(str(tmp_path / "cifrato.pdf"))
    asked = _answers(monkeypatch, "sbagliata", "segreta")

    mw = windows()
    assert mw.open_path(pdf) is True

    assert len(asked) == 2
    assert "errata" in asked[1]
    assert mw._doc_model.page_count == 2
    assert mw._worker._passwords[pdf] == "segreta"


def test_giving_up_leaves_the_document_on_screen(windows, tmp_path, monkeypatch):
    """Cancel, and nothing moves: same pages, same "to save" state."""
    plain = str(tmp_path / "normale.pdf")
    _make_pdf(plain, pages=3)
    locked = _encrypted_pdf(str(tmp_path / "cifrato.pdf"))
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False))
    )

    mw = windows()
    _open(mw, plain)
    before = mw.is_modified()

    assert mw.open_path(locked) is False

    assert mw._doc_model.sources == [plain]
    assert mw._doc_model.page_count == 3
    assert len(mw._page_view._canvases) == 3
    assert mw.is_modified() == before


# --------------------------------------------------------------------------- #
#  Merging: it is an undoable command now
# --------------------------------------------------------------------------- #


def test_merging_from_the_window_is_undoable(windows, tmp_path):
    first = str(tmp_path / "primo.pdf")
    second = str(tmp_path / "secondo.pdf")
    _make_pdf(first, pages=2, text="Uno")
    _make_pdf(second, pages=3, text="Due")

    mw = windows()
    _open(mw, first)
    assert not mw.is_modified()

    mw.merge_path(second)
    _pump()

    assert mw._doc_model.page_count == 5
    assert mw._undo_stack.count() == 1
    assert mw._undo_stack.undoText() == "Unisci «secondo.pdf»"
    assert mw.is_modified(), "un'unione non ancora salvata e` una modifica"
    assert mw._status.text().startswith("Unite 3 pagine")

    mw._undo_stack.undo()
    _pump()

    assert mw._doc_model.page_count == 2
    assert mw._doc_model.sources == [first]
    assert not mw.is_modified()

    mw._undo_stack.redo()
    _pump()

    assert mw._doc_model.page_count == 5
    assert len(mw._page_view._canvases) == 5


def test_merging_an_encrypted_file_asks_for_the_password(windows, tmp_path, monkeypatch):
    plain = str(tmp_path / "primo.pdf")
    _make_pdf(plain, pages=1)
    locked = _encrypted_pdf(str(tmp_path / "cifrato.pdf"), pages=1, text="PUBBLICO")
    asked = _answers(monkeypatch, "segreta")

    mw = windows()
    _open(mw, plain)

    mw.merge_path(locked)
    _pump()

    assert len(asked) == 1
    assert mw._doc_model.page_count == 2
    assert mw._worker._passwords[locked] == "segreta"


def test_merging_an_encrypted_file_can_be_cancelled(windows, tmp_path, monkeypatch):
    """No password, no pages — and no undo step either."""
    plain = str(tmp_path / "primo.pdf")
    _make_pdf(plain, pages=1)
    locked = _encrypted_pdf(str(tmp_path / "cifrato.pdf"), pages=1)
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False))
    )

    mw = windows()
    _open(mw, plain)

    mw.merge_path(locked)
    _pump()

    assert mw._doc_model.page_count == 1
    assert mw._undo_stack.count() == 0, "un'unione annullata non e` un passo di undo"
    assert not mw.is_modified()


# --------------------------------------------------------------------- #
#  Text editing: a mode, an editor over the span, a command on Enter
# --------------------------------------------------------------------- #


def _text_tool_on(mw: MainWindow) -> None:
    """Turn the tool on the way the menu does: trigger() checks and emits."""
    mw._text_act.trigger()
    assert mw._page_view.text_mode()


def _click_word(mw: MainWindow, pdf: str, word: str, page: int = 0) -> None:
    canvas = mw._page_view._canvases[page]
    (x0, y0), (x1, y1) = _pixel_for(canvas, pdf, word)
    centre = ((x0 + x1) // 2, (y0 + y1) // 2)
    canvas.label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, centre))


def _press(widget, key: Qt.Key) -> None:
    widget.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def _editing(mw: MainWindow, tmp_path, pages: int = 1) -> str:
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=pages)
    _open(mw, pdf)
    _text_tool_on(mw)
    return pdf


def test_text_tool_is_a_mode_in_the_edit_menu(windows):
    mw = windows()
    entries = {
        action.text().replace("&", ""): action
        for action in mw.menuBar().actions()[1].menu().actions()
    }
    action = entries["Modifica testo"]
    assert action.isCheckable()
    assert action.shortcut().toString() == "Ctrl+Shift+T"


def test_text_tool_and_redaction_exclude_each_other(windows, tmp_path):
    mw = windows()
    _editing(mw, tmp_path)

    mw._redact_act.trigger()
    assert mw._page_view.redaction_mode() and not mw._page_view.text_mode()
    assert not mw._text_act.isChecked()

    mw._text_act.trigger()
    assert mw._page_view.text_mode() and not mw._page_view.redaction_mode()
    assert not mw._redact_act.isChecked()


def test_text_tool_without_a_document_warns(windows, monkeypatch):
    mw = windows()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2]))
    )
    mw._text_act.trigger()
    assert warnings and not mw._text_act.isChecked()


def test_a_click_on_a_line_opens_the_editor_with_its_text(windows, tmp_path):
    mw = windows()
    pdf = _editing(mw, tmp_path)

    _click_word(mw, pdf, "Pagina 1")

    editor = mw._page_view.text_editor()
    assert editor is not None and editor.isVisibleTo(mw._page_view._canvases[0].label)
    assert editor.text() == "Pagina 1"


def test_a_click_on_nothing_opens_nothing_and_says_why(windows, tmp_path):
    """The first version stayed silent here, and the tool looked broken."""
    mw = windows()
    _editing(mw, tmp_path)
    label = mw._page_view._canvases[0].label
    label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, (300, 500)))
    assert mw._page_view.text_editor() is None
    assert "Qui non c'è testo" in mw._status.text()
    # Written on the page itself, not in a tooltip: a tooltip is a separate
    # window, and on Wayland it did not show at all.
    notice = mw._page_view.text_notice()
    assert notice is not None and notice.parent() is label
    assert notice.isVisibleTo(label) and "Qui non c'è testo" in notice.text()


def test_the_notice_goes_away_when_a_line_is_clicked(windows, tmp_path):
    mw = windows()
    pdf = _editing(mw, tmp_path)
    label = mw._page_view._canvases[0].label
    label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, (300, 500)))
    assert mw._page_view.text_notice() is not None

    _click_word(mw, pdf, "Pagina 1")

    assert mw._page_view.text_notice() is None
    assert mw._page_view.text_editor() is not None


def test_a_page_without_text_says_it_is_an_image(windows, tmp_path):
    """A scan is a picture of words: clicking it must not just do nothing."""
    pdf = str(tmp_path / "scansione.pdf")
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(60, 60, 500, 300), fill=(0.8, 0.8, 0.8))
    doc.save(pdf)
    doc.close()
    mw = windows()
    _open(mw, pdf)
    _text_tool_on(mw)

    label = mw._page_view._canvases[0].label
    label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, (100, 100)))

    assert mw._page_view.text_editor() is None
    assert "non contiene testo modificabile" in mw._status.text()
    assert "non contiene testo modificabile" in mw._page_view.text_notice().text()


def test_a_click_just_beside_a_line_still_opens_it(windows, tmp_path):
    """A span's box is tight around the glyphs: a near miss must still count."""
    mw = windows()
    pdf = _editing(mw, tmp_path)
    canvas = mw._page_view._canvases[0]
    (x0, y0), (_x1, y1) = _pixel_for(canvas, pdf, "Pagina 1")
    near = (x0 - max(1, int(canvas.scale * 2)), (y0 + y1) // 2)

    canvas.label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, near))

    editor = mw._page_view.text_editor()
    assert editor is not None and editor.text() == "Pagina 1"


def test_vertical_text_is_refused_at_the_click(windows, tmp_path):
    """No point typing a correction that can never be saved."""
    pdf = str(tmp_path / "verticale.pdf")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((300, 400), "Verticale", fontsize=24, rotate=90)
    doc.save(pdf)
    doc.close()
    mw = windows()
    _open(mw, pdf)
    _text_tool_on(mw)

    _click_word(mw, pdf, "Verticale")

    assert mw._page_view.text_editor() is None
    assert "orizzontale" in mw._status.text()


def test_enter_confirms_one_command_and_the_save_writes_it(windows, tmp_path):
    mw = windows()
    pdf = _editing(mw, tmp_path)
    _click_word(mw, pdf, "Pagina 1")
    editor = mw._page_view.text_editor()
    editor.setText("Pagina uno")

    _press(editor, Qt.Key.Key_Return)

    assert mw._page_view.text_editor() is None
    assert mw._undo_stack.count() == 1
    assert [e.new_text for e in mw._doc_model.pages[0].text_edits] == ["Pagina uno"]
    assert mw.is_modified()

    out = str(tmp_path / "out.pdf")
    save_as(mw._doc_model, out)
    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
    assert "Pagina uno" in text and "Pagina 1" not in text


def test_escape_cancels_and_leaves_the_tool_on(windows, tmp_path):
    """Esc belongs to the editor while it is open, not to the window's shortcut."""
    mw = windows()
    pdf = _editing(mw, tmp_path)
    _click_word(mw, pdf, "Pagina 1")
    editor = mw._page_view.text_editor()
    editor.setText("Pagina uno")

    override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    assert editor.event(override) and override.isAccepted(), "Esc must not reach the window"
    _press(editor, Qt.Key.Key_Escape)

    assert mw._page_view.text_editor() is None
    assert mw._undo_stack.count() == 0
    assert mw._page_view.text_mode()


def test_a_refused_edit_keeps_the_editor_and_says_why(windows, tmp_path):
    mw = windows()
    pdf = _editing(mw, tmp_path)
    _click_word(mw, pdf, "Pagina 1")
    editor = mw._page_view.text_editor()
    too_long = "Pagina " + "molto " * 60
    editor.setText(too_long)

    _press(editor, Qt.Key.Key_Return)

    assert mw._page_view.text_editor() is editor, "the typed text must not be lost"
    assert editor.text() == too_long
    assert "non ci sta" in mw._status.text()
    assert mw._undo_stack.count() == 0


def test_a_click_elsewhere_confirms_the_open_edit(windows, tmp_path):
    mw = windows()
    pdf = _editing(mw, tmp_path)
    _click_word(mw, pdf, "Pagina 1")
    mw._page_view.text_editor().setText("Pagina uno")

    label = mw._page_view._canvases[0].label
    label.mousePressEvent(_event(QEvent.Type.MouseButtonPress, (300, 500)))

    assert mw._page_view.text_editor() is None
    assert mw._undo_stack.count() == 1


def test_leaving_the_tool_confirms_the_open_edit(windows, tmp_path):
    mw = windows()
    pdf = _editing(mw, tmp_path)
    _click_word(mw, pdf, "Pagina 1")
    mw._page_view.text_editor().setText("Pagina uno")

    mw._leave_tools()

    assert not mw._page_view.text_mode()
    assert mw._undo_stack.count() == 1


def test_the_editor_reopens_on_the_edited_text(windows, tmp_path):
    """A second click on the same line edits the correction, not the original."""
    mw = windows()
    pdf = _editing(mw, tmp_path)
    _click_word(mw, pdf, "Pagina 1")
    mw._page_view.text_editor().setText("Pagina uno")
    _press(mw._page_view.text_editor(), Qt.Key.Key_Return)

    _click_word(mw, pdf, "Pagina 1")

    assert mw._page_view.text_editor().text() == "Pagina uno"


def test_the_preview_paints_the_correction_and_undo_takes_it_away(windows, tmp_path):
    mw = windows()
    mw.resize(1000, 700)
    mw.show()
    _editing(mw, tmp_path)
    _pump()
    label = mw._page_view._canvases[0].label
    # The outline is only drawn while the tool is on: compare without it.
    mw._leave_tools()
    before = label.grab().toImage()

    # Straight to the window's slot, as the editor would after Enter.
    span = mw._doc_model.text_span_at(0, 80, 65)
    assert span is not None
    mw._on_text_edited(0, span, "Pagina uno")
    _pump(0.2)
    after = label.grab().toImage()
    assert after != before, "the correction must be visible before saving"

    mw._undo_stack.undo()
    _pump(0.2)
    assert label.grab().toImage() == before


def test_a_rotated_page_edits_the_span_under_the_click(windows, tmp_path):
    mw = windows()
    pdf = _editing(mw, tmp_path)
    mw._thumb_bar.set_current_row(0)
    mw._rotate_cw_clicked()
    _pump()

    _click_word(mw, pdf, "Pagina 1")

    editor = mw._page_view.text_editor()
    assert editor is not None and editor.text() == "Pagina 1"


def test_a_structural_change_closes_the_editor(windows, tmp_path):
    mw = windows()
    pdf = _editing(mw, tmp_path, pages=2)
    _click_word(mw, pdf, "Pagina 1")
    mw._page_view.text_editor().setText("Pagina uno")

    mw._undo_stack.push(DeletePage(mw._doc_model, 1))

    assert mw._page_view.text_editor() is None
    assert mw._doc_model.pages[0].text_edits == [], "nothing confirmed, nothing recorded"


def test_opening_another_document_turns_the_text_tool_off(windows, tmp_path):
    mw = windows()
    _editing(mw, tmp_path)
    other = str(tmp_path / "other.pdf")
    _make_pdf(other, pages=1)

    _open(mw, other)

    assert not mw._page_view.text_mode() and not mw._text_act.isChecked()
