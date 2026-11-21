"""File → Proteggi con password: the password a file opens with, and what it allows."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ..model.save import Protection


class ProtectDialog(QDialog):
    """Choose a password and permissions, or no password at all.

    The permissions are a request to the programs that open the file, not a
    lock: anyone with the password reads the content, and a program that
    ignores them can print or copy it anyway. The dialog says so, rather than
    promising more than PDF encryption gives.
    """

    def __init__(self, protected: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Proteggi con password"))

        self._none = QRadioButton(self.tr("&Nessuna password"))
        self._some = QRadioButton(self.tr("&Con password"))
        self._some.setChecked(True)

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._repeat = QLineEdit()
        self._repeat.setEchoMode(QLineEdit.EchoMode.Password)
        self._print = QCheckBox(self.tr("Consenti la &stampa"))
        self._copy = QCheckBox(self.tr("Consenti di copiare il &testo"))
        self._modify = QCheckBox(self.tr("Consenti di &modificare"))
        for box in (self._print, self._copy, self._modify):
            box.setChecked(True)
        self._owner = QLineEdit()
        self._owner.setEchoMode(QLineEdit.EchoMode.Password)
        self._owner.setPlaceholderText(self.tr("facoltativa"))

        fields = QFormLayout()
        fields.addRow(self.tr("&Password:"), self._password)
        fields.addRow(self.tr("&Ripeti:"), self._repeat)
        fields.addRow(self._print)
        fields.addRow(self._copy)
        fields.addRow(self._modify)
        fields.addRow(self.tr("Password del pr&oprietario:"), self._owner)
        self._fields = QWidget()
        self._fields.setLayout(fields)

        note = QLabel(
            self.tr(
                "Il file si apre solo con la password (AES-256). I permessi sono "
                "una richiesta ai programmi che lo aprono, non un blocco. Con un "
                "limite e senza password del proprietario, Plico ne crea una che "
                "nessuno conosce: il limite non si potrà più togliere."
            )
        )
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        self._error = QLabel()
        self._error.setTextFormat(Qt.TextFormat.PlainText)
        self._error.setStyleSheet("color: #b71c1c")
        self._error.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        if protected:
            # Only a protected file has something to take away.
            layout.addWidget(self._none)
        else:
            self._none.hide()
        layout.addWidget(self._some)
        layout.addWidget(self._fields)
        layout.addWidget(note)
        layout.addWidget(self._error)
        layout.addWidget(buttons)
        self._none.toggled.connect(lambda on: self._fields.setEnabled(not on))

    def _accept(self) -> None:
        if self._some.isChecked():
            if not self._password.text():
                return self._refuse(self.tr("Scrivi una password."))
            if self._password.text() != self._repeat.text():
                return self._refuse(self.tr("Le due password non coincidono."))
        self.accept()
        return None

    def _refuse(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()

    def protection(self) -> Protection | None:
        """The protection chosen; None means "no password"."""
        if self._none.isChecked():
            return None
        return Protection.chosen(
            self._password.text(),
            self._owner.text(),
            allow_print=self._print.isChecked(),
            allow_copy=self._copy.isChecked(),
            allow_modify=self._modify.isChecked(),
        )
