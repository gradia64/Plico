"""MainWindow — orchestrates model, worker, commands, and views."""

import os
from collections.abc import Callable

from PySide6.QtCore import QMetaObject, QSettings, Qt, QThread
from PySide6.QtGui import QAction, QIcon, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QUndoView,
    QVBoxLayout,
    QWidget,
)

from .model import (
    DeletePage,
    DocumentModel,
    MovePage,
    RotatePage,
    extract_pages,
    parse_page_ranges,
    save_as,
)
from .rendering import RenderWorker
from .widgets.page_view import PageView
from .widgets.thumbnail_bar import ThumbnailBar, ThumbnailCache


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Plico")
        self.resize(1000, 700)

        # --- model ---
        self._doc_model = DocumentModel()
        # The PageView and ThumbnailBar observe the model themselves, so no
        # central "document changed" relay is needed here.

        # --- undo stack ---
        self._undo_stack = QUndoStack(self)

        # --- render worker thread ---
        # The QThread is deliberately NOT parented to this window (or any
        # widget): Qt aborts the process if a QThread is destroyed while
        # still running, and a parented thread would be deleted by
        # ~QWidget right along with the window.
        self._thread = QThread()
        self._worker = RenderWorker()  # no parent → moveToThread is valid
        self._worker.moveToThread(self._thread)
        self._worker.opened.connect(self._on_worker_opened)
        self._worker.rendered.connect(self._on_rendered)
        # Delete the worker in its own thread once the event loop has
        # exited (QEventLoop flushes deferred deletes on exit).
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

        # Stop the thread on ANY application exit path, not only when the
        # window is closed: a QThread destroyed while still running aborts
        # the whole process. Qt drops this connection automatically if this
        # window is destroyed first.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown_worker)

        # --- caches ---
        self._thumbnail_cache = ThumbnailCache(maxsize=60)

        # --- central widget (PageView handles its own rendering) ---
        self._page_view = PageView(self._worker, self._doc_model)
        self._status = QLabel(self.tr("Pronto"))

        # Layout: page view in a container with status bar
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._page_view)
        layout.addWidget(self._status)
        self.setCentralWidget(central)

        # --- thumbnail bar ---
        self._thumb_bar = ThumbnailBar(self._doc_model, self._worker, self._thumbnail_cache)
        # The bar never reorders itself: it reports the intent and we push
        # an undoable command.
        self._thumb_bar.move_requested.connect(self._move_page)
        self._thumb_bar.page_selected.connect(self._on_page_selected)
        dock = QDockWidget(self.tr("Miniature"), self)
        dock.setObjectName("thumbnail_dock")
        dock.setWidget(self._thumb_bar)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        # --- undo dock (dev tool) ---
        undo_dock = QDockWidget(self.tr("Storico azioni"), self)
        undo_dock.setObjectName("undo_dock")
        self._undo_view = QUndoView(self._undo_stack)
        undo_dock.setWidget(self._undo_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, undo_dock)

        # --- menus / toolbar ---
        self._setup_menus()
        self._setup_toolbar()

        # --- state ---
        self._sizes_pt: list[tuple[float, float]] = []
        self._current_page_index = 0

        # --- restore the previous session's UI state ---
        self._restore_settings()

    # ------------------------------------------------------------------ #
    #  Menus & Toolbar
    # ------------------------------------------------------------------ #

    def _act(
        self, text: str, icon_name: str, shortcut: str, slot: Callable[..., object]
    ) -> QAction:
        """Build an action carrying a Breeze theme icon.

        No icon assets are bundled: KDE ships the theme, and on a desktop
        without it ``fromTheme`` returns a null icon which we simply skip
        rather than showing an empty square.
        """
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        icon = QIcon.fromTheme(icon_name)
        if not icon.isNull():
            action.setIcon(icon)
        action.triggered.connect(slot)
        return action

    def _setup_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu(self.tr("&File"))

        file_menu.addAction(
            self._act(self.tr("A&pri…"), "document-open", "Ctrl+O", self._open_file)
        )
        file_menu.addAction(
            self._act(
                self.tr("&Salva con nome…"),
                "document-save-as",
                "Ctrl+Shift+S",
                self._save_file,
            )
        )
        file_menu.addAction(
            self._act(
                self.tr("&Estrai pagine…"),
                "document-export",
                "Ctrl+E",
                self._extract_pages,
            )
        )
        file_menu.addSeparator()
        file_menu.addAction(self._act(self.tr("&Esci"), "application-exit", "Ctrl+Q", self.close))

        edit_menu = menubar.addMenu(self.tr("&Modifica"))

        undo_act = self._undo_stack.createUndoAction(self, self.tr("Annulla"))
        undo_act.setShortcut("Ctrl+Z")
        undo_act.setIcon(QIcon.fromTheme("edit-undo"))
        edit_menu.addAction(undo_act)

        redo_act = self._undo_stack.createRedoAction(self, self.tr("Ripeti"))
        redo_act.setShortcut("Ctrl+Y")
        redo_act.setIcon(QIcon.fromTheme("edit-redo"))
        edit_menu.addAction(redo_act)

        edit_menu.addSeparator()

        self._delete_act = self._act(
            self.tr("Elimina pagina"), "edit-delete", "Del", self._delete_page
        )
        edit_menu.addAction(self._delete_act)

        view_menu = menubar.addMenu(self.tr("&Visualizza"))

        self._fit_act = self._act(
            self.tr("Adatta alla &larghezza"),
            "zoom-fit-best",
            "Ctrl+0",
            self._page_view.set_zoom_fit_width,
        )
        view_menu.addAction(self._fit_act)

        self._zoom_in_act = self._act(
            self.tr("Zoom a&vanti"), "zoom-in", "Ctrl++", self._page_view.zoom_in
        )
        view_menu.addAction(self._zoom_in_act)

        self._zoom_out_act = self._act(
            self.tr("Zoom &indietro"), "zoom-out", "Ctrl+-", self._page_view.zoom_out
        )
        view_menu.addAction(self._zoom_out_act)

    def _setup_toolbar(self) -> None:
        toolbar = QToolBar(self.tr("Strumenti"))
        # saveState()/restoreState() identify docks and toolbars by
        # objectName, and warn without one.
        toolbar.setObjectName("main_toolbar")
        self.addToolBar(toolbar)

        self._rotate_cw = self._act(
            self.tr("Ruota a destra"),
            "object-rotate-right",
            "Ctrl+R",
            self._rotate_cw_clicked,
        )
        self._rotate_cw.setToolTip(self.tr("Ruota a destra 90°"))
        toolbar.addAction(self._rotate_cw)

        self._rotate_ccw = self._act(
            self.tr("Ruota a sinistra"),
            "object-rotate-left",
            "Ctrl+Shift+R",
            self._rotate_ccw_clicked,
        )
        self._rotate_ccw.setToolTip(self.tr("Ruota a sinistra 90°"))
        toolbar.addAction(self._rotate_ccw)

        toolbar.addSeparator()
        toolbar.addAction(self._zoom_out_act)
        toolbar.addAction(self._zoom_in_act)
        toolbar.addAction(self._fit_act)

    # ------------------------------------------------------------------ #
    #  File operations
    # ------------------------------------------------------------------ #

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Apri PDF"),
            str(os.path.expanduser("~")),
            self.tr("File PDF (*.pdf)"),
        )
        if not path:
            return
        try:
            self.open_document(path)
        # A damaged/encrypted/unsupported PDF can raise a wide range of
        # exceptions from PyMuPDF; at this GUI boundary the correct
        # behaviour is to report it, never to crash the editor.
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self, self.tr("Errore"), self.tr("Impossibile aprire:\n{0}").format(e)
            )

    def open_document(self, path: str) -> None:
        """Open *path*, resetting every view and cache first.

        The caches matter: render keys are built from ``source_index``, so
        without flushing them a second document would be served the first
        document's pixmaps.
        """
        self._undo_stack.clear()
        self._page_view.reset()
        self._thumbnail_cache.clear()
        self._sizes_pt = []

        self._doc_model.open(path)
        self._worker.open_requested.emit(path)
        self._current_page_index = 0
        self._status.setText(self.tr("Aperto: {0}").format(path))

    def _save_file(self) -> None:
        if self._doc_model.path is None:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Salva con nome"),
            str(self._doc_model.path),
            self.tr("File PDF (*.pdf)"),
        )
        if not path:
            return
        try:
            save_as(self._doc_model, path)
            self._status.setText(self.tr("Salvato: {0}").format(path))
        # Same reasoning as _open_file: a failed write (permissions, full
        # disk, malformed source) must surface as a dialog, not a traceback.
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self, self.tr("Errore"), self.tr("Impossibile salvare:\n{0}").format(e)
            )

    def _extract_pages(self) -> None:
        """Split: write a typed page selection to a separate file.

        The open document is never modified -- this only materialises a
        subset, so it needs no undo entry.
        """
        if self._doc_model.path is None:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return

        spec, accepted = QInputDialog.getText(
            self,
            self.tr("Estrai pagine"),
            self.tr("Pagine da estrarre (es. 1-3,5,8):"),
        )
        if not accepted or not spec.strip():
            return

        try:
            indices = parse_page_ranges(spec, self._doc_model.page_count)
        except ValueError as e:
            # The message is written for the user, so show it verbatim.
            QMessageBox.warning(self, self.tr("Attenzione"), str(e))
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Estrai pagine"),
            str(os.path.expanduser("~")),
            self.tr("File PDF (*.pdf)"),
        )
        if not path:
            return

        try:
            extract_pages(self._doc_model, path, indices)
            self._status.setText(self.tr("Estratte {0} pagine in: {1}").format(len(indices), path))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self,
                self.tr("Errore"),
                self.tr("Impossibile estrarre:\n{0}").format(e),
            )

    # ------------------------------------------------------------------ #
    #  Worker signals
    # ------------------------------------------------------------------ #

    def _on_worker_opened(self, path: str, sizes_pt: list) -> None:
        """Worker has opened the PDF and reports page sizes in points.

        Any render requested before this point was dropped by the worker
        (it had no document yet), so this is where thumbnails are asked for.
        """
        self._sizes_pt = sizes_pt
        self._page_view.set_pages(self._doc_model.pages, sizes_pt)
        self._thumb_bar.refresh()

    def _on_rendered(self, key: tuple, image) -> None:
        """Route rendered images by role tag.

        PageView receives every render too, but handles only "page" keys;
        this slot handles only "thumb" keys. Tagging beats guessing from the
        tuple length.
        """
        if not key or key[0] != "thumb":
            return
        dpr = key[4]
        if dpr:
            image.setDevicePixelRatio(dpr)  # crisp on HiDPI
        self._thumbnail_cache[key] = image
        # Repaint just the row that just got its picture.
        row = self._thumb_bar._model.index_for_source(key[1])
        if row.isValid():
            self._thumb_bar._model.dataChanged.emit(row, row, [Qt.ItemDataRole.DecorationRole])

    # ------------------------------------------------------------------ #
    #  Page operations (undo commands)
    # ------------------------------------------------------------------ #

    def _on_doc_changed(self) -> None:
        """Kept for explicit callers; the views observe the model already."""
        if self._doc_model.page_count == 0:
            self._page_view.clear()
            return
        self._thumb_bar.refresh()

    def _on_page_selected(self, row: int) -> None:
        """Keep the main view aligned with the thumbnail selection."""
        self._page_view.ensure_page_visible(row)

    def _rotate_cw_clicked(self) -> None:
        self._rotate_selected(90)

    def _rotate_ccw_clicked(self) -> None:
        self._rotate_selected(-90)

    def _rotate_selected(self, delta: int) -> None:
        """Rotate the selected page.

        RotatePage emits ``page_changed``, and the view reacts by
        re-measuring — a rotation changes one page in place, so the page
        list keeps its shape and nothing needs rebuilding here.
        """
        idx = self._thumb_bar.current_row()
        if idx < 0 or idx >= self._doc_model.page_count:
            return
        self._undo_stack.push(RotatePage(self._doc_model, idx, delta))
        self._thumb_bar.refresh()

    def _delete_page(self) -> None:
        idx = self._thumb_bar.current_row()
        if idx < 0 or idx >= self._doc_model.page_count:
            return
        # DeletePage emits ``changed``; the view rebuilds itself from the
        # shorter page list, reusing the surviving pages' pixmaps.
        self._undo_stack.push(DeletePage(self._doc_model, idx))

    def _move_page(self, from_row: int, to_row: int) -> None:
        """Reordering requested by the thumbnail bar (drag & drop)."""
        if from_row == to_row:
            return
        if not (0 <= from_row < self._doc_model.page_count):
            return
        if not (0 <= to_row < self._doc_model.page_count):
            return
        # MovePage emits ``changed``; the view reorders itself.
        self._undo_stack.push(MovePage(self._doc_model, from_row, to_row))
        self._thumb_bar.set_current_row(to_row)

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    def closeEvent(self, event) -> None:
        """Persist the UI state and shut the worker thread down cleanly."""
        self._save_settings()
        self.shutdown_worker()
        event.accept()

    # ------------------------------------------------------------------ #
    #  Settings (QSettings: window geometry, dock/toolbar layout, zoom)
    # ------------------------------------------------------------------ #

    def _settings(self) -> QSettings:
        """Explicit org/app: no reliance on global QApplication state."""
        return QSettings("Plico", "plico")

    def _restore_settings(self) -> None:
        s = self._settings()
        geometry = s.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = s.value("window/state")
        if state is not None:
            self.restoreState(state)
        raw = s.value("view/zoom", 0.0)
        try:
            zoom = float(raw) if isinstance(raw, (int, float, str)) else 0.0
        except (TypeError, ValueError):
            zoom = 0.0
        if zoom > 0:
            self._page_view.set_zoom(zoom)

    def _save_settings(self) -> None:
        s = self._settings()
        s.setValue("window/geometry", self.saveGeometry())
        s.setValue("window/state", self.saveState())
        s.setValue("view/zoom", self._page_view.zoom())

    def shutdown_worker(self) -> None:
        """Stop the render thread deterministically.

        Order matters:
          1. Close the PDF *inside* the worker thread. A BlockingQueued
             connection waits for the worker's event loop to run the slot,
             so it cannot race an in-flight render (calling shutdown()
             directly from the GUI thread would touch the fitz document
             from the wrong thread).
          2. Quit the loop and wait, so the thread is no longer running
             when the window -- and this object -- are destroyed.
        """
        if not self._thread.isRunning():
            return
        QMetaObject.invokeMethod(
            self._worker, "shutdown", Qt.ConnectionType.BlockingQueuedConnection
        )
        self._thread.quit()
        if not self._thread.wait(5000):
            # A render is wedged; do not let a running thread outlive us.
            self._thread.terminate()
            self._thread.wait(2000)
