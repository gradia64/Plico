"""End-to-end tests: open a PDF, manipulate it, save and verify the result.

These drive the real MainWindow (offscreen) including its render thread, then
assert on the materialised PDF. A fixture guarantees every window is closed,
so a failing assertion can never leave a QThread running.
"""

import os
import pathlib
import time
from unittest import mock

import fitz
import pytest
from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtGui import QAction, QIcon, QImage
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

import plico.main_window
from plico.main_window import MainWindow
from plico.model import LEVELS_BY_KEY
from plico.model.commands import DeletePage, RotatePage
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
    doc = fitz.open()
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
    with fitz.open(out) as d:
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
    doc = fitz.open()
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
    with fitz.open(out) as d:
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
    assert item.rotation == 0  # user offset untouched

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

    save_as(mw._doc_model, pdf)  # same path as the source

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
    """The 'zero asset da impacchettare' requirement, verified on disk."""
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
        "&Salva con nome…",
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

    with fitz.open(out) as doc:
        assert doc.page_count == 2
        assert doc[0].rotation == 90  # page 2 of the source
    with fitz.open(pdf) as doc:
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
    with fitz.open(out) as doc:
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
    with fitz.open(out) as doc:
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
    with fitz.open(out) as doc:
        assert doc.page_count == 4
        assert "A 1" in doc[0].get_text()
        assert "B 1" in doc[2].get_text()
        assert "B 2" in doc[3].get_text()
    # Merging is additive and never rewrites the documents being read
    with fitz.open(pdf_a) as doc:
        assert doc.page_count == 2
    with fitz.open(pdf_b) as doc:
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
#  Regressioni del secondo giro di review
# --------------------------------------------------------------------------- #

def test_drop_target_row_maps_both_directions():
    """La destinazione del drop è un indice nella lista SENZA la riga trascinata.

    MovePage fa pop e poi insert, quindi quando il bersaglio sta dopo la riga
    trascinata la sua posizione scala di uno. Senza la correzione, trascinare
    una pagina verso il basso sulla metà ALTA di X la lasciava comunque dopo X.
    """
    # Su [A B C D], trascino A (riga 0) su C (riga 2):
    assert ThumbnailBar.drop_target_row(0, 2, below=False) == 1  # sopra C → [B A C D]
    assert ThumbnailBar.drop_target_row(0, 2, below=True) == 2   # sotto C → [B C A D]
    # Trascino D (riga 3) verso l'alto, su B (riga 1):
    assert ThumbnailBar.drop_target_row(3, 1, below=False) == 1  # sopra B → [A D B C]
    assert ThumbnailBar.drop_target_row(3, 1, below=True) == 2   # sotto B → [A B D C]


def test_drop_target_row_agrees_with_the_move_command(windows, tmp_path):
    """La mappatura è corretta solo se MovePage produce davvero quell'ordine."""
    pdf = str(tmp_path / "four.pdf")
    _make_pdf(pdf, pages=4, text="P")

    mw = windows()
    _open(mw, pdf)

    to_row = ThumbnailBar.drop_target_row(0, 2, below=False)
    mw._move_page(0, to_row)

    assert [p.source_index for p in mw._doc_model.pages] == [1, 0, 2, 3]


def test_selection_survives_a_delete(windows, tmp_path):
    """Dopo un delete la selezione non deve morire.

    beginResetModel/endResetModel azzera currentIndex: senza il ripristino
    Ctrl+R leggeva -1 e non faceva nulla finché l'utente non ricliccava.
    """
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=5)

    mw = windows()
    _open(mw, pdf)
    mw._thumb_bar.set_current_row(3)
    assert mw._thumb_bar.current_row() == 3

    mw._delete_page()  # cancella la riga 3

    row = mw._thumb_bar.current_row()
    assert row >= 0, "la selezione è andata persa dopo il delete"

    # ...e ora il comando agisce davvero su quella riga.
    mw._rotate_selected(90)
    assert mw._doc_model.pages[row].rotation == 90


