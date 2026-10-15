"""Basic tests for DocumentModel and PageItem."""

from plico.model.document import DocumentModel, PageItem


def test_open_pdf(tmp_path):
    # Create a simple PDF
    import fitz

    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i+1}", fontsize=12)
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
