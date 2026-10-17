"""Compression: what to compress, and doing the work off the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ..model import (
    LEVELS,
    LEVELS_BY_KEY,
    CompressionLevel,
    CompressionOptions,
    CompressionPreview,
    DocumentModel,
    parse_page_ranges,
    prepare_compressed,
)

__all__ = ["CompressionDialog", "CompressionTask", "format_size"]


def format_size(size: int) -> str:
    """A readable size, with the Italian decimal comma."""
    if size < 1024:
        return f"{size} byte"
    if size < 1024 * 1024:
        value, suffix = size / 1024, "KB"
    elif size < 1024 * 1024 * 1024:
        value, suffix = size / (1024 * 1024), "MB"
    else:
        value, suffix = size / (1024 * 1024 * 1024), "GB"
    return f"{value:.1f}".replace(".", ",") + f" {suffix}"


class CompressionDialog(QDialog):
    """Picks what to compress, explaining each time what it costs.

    The level is the shortcut: one choice sets the image step and everything
    around it. The two controls under it are what a preset cannot say -- do
    without the structural pass, and leave some pages' images alone -- and they
    only come alive where they mean something, i.e. where the level resamples
    images at all.

    The default is Medium: it is the compromise most people want, and the
    explanation under the combo box says plainly that from there on the images
    get resampled.
    """

    def __init__(self, page_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Salva compresso"))
        self._page_count = page_count

        label = QLabel(self.tr("Livello di compressione:"), self)

        self._choice = QComboBox(self)
        for level in LEVELS:
            # The level table carries source-language text; it is translated
            # here, where it actually goes on screen.
            self._choice.addItem(self.tr(level.label), level.key)
        self._choice.setCurrentIndex(LEVELS.index(LEVELS_BY_KEY["medium"]))

        self._images_only = QCheckBox(self.tr("Solo le immagini, senza ricompattare il file"))
        self._images_only.setToolTip(
            self.tr(
                "La ricompattazione non perde nulla: saltarla ha senso solo per "
                "lasciare il file com'e` dovunque non ci siano immagini."
            )
        )

        self._pages = QLineEdit(self)
        self._pages.setPlaceholderText(self.tr("tutte"))

        fields = QFormLayout()
        fields.addRow(self.tr("Pagine da ricampionare:"), self._pages)

        self._explanation = QLabel(self)
        self._explanation.setWordWrap(True)
        self._explanation.setMinimumWidth(380)

        self._summary = QLabel(self)
        self._summary.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self._choice)
        layout.addWidget(self._explanation)
        layout.addWidget(self._images_only)
        layout.addLayout(fields)
        layout.addWidget(self._summary)
        layout.addWidget(buttons)

        self._choice.currentIndexChanged.connect(self._update)
        self._pages.textChanged.connect(self._update)
        self._images_only.toggled.connect(self._update)
        self._update()

    @property
    def level(self) -> CompressionLevel:
        """The level selected at the moment OK is pressed."""
        return LEVELS[self._choice.currentIndex()]

    @property
    def options(self) -> CompressionOptions:
        """The level, plus the two adjustments this dialog can express."""
        return CompressionOptions(
            level=self.level,
            groom=not self._images_only.isChecked(),
            image_pages=self._chosen_pages(),
        )

    def _chosen_pages(self) -> tuple[int, ...] | None:
        """``None`` means every page, which is what an empty field means."""
        spec = self._pages.text().strip()
        if not spec:
            return None
        return tuple(parse_page_ranges(spec, self._page_count))

    def _update(self) -> None:
        level = self.level
        images = level.rewrites_images

        if not images and self._images_only.isChecked():
            # A level that leaves the images alone has nothing left to do
            # without the structural pass: unchecking keeps the dialog from
            # promising "only the images" and then producing nothing.
            self._images_only.setChecked(False)
            return

        text = self.tr(level.detail)
        if images and self._images_only.isChecked():
            text += self.tr("\nIl file non viene ricompattato: cambiano solo le immagini.")
        self._explanation.setText(text)

        self._images_only.setEnabled(images)
        self._pages.setEnabled(images)
        if not images:
            self._summary.setText("")
            self._ok.setEnabled(True)
            return

        spec = self._pages.text().strip()
        if not spec:
            self._summary.setText(self.tr("Le immagini di tutte le pagine vengono ricampionate."))
            self._ok.setEnabled(True)
            return

        try:
            indices = parse_page_ranges(spec, self._page_count)
        except ValueError as error:
            # The message is written for the user, so show it verbatim.
            self._summary.setText(str(error))
            self._ok.setEnabled(False)
            return

        self._summary.setText(
            self.tr("Le immagini di {0} pagine vengono ricampionate.").format(len(indices))
            if len(indices) > 1
            else self.tr("Le immagini di una pagina vengono ricampionate.")
        )
        self._ok.setEnabled(bool(indices))


class CompressionSignals(QObject):
    """A job's signals: a ``QRunnable`` is not a ``QObject``."""

    finished = Signal(object)  # CompressionPreview
    failed = Signal(str)
    progress = Signal(int)


class CompressionTask(QRunnable):
    """Materialises and compresses, off the GUI thread.

    The two passes (MuPDF's clean and qpdf) take seconds on a large scan:
    running them on the GUI thread would freeze the window, and with it the
    progress bar that has to tell the user what is going on.

    What comes back is a :class:`CompressionPreview`: the file is written, but
    not yet where it belongs. The window shows what was gained and only then
    decides whether to keep it, so the number is the real one and the passes
    run once.
    """

    def __init__(
        self, model: DocumentModel, out_path: str, options: CompressionOptions
    ) -> None:
        super().__init__()
        self.signals = CompressionSignals()
        self._model = model
        self._out_path = out_path
        self._options = options

    def run(self) -> None:
        try:
            preview: CompressionPreview = prepare_compressed(
                self._model,
                self._out_path,
                self._options,
                progress=self.signals.progress.emit,
            )
        except Exception as error:  # noqa: BLE001
            # Anything that goes wrong must reach the user as a message, not
            # as a stack trace on stderr.
            self.signals.failed.emit(str(error))
        else:
            self.signals.finished.emit(preview)
