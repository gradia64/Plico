"""What a hostile or careless PDF must not be able to do to Plico.

One test (or a few) per finding of a penetration test of 0.1.7: a protected
file saved in the clear, a redaction that left a vertical word in the file,
a signature hidden by a cleared flag, temporaries other users could read,
documents built to freeze the window, markup in file and field names
rendered as rich text, and trusted roots that changed under the user's feet.
"""

import os
import stat
from pathlib import Path

import pikepdf
import pymupdf
import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox
from test_sign import _build_certificate, _request

from plico.main_window import MainWindow
from plico.model import DocumentModel, is_signed, save_as, save_compressed, save_signed
from plico.model import document as document_module
from plico.model import forms as forms_module
from plico.model import save as save_module
from plico.model.forms import read_fields
from plico.model.optimize import LEVELS_BY_KEY, CompressionResult
from plico.model.sign import keep_root, kept_root_intact, read_signatures, sign_in_place
from plico.widgets.form_panel import FormPanel
from plico.widgets.sign import _signature_block

SECRET = "SEGRETO riservato"


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    mw = MainWindow()
    yield mw
    mw.shutdown_worker()
    mw.deleteLater()
    qapp.processEvents()


@pytest.fixture(scope="module")
def certificate(tmp_path_factory) -> tuple[str, str]:
    folder = tmp_path_factory.mktemp("certificato")
    path = str(folder / "firma.p12")
    _build_certificate(path, x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Mario Rossi")]))
    return path, str(folder / "root.pem")


def _encrypted_pdf(path: str, password: str = "segreta") -> None:
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), SECRET)
        doc.save(
            path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=password,
            owner_pw="proprietario",
            permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY,
        )


def _locked(path: str, password: str = "segreta") -> str:
    """The text of *path*, after checking it does not open without *password*."""
    with pymupdf.open(path) as doc:
        assert doc.needs_pass
        assert doc.authenticate(password)
        return doc[0].get_text()


# -- a protected file stays protected ------------------------------------------ #


def test_saving_over_a_protected_file_keeps_it_protected(qapp, tmp_path) -> None:
    path = str(tmp_path / "protetto.pdf")
    _encrypted_pdf(path)
    model = DocumentModel()
    model.open(path, "segreta")
    save_as(model, path)
    assert SECRET in _locked(path)
    with pikepdf.open(path, password="segreta") as pdf:
        # the permissions the file had: printing and copying, nothing else
        assert pdf.allow.extract and pdf.allow.print_lowres
        assert not pdf.allow.modify_other


def test_saving_a_protected_file_somewhere_else_writes_a_new_plain_file(qapp, tmp_path) -> None:
    path = str(tmp_path / "protetto.pdf")
    other = str(tmp_path / "copia.pdf")
    _encrypted_pdf(path)
    model = DocumentModel()
    model.open(path, "segreta")
    save_as(model, other)
    with pymupdf.open(other) as doc:
        assert not doc.needs_pass


def test_compressing_over_a_protected_file_keeps_it_protected(
    qapp, tmp_path, monkeypatch
) -> None:
    path = str(tmp_path / "protetto.pdf")
    _encrypted_pdf(path)
    # A gain, whatever this one-line page allows: the file is written.
    monkeypatch.setattr(
        save_module, "optimize_in_place", lambda *a, **k: CompressionResult(10_000, 1_000)
    )
    model = DocumentModel()
    model.open(path, "segreta")
    assert save_compressed(model, path, LEVELS_BY_KEY["light"]).shrank
    assert SECRET in _locked(path)


def test_signing_over_a_protected_file_keeps_it_protected_and_signed(
    qapp, tmp_path, certificate
) -> None:
    path = str(tmp_path / "protetto.pdf")
    _encrypted_pdf(path)
    model = DocumentModel()
    model.open(path, "segreta")
    save_signed(model, path, _request(certificate[0]))
    assert SECRET in _locked(path)
    [signature] = read_signatures(path, password="segreta")
    assert signature.intact and signature.valid


# -- a redaction takes the whole word, whichever way it runs -------------------- #


