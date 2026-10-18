"""Digital signatures: producing one, reading it back, and what saves do to it.

The certificate here is generated on the spot, never shipped: a real one would
be someone's identity in the repository, and a test certificate is a pile of
bytes that says "Mario Rossi" and nobody believes. What is tested is the
plumbing -- the file gets signed, the verdict is read back from the bytes,
and the two ways a signature can go stale (a later edit, a later save) are
reported instead of hidden.
"""

import datetime
import os

import pymupdf
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    pkcs12,
)
from cryptography.x509.oid import NameOID
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from plico.main_window import MainWindow
from plico.model import (
    DocumentModel,
    SigningError,
    is_signed,
    read_identity,
    read_signatures,
    save_as,
    save_signed,
    sign_in_place,
    stamp_box,
    stamp_text,
)
from plico.model.forms import SIGNATURE, read_fields
from plico.model.sign import SignatureRequest
from plico.widgets.sign import SignatureDialog, SignDialog, _verdict

PASSWORD = "prova"


def _bytes(path: str) -> bytes:
    """The whole file, for the tests that compare it before and after."""
    with open(path, "rb") as handle:
        return handle.read()


def _build_certificate(path, name: x509.Name, days: int = 3650) -> None:
    """Write a self-signed PKCS#12 at *path*, plus its PEM next to it."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    with open(os.path.join(os.path.dirname(path), "root.pem"), "wb") as handle:
        handle.write(certificate.public_bytes(Encoding.PEM))
    blob = pkcs12.serialize_key_and_certificates(
        b"Mario Rossi", key, certificate, None,
        BestAvailableEncryption(PASSWORD.encode()),
    )
    with open(path, "wb") as handle:
        handle.write(blob)


@pytest.fixture(scope="module")
def certificate(tmp_path_factory) -> tuple[str, str]:
    """A PKCS#12 file and the PEM of the same certificate, to trust it with."""
    folder = tmp_path_factory.mktemp("certificato")
    path = str(folder / "firma.p12")
    _build_certificate(
        path,
        x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "IT"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Studio Rossi"),
                x509.NameAttribute(NameOID.COMMON_NAME, "Mario Rossi"),
            ]
        ),
    )
    return path, str(folder / "root.pem")


def _plain_pdf(path, pages: int = 2) -> None:
    with pymupdf.open() as doc:
        for _ in range(pages):
            doc.new_page(width=595, height=842)
        doc.save(path)


def _request(certificate: str, **kwargs) -> SignatureRequest:
    return SignatureRequest(certificate=certificate, password=PASSWORD, **kwargs)


# --------------------------------------------------------------------- #
#  The certificate
# --------------------------------------------------------------------- #


def test_reading_the_identity_of_a_certificate(certificate) -> None:
    """What the signing dialog shows before anything is signed."""
    identity = read_identity(certificate[0], PASSWORD)

    assert identity.common_name == "Mario Rossi"
    assert identity.organization == "Studio Rossi"
    assert identity.country == "IT"
    assert identity.label == "Mario Rossi (Studio Rossi)"
    assert identity.not_after > datetime.datetime.now(datetime.UTC)


def test_a_wrong_password_is_reported_as_such(certificate) -> None:
    """The password is the only thing between an error and a crash here."""
    with pytest.raises(SigningError) as error:
        read_identity(certificate[0], "sbagliata")

    assert "Password errata" in str(error.value)


def test_a_file_that_is_not_a_pkcs12_says_so(certificate) -> None:
    """A PEM is a certificate, not a certificate *and its key*."""
    with pytest.raises(SigningError) as error:
        read_identity(certificate[1], PASSWORD)

    assert "non è un file PKCS#12" in str(error.value)


def test_a_missing_certificate_names_the_file() -> None:
    with pytest.raises(SigningError) as error:
        read_identity("/non/esiste/firma.p12", PASSWORD)

    assert "firma.p12" in str(error.value)


# --------------------------------------------------------------------- #
#  Signing
# --------------------------------------------------------------------- #


