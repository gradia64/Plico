"""Compressione: scelta del livello e lavoro fuori dal thread della GUI."""

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


def format_size(numero: int) -> str:
    """Dimensione leggibile, con la virgola decimale italiana."""
    if numero < 1024:
        return f"{numero} byte"
    if numero < 1024 * 1024:
        valore, suffisso = numero / 1024, "KB"
    elif numero < 1024 * 1024 * 1024:
        valore, suffisso = numero / (1024 * 1024), "MB"
    else:
        valore, suffisso = numero / (1024 * 1024 * 1024), "GB"
    return f"{valore:.1f}".replace(".", ",") + f" {suffisso}"


class CompressionDialog(QDialog):
    """Sceglie il livello, spiegando ogni volta cosa comporta.

    Il livello predefinito e` Medio: e` il compromesso che la maggior parte
    delle persone vuole, e la spiegazione sotto la tendina dice chiaramente
    che da li` in poi le immagini vengono ricampionate.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Salva compresso"))

        etichetta = QLabel(self.tr("Livello di compressione:"), self)

        self._scelta = QComboBox(self)
        for livello in LEVELS:
            self._scelta.addItem(livello.label, livello.key)
        self._scelta.setCurrentIndex(LEVELS.index(LEVELS_BY_KEY["medium"]))

        self._spiegazione = QLabel(self)
        self._spiegazione.setWordWrap(True)
        self._spiegazione.setMinimumWidth(380)

        bottoni = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        bottoni.accepted.connect(self.accept)
        bottoni.rejected.connect(self.reject)

        disposizione = QVBoxLayout(self)
        disposizione.addWidget(etichetta)
        disposizione.addWidget(self._scelta)
        disposizione.addWidget(self._spiegazione)
        disposizione.addWidget(bottoni)

        self._scelta.currentIndexChanged.connect(self._aggiorna_spiegazione)
        self._aggiorna_spiegazione()

    @property
    def level(self) -> CompressionLevel:
        """Il livello scelto al momento in cui si preme OK."""
        return LEVELS[self._scelta.currentIndex()]

    def _aggiorna_spiegazione(self) -> None:
        self._spiegazione.setText(LEVELS[self._scelta.currentIndex()].detail)


class CompressionSignals(QObject):
    """I segnali di un lavoro: un ``QRunnable`` non e` un ``QObject``."""

    finished = Signal(object)  # CompressionResult
    failed = Signal(str)
    progress = Signal(int)


class CompressionTask(QRunnable):
    """Materializza e comprime, fuori dal thread della GUI.

    Le due passate (clean di MuPDF e qpdf) su una scansione grande prendono
    secondi: farle nel thread della GUI congelerebbe la finestra, e con lei
    la barra di avanzamento che deve raccontare cosa sta succedendo.
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
        except Exception as e:  # noqa: BLE001
            # Qualunque cosa vada storta deve arrivare all'utente come
            # messaggio, non come traccia di stack su stderr.
            self.signals.failed.emit(str(e))
        else:
            self.signals.finished.emit(result)