@pytest.mark.parametrize("angle", [90, 30, 45])
@pytest.mark.parametrize("how", ["search", "words"])
def test_a_redaction_takes_a_word_that_is_not_horizontal(qapp, tmp_path, angle, how) -> None:
    path = str(tmp_path / "ruotato.pdf")
    with pymupdf.open() as doc:
        page = doc.new_page()
        if angle == 90:
            page.insert_text((100, 300), "ZQXSECRET01", fontsize=24, rotate=90)
        else:
            turn = pymupdf.Matrix(1, 1).prerotate(angle)
            page.insert_text((150, 500), "ZQXSECRET01", fontsize=24,
                             morph=(pymupdf.Point(150, 500), turn))
        page.insert_text((40, 760), "PUBBLICOKEEP", fontsize=20)
        doc.save(path)
    model = DocumentModel()
    model.open(path)
    if how == "search":
        marks = model.find_text("ZQXSECRET01")[0]
    else:
        marks = [r for r in model.words_on(0) if r.y1 < 700]
    assert marks and not any(mark.snug for mark in marks)
    model.pages[0].redactions.extend(marks)
    out = str(tmp_path / "out.pdf")
    save_as(model, out)
    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
    assert "PUBBLICOKEEP" in text
    for piece in ("ZQX", "SEC", "RET", "T01"):
        assert piece not in text


def test_a_horizontal_word_keeps_its_band(qapp, tmp_path) -> None:
    path = str(tmp_path / "piano.pdf")
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), "una parola SEGRETO qui")
        doc.save(path)
    model = DocumentModel()
    model.open(path)
    assert all(mark.snug for mark in model.find_text("SEGRETO")[0])
    assert all(mark.snug for mark in model.words_on(0))


# -- a signature is found by its field, not by a flag ----------------------------- #


def test_a_signature_with_its_flag_cleared_is_still_a_signature(
    qapp, tmp_path, certificate
) -> None:
    path = str(tmp_path / "firmato.pdf")
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(path)
    sign_in_place(path, _request(certificate[0]))
    assert is_signed(path)
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        del pdf.Root.AcroForm.SigFlags
        pdf.save(path)
    assert is_signed(path)


# -- the document in the making is the user's only ----------------------------- #


def test_the_temporary_of_a_save_is_in_a_directory_only_the_user_enters(
    qapp, tmp_path, monkeypatch
) -> None:
    source = str(tmp_path / "documento.pdf")
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), SECRET)
        doc.save(source)
    shared = tmp_path / "condivisa"
    shared.mkdir()
    shared.chmod(0o777)
    seen = []
    real = save_module._write_pdf

    def spy(model, out_path, pages=None):
        parent = os.path.dirname(out_path)
        seen.append((parent, stat.S_IMODE(os.stat(parent).st_mode)))
        real(model, out_path, pages)

    monkeypatch.setattr(save_module, "_write_pdf", spy)
    model = DocumentModel()
    model.open(source)
    save_as(model, str(shared / "uscita.pdf"))
    [(parent, mode)] = seen
    assert os.path.dirname(parent) == str(shared)
    assert mode == 0o700
    # and nothing is left behind
    assert sorted(os.listdir(shared)) == ["uscita.pdf"]


# -- documents built to freeze the window ---------------------------------------- #