def test_signing_an_invisible_signature(certificate, tmp_path) -> None:
    """The plain case: the file is signed, and the verdict says so."""
    path = str(tmp_path / "documento.pdf")
    _plain_pdf(path)

    sign_in_place(path, _request(certificate[0], reason="Approvazione"))

    assert is_signed(path)
    signatures = read_signatures(path)
    assert len(signatures) == 1
    signature = signatures[0]
    assert signature.identity is not None
    assert signature.identity.common_name == "Mario Rossi"
    assert signature.algorithm == "sha256"
    assert signature.intact
    assert signature.valid
    assert signature.covers_whole_file
    assert not signature.changed
    assert signature.ok


def test_the_certificate_is_not_trusted_until_told_so(certificate, tmp_path) -> None:
    """A signature over an unknown chain is valid, not trustworthy.

    Plico ships no certificate store, so this is the normal case: the verdict
    must say "integro, ma non so chi sia" rather than invent an authority.
    """
    path = str(tmp_path / "documento.pdf")
    _plain_pdf(path)
    sign_in_place(path, _request(certificate[0]))

    untrusted = read_signatures(path)[0]
    trusted = read_signatures(path, roots=[certificate[1]])[0]

    assert untrusted.intact and untrusted.valid
    assert not untrusted.trusted
    assert trusted.trusted


def test_a_visible_signature_prints_who_and_why(certificate, tmp_path) -> None:
    """The stamp is page content: it is read back like any other text."""
    path = str(tmp_path / "documento.pdf")
    _plain_pdf(path)

    sign_in_place(
        path,
        _request(
            certificate[0], reason="Visto", page=0, box=stamp_box(595, 842)
        ),
    )

    with pymupdf.open(path) as doc:
        text = doc[0].get_text()
        widgets = [widget for widget in doc[0].widgets() or ()]
    assert "Firmato da Mario Rossi" in text
    assert "Visto" in text
    assert len(widgets) == 1
    assert widgets[0].field_type_string == "Signature"


def test_the_stamp_box_is_given_in_pdf_coordinates(certificate, tmp_path) -> None:
    """``/Rect`` counts from the bottom-left corner, the widget reader does not.

    Getting this wrong puts the stamp at the top of the page, or off it, and
    the mistake only shows once the file is opened in another reader.
    """
    path = str(tmp_path / "documento.pdf")
    _plain_pdf(path)
    box = stamp_box(595, 842)
    sign_in_place(path, _request(certificate[0], page=0, box=box))

    with pymupdf.open(path) as doc:
        widget = next(iter(doc[0].widgets() or ()))
        height = doc[0].rect.height
    # The widget's own rectangle has its origin at the top, so the PDF box is
    # mirrored vertically around the page height.
    assert widget.rect.y0 == pytest.approx(height - box[3], abs=1)
    assert widget.rect.y1 == pytest.approx(height - box[1], abs=1)


def test_the_stamp_stays_on_the_page() -> None:
    """A page narrower than the stamp gets it at the left edge, not off it."""
    left, bottom, right, top = stamp_box(120, 400)

    assert left >= 0
    assert right <= 120
    assert bottom >= 0
    assert top <= 400


def test_the_stamp_text_mentions_the_reason_only_when_there_is_one() -> None:
    assert "%(name)s" in stamp_text("")
    assert "%(reason)s" not in stamp_text("   ")
    assert "%(reason)s" in stamp_text("Approvazione")


def test_a_signature_over_a_modified_file_says_it_is_old(certificate, tmp_path) -> None:
    """An edit after signing does not make the signature false: it makes it old.

    Saying "non valida" here would be a lie -- the bytes that were signed are
    intact -- and saying nothing would be worse.
    """
    path = str(tmp_path / "documento.pdf")
    _plain_pdf(path)
    sign_in_place(path, _request(certificate[0]))
    with pymupdf.open(path) as doc:
        doc[0].insert_text((72, 72), "aggiunto dopo la firma")
        doc.saveIncr()

    signature = read_signatures(path)[0]

    assert signature.intact
    assert signature.valid
    assert not signature.covers_whole_file
    assert signature.changed
    assert not signature.ok


