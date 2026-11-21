"""What a save carries over besides the pages: outline, labels, metadata.

Every save rebuilds the file from its pages, and used to leave the rest of
the document behind: one rotated page and Ctrl+S cost a manual its bookmarks,
its title and its roman-numbered preface (reported by a review of 0.1.8).
"""

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

from plico.model import DeletePage, DocumentModel, MovePage, extract_pages, save_as
from plico.model.redact import RedactionRect


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _book(path: str, pages: int = 4, title: str = "Manuale") -> None:
    with pymupdf.open() as doc:
        for i in range(pages):
            doc.new_page().insert_text((72, 72), f"{title} pagina {i + 1}")
        toc = [[1, "Prefazione", 1], [1, "Capitolo", 2], [2, "Sezione", 3], [1, "Fine", pages]]
        doc.set_toc([[level, title, min(page, pages)] for level, title, page in toc])
        doc.set_metadata({"title": title, "author": "Autrice"})
        doc.set_page_labels([
            {"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
            {"startpage": 1, "prefix": "", "style": "D", "firstpagenum": 1},
        ])
        doc.save(path)


def _labels(path: str) -> list[str]:
    with pymupdf.open(path) as doc:
        return [page.get_label() for page in doc]


def test_a_plain_save_keeps_outline_labels_and_metadata(qapp, tmp_path) -> None:
    path = str(tmp_path / "manuale.pdf")
    _book(path)
    model = DocumentModel()
    model.open(path)
    save_as(model, path)
    with pymupdf.open(path) as doc:
        assert doc.get_toc() == [[1, "Prefazione", 1], [1, "Capitolo", 2], [2, "Sezione", 3], [1, "Fine", 4]]
        assert doc.metadata["title"] == "Manuale"
        assert doc.metadata["author"] == "Autrice"
    assert _labels(path) == ["i", "1", "2", "3"]


def test_bookmarks_follow_their_pages_and_go_with_deleted_ones(qapp, tmp_path) -> None:
    path = str(tmp_path / "manuale.pdf")
    out = str(tmp_path / "salvato.pdf")
    _book(path)
    model = DocumentModel()
    model.open(path)
    DeletePage(model, 1).redo()  # "Capitolo" goes, "Sezione" loses its parent
    MovePage(model, 2, 0).redo()  # "Fine" first
    save_as(model, out)
    with pymupdf.open(out) as doc:
        assert doc.get_toc() == [[1, "Prefazione", 2], [1, "Sezione", 3], [1, "Fine", 1]]
    # Each page keeps the label it showed.
    assert _labels(out) == ["3", "i", "2"]


def test_a_merge_reads_like_its_files(qapp, tmp_path) -> None:
    first = str(tmp_path / "uno.pdf")
    second = str(tmp_path / "due.pdf")
    out = str(tmp_path / "unito.pdf")
    _book(first, pages=2, title="Uno")
    _book(second, pages=2, title="Due")
    model = DocumentModel()
    model.open(first)
    model.append_document(second)
    save_as(model, out)
    with pymupdf.open(out) as doc:
        assert [entry[2] for entry in doc.get_toc()] == [1, 2, 2, 2, 3, 4, 4, 4]
        assert doc.metadata["title"] == "Uno"
    assert _labels(out) == ["i", "1", "i", "1"]


def test_an_extraction_keeps_what_its_pages_had(qapp, tmp_path) -> None:
    path = str(tmp_path / "manuale.pdf")
    out = str(tmp_path / "estratto.pdf")
    _book(path)
    model = DocumentModel()
    model.open(path)
    extract_pages(model, out, [2, 3])
    with pymupdf.open(out) as doc:
        assert doc.get_toc() == [[1, "Sezione", 1], [1, "Fine", 2]]
    assert _labels(out) == ["2", "3"]


def test_a_redaction_leaves_outline_and_metadata_behind(qapp, tmp_path) -> None:
    path = str(tmp_path / "manuale.pdf")
    out = str(tmp_path / "cancellato.pdf")
    _book(path)
    model = DocumentModel()
    model.open(path)
    model.pages[0].redactions.append(RedactionRect(60, 50, 300, 90))
    save_as(model, out)
    with pymupdf.open(out) as doc:
        assert doc.get_toc() == []
        assert doc.metadata["title"] == ""
        assert doc.get_xml_metadata() == ""
    # Labels are numbers, not words: they stay.
    assert _labels(out) == ["i", "1", "2", "3"]
