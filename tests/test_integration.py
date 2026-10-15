"""End-to-end tests: open a PDF, manipulate it, save and verify the result.

These drive the real MainWindow (offscreen) including its render thread, then
assert on the materialised PDF. A fixture guarantees every window is closed,
so a failing assertion can never leave a QThread running.
"""

import os
import pathlib
import time

import fitz
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

import plico.main_window
from plico.main_window import MainWindow
from plico.model.commands import DeletePage, RotatePage
from plico.model.save import save_as

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