def test_a_second_signature_gets_a_field_of_its_own(certificate, tmp_path) -> None:
    """Signing an already signed document adds to it, it does not fail.

    The window asks before doing this and promises a second signature on top
    of the first. One field cannot hold two signatures -- pyHanko refuses to
    fill a field twice -- so the second one needs a name of its own.
    """
    path = str(tmp_path / "documento.pdf")
    _plain_pdf(path)
    sign_in_place(path, _request(certificate[0]))

    sign_in_place(path, _request(certificate[0], reason="Seconda firma"))

    signatures = read_signatures(path)
    assert [signature.field_name for signature in signatures] == ["Firma", "Firma 2"]
    assert all(signature.intact for signature in signatures)
    assert signatures[-1].covers_whole_file


def test_a_plain_file_has_no_signatures(tmp_path) -> None:
    path = str(tmp_path / "documento.pdf")
    _plain_pdf(path)

    assert not is_signed(path)
    assert read_signatures(path) == []


# --------------------------------------------------------------------- #
#  Saving a signed document
# --------------------------------------------------------------------- #


def test_saving_a_signed_document_signs_the_written_file(certificate, tmp_path) -> None:
    """``save_signed`` = the save path, then the signature, then the swap.

    The source is untouched: what gets signed is the materialised document,
    exactly as it would have been written.
    """
    source = str(tmp_path / "sorgente.pdf")
    target = str(tmp_path / "firmato.pdf")
    _plain_pdf(source, pages=3)
    model = DocumentModel()
    model.open(source)

    save_signed(model, target, _request(certificate[0]))

    assert model.page_count == 3
    assert not is_signed(source)
    assert is_signed(target)
    with pymupdf.open(target) as doc:
        assert doc.page_count == 3


def test_a_failed_signature_leaves_the_old_file_alone(certificate, tmp_path) -> None:
    """Signing runs inside the temporary, so a bad password costs nothing."""
    target = str(tmp_path / "documento.pdf")
    _plain_pdf(target)
    before = _bytes(target)
    model = DocumentModel()
    model.open(target)

    with pytest.raises(SigningError):
        save_signed(
            model,
            target,
            SignatureRequest(certificate=certificate[0], password="sbagliata"),
        )

    assert _bytes(target) == before
    assert not is_signed(target)


def test_a_signature_field_is_not_an_editable_form_field(certificate, tmp_path) -> None:
    """The form panel offers what can be written, and a signature cannot.

    PyMuPDF reports it as a widget like any other; offering it for typing
    would be an editor that silently does nothing.
    """
    path = str(tmp_path / "documento.pdf")
    _plain_pdf(path, pages=1)
    sign_in_place(
        path, _request(certificate[0], page=0, box=stamp_box(595, 842))
    )

    with pymupdf.open(path) as doc:
        fields = read_fields(doc[0])

    assert [field.kind for field in fields] == [SIGNATURE]
    assert not fields[0].editable


# --------------------------------------------------------------------- #
#  The dialogs
# --------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    """A real MainWindow, shut down for sure."""
    mw = MainWindow()
    yield mw
    mw.shutdown_worker()
    mw.deleteLater()
    qapp.processEvents()


def test_the_signing_dialog_refuses_a_certificate_it_cannot_read(qapp) -> None:
    """OK stays disabled: a signature made with the wrong file is a bad file."""
    dialog = SignDialog([(595.0, 842.0)])
    dialog._certificate.setText("/non/esiste/firma.p12")

    dialog._read()

    assert not dialog._ok.isEnabled()
    assert "firma.p12" in dialog._identity_label.text()


def test_the_signing_dialog_reads_the_certificate_and_builds_the_request(
    qapp, certificate
) -> None:
    """The request carries the box for the page the user chose."""
    dialog = SignDialog([(595.0, 842.0), (421.0, 595.0)])
    dialog._certificate.setText(certificate[0])
    dialog._password.setText(PASSWORD)
    dialog._read()
    dialog._reason.setText("Approvazione")
    dialog._visible.setChecked(True)
    dialog._page.setValue(2)

    request = dialog.request()

    assert dialog._ok.isEnabled()
    assert "Mario Rossi" in dialog._identity_label.text()
    assert request.certificate == certificate[0]
    assert request.reason == "Approvazione"
    assert request.page == 1
    assert request.box is not None
    assert request.box[2] <= 421


