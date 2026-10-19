"""MainWindow — orchestrates model, worker, commands, and views."""

import os
import tempfile
from collections.abc import Callable

from PySide6.QtCore import (
    Q_ARG,
    QEventLoop,
    QMetaObject,
    QSettings,
    Qt,
    QThread,
    QThreadPool,
)
from PySide6.QtGui import QAction, QIcon, QKeySequence, QUndoStack, QWindow
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QToolBar,
    QUndoView,
    QVBoxLayout,
    QWidget,
)

from .model import (
    IMAGE_SUFFIXES,
    AddRedaction,
    AdjustRedaction,
    AppendDocument,
    CompressionOptions,
    CompressionPreview,
    CompressionResult,
    DeletePage,
    DocumentModel,
    EditText,
    MovePage,
    OcrPage,
    OcrWord,
    PageItem,
    PasswordRequired,
    RedactionRect,
    RemoveRedaction,
    RotatePage,
    SetFieldValue,
    SignatureRequest,
    TextSpan,
    extract_pages,
    images_to_pdf,
    is_image,
    is_signed,
    parse_page_ranges,
    save_as,
    save_signed,
    sign_copy,
)
from .rendering import RenderWorker
from .widgets.compress import CompressionDialog, CompressionTask, format_size
from .widgets.find_bar import FindBar
from .widgets.form_panel import FormPanel
from .widgets.ocr import OcrDialog, OcrTask
from .widgets.page_view import PageView
from .widgets.sign import SignatureDialog, SignDialog
from .widgets.toast import Toast


def _host_path(path: str) -> str:
    """The path *path* has outside the Flatpak sandbox, when it has another.

    Without ``--filesystem=home`` every file comes in through the document
    portal and is seen as ``/run/user/<uid>/doc/<id>/name``: fine to read and
    to write, useless as a place to propose in a file dialog, which runs
    outside the sandbox and would open on a directory holding one file. The
    portal records the real path in an extended attribute; anywhere else
    (no portal, an old portal, a plain filesystem) the path is already the
    real one.
    """
    try:
        return os.fsdecode(os.getxattr(path, "user.document-portal.host-path"))
    except (OSError, AttributeError):
        return path
from .widgets.thumbnail_bar import ThumbnailBar, ThumbnailCache


