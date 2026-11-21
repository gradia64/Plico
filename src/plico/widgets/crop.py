"""Modifica → Ritaglia margini: how much to take off each side, and of which pages."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

MM = 72 / 25.4  # points per millimetre

Margins = tuple[float, float, float, float]  # top, right, bottom, left, in points


class CropDialog(QDialog):
    """Four margins in millimetres, as seen on screen, and the pages they apply to.

    *margins* are the current page's, in points. *detect* returns the margins
    that leave only the content of the current page (None for a blank page).
    """

    def __init__(
        self,
        margins: Margins,
        page_count: int,
        detect: Callable[[], Margins | None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Ritaglia margini"))
        self._detect = detect

        self._boxes: list[QDoubleSpinBox] = []
        fields = QFormLayout()
        for label, value in zip(
            (self.tr("S&opra:"), self.tr("&Destra:"), self.tr("So&tto:"), self.tr("&Sinistra:")),
            margins,
            strict=True,
        ):
            box = QDoubleSpinBox()
            box.setRange(0.0, 500.0)
            box.setDecimals(1)
            box.setSingleStep(1.0)
            box.setSuffix(" mm")
            box.setValue(round(value / MM, 1))
            fields.addRow(label, box)
            self._boxes.append(box)

        detect_button = QPushButton(self.tr("&Rileva dal contenuto"))
        detect_button.setToolTip(self.tr("Margini che lasciano solo il contenuto di questa pagina"))
        detect_button.clicked.connect(self._fill_from_content)
        clear_button = QPushButton(self.tr("&Nessun margine"))
        clear_button.clicked.connect(lambda: self.set_margins_mm(0.0, 0.0, 0.0, 0.0))
        tools = QHBoxLayout()
        tools.addWidget(detect_button)
        tools.addWidget(clear_button)
        tools.addStretch(1)

        self._this = QRadioButton(self.tr("&Questa pagina"))
        self._all = QRadioButton(self.tr("T&utte le pagine ({0})").format(page_count))
        self._this.setChecked(True)

        note = QLabel(
            self.tr(
                "Il ritaglio nasconde, non cancella: quello che resta fuori rimane "
                "nel file. Per eliminare un dato usa Cancella zona."
            )
        )
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        self._notice = QLabel()
        self._notice.setTextFormat(Qt.TextFormat.PlainText)
        self._notice.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(fields)
        layout.addLayout(tools)
        layout.addWidget(self._notice)
        layout.addWidget(self._this)
        layout.addWidget(self._all)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _fill_from_content(self) -> None:
        found = self._detect()
        if found is None:
            self._notice.setText(self.tr("Questa pagina è vuota: nessun margine da rilevare."))
            self._notice.show()
            return
        self._notice.hide()
        for box, value in zip(self._boxes, found, strict=True):
            box.setValue(round(value / MM, 1))

    def margins(self) -> Margins:
        """The margins chosen, in points: top, right, bottom, left."""
        top, right, bottom, left = (box.value() * MM for box in self._boxes)
        return (top, right, bottom, left)

    def all_pages(self) -> bool:
        return self._all.isChecked()

    def set_margins_mm(self, top: float, right: float, bottom: float, left: float) -> None:
        """For tests and scripts: type the four values."""
        for box, value in zip(self._boxes, (top, right, bottom, left), strict=True):
            box.setValue(value)

    def choose_all_pages(self, every: bool) -> None:
        (self._all if every else self._this).setChecked(True)
