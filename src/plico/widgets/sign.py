"""Dialogs for signing a document and for reading the signatures it carries.

Two halves of the same idea, kept apart on purpose. Signing asks for a
certificate and a password -- things that exist only on the user's machine and
that the program cannot check for them. Reading asks nothing: a signature is
either intact or it is not, and the dialog's job is to say which, in the plainest
words it can find, because a signature verdict is only useful if the person
reading it understands what was and was not verified.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..model.sign import (
    Identity,
    Signature,
    SignatureRequest,
    SigningError,
    read_identity,
    read_signatures,
    stamp_box,
)

_GOOD = "color: #1b5e20"
# Amber rather than red: a signature over a document that changed afterwards is
# still a true signature, of an older version. Calling it invalid would be wrong.
_WARN = "color: #8a5300"
_BAD = "color: #b00020"



def _date(moment: datetime | None) -> str:
    return moment.strftime("%d/%m/%Y") if moment else ""


class SignDialog(QDialog):
    """Collect what :func:`plico.model.sign.sign_in_place` needs."""

    def __init__(
        self, sizes: list[tuple[float, float]], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Firma il documento"))
        self._sizes = sizes
        self._identity: Identity | None = None

        self._certificate = QLineEdit()
        self._certificate.setPlaceholderText(self.tr("File del certificato (.p12)"))
        browse = QPushButton(self.tr("Sfoglia…"))
        browse.clicked.connect(self._browse)
        certificate_row = QHBoxLayout()
        certificate_row.addWidget(self._certificate)
        certificate_row.addWidget(browse)

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText(self.tr("Password del certificato"))

        self._identity_label = QLabel()
        self._identity_label.setWordWrap(True)

        self._reason = QLineEdit()
        self._reason.setPlaceholderText(self.tr("Perché firmi (facoltativo)"))
        self._location = QLineEdit()
        self._location.setPlaceholderText(self.tr("Dove (facoltativo)"))

        self._visible = QCheckBox(self.tr("Riquadro visibile sulla pagina"))
        self._page = QSpinBox()
        self._page.setRange(1, max(1, len(sizes)))
        self._page.setEnabled(False)
        self._visible.toggled.connect(self._page.setEnabled)
        visible_row = QHBoxLayout()
        visible_row.addWidget(self._visible)
        visible_row.addWidget(QLabel(self.tr("pagina")))
        visible_row.addWidget(self._page)
        visible_row.addStretch(1)

        form = QFormLayout()
        form.addRow(self.tr("Certificato"), certificate_row)
        form.addRow(self.tr("Password"), self._password)
        form.addRow("", self._identity_label)
        form.addRow(self.tr("Motivo"), self._reason)
        form.addRow(self.tr("Luogo"), self._location)
        form.addRow("", visible_row)

        note = QLabel(
            self.tr(
                "La firma copre il file appena salvato: il documento si riapre "
                "dalla copia firmata e ogni modifica successiva la annulla."
            )
        )
        note.setWordWrap(True)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText(self.tr("Firma"))
        self._ok.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(self._buttons)

        # Reading the certificate hits the disk and decrypts it, so it waits for
        # a pause in the typing rather than running on every keystroke.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._read)
        self._certificate.textChanged.connect(self._timer.start)
        self._password.textChanged.connect(self._timer.start)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Scegli il certificato"),
            "",
            # PKCS#12 only: a .pem holds no private key Plico can use, and
            # offering it led straight to "cannot read the certificate"
            # (reported by a review). The trusted roots, which ARE .pem, have
            # their own dialog.
            self.tr("Certificati (*.p12 *.pfx);;Tutti i file (*)"),
        )
        if path:
            self._certificate.setText(path)

    def _read(self) -> None:
        """Try the certificate currently typed, and say what is wrong."""
        path = self._certificate.text().strip()
        self._identity = None
        self._ok.setEnabled(False)
        if not path:
            self._identity_label.clear()
            return
        try:
            identity = read_identity(path, self._password.text())
        except SigningError as error:
            self._identity_label.setStyleSheet(_BAD)
            self._identity_label.setText(str(error))
            return
        expired = identity.not_after < datetime.now(identity.not_after.tzinfo)
        self._identity = None if expired else identity
        if expired:
            self._identity_label.setStyleSheet(_BAD)
            self._identity_label.setText(
                self.tr("Il certificato è scaduto il {0}.").format(_date(identity.not_after))
            )
            return
        self._identity_label.setStyleSheet(_GOOD)
        self._identity_label.setText(
            self.tr("{0}\nvalido fino al {1}").format(
                identity.label, _date(identity.not_after)
            )
        )
        self._ok.setEnabled(True)

    def request(self) -> SignatureRequest:
        """The request built from what the user chose."""
        page: int | None = None
        box: tuple[float, float, float, float] | None = None
        if self._visible.isChecked():
            page = self._page.value() - 1
            width, height = self._sizes[page]
            box = stamp_box(width, height)
        return SignatureRequest(
            certificate=self._certificate.text().strip(),
            password=self._password.text(),
            reason=self._reason.text().strip(),
            location=self._location.text().strip(),
            page=page,
            box=box,
        )


class SignatureDialog(QDialog):
    """Show the verdict on every signature of a file.

    *roots* are PEM files the user decided to trust; the dialog adds to them and
    hands the list back, so the window can remember the decision. Without one,
    ``trusted`` is false for every signature and the dialog says so instead of
    pretending to know who the signer is.
    """

    def __init__(
        self,
        path: str,
        roots: list[str] | None = None,
        password: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Firme del documento"))
        self.resize(520, 320)
        self._path = path
        self._password = password
        self.roots = list(roots or [])

        self._body = QVBoxLayout()
        self._body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._body.setSpacing(10)

        self._trust = QPushButton(self.tr("Aggiungi un certificato fidato…"))
        self._trust.clicked.connect(self._add_root)
        close = QPushButton(self.tr("Chiudi"))
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self._trust)
        buttons.addStretch(1)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addLayout(self._body)
        layout.addStretch(1)
        layout.addLayout(buttons)
        self._load()

    def _add_root(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Scegli un certificato da considerare fidato"), "", "*.pem"
        )
        if path and path not in self.roots:
            self.roots.append(path)
            self._load()

    def _clear(self) -> None:
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

    def _load(self) -> None:
        """Read the signatures again, with the roots decided so far."""
        self._clear()
        self._trust.setEnabled(bool(self._path))
        try:
            signatures = read_signatures(self._path, roots=self.roots, password=self._password)
        except SigningError as error:
            message = QLabel(str(error))
            message.setStyleSheet(_BAD)
            message.setWordWrap(True)
            self._body.addWidget(message)
            return
        if not signatures:
            self._body.addWidget(QLabel(self.tr("Il documento non contiene firme.")))
            return
        for signature in signatures:
            self._body.addWidget(_signature_block(signature))


def _signature_block(signature: Signature) -> QWidget:
    """One signature, described in the order a reader needs it."""
    block = QWidget()
    layout = QVBoxLayout(block)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    who = QLabel(signature.identity.label if signature.identity else signature.field_name)
    font = who.font()
    font.setBold(True)
    who.setFont(font)
    layout.addWidget(who)

    details: list[str] = []
    if signature.signed_at is not None:
        details.append(
            signature.signed_at.strftime("%d/%m/%Y %H:%M")
        )
    if signature.algorithm:
        details.append(signature.algorithm)
    if signature.identity is not None and signature.identity.organization:
        details.append(signature.identity.organization)
    if details:
        line = QLabel(" · ".join(details))
        line.setStyleSheet("color: #555")
        layout.addWidget(line)

    verdict, style = _verdict(signature)
    message = QLabel(verdict)
    message.setStyleSheet(style)
    message.setWordWrap(True)
    layout.addWidget(message)
    return block


def _verdict(signature: Signature) -> tuple[str, str]:
    """What to say about one signature, and how loudly."""
    if signature.error:
        return signature.error, _BAD
    # First, before "changed": a broken signature over a file that also has
    # later revisions is still broken, and calling it "integra" would be the
    # one reassurance this dialog must never give.
    if not signature.intact:
        return (
            QCoreApplication.translate(
                "SignatureDialog",
                "La firma è rotta: il contenuto che copriva è stato cambiato dopo la firma."
            ),
            _BAD,
        )
    if signature.changed:
        return (
            QCoreApplication.translate(
                "SignatureDialog",
                "La firma è integra, ma il documento è stato modificato dopo: "
                "vale solo per la versione che è stata firmata."
            ),
            _WARN,
        )
    if not signature.valid:
        return (
            QCoreApplication.translate(
                "SignatureDialog",
                "La firma non è valida: non corrisponde al certificato che la porta.",
            ),
            _BAD,
        )
    if not signature.trusted:
        return (
            QCoreApplication.translate(
                "SignatureDialog",
                "Firma integra e valida. Il certificato però non è fra quelli che "
                "consideri fidati: aggiungi la sua autorità per sapere chi ha firmato."
            ),
            _WARN,
        )
    return (
        QCoreApplication.translate("SignatureDialog", "Firma valida e firmatario attendibile."),
        _GOOD,
    )
