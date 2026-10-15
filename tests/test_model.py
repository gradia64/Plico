"""Basic tests for DocumentModel and PageItem."""

import fitz
import pytest

from plico.model import extract_pages, parse_page_ranges
from plico.model.document import DocumentModel, PageItem


def test_open_pdf(tmp_path):
    # Create a simple PDF
    import fitz

    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}", fontsize=12)
    doc.save(str(pdf_path))
    doc.close()

    model = DocumentModel()
    model.open(str(pdf_path))

    assert model.page_count == 5
    assert model.pages[0].source_index == 0
    assert model.pages[4].source_index == 4
    assert model.pages[0].base_rotation == 0


def test_rotate_undo():
    model = DocumentModel()
    model.pages = [PageItem(source_index=0, base_rotation=0, rotation=0)]

    from PySide6.QtGui import QUndoStack

    from plico.model.commands import RotatePage

    stack = QUndoStack()
    stack.push(RotatePage(model, 0, 90))
    assert model.pages[0].rotation == 90

    stack.undo()
    assert model.pages[0].rotation == 0


def test_delete_undo():
    model = DocumentModel()
    model.pages = [
        PageItem(source_index=0, base_rotation=0),
        PageItem(source_index=1, base_rotation=0),
        PageItem(source_index=2, base_rotation=0),
    ]

    from PySide6.QtGui import QUndoStack

    from plico.model.commands import DeletePage

    stack = QUndoStack()
    stack.push(DeletePage(model, 1))
    assert model.page_count == 2
    assert model.pages[0].source_index == 0
    assert model.pages[1].source_index == 2  # page 1 deleted, 2 shifted

    stack.undo()
    assert model.page_count == 3
    assert model.pages[1].source_index == 1  # restored


def test_save_as(tmp_path):
    import fitz

    from plico.model.save import save_as

    src_path = tmp_path / "src.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello World", fontsize=12)
    doc.save(str(src_path))
    doc.close()

    model = DocumentModel()
    model.open(str(src_path))
    # Rotate page 0
    model.pages[0].rotation = 90

    out_path = tmp_path / "out.pdf"
    save_as(model, str(out_path))

    # Verify output
    with fitz.open(str(out_path)) as out:
        assert out.page_count == 1
        assert out[0].rotation == 90


class TestParsePageRanges:
    """The split dialog must never silently drop pages."""

    def test_single_pages_and_ranges(self):
        assert parse_page_ranges("1,3-5,8", 10) == [0, 2, 3, 4, 7]

    def test_order_is_preserved_so_a_split_can_also_reorder(self):
        assert parse_page_ranges("5,1-3", 10) == [4, 0, 1, 2]

    def test_whitespace_is_ignored(self):
        assert parse_page_ranges(" 1 , 3 - 5 ", 10) == [0, 2, 3, 4]

    def test_range_bounds_are_inclusive(self):
        assert parse_page_ranges("1-1", 10) == [0]
        assert parse_page_ranges("1-10", 10) == list(range(10))

    @pytest.mark.parametrize(
        "spec",
        ["", "   ", ",", "a", "1-", "-3", "3-1", "1-a", "0", "11", "1-11", "1;2"],
    )
    def test_bad_input_is_rejected_not_ignored(self, spec):
        with pytest.raises(ValueError):
            parse_page_ranges(spec, 10)


class TestExtractPages:
    """Splitting writes a subset and leaves the source untouched."""

    def _doc(self, tmp_path, pages=6):
        path = tmp_path / "src.pdf"
        doc = fitz.open()
        for i in range(pages):
            page = doc.new_page()
            page.insert_text((72, 72), f"p{i + 1}", fontsize=24)
        doc.save(path)
        doc.close()
        model = DocumentModel()
        model.open(str(path))
        return model, str(path)

    def test_extract_subset_in_typed_order(self, tmp_path):
        model, src = self._doc(tmp_path)
        out = str(tmp_path / "split.pdf")

        extract_pages(model, out, parse_page_ranges("3-4,1", model.page_count))

        with fitz.open(out) as doc:
            assert doc.page_count == 3

        # Source is still a 6-page document: extracting is not destructive.
        with fitz.open(src) as doc:
            assert doc.page_count == 6

    def test_extract_keeps_rotations_of_the_selection(self, tmp_path):
        model, _ = self._doc(tmp_path)
        model.pages[2].rotation = 90
        out = str(tmp_path / "split.pdf")

        extract_pages(model, out, [2])

        with fitz.open(out) as doc:
            assert doc[0].rotation == 90

    def test_extract_refuses_an_empty_selection(self, tmp_path):
        model, _ = self._doc(tmp_path)
        with pytest.raises(ValueError):
            extract_pages(model, str(tmp_path / "split.pdf"), [])
