"""File → Stampa: the document as a save would write it, painted page by page."""

import os

import pymupdf
import pytest
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter
from PySide6.QtWidgets import QApplication, QDialog

from plico.main_window import MainWindow
from plico.model import DeletePage, DocumentModel
from plico.model.redact import RedactionRect
from plico.model.save import discard_copy, printable_copy
from plico.printing import page_fit, print_pdf

SECRET = "SEGRETO"


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


def _document(path: str) -> None:
    with pymupdf.open() as doc:
        for i in range(2):
            doc.new_page().insert_text((72, 72), f"pagina {i + 1}", fontsize=30)
        landscape = doc.new_page(width=842, height=595)
        landscape.insert_text((72, 72), "pagina 3", fontsize=30)
        doc.save(path)


def _writer(path: str) -> QPdfWriter:
    writer = QPdfWriter(path)
    writer.setResolution(150)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    return writer


def test_a_page_fits_the_paper_and_a_landscape_one_is_turned() -> None:
    assert page_fit((595, 842), (1240, 1754)) == (False, pytest.approx(1754 / 842))
    turned, scale = page_fit((842, 595), (1240, 1754))
    assert turned and scale == pytest.approx(1754 / 842)
    assert page_fit((842, 595), (1240, 1754), auto_rotate=False)[0] is False


def test_every_page_reaches_the_device(qapp, tmp_path) -> None:
    source = str(tmp_path / "documento.pdf")
    out = str(tmp_path / "stampa.pdf")
    _document(source)
    writer = _writer(out)
    seen = []
    assert print_pdf(source, writer, progress=lambda n: seen.append(n) or True) == 3
    del writer  # the file is finished when the writer goes
    assert seen == [1, 2, 3]
    with pymupdf.open(out) as printed:
        assert len(printed) == 3
        # Each page is one image, as MuPDF rendered it; all portrait A4.
        assert all(len(page.get_images()) == 1 for page in printed)
        assert all(page.rect.width < page.rect.height for page in printed)


def test_a_stop_ends_the_job(qapp, tmp_path) -> None:
    source = str(tmp_path / "documento.pdf")
    _document(source)
    writer = _writer(str(tmp_path / "stampa.pdf"))
    assert print_pdf(source, writer, [2, 0], progress=lambda n: False) == 1


def test_what_is_printed_is_what_would_be_saved(qapp, tmp_path) -> None:
    source = str(tmp_path / "documento.pdf")
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), SECRET)
        doc.new_page().insert_text((72, 72), "pubblico")
        doc.save(source)
    model = DocumentModel()
    model.open(source)
    model.pages[0].redactions.append(RedactionRect(60, 50, 300, 90))
    copy = printable_copy(model)
    try:
        assert oct(os.stat(os.path.dirname(copy)).st_mode & 0o777) == "0o700"
        with pymupdf.open(copy) as doc:
            assert SECRET not in doc[0].get_text()
    finally:
        discard_copy(copy)
    assert not os.path.exists(os.path.dirname(copy))
    DeletePage(model, 0).redo()
    copy = printable_copy(model)
    try:
        with pymupdf.open(copy) as doc:
            assert len(doc) == 1 and "pubblico" in doc[0].get_text()
    finally:
        discard_copy(copy)


def test_the_window_prints_the_pages_chosen(window, qapp, tmp_path, monkeypatch) -> None:
    printsupport = pytest.importorskip("PySide6.QtPrintSupport")
    source = str(tmp_path / "documento.pdf")
    out = str(tmp_path / "stampa.pdf")
    _document(source)
    assert window.open_path(source)

    def accept(dialog):
        printer = dialog.printer()
        printer.setOutputFormat(printsupport.QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(out)
        printer.setPrintRange(printsupport.QPrinter.PrintRange.PageRange)
        printer.setFromTo(2, 3)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(printsupport.QPrintDialog, "exec", accept)
    window._print_document()
    with pymupdf.open(out) as printed:
        assert len(printed) == 2
    assert "2" in window._status.text()