def test_the_verdict_of_a_signature_names_the_problem(certificate, tmp_path) -> None:
    """The three answers a reader needs, and none of them in the wrong colour."""
    path = str(tmp_path / "documento.pdf")
    _plain_pdf(path)
    sign_in_place(path, _request(certificate[0]))
    good = read_signatures(path, roots=[certificate[1]])[0]
    untrusted = read_signatures(path)[0]
    with pymupdf.open(path) as doc:
        doc[0].insert_text((72, 72), "dopo")
        doc.saveIncr()
    old = read_signatures(path)[0]

    assert "attendibile" in _verdict(good)[0]
    assert "non è fra quelli" in _verdict(untrusted)[0]
    assert "modificato dopo" in _verdict(old)[0]


def test_the_signature_dialog_lists_what_the_file_carries(
    qapp, certificate, tmp_path
) -> None:
    path = str(tmp_path / "documento.pdf")
    _plain_pdf(path)
    sign_in_place(path, _request(certificate[0]))

    dialog = SignatureDialog(path, roots=[certificate[1]])

    assert dialog.windowTitle() == "Firme del documento"


def test_signing_from_the_window_adopts_the_signed_file(
    window, certificate, tmp_path, monkeypatch
) -> None:
    """After signing, the signed file IS the document.

    Carrying on with the page list that produced it would let the very next
    save drop the signature -- the one thing that must not happen quietly.
    """
    import plico.main_window as window_module

    source = str(tmp_path / "documento.pdf")
    target = str(tmp_path / "firmato.pdf")
    _plain_pdf(source)
    window.open_document(source)
    request = _request(certificate[0])

    class FakeDialog:
        def __init__(self, sizes, parent=None):
            assert len(sizes) == 2

        def exec(self):
            return QDialog.DialogCode.Accepted

        def request(self):
            return request

    monkeypatch.setattr(window_module, "SignDialog", FakeDialog)
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: (target, "")
    )

    window._sign_file()

    assert window._save_target == target
    assert window._signed_on_disk
    assert "firmato" in window.windowTitle()
    assert window._doc_model.page_count == 2
    assert is_signed(target)


def test_verifying_from_the_window_reads_the_file_on_disk(
    window, certificate, tmp_path, monkeypatch
) -> None:
    """The dialog is handed the path and the roots the user trusted before."""
    import plico.main_window as window_module

    source = str(tmp_path / "documento.pdf")
    _plain_pdf(source)
    window.open_document(source)
    window._settings().setValue("firma/radici", [certificate[1]])
    seen: dict[str, object] = {}

    class FakeDialog:
        def __init__(self, path, roots=None, password="", parent=None):
            seen["path"] = path
            seen["roots"] = list(roots or [])
            self.roots = list(roots or [])

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(window_module, "SignatureDialog", FakeDialog)

    window._verify_signatures()

    assert seen["path"] == source
    assert seen["roots"] == [certificate[1]]


def test_saving_a_signed_document_asks_before_dropping_the_signature(
    window, certificate, tmp_path, monkeypatch
) -> None:
    """A plain save writes a file without the signature: ask, and obey "no"."""
    source = str(tmp_path / "documento.pdf")
    _plain_pdf(source)
    window.open_document(source)
    sign_in_place(source, _request(certificate[0]))
    window.open_document(source)
    assert window._signed_on_disk
    before = _bytes(source)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: QMessageBox.StandardButton.Cancel,
    )

    saved = window._save_file()

    assert not saved
    assert _bytes(source) == before
    assert is_signed(source)


def test_saving_an_unsigned_document_never_asks(window, tmp_path, monkeypatch) -> None:
    """The question is about a signature that exists, not about saving."""
    source = str(tmp_path / "documento.pdf")
    _plain_pdf(source)
    window.open_document(source)
    asked: list[str] = []

    def question(*args, **kwargs):
        asked.append("chiesto")
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", question)

    assert window._save_file()
    assert asked == []


def test_the_proposed_signed_path_sits_next_to_the_original(window, tmp_path) -> None:
    source = str(tmp_path / "documento.pdf")
    _plain_pdf(source)
    window.open_document(source)

    assert window._proposed_signed_path() == str(tmp_path / "documento-firmato.pdf")


