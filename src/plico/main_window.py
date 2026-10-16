"""MainWindow — orchestrates model, worker, commands, and views."""

import os
from collections.abc import Callable

from PySide6.QtCore import QMetaObject, QSettings, Qt, QThread, QThreadPool
from PySide6.QtGui import QAction, QIcon, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QToolBar,
    QUndoView,
    QVBoxLayout,
    QWidget,
)

from .model import (
    AddRedaction,
    CompressionLevel,
    CompressionResult,
    DeletePage,
    DocumentModel,
    MovePage,
    RedactionRect,
    RemoveRedaction,
    RotatePage,
    SetFieldValue,
    extract_pages,
    parse_page_ranges,
    save_as,
)
from .rendering import RenderWorker
from .widgets.compress import CompressionDialog, CompressionTask, format_size
from .widgets.form_panel import FormPanel
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
        # No rendered.connect here: the PageView and the ThumbnailBar each
        # subscribe to what they own and route by the key's role tag.
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

        # --- compressione: gira nel thread pool, non in quello dei render ---
        self._compression_task: CompressionTask | None = None
        self._progress: QProgressDialog | None = None
        self._compression_path = ""
        self._compression_overwritten: list[str] = []

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
        # The same route the bar's drag & drop takes: the view reports the
        # gesture, the window pushes the undoable command.
        self._page_view.redaction_added.connect(self._add_redaction)
        self._page_view.redaction_removed.connect(self._remove_redaction)
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

        # --- form dock ---
        self._form_panel = FormPanel()
        self._form_panel.value_changed.connect(self._on_field_edited)
        # The same route redactions take: the view reports where the user
        # pointed, and the window decides what to do about it.
        self._page_view.field_clicked.connect(self._on_field_clicked)
        self._form_dock = QDockWidget(self.tr("Modulo"), self)
        self._form_dock.setObjectName("form_dock")
        self._form_dock.setWidget(self._form_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._form_dock)

        # --- menus / toolbar ---
        self._setup_menus()
        self._setup_toolbar()

        # --- state ---
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
                self.tr("&Unisci PDF…"),
                "document-open-recent",
                "Ctrl+Shift+M",
                self._merge_file,
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
        file_menu.addAction(
            self._act(
                self.tr("Salva &compresso…"),
                "archive-insert",
                "Ctrl+Shift+C",
                self._compress_file,
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

        edit_menu.addSeparator()

        self._redact_act = self._act(
            self.tr("&Redazione"), "edit-cut", "Ctrl+Shift+X", self._on_redaction_toggled
        )
        # A mode, not a one-shot command: it stays on while the user works
        # through a page, and the marks it collects are only painted — they
        # are burned into the PDF when the document is saved.
        self._redact_act.setCheckable(True)
        self._redact_act.setToolTip(
            self.tr(
                "Trascina sui dati da eliminare; un clic su una zona la annulla.\n"
                "Le redazioni diventano definitive solo al salvataggio."
            )
        )
        edit_menu.addAction(self._redact_act)

        # Esc leaves the tool whatever has focus. It sets the check state
        # directly: setChecked() does not emit `triggered`, so the mode is
        # turned off explicitly instead of through the menu slot.
        self._escape_act = QAction(self)
        self._escape_act.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        self._escape_act.triggered.connect(self._leave_redaction)
        self.addAction(self._escape_act)

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
        self.open_path(path)

    def open_path(self, path: str) -> bool:
        """Open *path*, reporting any failure instead of propagating it.

        Shared by the "Apri" action and by the command line, so a document
        handed over by the desktop entry fails exactly like one chosen from
        the dialog. Returns whether the document is now open.
        """
        try:
            self.open_document(path)
        # A damaged/encrypted/unsupported PDF can raise a wide range of
        # exceptions from PyMuPDF; at this GUI boundary the correct
        # behaviour is to report it, never to crash the editor.
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self, self.tr("Errore"), self.tr("Impossibile aprire:\n{0}").format(e)
            )
            return False
        return True

    def open_document(self, path: str) -> None:
        """Open *path*, resetting every view and cache first.

        The caches matter: render keys are built from ``source_index``, so
        without flushing them a second document would be served the first
        document's pixmaps.
        """
        self._undo_stack.clear()
        self._page_view.reset()
        self._thumbnail_cache.clear()

        self._doc_model.open(path)
        # The model emits ``changed`` and the views rebuild from it. Page
        # sizes come from the model too, so the render thread needs no
        # round-trip before the layout is correct.
        self._current_page_index = 0
        # Explicit: a fresh document starts at page 1. (The model reset
        # clears the selection, and the bar would otherwise restore the
        # previous document's row.)
        self._thumb_bar.set_current_row(0)
        # Never carry the redaction tool over into another document: the next
        # drag would mark a page the user has not even looked at.
        self._redact_act.setChecked(False)
        self._on_redaction_toggled(False)
        self._refresh_form_panel(0)
        self._status.setText(self.tr("Aperto: {0}").format(path))

    def _merge_file(self) -> None:
        """Unire: append every page of another PDF to the document.

        Nothing is copied or rewritten -- the model just grows a second
        source and the new pages point into it, exactly like the original
        ones. Undo is not involved: this is an additive file operation.
        """
        if not self._doc_model.sources:
            QMessageBox.warning(
                self, self.tr("Attenzione"), self.tr("Nessun documento aperto.")
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Unisci PDF"),
            str(os.path.expanduser("~")),
            self.tr("File PDF (*.pdf)"),
        )
        if not path:
            return

        self.merge_path(path)

    def merge_path(self, path: str) -> None:
        """Append every page of *path*, reporting failures instead of raising.

        Also reachable from the command line, where several arguments mean
        "open the first and append the rest".
        """
        try:
            added = self._doc_model.append_document(path)
        # Same reasoning as open_path: a damaged PDF is reported, never fatal.
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self,
                self.tr("Errore"),
                self.tr("Impossibile unire:\n{0}").format(e),
            )
            return

        if added == 0:
            QMessageBox.warning(
                self,
                self.tr("Attenzione"),
                self.tr("Il documento scelto non contiene pagine."),
            )
            return

        # Jump to the first merged page: the whole point of the gesture is to
        # check what was just appended, and lazily-rendered pages only appear
        # once they are on screen.
        first_new = self._doc_model.page_count - added
        self._page_view.ensure_page_visible(first_new)
        self._thumb_bar.set_current_row(first_new)
        self._status.setText(self.tr("Unite {0} pagine da: {1}").format(added, path))

    def _save_file(self) -> None:
        if not self._doc_model.sources:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Salva con nome"),
            self._doc_model.path or "",
            self.tr("File PDF (*.pdf)"),
        )
        if not path:
            return
        overwritten = self._sources_overwritten_by(path)
        try:
            save_as(self._doc_model, path)
            # save_as() replaces the file with os.replace(), which swaps the
            # inode: the worker still holds the OLD document under that path.
            # Without this, re-opening the file would render the pre-save
            # content from the stale handle.
            for source in overwritten:
                self._worker.evict_requested.emit(source)
            self._status.setText(self.tr("Salvato: {0}").format(path))
        # Same reasoning as _open_file: a failed write (permissions, full
        # disk, malformed source) must surface as a dialog, not a traceback.
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self, self.tr("Errore"), self.tr("Impossibile salvare:\n{0}").format(e)
            )

    def _sources_overwritten_by(self, target: str) -> list[str]:
        """Sources a save to *target* would replace (compared by inode).

        Mirrors the overwrite test inside save.py, so the two can never
        disagree about what counts as "saving over a file we are reading".
        """
        if not os.path.exists(target):
            return []
        sources = []
        for source in self._doc_model.sources:
            try:
                if os.path.exists(source) and os.path.samefile(target, source):
                    sources.append(source)
            except OSError:
                continue
        return sources

    # ------------------------------------------------------------------ #
    #  Compressione
    # ------------------------------------------------------------------ #

    def _compress_file(self) -> None:
        """Scrive una copia compressa del documento materializzato.

        Non e` un'alternativa a "Salva con nome": il contenuto e` lo stesso,
        solo piu` piccolo -- eliminazioni, riordini e rotazioni compresi. I
        PDF di partenza non vengono toccati.
        """
        if not self._doc_model.sources:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return

        scelta = CompressionDialog(self)
        if scelta.exec() != QDialog.DialogCode.Accepted:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Salva compresso"),
            self._proposed_compressed_path(),
            self.tr("File PDF (*.pdf)"),
        )
        if not path:
            return
        self._start_compression(path, scelta.level)

    def _proposed_compressed_path(self) -> str:
        """``documento.pdf`` -> ``documento-compresso.pdf``."""
        origine = self._doc_model.path or ""
        radice, estensione = os.path.splitext(origine)
        if not radice:
            return str(os.path.expanduser("~"))
        return f"{radice}-compresso{estensione or '.pdf'}"

    def _start_compression(self, path: str, level: CompressionLevel) -> None:
        # Va calcolato PRIMA di scrivere: comprimendo sopra un sorgente il
        # file cambia inode, e dopo il confronto non riconoscerebbe piu`
        # l'originale.
        self._compression_overwritten = self._sources_overwritten_by(path)
        self._compression_path = path

        progresso = QProgressDialog(self)
        progresso.setWindowTitle(self.tr("Salva compresso"))
        progresso.setLabelText(self.tr("Compressione in corso…"))
        progresso.setRange(0, 100)
        # Il lavoro non e` interrompibile a meta`: meglio non offrire un
        # pulsante che non potrebbe mantenere quello che promette.
        progresso.setCancelButton(None)
        progresso.setWindowModality(Qt.WindowModality.WindowModal)
        progresso.setMinimumDuration(0)
        progresso.setAutoClose(False)
        progresso.setAutoReset(False)
        progresso.setValue(0)
        self._progress = progresso

        attivita = CompressionTask(self._doc_model, path, level)
        attivita.signals.progress.connect(progresso.setValue)
        attivita.signals.finished.connect(self._on_compression_finished)
        attivita.signals.failed.connect(self._on_compression_failed)
        # Finche` il pool non ha finito qualcuno deve tenere vivo il task.
        self._compression_task = attivita
        QThreadPool.globalInstance().start(attivita)

    def _on_compression_finished(self, result: CompressionResult) -> None:
        self._close_progress()
        path = self._compression_path

        # Come in _save_file: os.replace() cambia l'inode, quindi il worker
        # terrebbe aperto il documento vecchio sotto quel percorso.
        for source in self._compression_overwritten:
            self._worker.evict_requested.emit(source)
        self._status.setText(self.tr("Compresso: {0}").format(path))

        if result.shrank:
            QMessageBox.information(
                self,
                self.tr("Salva compresso"),
                self.tr(
                    "Scritto:\n{0}\n\nPrima: {1}\nDopo: {2}\nRisparmiato: {3} ({4}%)"
                ).format(
                    path,
                    format_size(result.source_size),
                    format_size(result.output_size),
                    format_size(result.saved_bytes),
                    result.percent_saved,
                ),
            )
        else:
            QMessageBox.information(
                self,
                self.tr("Salva compresso"),
                self.tr(
                    "Scritto:\n{0}\n\nQuesto file non aveva niente da guadagnare: "
                    "e` rimasto di {1}."
                ).format(path, format_size(result.source_size)),
            )

    def _on_compression_failed(self, messaggio: str) -> None:
        self._close_progress()
        QMessageBox.critical(
            self,
            self.tr("Errore"),
            self.tr("Impossibile comprimere:\n{0}").format(messaggio),
        )

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None
        self._compression_task = None

    def _extract_pages(self) -> None:
        """Split: write a typed page selection to a separate file.

        The open document is never modified -- this only materialises a
        subset, so it needs no undo entry.
        """
        if not self._doc_model.sources:
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
        # The form panel follows the page the user is on: a field belongs to
        # one page, so showing another page's fields would be a lie. The
        # highlight is dropped with the page it belonged to.
        self._page_view.set_selected_field(row, None)
        self._refresh_form_panel(row)

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
        # No manual refresh: RotatePage emits page_changed, which both the
        # view and the thumbnail bar observe (including on undo, where a
        # manual refresh would never be called).
        self._undo_stack.push(RotatePage(self._doc_model, idx, delta))

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
    #  Redazione (undo commands)
    # ------------------------------------------------------------------ #

    def _on_redaction_toggled(self, active: bool) -> None:
        """Enter or leave the redaction tool."""
        if active and not self._doc_model.sources:
            # Nothing to redact. Put the check mark back; setChecked() does
            # not emit `triggered`, so this cannot recurse.
            self._redact_act.setChecked(False)
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return
        self._page_view.set_redaction_mode(active)
        if active:
            self._status.setText(
                self.tr("Redazione: trascina sui dati da eliminare; un clic su una zona la annulla.")
            )
        else:
            self._status.setText(self.tr("Pronto"))

    def _leave_redaction(self) -> None:
        """Esc: leave the tool, leaving the marks where they are."""
        if self._redact_act.isChecked():
            self._redact_act.setChecked(False)
            self._on_redaction_toggled(False)

    def _add_redaction(self, index: int, rect: RedactionRect) -> None:
        """A rectangle was drawn on page *index*."""
        self._undo_stack.push(AddRedaction(self._doc_model, index, rect))

    def _remove_redaction(self, index: int, rect: RedactionRect) -> None:
        """An existing mark was clicked away."""
        self._undo_stack.push(RemoveRedaction(self._doc_model, index, rect))

    # ------------------------------------------------------------------ #
    #  Form fields (an AcroForm field is state of the virtual page too)
    # ------------------------------------------------------------------ #

    def _refresh_form_panel(self, row: int | None = None) -> None:
        """Show the fields of *row*, defaulting to the selected page."""
        if row is None:
            row = self._thumb_bar.current_row()
        if not (0 <= row < len(self._doc_model.pages)):
            self._form_panel.set_page(0, [], {})
            self._page_view.set_selected_field(0, None)
            return
        item = self._doc_model.pages[row]
        self._form_panel.set_page(row, item.form_fields, item.form_values)

    def _on_field_edited(self, name: str, value: str) -> None:
        """The user changed a field in the panel: record it, undoably."""
        row = self._form_panel.page()
        if not (0 <= row < len(self._doc_model.pages)):
            return
        item = self._doc_model.pages[row]
        # What the save would write right now: the model's value, or the one
        # the file already carries when the field was never touched.
        originale = next(
            (campo.value for campo in item.form_fields if campo.name == name), ""
        )
        if item.form_values.get(name, originale) == value:
            return
        self._undo_stack.push(SetFieldValue(self._doc_model, row, name, value))

    def _on_field_clicked(self, row: int, name: str) -> None:
        """A field drawn on the page was clicked: edit it in the panel."""
        self._refresh_form_panel(row)
        # Tell the view which field is selected, so that the page picks it out
        # too: the panel and the page must agree on what is being edited.
        self._page_view.set_selected_field(row, name)
        self._form_panel.select_field(name)
        self._form_dock.show()
        self._form_dock.raise_()

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
        # Una compressione in corso gira nel thread pool e sta scrivendo un
        # file: aspettarla evita che il processo esca a meta` scrittura.
        QThreadPool.globalInstance().waitForDone()
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