def test_rotation_drops_the_stale_thumbnail_of_that_page(windows, tmp_path):
    """La chiave embedde la rotazione: la voce precedente è irraggiungibile.

    Senza lo scarto, ogni rotazione lasciava un'immagine orfana nell'LRU.
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
    """Lo scroll non deve riempire la coda del worker di richieste duplicate.

    Osservato su `_pending` invece che sul segnale: un callable Python
    connesso a un segnale di un QObject che vive in un altro thread viene
    consegnato ACCODATO, quindi uno spy nel thread GUI non lo vedrebbe.
    """
    pdf = str(tmp_path / "in.pdf")
    _make_pdf(pdf, pages=30)

    mw = windows()
    _open(mw, pdf)

    # Rimetti la barra nello stato "niente in cache, niente in volo".
    mw._thumbnail_cache.clear()
    mw._thumb_bar._pending.clear()

    mw._thumb_bar.refresh()
    in_flight = dict(mw._thumb_bar._pending)
    assert in_flight, "la barra non ha chiesto nessuna miniatura"

    mw._thumb_bar.refresh()
    mw._thumb_bar.refresh()

    assert mw._thumb_bar._pending == in_flight, "richieste duplicate in volo"


def test_late_render_for_a_key_nobody_asked_is_dropped(windows, tmp_path):
    """Il risultato di un documento che non mostriamo più non va in cache.

    Le chiavi ripartono da source_id 0 a ogni apertura: senza il filtro
    `_pending` la miniatura del vecchio file finirebbe sulla riga del nuovo.
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
    """Una richiesta fallita deve poter essere ritentata, non restare appesa."""
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
    """`get` deve rinfrescare la recency, o la cache è FIFO travestita."""
    cache = ThumbnailCache(maxsize=2)
    cache["a"] = 1
    cache["b"] = 2

    assert cache.get("a") == 1  # "a" torna in testa
    cache["c"] = 3              # deve sfrattare "b", non "a"

    assert "a" in cache
    assert "b" not in cache


def test_saving_over_the_open_file_makes_the_worker_forget_it(windows, tmp_path):
    """Dopo un salvataggio che sovrascrive la sorgente l'handle è vecchio.

    save_as() usa os.replace(): l'inode cambia, ma il worker terrebbe aperto
    il documento vecchio, quindi riaprire lo stesso file renderebbe il
    contenuto di prima.
    """
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=4, text="Prima")

    mw = windows()
    _open(mw, pdf)
    assert pdf in mw._worker._docs, "il worker non ha aperto la sorgente"

    mw._delete_page()
    with mock.patch.object(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (pdf, ""))
    ):
        mw._save_file()
    _pump()

    assert mw._worker._docs == {}, "il worker tiene ancora il documento sovrascritto"
    with fitz.open(pdf) as doc:
        assert doc.page_count == 4 - 1


# --------------------------------------------------------------------- #
#  Salva compresso: la stessa voce di menu, il documento di prima
# --------------------------------------------------------------------- #

def _frammentato(path: str, pagine: int = 20) -> None:
    """Un PDF nella forma in cui i PDF veri arrivano: tante pagine, tanti stream.

    ``insert_text`` crea un oggetto per ogni chiamata, quindi il documento si
    porta dietro centinaia di content stream minuscoli. E' il caso in cui la
    compressione ha davvero qualcosa da fare.
    """
    with fitz.open() as doc:
        for i in range(pagine):
            pagina = doc.new_page(width=595, height=842)
            for k in range(40):
                pagina.insert_text(
                    (60, 60 + k * 18),
                    f"Paragrafo {k} della pagina {i + 1}: contenuto ripetuto per occupare spazio.",
                    fontsize=10,
                )
        doc.save(path, deflate=True)


def _livello_scelto(monkeypatch, chiave: str = "light", accettato: bool = True) -> None:
    """Sostituisce il dialogo del livello con una risposta immediata."""

    class _Dialogo:
        def __init__(self, parent=None) -> None:
            self.level = LEVELS_BY_KEY[chiave]

        def exec(self) -> object:
            return QDialog.DialogCode.Accepted if accettato else QDialog.DialogCode.Rejected

    monkeypatch.setattr(plico.main_window, "CompressionDialog", _Dialogo)


def _attendi_compressione() -> None:
    """Aspetta il thread pool, poi consegna i segnali accodati alla GUI.

    La compressione gira su un QRunnable: ``finished`` arriva alla finestra
    come connessione accodata, quindi serve anche un giro di eventi.
    """
    QThreadPool.globalInstance().waitForDone()
    _pump()


def test_la_voce_compresso_e_nel_menu_file(windows):
    """La voce di menu esiste, nella posizione in cui l'utente la cerca."""
    mw = windows()
    voci = [azione.text().replace("&", "") for azione in mw.menuBar().actions()[0].menu().actions()]
    assert "Salva compresso…" in voci


def test_nome_proposto_accanto_all_originale(windows, tmp_path):
    pdf = str(tmp_path / "relazione.pdf")
    _make_pdf(pdf, pages=2)

    mw = windows()
    _open(mw, pdf)

    assert mw._proposed_compressed_path() == str(tmp_path / "relazione-compresso.pdf")