class MainWindow(QMainWindow):
    # The window handle `screenChanged` has already been connected to. None
    # until the window is shown: before that there is no QWindow to watch.
    _screen_handle: QWindow | None = None

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
        # The stack's clean index is what "saved" means for every undoable
        # edit; the title's [*] follows it, including when an undo walks the
        # document back to exactly what was saved.
        self._undo_stack.cleanChanged.connect(self._update_title)
        # Every step can add or remove a redaction, and the title counts the
        # ones still waiting for a save.
        self._undo_stack.indexChanged.connect(self._update_title)

        # --- what "Salva" writes to, and what the undo stack cannot see ---
        # The file a plain Ctrl+S writes: the document opened, or the last
        # "Salva con nome" target. None when nothing is open -- and for a
        # document created from images, which has no file of its own yet.
        self._save_target: str | None = None
        # Where "Salva con nome" proposes to write a document that has no file
        # yet: next to the images it was made from.
        self._save_suggestion: str | None = None
        # Whether the file on disk carries a signature. Cached because the
        # title is rebuilt on every change and reading a PDF is not free; it
        # is refreshed exactly where the file on disk can change: open, save
        # and sign.
        self._signed_on_disk = False
        # The redactions already written into the save target, as
        # (source_id, source_index, rect). The model keeps its marks after a
        # "Salva con nome" -- the sources are untouched -- so "pending" is what
        # the model has minus what the file already has: that is what the
        # title counts and what a save asks to confirm.
        self._saved_marks: frozenset[tuple[int, int, RedactionRect]] = frozenset()
        # The PDFs made from images live here until Plico exits: the worker
        # renders from a path, so they must be real files. Created on first
        # use, removed by shutdown_worker().
        self._scratch: tempfile.TemporaryDirectory | None = None
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

        # --- compression: it runs in the thread pool, not the render one ---
        self._compression_task: CompressionTask | None = None
        self._progress: QProgressDialog | None = None
        self._compression_path = ""
        self._compression_options: CompressionOptions | None = None
        self._compression_overwritten: list[str] = []

        # --- central widget (PageView handles its own rendering) ---
        self._page_view = PageView(self._worker, self._doc_model)
        self._status = QLabel(self.tr("Pronto"))
        # The same message as the status bar, over the page, for the outcomes
        # the user must not miss (an OCR run, a mark that waits for a save).
        self._toast = Toast(self._page_view)

        # Layout: page view in a container with status bar
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._page_view)
        # Ctrl+F: hidden until asked for, between the page and the status bar.
        self._find_bar = FindBar(central)
        self._find_hits: list[tuple[int, RedactionRect]] = []
        self._find_position = -1
        self._find_bar.search_requested.connect(self._run_search)
        self._find_bar.next_requested.connect(lambda: self._step_search(1))
        self._find_bar.previous_requested.connect(lambda: self._step_search(-1))
        self._find_bar.closed.connect(self._close_search)
        # The hits are page indices and rectangles of one moment: a page
        # deleted, moved or recognised by OCR makes them wrong, so the search
        # runs again (only while the bar is open).
        self._doc_model.changed.connect(self._find_bar.refresh)
        self._doc_model.page_changed.connect(lambda _row: self._find_bar.refresh())
        layout.addWidget(self._find_bar)
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
        self._page_view.redaction_adjusted.connect(self._adjust_redaction)
        self._page_view.selection_made.connect(self._add_selection)
        self._page_view.text_edited.connect(self._on_text_edited)
        self._page_view.text_edit_refused.connect(self._status.setText)
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
        # A field filled in on the page comes back as a value, exactly like a
        # field changed in the panel: one command, one way of recording it.
        self._page_view.field_value_committed.connect(self._on_field_value_committed)
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
                self.tr("C&rea da immagini…"),
                "image-x-generic",
                "Ctrl+Shift+N",
                self._create_from_images_dialog,
            )
        )
        file_menu.addAction(
            self._act(self.tr("&Salva"), "document-save", "Ctrl+S", self._save_file)
        )
        file_menu.addAction(
            self._act(
                self.tr("Salva con &nome…"),
                "document-save-as",
                "Ctrl+Shift+S",
                self._save_file_as,
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
        file_menu.addAction(
            self._act(
                self.tr("&Firma…"),
                "application-pgp-signature",
                "Ctrl+Shift+D",
                self._sign_file,
            )
        )
        file_menu.addAction(
            self._act(
                self.tr("&Verifica le firme…"),
                "dialog-password",
                "",
                self._verify_signatures,
            )
        )
        file_menu.addSeparator()
        # Close the document, keep the window: the only other way to put a
        # document down was to open another one in its place.
        self._close_act = self._act(
            self.tr("&Chiudi"), "document-close", "Ctrl+W", self._close_file
        )
        # Nothing to close until something is open; _update_title() keeps
        # this in step from then on.
        self._close_act.setEnabled(False)
        file_menu.addAction(self._close_act)
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

        self._find_act = self._act(self.tr("&Trova…"), "edit-find", "", self._open_search)
        self._find_act.setShortcut(QKeySequence(QKeySequence.StandardKey.Find))
        edit_menu.addAction(self._find_act)
        # F3 / Shift+F3 work whatever has focus, as in every reader.
        for keys, step in (
            (QKeySequence.StandardKey.FindNext, 1),
            (QKeySequence.StandardKey.FindPrevious, -1),
        ):
            action = QAction(self)
            action.setShortcut(QKeySequence(keys))
            action.triggered.connect(lambda _checked=False, step=step: self._step_search(step))
            self.addAction(action)

        edit_menu.addSeparator()

        self._delete_act = self._act(
            self.tr("Elimina pagina"), "edit-delete", "Del", self._delete_page
        )
        edit_menu.addAction(self._delete_act)

        edit_menu.addSeparator()

        self._redact_act = self._act(
            self.tr("Cancella &zona"), "edit-cut", "Ctrl+Shift+X", self._on_redaction_toggled
        )
        # A mode, not a one-shot command: it stays on while the user works
        # through a page, and the marks it collects are only painted — they
        # are burned into the PDF when the document is saved.
        self._redact_act.setCheckable(True)
        self._redact_act.setToolTip(
            self.tr(
                "Trascina un rettangolo sul contenuto da eliminare: testo e immagini\n"
                "sotto di esso spariscono dal file, non vengono solo coperti.\n"
                "Un clic su una zona la ripristina. Diventa definitivo solo al salvataggio."
            )
        )
        edit_menu.addAction(self._redact_act)

        self._select_act = self._act(
            self.tr("Cancella &selezione"),
            "edit-select-all",
            "Ctrl+Shift+L",
            self._on_selection_toggled,
        )
        # The other half of the redaction tool: the same marks, chosen by
        # dragging over the words instead of drawing a box around them.
        self._select_act.setCheckable(True)
        self._select_act.setToolTip(
            self.tr(
                "Trascina sulle parole da eliminare: la selezione si allarga ai\n"
                "confini delle parole, così nessuna resta tagliata a metà.\n"
                "Un clic su una zona la ripristina. Diventa definitivo solo al salvataggio."
            )
        )
        edit_menu.addAction(self._select_act)

        edit_menu.addAction(
            self._act(
                self.tr("Cancella &parola…"),
                "edit-find",
                "Ctrl+Shift+F",
                self._redact_text,
            )
        )

        edit_menu.addSeparator()

        self._text_act = self._act(
            self.tr("&Modifica testo"), "insert-text", "Ctrl+Shift+T", self._on_text_mode_toggled
        )
        # A mode like Redazione, and never on at the same time: a click on a
        # page either opens the editor or starts a mark, not both.
        self._text_act.setCheckable(True)
        self._text_act.setToolTip(
            self.tr(
                "Corregge il testo già presente nel PDF: clic su una riga,\n"
                "Invio conferma, Esc annulla. Il testo nuovo entra nel file\n"
                "solo al salvataggio."
            )
        )
        edit_menu.addAction(self._text_act)

        edit_menu.addSeparator()

        ocr_act = self._act(
            self.tr("&Riconosci testo…"), "draw-text", "Ctrl+Shift+O", self._ocr_pages
        )
        ocr_act.setToolTip(
            self.tr(
                "Legge il testo delle pagine scansionate e lo rende selezionabile,\n"
                "cercabile e cancellabile: resta invisibile e non si stampa."
            )
        )
        edit_menu.addAction(ocr_act)

        # Esc leaves the tool whatever has focus. It sets the check state
        # directly: setChecked() does not emit `triggered`, so the mode is
        # turned off explicitly instead of through the menu slot. (An open
        # text editor claims Esc for itself first: there it cancels the edit.)
        self._escape_act = QAction(self)
        self._escape_act.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        self._escape_act.triggered.connect(self._leave_tools)
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

        # The two page tools, where they can be seen: a checked button says
        # which mode a click on the page is in.
        toolbar.addSeparator()
        toolbar.addAction(self._text_act)
        toolbar.addAction(self._redact_act)
        toolbar.addAction(self._select_act)

    # ------------------------------------------------------------------ #
    #  File operations
    # ------------------------------------------------------------------ #

    def _open_file(self) -> None:
        # Asked before the file dialog: the question is about the document
        # on screen, and answering it after picking a file is backwards.
        if not self._confirm_discard():
            return
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

        An encrypted file is not a failure: the password is asked for and the
        attempt is repeated, for as long as the user wants to try. Giving up
        leaves whatever was on screen untouched -- the model refuses before
        it changes anything.
        """
        password: str | None = None
        while True:
            try:
                self.open_document(path, password)
            except PasswordRequired as needed:
                password = self._ask_password(needed.path, retry=needed.wrong)
                if password is None:
                    return False
                continue
            # A damaged or unsupported PDF can raise a wide range of
            # exceptions from PyMuPDF; at this GUI boundary the correct
            # behaviour is to report it, never to crash the editor.
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(
                    self,
                    self.tr("Errore"),
                    self.tr("Impossibile aprire:\n{0}").format(e),
                )
                return False
            return True

    def _ask_password(self, path: str, retry: bool = False) -> str | None:
        """Ask for the password of *path*; None means the user gave up."""
        name = os.path.basename(path)
        if retry:
            label = self.tr("Password errata per «{0}».").format(name)
        else:
            label = self.tr("«{0}» è protetto da una password.").format(name)
        password, accepted = QInputDialog.getText(
            self,
            self.tr("Documento protetto"),
            label,
            QLineEdit.EchoMode.Password,
        )
        return password if accepted else None

    def _unlock_worker(self, path: str, password: str) -> None:
        """Tell the render thread the password of *path*, waiting for it.

        Blocking, with the same reasoning as ``shutdown_worker``: the handle
        must be open -- and decrypted -- inside the worker thread before any
        render request for those pages is served. Queueing the password
        behind the requests it enables would be worse than useless.
        """
        QMetaObject.invokeMethod(
            self._worker,
            "authenticate",
            Qt.ConnectionType.BlockingQueuedConnection,
            Q_ARG(str, path),
            Q_ARG(str, password),
        )

    def open_document(self, path: str, password: str | None = None) -> None:
        """Open *path*, resetting every view and cache first.

        The caches matter: render keys are built from ``source_index``, so
        without flushing them a second document would be served the first
        document's pixmaps.

        Raises :class:`PasswordRequired` when the file is encrypted and
        *password* is missing or wrong. The file is read before anything is
        reset, and the view is only emptied once those pages exist, so a
        document that refuses to open cannot leave the window showing an
        empty page 1.
        """
        # Read first: the resets below are destructive, and a wrong password
        # must cost the user nothing.
        items = self._doc_model.read_source(0, path, password)

        self._undo_stack.clear()
        self._page_view.reset()
        self._thumbnail_cache.clear()
        # Renders are held back from here to a few lines below: the model is
        # about to announce the new pages while the worker has not been told
        # the password yet. A request in that window would come back as
        # "failed" and nothing would ask for it again.
        self._page_view.set_paused(True)
        self._doc_model.set_pages(items, path)
        self._saved_marks = frozenset()
        # The model emits ``changed`` and the views rebuild from it. Page
        # sizes come from the model too, so the render thread needs no
        # round-trip before the layout is correct.
        self._current_page_index = 0
        # Explicit: a fresh document starts at page 1. (The model reset
        # clears the selection, and the bar would otherwise restore the
        # previous document's row.)
        self._thumb_bar.set_current_row(0)
        # Never carry a tool over into another document: the next drag would
        # mark (or the next click edit) a page the user has not even looked at.
        self._redact_act.setChecked(False)
        self._on_redaction_toggled(False)
        self._select_act.setChecked(False)
        self._on_selection_toggled(False)
        self._text_act.setChecked(False)
        self._page_view.set_text_mode(False)
        self._refresh_form_panel(0)
        self._save_target = path
        self._save_suggestion = None
        self._signed_on_disk = is_signed(path, password or "")
        self._update_title()
        self._status.setText(self.tr("Aperto: {0}").format(path))

        # The worker opens the sources on its own, so it needs the password
        # too; the thumbnails are asked again because theirs failed while the
        # file was still locked.
        if password is not None:
            self._unlock_worker(path, password)
        self._page_view.set_paused(False)
        self._thumb_bar.refresh()

    def _close_file(self) -> bool:
        """File → Chiudi: put the document down, keep the window.

        Asks first when there are unsaved changes, like quitting and like
        "Apri". Returns whether the document is now closed.
        """
        if not self._doc_model.sources:
            return True
        if not self._confirm_discard():
            return False
        self.close_document()
        return True

    def close_document(self) -> None:
        """Empty the window: no document, no history, no tool on.

        Unconditional -- the question about unsaved changes belongs to the
        caller (:meth:`_close_file`). The worker is told to forget every
        source too: it would otherwise keep the files open, and the user who
        closes a PDF expects to be able to move or delete it.
        """
        sources = list(self._doc_model.sources)
        # The view first: it drops an open editor WITHOUT confirming it (the
        # answer about changes has already been given) and its render cache.
        self._page_view.clear()
        self._redact_act.setChecked(False)
        self._on_redaction_toggled(False)
        self._select_act.setChecked(False)
        self._on_selection_toggled(False)
        self._text_act.setChecked(False)
        self._page_view.set_text_mode(False)
        self._undo_stack.clear()
        self._doc_model.close()
        self._thumbnail_cache.clear()
        for source in sources:
            self._worker.evict_requested.emit(source)
        self._current_page_index = 0
        self._refresh_form_panel()
        self._save_target = None
        self._signed_on_disk = False
        self._saved_marks = frozenset()
        self._update_title()
        self._status.setText(self.tr("Documento chiuso."))

    def _merge_file(self) -> None:
        """Unire: append every page of another PDF to the document.

        Nothing is copied or rewritten -- the model just grows a second
        source and the new pages point into it, exactly like the original
        ones. The merge is a command like any other, so Ctrl+Z takes the
        appended pages away again.
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
            self.tr("PDF e immagini ({0});;File PDF (*.pdf);;Immagini ({1})").format(
                "*.pdf " + self._image_patterns(), self._image_patterns()
            ),
        )
        if not path:
            return

        self.merge_path(path)

    def merge_path(self, path: str) -> None:
        """Append every page of *path*, reporting failures instead of raising.

        Also reachable from the command line, where several arguments mean
        "open the first and append the rest". Encrypted files are asked for a
        password here as well, and the render thread is told it before the
        first page of the merge can be asked for.
        """
        label: str | None = None
        if is_image(path):
            # An image becomes a one-page PDF first, and that PDF is what gets
            # merged: from then on it is a source like any other.
            label = os.path.basename(path)
            converted = self._images_to_scratch([path])
            if converted is None:
                return
            path = converted
        password: str | None = None
        while True:
            try:
                # Read first, command later: a file that brings no page, or
                # that will not open, must not leave an undo step behind.
                items = self._doc_model.read_source(
                    len(self._doc_model.sources), path, password
                )
            except PasswordRequired as needed:
                password = self._ask_password(needed.path, retry=needed.wrong)
                if password is None:
                    return
                continue
            # Same reasoning as open_path: a damaged PDF is reported, never
            # fatal.
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(
                    self,
                    self.tr("Errore"),
                    self.tr("Impossibile unire:\n{0}").format(e),
                )
                return
            break

        if not items:
            QMessageBox.warning(
                self,
                self.tr("Attenzione"),
                self.tr("Il documento scelto non contiene pagine."),
            )
            return

        if password is not None:
            # Before the model announces the new pages: the first render
            # requests for them would otherwise be answered by a locked
            # handle and leave the pages blank.
            self._unlock_worker(path, password)
        self._push_merge(path, items, label)

    def _push_merge(
        self, path: str, items: list[PageItem], label: str | None = None
    ) -> None:
        """Make *items* an undo step, then show what was appended.

        Pushing the command is what makes the merge undoable; the window used
        to track it with a flag of its own because it was the one
        modification outside the undo stack. The last merged page is brought
        on screen because lazily-rendered pages only appear once they are.
        """
        first_new = self._doc_model.page_count
        self._undo_stack.push(
            AppendDocument(
                self._doc_model, len(self._doc_model.sources), path, items, label
            )
        )
        self._update_title()
        self._page_view.ensure_page_visible(first_new)
        self._thumb_bar.set_current_row(first_new)
        self._status.setText(
            self.tr("Unite {0} pagine da: {1}").format(len(items), label or path)
        )

    # ------------------------------------------------------------------ #
    #  Create from images
    # ------------------------------------------------------------------ #

    @staticmethod
    def _image_patterns() -> str:
        return " ".join(f"*{suffix}" for suffix in IMAGE_SUFFIXES)

    def _create_from_images_dialog(self) -> None:
        """File → Crea da immagini: pick the images, then build the document."""
        # Asked before the file dialog, like "Apri": the question is about
        # the document on screen.
        if not self._confirm_discard():
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr("Crea PDF da immagini"),
            str(os.path.expanduser("~")),
            self.tr("Immagini ({0})").format(self._image_patterns()),
        )
        if paths:
            self.create_from_images(paths)

    def create_from_images(self, paths: list[str]) -> bool:
        """Make a new document out of *paths*, one page per image, in that order.

        The document has no file yet: it is "Senza titolo", modified from the
        start, and Ctrl+S asks where to save it -- next to the first image.
        Returns whether the document is now open.
        """
        converted = self._images_to_scratch(paths)
        if converted is None:
            return False
        self.open_document(converted)
        self._save_target = None
        first = paths[0]
        self._save_suggestion = os.path.join(
            os.path.dirname(_host_path(first)), os.path.splitext(os.path.basename(first))[0] + ".pdf"
        )
        # Nothing of this exists on disk except a temporary: closing now
        # would lose it, so the document starts out as unsaved.
        self._undo_stack.resetClean()
        self._update_title()
        self._status.setText(
            self.tr("Creato da {0} immagini, {1} pagine: salvalo con Ctrl+S per tenerlo.").format(
                len(paths), self._doc_model.page_count
            )
        )
        return True

    def _images_to_scratch(self, paths: list[str]) -> str | None:
        """Convert *paths* into one temporary PDF; None (and a message) on failure."""
        if self._scratch is None:
            self._scratch = tempfile.TemporaryDirectory(prefix="plico-")
        stem = os.path.splitext(os.path.basename(paths[0]))[0] if paths else "immagini"
        handle, target = tempfile.mkstemp(
            dir=self._scratch.name, prefix=f"{stem}-", suffix=".pdf"
        )
        os.close(handle)
        try:
            images_to_pdf(paths, target)
        except ValueError as error:
            os.unlink(target)
            QMessageBox.critical(
                self,
                self.tr("Errore"),
                self.tr("Impossibile creare il PDF:\n{0}").format(error),
            )
            return None
        return target

    def _save_file(self) -> bool:
        """Salva: write the document to the file it came from (Ctrl+S).

        Returns whether the document was saved, so that the "unsaved
        changes" question can tell a save from a cancelled dialog.
        """
        if not self._doc_model.sources:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return False
        if self._save_target is None:
            return self._save_file_as()
        return self._save_to(self._save_target)

    def _save_file_as(self) -> bool:
        """Salva con nome: ask where, then save there."""
        if not self._doc_model.sources:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return False
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Salva con nome"),
            self._proposal_origin(),
            self.tr("File PDF (*.pdf)"),
        )
        if not path:
            return False
        return self._save_to(path)

    def _save_to(self, path: str) -> bool:
        """Write the whole document to *path*; it becomes the "Salva" target."""
        # A plain save writes a fresh file: the signature of the file it
        # replaces would not be in it. Say so before doing it, because losing
        # a signature is not something an undo can bring back.
        if (
            self._signed_on_disk
            and self._save_target is not None
            and os.path.abspath(path) == os.path.abspath(self._save_target)
        ):
            choice = QMessageBox.question(
                self,
                self.tr("Il documento è firmato"),
                self.tr(
                    "Salvare «{0}» così com'è toglie la firma: il file nuovo non "
                    "è firmato.\n\nContinuare?"
                ).format(os.path.basename(path)),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice != QMessageBox.StandardButton.Save:
                return False
        if not self._confirm_redactions(self._marks_to_write(path)):
            return False
        # Computed BEFORE writing: os.replace() gives the target a new inode,
        # and afterwards it would no longer match the source it replaced.
        overwritten = self._doc_model.sources_at(path)
        try:
            save_as(self._doc_model, path)
        # Same reasoning as _open_file: a failed write (permissions, full
        # disk, malformed source) must surface as a dialog, not a traceback.
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self, self.tr("Errore"), self.tr("Impossibile salvare:\n{0}").format(e)
            )
            return False
        if overwritten:
            # Re-opening resets the undo stack, the target and the title.
            self._adopt_saved_file(path, overwritten)
        else:
            self._mark_saved(path)
            self._status.setText(self.tr("Salvato: {0}").format(path))
        return True

    def _mark_saved(self, path: str) -> None:
        """The document as it is now has been written to *path*.

        The model keeps its sources -- they are untouched -- so the undo
        history survives; only the meaning of "unsaved" moves to this point.
        """
        self._save_target = path
        # Every write here materialises the page list; none of them signs.
        self._signed_on_disk = False
        self._saved_marks = self._marks()
        self._undo_stack.setClean()
        self._update_title()

    def is_modified(self) -> bool:
        """Whether closing the document now would lose something.

        The undo stack is the whole truth now that the merge is a command:
        there is no modification left that would leave the stack clean.
        """
        if not self._doc_model.sources:
            return False
        return not self._undo_stack.isClean()

    def _marks(
        self, indices: list[int] | None = None
    ) -> frozenset[tuple[int, int, RedactionRect]]:
        """Every redaction of the pages at *indices* (all pages for None)."""
        pages = self._doc_model.pages
        chosen = range(len(pages)) if indices is None else indices
        return frozenset(
            (pages[i].source_id, pages[i].source_index, rect)
            for i in chosen
            for rect in pages[i].redactions
        )

    def _pending_marks(self) -> frozenset[tuple[int, int, RedactionRect]]:
        """The redactions the save target does not have yet."""
        return self._marks() - self._saved_marks

    def _marks_to_write(self, path: str) -> frozenset[tuple[int, int, RedactionRect]]:
        """What a full save to *path* burns that was not confirmed already.

        Saving again to the target the marks went into last time asks nothing
        for those; any other file gets all of them, and they are asked again.
        """
        same = self._save_target is not None and os.path.abspath(path) == os.path.abspath(
            self._save_target
        )
        return self._pending_marks() if same else self._marks()

    def _confirm_redactions(self, marks: frozenset[tuple[int, int, RedactionRect]]) -> bool:
        """Ask before *marks* become permanent in a file; True to go ahead.

        The marks are undoable until now and the preview has shown them, but
        what comes next is not: the content under them leaves the file for
        good. One question, with the numbers, right before the write.
        """
        if not marks:
            return True
        pages = sorted({
            i
            for i, item in enumerate(self._doc_model.pages)
            for rect in item.redactions
            if (item.source_id, item.source_index, rect) in marks
        })
        listed = ", ".join(str(i + 1) for i in pages)
        # Whole sentences, one per case: a translator cannot reorder the
        # halves of a sentence glued together in code.
        if len(marks) == 1:
            what = self.tr(
                "Il contenuto di una zona, a pagina {0}, verrà eliminato definitivamente dal file."
            ).format(listed)
        elif len(pages) == 1:
            what = self.tr(
                "Il contenuto di {0} zone, a pagina {1}, verrà eliminato definitivamente dal file."
            ).format(len(marks), listed)
        else:
            what = self.tr(
                "Il contenuto di {0} zone, alle pagine {1}, verrà eliminato "
                "definitivamente dal file."
            ).format(len(marks), listed)
        text = (
            what
            + "\n\n"
            + self.tr(
                "Testo, immagini e grafica sotto le zone non si potranno più recuperare "
                "da quel file. Il documento aperto resta modificabile."
            )
        )
        return self._ask_to_burn(text)

    def _ask_to_burn(self, text: str) -> bool:
        """The dialog of :meth:`_confirm_redactions`; tests replace it."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Cancellazione definitiva"))
        box.setText(text)
        burn = box.addButton(self.tr("Elimina e salva"), QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel)
        box.exec()
        return box.clickedButton() is burn

    def _notify(self, text: str) -> None:
        """Say *text* in the status bar and, for a few seconds, over the page."""
        self._status.setText(text)
        self._toast.show_message(text)

    def _update_title(self) -> None:
        """File name in the title, with the [*] that marks unsaved changes.

        Only the name: Qt appends the application display name itself.
        """
        if not self._doc_model.sources:
            self.setWindowTitle("Plico")
        elif self._save_target is None:
            # A document made from images: there is no file name to show yet.
            self.setWindowTitle(self.tr("Senza titolo") + "[*]")
        else:
            name = os.path.basename(self._save_target)
            if self._signed_on_disk:
                # The signature is a property of the file on disk, so it is
                # named here: a title that does not say it would let the user
                # believe the version on screen is the signed one.
                name += self.tr(" — firmato")
            self.setWindowTitle(f"{name}[*]")
        pending = len(self._pending_marks())
        if pending:
            # Said in the title because it is a state, not an event: until the
            # next save these marks are a promise, and the file on disk still
            # has what is under them.
            suffix = (
                self.tr(" — una cancellazione da applicare")
                if pending == 1
                else self.tr(" — {0} cancellazioni da applicare").format(pending)
            )
            title = self.windowTitle()
            self.setWindowTitle(title.replace("[*]", suffix + "[*]"))
        self.setWindowModified(self.is_modified())
        # Every open, close and save passes through here, so "Chiudi" is
        # enabled exactly while there is a document to close.
        self._close_act.setEnabled(bool(self._doc_model.sources))

    def _confirm_discard(self) -> bool:
        """Ask before dropping unsaved changes; True means "go ahead".

        Redactions and filled-in fields live only in the model until the
        document is saved, so closing or opening another file would throw
        them away without a trace. The answer "Salva" goes through the same
        path as Ctrl+S, and a save that fails or is cancelled keeps the
        document open.
        """
        # A correction typed in the text editor but not yet confirmed is a
        # change too: confirm it first, so the question below counts it
        # instead of the window dropping it with the editor.
        self._page_view.finish_text_edit()
        self._page_view.finish_field_edit()
        if not self.is_modified():
            return True
        name = os.path.basename(self._save_target or "") or self.tr("Senza titolo")
        choice = QMessageBox.question(
            self,
            self.tr("Modifiche non salvate"),
            self.tr("«{0}» ha modifiche non salvate.\nVuoi salvarle?").format(name),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self._save_file()
        return choice == QMessageBox.StandardButton.Discard

    def _adopt_saved_file(self, path: str, overwritten: list[str]) -> None:
        """Bring the model back in line after a save that replaced a source.

        The virtual pages still describe the file as it was BEFORE the save:
        its page numbers, its /Rotate, its sizes. The file on disk is now the
        materialised document -- deletions gone, pages renumbered, the user's
        rotation baked into /Rotate, redactions burned in -- so carrying on
        with the old items renders the wrong pages, rotates them twice, and
        the next save silently drops pages. The saved file IS the document,
        so it is re-opened in place of the old sources: the undo history goes
        with them, because no command can take back what is now on disk.
        """
        # os.replace() swapped the inode: the worker would keep reading the
        # OLD document under that path from the handle it holds. The evict is
        # queued before the renders the re-open asks for, so it lands first.
        for source in overwritten:
            self._worker.evict_requested.emit(source)

        row = self._thumb_bar.current_row()
        if not self.open_path(path):
            # The old items point into a file that no longer matches them:
            # keeping them on screen would be the very bug this avoids.
            self._undo_stack.clear()
            self._doc_model.close()
            self._save_target = None
            self._refresh_form_panel()
            self._update_title()
            return
        row = min(max(row, 0), self._doc_model.page_count - 1)
        self._thumb_bar.set_current_row(row)
        self._page_view.ensure_page_visible(row)
        self._status.setText(
            self.tr(
                "Salvato e riaperto: {0}. Le modifiche ora sono nel file e non si "
                "possono più annullare."
            ).format(path)
        )

    # ------------------------------------------------------------------ #
    #  Signatures
    # ------------------------------------------------------------------ #

    def _sign_file(self) -> None:
        """File → Firma: write the page list, then sign the file that came out.

        The signature is computed over the saved bytes, so it cannot be
        applied to the page list on screen: a document is signed by signing a
        *file*. What is written is the materialised document -- deletions,
        rotations, redactions and form values included -- and the window then
        adopts the signed file, because continuing to edit the page list
        would silently invalidate what was just signed.
        """
        if not self._doc_model.sources:
            QMessageBox.warning(
                self, self.tr("Attenzione"), self.tr("Nessun documento aperto.")
            )
            return
        # A signed file with nothing changed is signed as it is on disk, with
        # the new signature appended: only that keeps the first one valid.
        # Unsaved changes can only be signed by rebuilding the file, and a
        # rebuilt file is new bytes the old signature does not cover.
        self._page_view.finish_text_edit()
        self._page_view.finish_field_edit()
        on_disk = self._signed_on_disk and not self.is_modified() and bool(self._save_target)
        if self._signed_on_disk:
            name = os.path.basename(self._save_target or "")
            if on_disk:
                text = self.tr(
                    "«{0}» è già firmato.\n\nUna seconda firma si aggiunge alla "
                    "prima, non la sostituisce: vuoi continuare?"
                ).format(name)
            else:
                text = self.tr(
                    "«{0}» è firmato, ma ha modifiche non salvate.\n\nPer firmarle il "
                    "file va riscritto, e la firma che porta ora verrà tolta: resterà "
                    "solo la nuova. Vuoi continuare?"
                ).format(name)
            choice = QMessageBox.question(
                self,
                self.tr("Documento già firmato"),
                text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return

        sizes = [item.unrotated_size for item in self._doc_model.pages]
        dialog = SignDialog(sizes, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        request: SignatureRequest = dialog.request()

        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Salva e firma"),
            self._proposed_signed_path(),
            self.tr("File PDF (*.pdf)"),
        )
        if not path:
            return
        # Computed BEFORE writing, as in _save_to: the swap gives the target a
        # new inode.
        if not on_disk and not self._confirm_redactions(self._marks_to_write(path)):
            return
        overwritten = self._doc_model.sources_at(path)
        try:
            if on_disk:
                assert self._save_target is not None
                sign_copy(self._save_target, path, request)
            else:
                save_signed(self._doc_model, path, request)
        # MuPDF, pyHanko and the filesystem all have their own exception types
        # here; what the user needs is the reason, not the class.
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(
                self, self.tr("Errore"), self.tr("Impossibile firmare:\n{0}").format(error)
            )
            return

        # The signed file IS the document now: the pages on screen describe
        # the unsigned version, and any later save would drop the signature.
        for source in overwritten:
            self._worker.evict_requested.emit(source)
        if not self.open_path(path):
            return
        self._signed_on_disk = True
        self._update_title()
        self._status.setText(self.tr("Documento firmato: {0}").format(path))

    def _proposal_origin(self) -> str:
        """The path the save dialogs start from, as the user knows it."""
        if self._save_target:
            return _host_path(self._save_target)
        return self._save_suggestion or ""

    def _proposed_signed_path(self) -> str:
        """``documento.pdf`` -> ``documento-firmato.pdf``."""
        origin = self._proposal_origin()
        stem, extension = os.path.splitext(origin)
        if not stem:
            return ""
        return f"{stem}-firmato{extension or '.pdf'}"

    def _verify_signatures(self) -> None:
        """File → Verifica le firme: read what the file on disk carries.

        What is verified is the file, not the page list: a signature covers
        bytes, and unsaved changes are not in those bytes. Asking first is the
        difference between a verdict the user can trust and one about a
        document they are not looking at.
        """
        if not self._doc_model.sources:
            QMessageBox.warning(
                self, self.tr("Attenzione"), self.tr("Nessun documento aperto.")
            )
            return
        path = self._save_target
        if not path:
            QMessageBox.warning(
                self,
                self.tr("Attenzione"),
                self.tr("Questo documento non ha ancora un file: salvalo prima di verificarlo."),
            )
            return
        if self.is_modified():
            choice = QMessageBox.question(
                self,
                self.tr("Modifiche non salvate"),
                self.tr(
                    "Il file «{0}» non contiene ancora le modifiche non salvate.\n\n"
                    "Verificare lo stesso la copia che sta su disco?"
                ).format(os.path.basename(path)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
        roots = self._signed_roots()
        dialog = SignatureDialog(
            path,
            roots,
            password=self._doc_model.passwords.get(path, ""),
            parent=self,
        )
        dialog.exec()
        if dialog.roots != roots:
            self._settings().setValue("firma/radici", dialog.roots)

    def _signed_roots(self) -> list[str]:
        """The PEM certificates the user decided to trust, as far as they exist."""
        stored = self._settings().value("firma/radici", [])
        if isinstance(stored, str):
            stored = [stored]
        if not isinstance(stored, list):
            return []
        return [path for path in stored if isinstance(path, str) and os.path.exists(path)]

    # ------------------------------------------------------------------ #
    #  Compression
    # ------------------------------------------------------------------ #

    def _compress_file(self) -> None:
        """Write a compressed copy of the materialised document.

        It is not an alternative to "Salva con nome": the content is the same,
        only smaller -- deletions, reorderings and rotations included. The
        source PDFs are not touched.
        """
        if not self._doc_model.sources:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return

        choice = CompressionDialog(len(self._doc_model.pages), self)
        if choice.exec() != QDialog.DialogCode.Accepted:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Salva compresso"),
            self._proposed_compressed_path(),
            self.tr("File PDF (*.pdf)"),
        )
        if not path:
            return
        self._start_compression(path, choice.options)

    def _proposed_compressed_path(self) -> str:
        """``documento.pdf`` -> ``documento-compresso.pdf``."""
        # The file the document will be saved as, not the model's path: for a
        # document made from images that is a temporary nobody should see.
        origin = self._proposal_origin()
        stem, extension = os.path.splitext(origin)
        if not stem:
            return str(os.path.expanduser("~"))
        return f"{stem}-compresso{extension or '.pdf'}"

    def _start_compression(self, path: str, options: CompressionOptions) -> None:
        # Computed BEFORE writing: compressing over a source gives that file
        # a new inode, and afterwards the comparison would no longer
        # recognise the original.
        # A copy, not the save target: every mark goes into it.
        if not self._confirm_redactions(self._marks()):
            return
        self._compression_overwritten = self._doc_model.sources_at(path)
        self._compression_path = path
        self._compression_options = options

        progress = QProgressDialog(self)
        progress.setWindowTitle(self.tr("Salva compresso"))
        progress.setLabelText(self.tr("Compressione in corso…"))
        progress.setRange(0, 100)
        # The work cannot be interrupted half-way: better to offer no button
        # than one that cannot keep what it promises.
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        self._progress = progress

        task = CompressionTask(self._doc_model, path, options)
        task.signals.progress.connect(progress.setValue)
        task.signals.finished.connect(self._on_compression_finished)
        task.signals.failed.connect(self._on_compression_failed)
        # Until the pool is done, someone has to keep the task alive.
        self._compression_task = task
        QThreadPool.globalInstance().start(task)

    def _on_compression_finished(self, preview: CompressionPreview) -> None:
        """The compressed file exists: show what it really gained, then keep it.

        The work is already done when the question is asked, so the numbers are
        the real ones; refusing throws the temporary away and leaves the
        destination -- which may be one of the open sources -- exactly as it
        was.
        """
        self._close_progress()
        result = preview.result

        if not result.shrank:
            preview.drop()
            self._status.setText(
                self.tr("Nessuna compressione: {0}").format(preview.target)
            )
            QMessageBox.information(
                self, self.tr("Salva compresso"), self._nothing_gained(result)
            )
            return

        try:
            preview.keep()
        # The swap can still fail here -- the destination became read-only,
        # or its directory went away while the passes ran. Said in a dialog,
        # and the temporary is not left next to it: nobody would ever claim it.
        except OSError as error:
            preview.drop()
            QMessageBox.critical(
                self,
                self.tr("Errore"),
                self.tr("Impossibile salvare il file compresso:\n{0}").format(error),
            )
            return
        path = preview.target

        # Same as _save_file: a compressed copy written over a source has
        # replaced it, and the model must follow the file it now describes.
        if self._compression_overwritten:
            self._adopt_saved_file(path, self._compression_overwritten)
        else:
            self._status.setText(self.tr("Compresso: {0}").format(path))

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

    def _nothing_gained(self, result: CompressionResult) -> str:
        """Why nothing was gained, and the one thing still worth trying."""
        text = self.tr(
            "Questo file non aveva niente da guadagnare: è rimasto di {0}."
        ).format(format_size(result.source_size))
        options = self._compression_options
        if options is not None and options.image_pages is not None:
            # Fewer pages can gain nothing even when those pages would get much
            # smaller: the images left alone keep all their weight.
            text += "\n\n" + self.tr(
                "Il peso sta nelle immagini delle pagine che non hai scelto: "
                "prova con tutte le pagine."
            )
        return text

    def _on_compression_failed(self, message: str) -> None:
        self._close_progress()
        QMessageBox.critical(
            self,
            self.tr("Errore"),
            self.tr("Impossibile comprimere:\n{0}").format(message),
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

        if not self._confirm_redactions(self._marks(indices)):
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
    #  Redaction (undo commands)
    # ------------------------------------------------------------------ #

    def _on_redaction_toggled(self, active: bool) -> None:
        """Enter or leave the redaction tool."""
        if active and not self._doc_model.sources:
            # Nothing to redact. Put the check mark back; setChecked() does
            # not emit `triggered`, so this cannot recurse.
            self._redact_act.setChecked(False)
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return
        if active and self._text_act.isChecked():
            self._text_act.setChecked(False)
            self._page_view.set_text_mode(False)
        if active and self._select_act.isChecked():
            self._select_act.setChecked(False)
            self._page_view.set_selection_mode(False)
        self._page_view.set_redaction_mode(active)
        if active:
            self._status.setText(
                self.tr("Cancella zona: trascina un rettangolo sul contenuto da eliminare; un clic su una zona la ripristina.")
            )
        else:
            self._announce_preview()

    def _on_selection_toggled(self, active: bool) -> None:
        """Enter or leave the tool that redacts the words you drag over."""
        if active and not self._doc_model.sources:
            self._select_act.setChecked(False)
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return
        if active and self._text_act.isChecked():
            self._text_act.setChecked(False)
            self._page_view.set_text_mode(False)
        if active and self._redact_act.isChecked():
            self._redact_act.setChecked(False)
            self._page_view.set_redaction_mode(False)
        self._page_view.set_selection_mode(active)
        if active:
            self._status.setText(
                self.tr(
                    "Cancella selezione: trascina sulle parole da eliminare; le zone "
                    "restano modificabili finché non salvi. Un clic su una zona la ripristina."
                )
            )
        else:
            self._announce_preview()

    def _announce_preview(self) -> None:
        """Leaving a mark tool: say what the page now shows, if anything waits.

        Without a tool the pages are the preview -- the redactions applied --
        and the change of picture deserves a word, or a page with holes in it
        looks like damage instead of like the result.
        """
        if not self._doc_model.sources:
            self._status.setText(self.tr("Pronto"))
            return
        pending = len(self._pending_marks())
        if not pending:
            self._status.setText(self.tr("Pronto"))
            return
        self._notify(
            self.tr("Anteprima: la pagina è come verrà salvata. Una cancellazione da applicare.")
            if pending == 1
            else self.tr(
                "Anteprima: la pagina è come verrà salvata. {0} cancellazioni da applicare."
            ).format(pending)
        )

    def _leave_tools(self) -> None:
        """Esc: leave whichever tool is on, leaving its work where it is.

        Typing in the search bar, Esc closes the bar and nothing else; with no
        tool on, Esc closes the bar wherever the focus is.
        """
        if self._find_bar.has_focus():
            self._find_bar.close_bar()
            return
        if not (
            self._redact_act.isChecked()
            or self._select_act.isChecked()
            or self._text_act.isChecked()
        ):
            self._find_bar.close_bar()
            return
        if self._redact_act.isChecked():
            self._redact_act.setChecked(False)
            self._on_redaction_toggled(False)
        if self._select_act.isChecked():
            self._select_act.setChecked(False)
            self._on_selection_toggled(False)
        if self._text_act.isChecked():
            self._text_act.setChecked(False)
            self._on_text_mode_toggled(False)

    # ------------------------------------------------------------------ #
    #  Search (Ctrl+F)
    # ------------------------------------------------------------------ #

    def _open_search(self) -> None:
        """Ctrl+F: show the bar, ready to type."""
        if not self._doc_model.sources:
            self._status.setText(self.tr("Nessun documento aperto."))
            return
        self._find_bar.open_bar()

    def _run_search(self, text: str) -> None:
        """Look for *text* in every page and go to the first hit from here on.

        The same search as *Cancella parola*: it reads the sources and the
        words an OCR run has recognised but not saved yet. Words already
        under a redaction are not found -- they are gone from the page the
        preview shows, and will be from the file.
        """
        found = self._doc_model.find_text(text) if text and self._doc_model.sources else {}
        self._find_hits = [
            (index, rect)
            for index in sorted(found)
            for rect in sorted(found[index], key=lambda r: (round(r.y0), r.x0))
        ]
        if not self._find_hits:
            self._find_position = -1
            self._show_search()
            return
        # From the page the user is on: searching is "where next", not "where
        # first", and a hit behind the reader is found by going back.
        here = max(0, self._thumb_bar.current_row())
        self._find_position = next(
            (i for i, (index, _) in enumerate(self._find_hits) if index >= here), 0
        )
        self._show_search(scroll=True)

    def _step_search(self, step: int) -> None:
        """F3 / Shift+F3: the next or the previous hit, round the document."""
        # isHidden, not isVisible: the bar is open even in a window that is
        # not on screen yet.
        if self._find_bar.isHidden():
            self._open_search()
            return
        if not self._find_hits:
            return
        self._find_position = (self._find_position + step) % len(self._find_hits)
        self._show_search(scroll=True)

    def _show_search(self, scroll: bool = False) -> None:
        """Hand the hits to the view and the count to the bar."""
        by_page: dict[int, list[RedactionRect]] = {}
        current: tuple[int, int] | None = None
        for position, (index, rect) in enumerate(self._find_hits):
            if position == self._find_position:
                current = (index, len(by_page.get(index, [])))
            by_page.setdefault(index, []).append(rect)
        self._page_view.set_search_hits(by_page, current)
        self._find_bar.set_count(self._find_position + 1, len(self._find_hits))
        if scroll and 0 <= self._find_position < len(self._find_hits):
            index, rect = self._find_hits[self._find_position]
            # The thumbnail first: selecting it scrolls to the top of the page,
            # and the hit must be what the view settles on.
            self._thumb_bar.set_current_row(index)
            self._page_view.ensure_rect_visible(index, rect)

    def _close_search(self) -> None:
        """The bar closed: the highlights go with it."""
        self._find_hits = []
        self._find_position = -1
        self._page_view.set_search_hits({}, None)
        self._page_view.setFocus()

    # ------------------------------------------------------------------ #
    #  Text editing (undo commands)
    # ------------------------------------------------------------------ #

    def _on_text_mode_toggled(self, active: bool) -> None:
        """Enter or leave the text tool."""
        if active and not self._doc_model.sources:
            self._text_act.setChecked(False)
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return
        if active and self._redact_act.isChecked():
            self._redact_act.setChecked(False)
            self._page_view.set_redaction_mode(False)
        if active and self._select_act.isChecked():
            self._select_act.setChecked(False)
            self._page_view.set_selection_mode(False)
        self._page_view.set_text_mode(active)
        if active:
            self._status.setText(
                self.tr(
                    "Modifica testo: clic su una riga del documento per correggerla; "
                    "Invio conferma, Esc annulla."
                )
            )
        else:
            self._status.setText(self.tr("Pronto"))

    def _on_text_edited(self, index: int, span: TextSpan, text: str) -> None:
        """A correction was confirmed in the editor (and already checked)."""
        if not (0 <= index < self._doc_model.page_count):
            return
        self._undo_stack.push(EditText(self._doc_model, index, span, text))

    def _add_redaction(self, index: int, rect: RedactionRect) -> None:
        """A rectangle was drawn on page *index*."""
        self._undo_stack.push(AddRedaction(self._doc_model, index, rect))
        self._notify(
            self.tr(
                "Zona segnata a pagina {0}: il contenuto sarà eliminato al salvataggio. "
                "Esc per vedere l'anteprima."
            ).format(index + 1)
        )

    def _adjust_redaction(
        self,
        index: int,
        position: int,
        before: RedactionRect,
        after: RedactionRect,
        moved: bool,
    ) -> None:
        """A mark on page *index* was moved or resized with the mouse."""
        self._undo_stack.push(
            AdjustRedaction(self._doc_model, index, position, before, after, moved)
        )

    def _add_selection(self, index: int, words: list[RedactionRect]) -> None:
        """Words were selected on page *index*: mark them all, as ONE step.

        The selection is one gesture, so it is one Ctrl+Z. Undoing it word by
        word would be worse than not undoing it at all.
        """
        if not words:
            return
        self._undo_stack.beginMacro(
            self.tr("Cancella la selezione su pagina {0}").format(index + 1)
        )
        try:
            for rect in words:
                self._undo_stack.push(AddRedaction(self._doc_model, index, rect))
        finally:
            self._undo_stack.endMacro()
        self._notify(
            self.tr(
                "{0} parole segnate a pagina {1}: saranno eliminate al salvataggio. "
                "Esc per vedere l'anteprima."
            ).format(len(words), index + 1)
            if len(words) != 1
            else self.tr(
                "Una parola segnata a pagina {0}: sarà eliminata al salvataggio. "
                "Esc per vedere l'anteprima."
            ).format(index + 1)
        )

    def _remove_redaction(self, index: int, rect: RedactionRect) -> None:
        """An existing mark was clicked away."""
        self._undo_stack.push(RemoveRedaction(self._doc_model, index, rect))

    def _redact_text(self) -> None:
        """Mark every occurrence of a string the user types.

        The whole search is ONE undo step: the user asked for one operation,
        and undoing it word by word would be absurd.
        """
        if not self._doc_model.sources:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return
        text, ok = QInputDialog.getText(
            self,
            self.tr("Cancella parola"),
            self.tr("Parola da eliminare in tutte le pagine:"),
        )
        if not ok or not text:
            return
        occurrences = self._doc_model.find_text(text)
        if not occurrences:
            self._status.setText(self.tr("Nessuna occorrenza di «{0}».").format(text))
            return

        self._undo_stack.beginMacro(self.tr("Cancella «{0}»").format(text))
        try:
            for index, rects in occurrences.items():
                for rect in rects:
                    self._undo_stack.push(AddRedaction(self._doc_model, index, rect))
        finally:
            self._undo_stack.endMacro()

        # No tool is turned on: without one the pages show the redactions
        # applied, which is the answer to "what did that just do?". The marks
        # can still be corrected with Cancella zona.
        count = sum(len(rects) for rects in occurrences.values())
        if count == 1:
            page = next(iter(occurrences)) + 1
            message = self.tr(
                "Un'occorrenza di «{0}» segnata a pagina {1}: sarà eliminata al "
                "salvataggio. La pagina ne mostra già l'anteprima."
            ).format(text, page)
        elif len(occurrences) == 1:
            page = next(iter(occurrences)) + 1
            message = self.tr(
                "{0} occorrenze di «{1}» segnate a pagina {2}: saranno eliminate al "
                "salvataggio. La pagina ne mostra già l'anteprima."
            ).format(count, text, page)
        else:
            message = self.tr(
                "{0} occorrenze di «{1}» segnate su {2} pagine: saranno eliminate al "
                "salvataggio. La pagina ne mostra già l'anteprima."
            ).format(count, text, len(occurrences))
        self._notify(message)

    # ------------------------------------------------------------------ #
    #  OCR (a scan is a picture of words: this makes the words real)
    # ------------------------------------------------------------------ #

    def _ocr_pages(self) -> None:
        """Read the text of scanned pages, as ONE undoable step.

        The run is one operation for the user, so it is one step in the stack,
        and that means the window has to know when the last page is done. The
        task therefore loops over the pages itself, and the wait here is a
        local event loop rather than a blocked GUI thread: the progress dialog
        keeps painting and Cancel keeps arriving while it runs.
        """
        if not self._doc_model.sources:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun documento aperto."))
            return
        dialog = OcrDialog(len(self._doc_model.pages), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        indices = dialog.pages
        task = OcrTask(self._doc_model, indices, dialog.language)
        progress = QProgressDialog(
            self.tr("Riconoscimento del testo…"), self.tr("Annulla"), 0, len(indices), self
        )
        progress.setWindowTitle(self.tr("Riconosci testo"))
        # Window-modal: the pages are being read from the sources, so the model
        # must not be rearranged under the task. Shown at once, not after the
        # usual delay: a dialog that is not on screen yet is not modal yet,
        # and for half a second the window took a Del or a drag while the
        # task was reading the page list.
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        task.signals.progress.connect(lambda done, total: progress.setValue(done))
        progress.canceled.connect(task.cancel)
        loop = QEventLoop()
        task.signals.finished.connect(loop.quit)
        task.signals.failed.connect(loop.quit)
        QThreadPool.globalInstance().start(task)
        loop.exec()
        # Read before closing: closing a QProgressDialog emits canceled(), and
        # the connection above would report a finished run as an interrupted
        # one.
        cancelled = task.cancelled
        progress.close()
        if task.error is not None:
            QMessageBox.warning(self, self.tr("Riconoscimento fallito"), task.error)
            return
        self._install_ocr(task.words, cancelled=cancelled)

    def _install_ocr(self, words: dict[int, list[OcrWord]], cancelled: bool = False) -> None:
        """Put what the task read into the stack, or say that there is nothing.

        A page that came back empty is skipped: reading a born-digital page
        must not mark the document modified, and an undo step that changes
        nothing is noise in the menu.
        """
        found = {index: read for index, read in words.items() if read}
        if not found:
            self._notify(
                self.tr("Riconoscimento interrotto: nessun testo letto.")
                if cancelled
                else self.tr("Nessun testo riconosciuto nelle pagine scelte.")
            )
            return
        count = len(found)
        # Singular and plural written out: "Riconosci testo su 1 pagine" is
        # what the undo stack would otherwise read.
        macro = self.tr("Riconosci testo su una pagina")
        if count > 1:
            macro = self.tr("Riconosci testo su {0} pagine").format(count)
        self._undo_stack.beginMacro(macro)
        try:
            for index in sorted(found):
                self._undo_stack.push(OcrPage(self._doc_model, index, found[index]))
        finally:
            self._undo_stack.endMacro()
        message = self.tr("Riconosciuto testo su una pagina.")
        if count > 1:
            message = self.tr("Riconosciuto testo su {0} pagine.").format(count)
        empty = len(words) - count
        if empty == 1:
            message += " " + self.tr("Una pagina senza testo.")
        elif empty:
            message += " " + self.tr("{0} pagine senza testo.").format(empty)
        if cancelled:
            message = self.tr("Riconoscimento interrotto. ") + message
        # Over the page as well: the run ends behind a progress dialog, and
        # the status bar alone is easy to miss (reported by a user who did).
        self._notify(message)

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
        self._set_field_value(self._form_panel.page(), name, value)

    def _on_field_value_committed(self, row: int, name: str, value: str) -> None:
        """The user filled a field in on the page itself: record it too.

        The panel is put back in step with the page, because the two show the
        same value and the panel's editor would otherwise keep the old one.
        """
        self._set_field_value(row, name, value, refresh_panel=True)

    def _set_field_value(
        self, row: int, name: str, value: str, refresh_panel: bool = False
    ) -> None:
        """Record one field value, whichever side of the window asked."""
        if not (0 <= row < len(self._doc_model.pages)):
            return
        item = self._doc_model.pages[row]
        # What the save would write right now: the model's value, or the one
        # the file already carries when the field was never touched.
        current = next(
            (field.value for field in item.form_fields if field.name == name), ""
        )
        if item.form_values.get(name, current) == value:
            return
        self._undo_stack.push(SetFieldValue(self._doc_model, row, name, value))
        self._status.setText(self.tr("Campo «{0}» aggiornato.").format(name))
        if refresh_panel:
            self._refresh_form_panel(row)
            self._page_view.set_selected_field(row, name)

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

    def showEvent(self, event) -> None:
        """Start watching the screen as soon as there is a window handle."""
        super().showEvent(event)
        self._watch_screen()

    def _watch_screen(self) -> None:
        """Re-render at the right resolution when the window changes screen.

        Every render request reads the device pixel ratio afresh, so the only
        thing missing is the signal: dragging the window onto a monitor with a
        different scaling would otherwise keep the pixmaps rendered for the
        old one until something else happened to force a relayout.
        """
        handle = self.windowHandle()
        if handle is None or handle is self._screen_handle:
            return
        self._screen_handle = handle
        handle.screenChanged.connect(self._on_screen_changed)

    def _on_screen_changed(self, screen) -> None:
        """A different monitor: refresh pages and thumbnails for it."""
        del screen
        self._page_view.refresh_geometry()
        self._thumb_bar.refresh()

    def closeEvent(self, event) -> None:
        """Persist the UI state and shut the worker thread down cleanly."""
        if not self._confirm_discard():
            event.ignore()
            return
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
             directly from the GUI thread would touch the PyMuPDF document
             from the wrong thread).
          2. Quit the loop and wait, so the thread is no longer running
             when the window -- and this object -- are destroyed.
        """
        # A compression job is running in the thread pool and is writing a
        # file: waiting for it keeps the process from exiting mid-write.
        QThreadPool.globalInstance().waitForDone()
        if not self._thread.isRunning():
            self._remove_scratch()
            return
        QMetaObject.invokeMethod(
            self._worker, "shutdown", Qt.ConnectionType.BlockingQueuedConnection
        )
        self._thread.quit()
        if not self._thread.wait(5000):
            # A render is wedged; do not let a running thread outlive us.
            self._thread.terminate()
            self._thread.wait(2000)
        # Only now: the worker has closed its handles, so the temporaries
        # it was reading can go.
        self._remove_scratch()

    def _remove_scratch(self) -> None:
        """Delete the PDFs made from images, when Plico is done with them."""
        if self._scratch is not None:
            self._scratch.cleanup()
            self._scratch = None