def test_a_document_with_too_many_pages_is_refused(qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(document_module, "MAX_PAGES", 4)
    path = str(tmp_path / "lungo.pdf")
    with pymupdf.open() as doc:
        for _ in range(5):
            doc.new_page()
        doc.save(path)
    model = DocumentModel()
    with pytest.raises(ValueError, match="5 pagine"):
        model.open(path)


def test_a_merge_cannot_pass_the_page_limit(qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(document_module, "MAX_PAGES", 4)
    path = str(tmp_path / "tre.pdf")
    with pymupdf.open() as doc:
        for _ in range(3):
            doc.new_page()
        doc.save(path)
    model = DocumentModel()
    model.open(path)
    with pytest.raises(ValueError, match="6 pagine"):
        model.append_document(path)
    assert model.page_count == 3


def test_a_page_crowded_with_widgets_is_not_walked(qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(forms_module, "MAX_FIELDS_PER_PAGE", 3)
    path = str(tmp_path / "campi.pdf")
    with pymupdf.open() as doc:
        page = doc.new_page()
        for i in range(4):
            widget = pymupdf.Widget()
            widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            widget.field_name = f"campo{i}"
            widget.rect = pymupdf.Rect(10, 10 + 30 * i, 200, 30 + 30 * i)
            page.add_widget(widget)
        doc.save(path)
    with pymupdf.open(path) as doc:
        page = doc[0]
        assert read_fields(page) == []
    monkeypatch.setattr(forms_module, "MAX_FIELDS_PER_PAGE", 4)
    with pymupdf.open(path) as doc:
        page = doc[0]
        assert len(read_fields(page)) == 4


# -- text from a file is text ---------------------------------------------------- #

MARKUP = '<font color=green><b>Firma valida</b></font><a href="https://example.org">x</a>'


def test_message_boxes_of_the_window_show_markup_as_text(window, qapp) -> None:
    seen = []

    def inspect():
        box = QApplication.activeModalWidget()
        assert isinstance(box, QMessageBox)
        seen.extend(
            label.textFormat() for label in box.findChildren(QLabel) if MARKUP in label.text()
        )
        box.reject()

    QTimer.singleShot(0, inspect)
    QMessageBox.warning(window, "Errore", f"«{MARKUP}» ha modifiche non salvate.")
    assert seen == [Qt.TextFormat.PlainText]


def test_the_status_bar_and_the_form_panel_show_markup_as_text(window, qapp) -> None:
    assert window._status.textFormat() == Qt.TextFormat.PlainText
    assert window._toast.textFormat() == Qt.TextFormat.PlainText
    panel = FormPanel()
    field = forms_module.Field(name=MARKUP, kind=forms_module.TEXT, value="", rect=(0, 0, 9, 9))
    panel.set_page(0, [field], {})
    labels = [label for label in panel.findChildren(QLabel) if label.text() == MARKUP]
    assert labels and all(label.textFormat() == Qt.TextFormat.PlainText for label in labels)


def test_a_signature_block_shows_markup_as_text(qapp, tmp_path, certificate) -> None:
    path = str(tmp_path / "firmato.pdf")
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(path)
    sign_in_place(path, _request(certificate[0], field_name=MARKUP))
    [signature] = read_signatures(path)
    block = _signature_block(signature)
    labels = block.findChildren(QLabel)
    assert labels and all(label.textFormat() == Qt.TextFormat.PlainText for label in labels)


# -- a trusted root is what the user approved ------------------------------------ #


def test_a_trusted_root_is_a_copy_the_original_cannot_change(qapp, tmp_path, certificate) -> None:
    original = tmp_path / "radice.pem"
    original.write_bytes(Path(certificate[1]).read_bytes())
    store = str(tmp_path / "radici")
    kept = keep_root(str(original), store)
    assert stat.S_IMODE(os.stat(store).st_mode) == 0o700
    other = tmp_path / "altra"
    other.mkdir()
    _build_certificate(
        str(other / "x.p12"), x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Altro")])
    )
    original.write_bytes((other / "root.pem").read_bytes())
    assert kept_root_intact(kept, store)
    assert Path(kept).read_bytes() == Path(certificate[1]).read_bytes()
    # a copy changed inside the store is not one any more
    with open(kept, "ab") as handle:
        handle.write(b"\n")
    assert not kept_root_intact(kept, store)


def test_roots_remembered_as_paths_are_copied_once(window, tmp_path, certificate) -> None:
    legacy = tmp_path / "vecchia.pem"
    legacy.write_bytes(Path(certificate[1]).read_bytes())
    window._settings().setValue("firma/radici", [str(legacy)])
    [root] = window._signed_roots()
    assert os.path.dirname(root) == window._root_store()
    assert window._settings().value("firma/radici") == [root]
    legacy.write_bytes(b"non un certificato")
    assert window._signed_roots() == [root]
