"""File → Proteggi con password: a password chosen by the user, or none."""

import pikepdf
import pymupdf
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from plico.main_window import MainWindow
from plico.model import DocumentModel, save_as
from plico.model.save import Protection
from plico.widgets.protect import ProtectDialog

SECRET = "riservato"


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


def _plain(path: str) -> None:
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), SECRET)
        doc.save(path)


def test_everything_allowed_needs_no_owner_password() -> None:
    chosen = Protection.chosen("segreta")
    assert chosen.owner == "segreta"
    assert chosen.permissions & (1 << 2) and chosen.permissions & (1 << 4)


def test_a_restriction_gets_an_owner_password_of_its_own() -> None:
    chosen = Protection.chosen("segreta", allow_print=False)
    assert chosen.owner not in ("", "segreta")
    assert not chosen.permissions & (1 << 2) and not chosen.permissions & (1 << 11)
    assert Protection.chosen("segreta", "titolare", allow_copy=False).owner == "titolare"


def test_a_new_file_gets_the_password_and_the_restrictions(qapp, tmp_path) -> None:
    source = str(tmp_path / "aperto.pdf")
    out = str(tmp_path / "protetto.pdf")
    _plain(source)
    model = DocumentModel()
    model.open(source)
    save_as(model, out, Protection.chosen("segreta", "titolare", allow_copy=False))
    with pymupdf.open(out) as doc:
        assert doc.needs_pass and doc.authenticate("segreta")
        assert SECRET in doc[0].get_text()
    with pikepdf.open(out, password="segreta") as pdf:
        assert not pdf.allow.extract and pdf.allow.print_highres and pdf.allow.modify_other
    with pikepdf.open(out, password="titolare") as pdf:
        assert pdf.owner_password_matched


def test_no_password_takes_the_protection_off(qapp, tmp_path) -> None:
    path = str(tmp_path / "protetto.pdf")
    _plain(path)
    model = DocumentModel()
    model.open(path)
    save_as(model, path, Protection.chosen("segreta"))
    model = DocumentModel()
    model.open(path, "segreta")
    save_as(model, path)  # the automatic protection keeps it
    with pymupdf.open(path) as doc:
        assert doc.needs_pass
    save_as(model, path, None)
    with pymupdf.open(path) as doc:
        assert not doc.needs_pass and SECRET in doc[0].get_text()


def test_the_dialog_wants_the_password_twice(qapp) -> None:
    dialog = ProtectDialog(protected=False)
    dialog._password.setText("segreta")
    dialog._repeat.setText("segreto")
    dialog._accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._error.isVisibleTo(dialog)
    dialog._repeat.setText("segreta")
    dialog._accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.protection() == Protection("segreta", "segreta", dialog.protection().permissions)
    assert not ProtectDialog(protected=False)._none.isVisibleTo(dialog)


def test_the_window_protects_the_file_and_keeps_it_protected(
    window, qapp, tmp_path, monkeypatch
) -> None:
    path = str(tmp_path / "documento.pdf")
    _plain(path)
    assert window.open_path(path)

    def fill(dialog):
        dialog._password.setText("segreta")
        dialog._repeat.setText("segreta")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ProtectDialog, "exec", fill)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (path, ""))
    monkeypatch.setattr(
        window, "_ask_password", lambda *a, **k: pytest.fail("the password was asked again")
    )
    window._protect_file()
    assert window._doc_model.sources == [path]
    assert window._doc_model.passwords[path] == "segreta"
    assert "password" in window._status.text()
    # The next plain save keeps it.
    assert window._save_to(path)
    with pymupdf.open(path) as doc:
        assert doc.needs_pass
