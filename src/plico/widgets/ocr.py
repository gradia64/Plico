"""OCR: choosing the pages and the languages, and reading them off the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtWidgets import (
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
    DocumentModel,
    OcrWord,
    default_language,
    languages,
    parse_page_ranges,
    user_tessdata_dir,
)

__all__ = ["OcrDialog", "OcrSignals", "OcrTask"]

# Tesseract speaks ISO 639-2, so ``ita`` and not ``it``. A code missing here is
# shown as it is: better an unexplained "dan" than a wrong Italian name.
_NAMES = {
    "ita": "Italiano",
    "eng": "Inglese",
    "deu": "Tedesco",
    "fra": "Francese",
    "spa": "Spagnolo",
    "por": "Portoghese",
    "nld": "Olandese",
    "rus": "Russo",
    "pol": "Polacco",
    "ell": "Greco",
    "tur": "Turco",
    "ara": "Arabo",
    "zho": "Cinese",
    "jpn": "Giapponese",
    "kor": "Coreano",
}


def _runs(indices: list[int]) -> str:
    """Write 0-based *indices* back as the 1-based spec the user understands."""
    runs: list[tuple[int, int]] = []
    for index in indices:
        if runs and index == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], index)
        else:
            runs.append((index, index))
    return ",".join(
        str(first + 1) if first == last else f"{first + 1}-{last + 1}" for first, last in runs
    )


class OcrDialog(QDialog):
    """Picks the pages and the languages, and says what OCR is about to do.

    The range is checked here rather than after the dialog closes: a typo
    would otherwise send the user back through the whole selection to learn
    that "5-" is not a page range.
    """

    def __init__(
        self,
        page_count: int,
        selection: list[int] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Riconosci testo"))
        self._page_count = page_count

        self._pages = QLineEdit(self)
        chosen = selection or list(range(page_count))
        self._pages.setText(_runs(chosen))
        self._pages.selectAll()

        self._language = QComboBox(self)
        for code in self._choices():
            self._language.addItem(self._label(code), code)

        self._explanation = QLabel(
            self.tr(
                "Il testo riconosciuto entra nel PDF come strato invisibile: lo si può\n"
                "selezionare, cercare e copiare, ma non si stampa e non si vede.\n"
                "Entra nel file solo al salvataggio, come ogni altra modifica."
            ),
            self,
        )
        # A page that already has text is left alone by the recognition, so
        # the tool is not going to duplicate what a born-digital PDF carries.
        self._summary = QLabel(self)
        self._summary.setWordWrap(True)
        self._summary.setMinimumWidth(420)

        fields = QFormLayout()
        fields.addRow(self.tr("Pagine:"), self._pages)
        fields.addRow(self.tr("Lingua:"), self._language)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)

        layout = QVBoxLayout(self)
        layout.addLayout(fields)
        layout.addWidget(self._explanation)
        layout.addWidget(self._summary)
        layout.addWidget(buttons)

        self._pages.textChanged.connect(self._update_summary)
        self._update_summary()

    @staticmethod
    def _choices() -> list[str]:
        """The languages to offer, the usual pair first."""
        installed = languages()
        if not installed:
            return []
        default = default_language()
        rest = [code for code in installed if code != default]
        return ([default] if default else []) + rest

    def _label(self, code: str) -> str:
        if not code:
            return self.tr("(nessuna lingua installata)")
        return " + ".join(self.tr(_NAMES.get(part, part)) for part in code.split("+"))

    @property
    def pages(self) -> list[int]:
        """The 0-based page indices to read, in the order the user typed them."""
        return parse_page_ranges(self._pages.text(), self._page_count)

    @property
    def language(self) -> str:
        return str(self._language.currentData() or "")

    def _update_summary(self) -> None:
        spec = self._pages.text()
        try:
            indices = parse_page_ranges(spec, self._page_count)
        except ValueError as error:
            self._summary.setText(str(error))
            self._ok.setEnabled(False)
            return
        count = len(indices)
        if not self.language:
            self._summary.setText(
                self.tr(
                    "Nessuna lingua installata: metti i file .traineddata di Tesseract in {0}."
                ).format(user_tessdata_dir())
            )
            self._ok.setEnabled(False)
            return
        name = self._label(self.language)
        self._summary.setText(
            self.tr("{0} pagine, lingua {1}.").format(count, name)
            if count > 1
            else self.tr("Una pagina, lingua {0}.").format(name)
        )
        self._ok.setEnabled(count > 0)


class OcrSignals(QObject):
    """A job's signals: a ``QRunnable`` is not a ``QObject``."""

    finished = Signal()
    failed = Signal(str)
    progress = Signal(int, int)  # done, total


class OcrTask(QRunnable):
    """Reads the chosen pages, one at a time, off the GUI thread.

    A scan costs seconds per page, so the loop cannot live on the GUI thread --
    and it cannot be one task per page either: the window has to fold the whole
    run into ONE undo step, which means it must know when the last page is
    done before it can close the macro. The words land in :attr:`words`, read
    once the task has finished.
    """

    def __init__(self, model: DocumentModel, indices: list[int], language: str) -> None:
        super().__init__()
        self.signals = OcrSignals()
        self.words: dict[int, list[OcrWord]] = {}
        self.error: str | None = None
        self._model = model
        self._indices = list(indices)
        self._language = language
        self._cancelled = False

    def cancel(self) -> None:
        """Ask the loop to stop: read from the GUI thread, checked between pages."""
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        total = len(self._indices)
        try:
            for done, index in enumerate(self._indices, start=1):
                if self._cancelled:
                    break
                self.words[index] = self._model.ocr_page(index, self._language)
                self.signals.progress.emit(done, total)
        except Exception as error:  # noqa: BLE001
            # Anything that goes wrong must reach the user as a message, not
            # as a stack trace on stderr.
            self.error = str(error)
            self.signals.failed.emit(self.error)
            return
        self.signals.finished.emit()