def test_save_as_of_a_ready_document_matches_a_plain_save(certificate, tmp_path) -> None:
    """``save_signed`` must not change what the page list turns into.

    Both go through the same writer; only the signing step differs. If they
    ever diverged, the signed file would be a different document.
    """
    source = str(tmp_path / "sorgente.pdf")
    plain = str(tmp_path / "plain.pdf")
    signed = str(tmp_path / "signed.pdf")
    _plain_pdf(source, pages=2)
    model = DocumentModel()
    model.open(source)

    save_as(model, plain)
    save_signed(model, signed, _request(certificate[0], reason="Prova"))

    with pymupdf.open(plain) as one, pymupdf.open(signed) as two:
        assert one.page_count == two.page_count
        assert [page.rect for page in one] == [page.rect for page in two]
        assert one[0].get_text() == two[0].get_text()


# --------------------------------------------------------------------- #
#  A second signature from the window
# --------------------------------------------------------------------- #


def _sign_from_window(window, monkeypatch, request, target, answer) -> list[str]:
    """Run File → Firma with the dialogs answered; return the questions asked."""
    import plico.main_window as window_module

    class FakeDialog:
        def __init__(self, sizes, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def request(self):
            return request

    asked: list[str] = []

    def question(parent, title, text, *args, **kwargs):
        asked.append(text)
        return answer

    monkeypatch.setattr(window_module, "SignDialog", FakeDialog)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (target, ""))
    monkeypatch.setattr(QMessageBox, "question", question)
    window._sign_file()
    return asked


def test_a_second_signature_from_the_window_keeps_the_first_valid(
    window, certificate, tmp_path, monkeypatch
) -> None:
    """The window promises the second signature is added to the first.

    It used to rebuild the file from its pages before signing, and a rebuilt
    file is new bytes: the first signature came out with ``intact=False``.
    """
    source = str(tmp_path / "documento.pdf")
    first = str(tmp_path / "firmato.pdf")
    second = str(tmp_path / "firmato-due.pdf")
    _plain_pdf(source)
    window.open_document(source)
    _sign_from_window(window, monkeypatch, _request(certificate[0]), first, None)
    assert window._signed_on_disk

    asked = _sign_from_window(
        window,
        monkeypatch,
        _request(certificate[0], reason="Seconda"),
        second,
        QMessageBox.StandardButton.Yes,
    )

    assert any("si aggiunge alla prima" in text for text in asked)
    signatures = read_signatures(second)
    assert [s.field_name for s in signatures] == ["Firma", "Firma 2"]
    assert all(s.intact and s.valid for s in signatures)
    assert signatures[-1].covers_whole_file
    assert window._save_target == second


def test_signing_unsaved_changes_says_the_old_signature_goes(
    window, certificate, tmp_path, monkeypatch
) -> None:
    """Changes can only be signed by rewriting the file: say what that costs."""
    source = str(tmp_path / "documento.pdf")
    target = str(tmp_path / "firmato.pdf")
    _plain_pdf(source)
    sign_in_place(source, _request(certificate[0]))
    window.open_document(source)
    window._rotate_cw_clicked()
    assert window.is_modified()

    asked = _sign_from_window(
        window,
        monkeypatch,
        _request(certificate[0]),
        target,
        QMessageBox.StandardButton.Cancel,
    )

    assert any("non sarà più valida" in text for text in asked)
    assert not os.path.exists(target)


def test_a_broken_signature_is_never_called_intact(certificate, tmp_path) -> None:
    """``intact`` comes first: a broken signature on a file that also has
    later revisions used to read «La firma è integra, ma … modificato dopo»."""
    source = str(tmp_path / "documento.pdf")
    signed = str(tmp_path / "firmato.pdf")
    rebuilt = str(tmp_path / "riscritto.pdf")
    _plain_pdf(source)
    sign_in_place(source, _request(certificate[0]))
    model = DocumentModel()
    model.open(source)
    save_as(model, signed)
    sign_in_place(signed, _request(certificate[0]))
    model = DocumentModel()
    model.open(signed)
    save_signed(model, rebuilt, _request(certificate[0]))

    broken = next(s for s in read_signatures(rebuilt) if not s.intact)
    text, style = _verdict(broken)

    assert "integra" not in text
    assert "rotta" in text
    assert style == "color: #b00020"
