"""Compression: picking a level, and doing the work off the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..model import (
    LEVELS,
    LEVELS_BY_KEY,
    CompressionLevel,
    DocumentModel,
    save_compressed,
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
    """Picks the level, explaining each time what it costs.

    The default is Medium: it is the compromise most people want, and the
    explanation under the combo box says plainly that from there on the images
    get resampled.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Salva compresso"))

        label = QLabel(self.tr("Livello di compressione:"), self)

        self._choice = QComboBox(self)
        for level in LEVELS:
            # The level table carries source-language text; it is translated
            # here, where it actually goes on screen.
            self._choice.addItem(self.tr(level.label), level.key)
        self._choice.setCurrentIndex(LEVELS.index(LEVELS_BY_KEY["medium"]))

        self._explanation = QLabel(self)
        self._explanation.setWordWrap(True)
        self._explanation.setMinimumWidth(380)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self._choice)
        layout.addWidget(self._explanation)
        layout.addWidget(buttons)

        self._choice.currentIndexChanged.connect(self._update_explanation)
        self._update_explanation()

    @property
    def level(self) -> CompressionLevel:
        """The level selected at the moment OK is pressed."""
        return LEVELS[self._choice.currentIndex()]

    def _update_explanation(self) -> None:
        self._explanation.setText(self.tr(LEVELS[self._choice.currentIndex()].detail))


class CompressionSignals(QObject):
    """A job's signals: a ``QRunnable`` is not a ``QObject``."""

    finished = Signal(object)  # CompressionResult
    failed = Signal(str)
    progress = Signal(int)


class CompressionTask(QRunnable):
    """Materialises and compresses, off the GUI thread.

    The two passes (MuPDF's clean and qpdf) take seconds on a large scan:
    running them on the GUI thread would freeze the window, and with it the
    progress bar that has to tell the user what is going on.
    """

    def __init__(self, model: DocumentModel, out_path: str, level: CompressionLevel) -> None:
        super().__init__()
        self.signals = CompressionSignals()
        self._model = model
        self._out_path = out_path
        self._level = level

    def run(self) -> None:
        try:
            result = save_compressed(
                self._model,
                self._out_path,
                self._level,
                progress=self.signals.progress.emit,
            )
        except Exception as error:  # noqa: BLE001
            # Anything that goes wrong must reach the user as a message, not
            # as a stack trace on stderr.
            self.signals.failed.emit(str(error))
        else:
            self.signals.finished.emit(result)