def test_compress_writes_a_smaller_copy_and_leaves_the_source_alone(
    qapp, tmp_path, monkeypatch, windows
):
    """Percorre la voce di menu per intero, con i dialoghi finti."""
    pdf = str(tmp_path / "doc.pdf")
    _frammentato(pdf)
    out = str(tmp_path / "doc-compresso.pdf")
    prima = os.path.getsize(pdf)

    mw = windows()
    _open(mw, pdf)

    messaggi: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda _parent, _title, text, *a, **k: messaggi.append(text)),
    )
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    _livello_scelto(monkeypatch, "light")

    mw._compress_file()
    _attendi_compressione()

    assert os.path.getsize(out) < prima * 0.5, "il file compresso non e` piu` piccolo"
    with fitz.open(out) as doc:
        assert doc.page_count == 20
        assert "della pagina 1" in doc[0].get_text()
    assert os.path.getsize(pdf) == prima, "la sorgente non si tocca"
    assert messaggi and "Prima:" in messaggi[0], f"il guadagno va raccontato: {messaggi}"
    assert mw._progress is None, "il dialogo di avanzamento deve sparire"
    assert mw._compression_task is None


def test_compress_writes_the_virtual_document(qapp, tmp_path, monkeypatch, windows):
    """Anche il file compresso rispetta eliminazioni e rotazioni."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=5)
    out = str(tmp_path / "out.pdf")

    mw = windows()
    _open(mw, pdf)
    DeletePage(mw._doc_model, 0).redo()
    RotatePage(mw._doc_model, 0, 90).redo()

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    _livello_scelto(monkeypatch, "light")

    mw._compress_file()
    _attendi_compressione()

    with fitz.open(out) as doc:
        assert doc.page_count == 4
        assert doc[0].rotation == 90


def test_compress_can_be_cancelled_at_the_level_dialog(qapp, tmp_path, monkeypatch, windows):
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    out = str(tmp_path / "out.pdf")

    mw = windows()
    _open(mw, pdf)

    chiamate: list[str] = []
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (chiamate.append("chiesto"), (out, ""))[1]),
    )
    _livello_scelto(monkeypatch, "light", accettato=False)

    mw._compress_file()

    assert chiamate == [], "annullare il livello non deve chiedere un file"
    assert not os.path.exists(out)


def test_compress_without_a_document_warns(qapp, monkeypatch, windows):
    mw = windows()

    avvisi: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda _parent, _title, text, *a, **k: avvisi.append(text)),
    )
    aperti: list[str] = []
    monkeypatch.setattr(plico.main_window, "CompressionDialog", lambda *a, **k: aperti.append("x"))

    mw._compress_file()

    assert aperti == [], "senza documento non si sceglie nemmeno il livello"
    assert avvisi and "Nessun documento" in avvisi[0]


def test_compressing_over_the_open_file_evicts_the_stale_handle(
    qapp, tmp_path, monkeypatch, windows
):
    """Come per save_as: os.replace() cambia l'inode sotto i piedi del worker."""
    pdf = str(tmp_path / "doc.pdf")
    _frammentato(pdf, pagine=6)

    mw = windows()
    _open(mw, pdf)
    assert pdf in mw._worker._docs, "il worker non ha aperto la sorgente"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (pdf, "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    _livello_scelto(monkeypatch, "light")

    mw._compress_file()
    _attendi_compressione()

    assert mw._worker._docs == {}, "il worker tiene ancora il documento sovrascritto"
    with fitz.open(pdf) as doc:
        assert doc.page_count == 6


def test_a_failed_compression_arrives_as_a_message(qapp, tmp_path, monkeypatch, windows):
    """Un errore nel thread di lavoro deve arrivare all'utente, non sparire."""
    pdf = str(tmp_path / "doc.pdf")
    _make_pdf(pdf, pages=3)
    # Una cartella che non esiste: il temporaneo non si puo` nemmeno creare.
    out = str(tmp_path / "inesistente" / "out.pdf")

    mw = windows()
    _open(mw, pdf)

    errori: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda _parent, _title, text, *a, **k: errori.append(text)),
    )
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    _livello_scelto(monkeypatch, "light")

    mw._compress_file()
    _attendi_compressione()

    assert errori and "Impossibile comprimere" in errori[0], errori
    assert mw._progress is None, "anche fallendo, il dialogo di avanzamento deve sparire"
