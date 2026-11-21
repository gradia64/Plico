"""Modifica → Duplica pagina and Inserisci pagina vuota."""

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from plico.main_window import MainWindow
from plico.model import DocumentModel, DuplicatePage, RotatePage, save_as
from plico.model.redact import RedactionRect


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


def _pages(path: str, count: int = 2) -> None:
    with pymupdf.open() as doc:
        for i in range(count):
            doc.new_page().insert_text((72, 72), f"pagina {i + 1}")
        landscape = doc.new_page(width=842, height=595)
        landscape.insert_text((72, 72), "orizzontale")
        doc.save(path)


def _texts(path: str) -> list[str]:
    with pymupdf.open(path) as doc:
        return [page.get_text().strip() for page in doc]


def test_a_duplicate_is_a_page_of_its_own(qapp, tmp_path) -> None:
    path = str(tmp_path / "documento.pdf")
    out = str(tmp_path / "salvato.pdf")
    _pages(path)
    model = DocumentModel()
    model.open(path)
    command = DuplicatePage(model, 0)
    command.redo()
    assert [item.source_index for item in model.pages] == [0, 0, 1, 2]
    # Marking the copy leaves the original alone.
    model.pages[1].redactions.append(RedactionRect(60, 50, 300, 90))
    RotatePage(model, 1, 90).redo()
    assert model.pages[0].redactions == [] and model.pages[0].rotation == 0
    save_as(model, out)
    assert _texts(out) == ["pagina 1", "", "pagina 2", "orizzontale"]
    with pymupdf.open(out) as doc:
        assert doc[0].rotation == 0 and doc[1].rotation == 90
    command.undo()
    assert [item.source_index for item in model.pages] == [0, 1, 2]


def test_the_window_duplicates_and_undoes(window, qapp, tmp_path) -> None:
    path = str(tmp_path / "documento.pdf")
    _pages(path)
    assert window.open_path(path)
    window._thumb_bar.set_current_row(1)
    window._duplicate_page()
    assert [item.source_index for item in window._doc_model.pages] == [0, 1, 1, 2]
    assert window._thumb_bar.current_row() == 2
    assert window.is_modified()
    window._undo_stack.undo()
    assert window._doc_model.page_count == 3


def test_a_blank_page_takes_the_size_of_the_page_before(window, qapp, tmp_path) -> None:
    path = str(tmp_path / "documento.pdf")
    out = str(tmp_path / "salvato.pdf")
    _pages(path)
    assert window.open_path(path)
    window._thumb_bar.set_current_row(2)  # the landscape page
    window._insert_blank_page()
    window._thumb_bar.set_current_row(0)
    window._undo_stack.push(RotatePage(window._doc_model, 0, 90))
    window._insert_blank_page()  # after a page turned to landscape
    pages = window._doc_model.pages
    assert len(pages) == 5
    assert (pages[4].width_pt, pages[4].height_pt) == (842, 595)
    assert pages[1].width_pt > pages[1].height_pt
    assert window._thumb_bar.current_row() == 1
    save_as(window._doc_model, out)
    assert _texts(out) == ["pagina 1", "", "pagina 2", "orizzontale", ""]
    # Undo takes the pages away and leaves their sources registered.
    sources = len(window._doc_model.sources)
    window._undo_stack.undo()
    window._undo_stack.undo()
    window._undo_stack.undo()
    assert window._doc_model.page_count == 3
    assert len(window._doc_model.sources) == sources
    window._undo_stack.redo()
    window._undo_stack.redo()
    window._undo_stack.redo()
    assert window._doc_model.page_count == 5
