"""Text editing in the document: the EditText command and the save.

tests/test_textedit.py proves that one span can be replaced on one page.
These tests prove the rest of the promise: the edit is state of the virtual
page (undoable, one per span, never written early), and every way of
materialising the document -- save, save over the open file, extract,
compress -- carries it, with redactions still having the last word.
"""

import os

import pymupdf
import pytest
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication

from plico.model import (
    LEVELS_BY_KEY,
    AddRedaction,
    DeletePage,
    DocumentModel,
    EditText,
    MovePage,
    RedactionRect,
    RotatePage,
    TextEdit,
    extract_pages,
    save_as,
    save_compressed,
)

SECRET = "segreta"


@pytest.fixture(scope="module")
def qapp():
    """A QApplication, not a QCoreApplication: the instance outlives this module.

    This file runs before test_integration.py, whose windows need a widget
    application; finding a QCoreApplication there, Qt aborts the whole run
    ("QWidget: Must construct a QApplication before a QWidget").
    """
    return QApplication.instance() or QApplication([])


def _write(path, lines: list[str], rotate: int = 0, **save_kwargs) -> str:
    """One page per line of text, in an embedded font that has a character map."""
    doc = pymupdf.open()
    for text in lines:
        page = doc.new_page(width=595, height=842)
        page.insert_font(fontname="F0", fontbuffer=pymupdf.Font("tiro").buffer)
        page.insert_text((72, 100), text, fontname="F0", fontsize=14)
        page.insert_text((72, 140), "Riga che non si tocca", fontname="F0", fontsize=14)
        page.set_rotation(rotate)
    doc.save(str(path), **save_kwargs)
    doc.close()
    return str(path)


def _model(path: str, password: str | None = None) -> DocumentModel:
    model = DocumentModel()
    model.open(path, password)
    return model


def _span(model: DocumentModel, index: int, words: str):
    """The source span under *words* on page *index*, found the way the view will."""
    item = model.pages[index]
    with pymupdf.open(model.sources[item.source_id]) as doc:
        hit = doc[item.source_index].search_for(words)[0]
    span = model.text_span_at(index, (hit.x0 + hit.x1) / 2, (hit.y0 + hit.y1) / 2)
    assert span is not None
    return span


def _texts(path: str) -> list[str]:
    with pymupdf.open(path) as doc:
        return [page.get_text() for page in doc]


# --- finding the span ---------------------------------------------------------


def test_text_span_at_reads_the_source_page_of_the_item(qapp, tmp_path):
    """After a reorder, page 0 of the model is page 1 of the source."""
    model = _model(_write(tmp_path / "a.pdf", ["Prima pagina", "Seconda pagina"]))
    MovePage(model, 1, 0).redo()

    assert _span(model, 0, "Seconda").text == "Seconda pagina"


def test_text_span_at_on_an_empty_spot_is_none(qapp, tmp_path):
    model = _model(_write(tmp_path / "a.pdf", ["Testo"]))
    assert model.text_span_at(0, 400, 700) is None


def test_text_span_at_unlocks_an_encrypted_source(qapp, tmp_path):
    """The password the model kept is what lets the span be read at all."""
    path = _write(
        tmp_path / "cifrato.pdf",
        ["Contenuto riservato"],
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="proprietario",
        user_pw=SECRET,
    )
    model = _model(path, SECRET)

    span = model.text_span_at(0, 80, 95)

    assert span is not None and span.text == "Contenuto riservato"


# --- the command --------------------------------------------------------------


def test_edit_is_page_state_and_undo_takes_it_back(qapp, tmp_path):
    model = _model(_write(tmp_path / "a.pdf", ["Importo 12.400 euro"]))
    span = _span(model, 0, "12.400")
    changed: list[int] = []
    model.page_changed.connect(changed.append)

    command = EditText(model, 0, span, "Importo 13.950 euro")
    command.redo()
    assert model.pages[0].text_edits == [TextEdit(span, "Importo 13.950 euro")]
    assert model.pages[0].text_of(span) == "Importo 13.950 euro"

    command.undo()
    assert model.pages[0].text_edits == []
    assert model.pages[0].text_of(span) == "Importo 12.400 euro"
    assert changed == [0, 0], "the view must hear about both"


def test_a_second_edit_of_the_same_span_replaces_the_first(qapp, tmp_path):
    """One edit per span: two would write two texts on top of each other."""
    model = _model(_write(tmp_path / "a.pdf", ["Importo 12.400 euro"]))
    span = _span(model, 0, "12.400")
    stack = QUndoStack()
    stack.push(EditText(model, 0, span, "Importo 13.000 euro"))
    # Something else in between, so the two edits do not merge.
    stack.push(RotatePage(model, 0, 90))
    stack.push(EditText(model, 0, span, "Importo 14.000 euro"))

    assert model.pages[0].text_edits == [TextEdit(span, "Importo 14.000 euro")]

    stack.undo()
    assert model.pages[0].text_edits == [TextEdit(span, "Importo 13.000 euro")]


def test_consecutive_edits_of_the_same_span_are_one_undo_step(qapp, tmp_path):
    model = _model(_write(tmp_path / "a.pdf", ["Importo 12.400 euro"]))
    span = _span(model, 0, "12.400")
    stack = QUndoStack()
    stack.push(EditText(model, 0, span, "Importo 13.000 euro"))
    stack.push(EditText(model, 0, span, "Importo 14.000 euro"))

    assert stack.count() == 1
    stack.undo()
    assert model.pages[0].text_edits == []


def test_typing_the_original_back_removes_the_edit(qapp, tmp_path):
    """Back to what the file says: no edit left, and no empty undo step either."""
    model = _model(_write(tmp_path / "a.pdf", ["Importo 12.400 euro"]))
    span = _span(model, 0, "12.400")
    stack = QUndoStack()
    stack.push(EditText(model, 0, span, "Importo 13.000 euro"))
    stack.push(EditText(model, 0, span, "Importo 12.400 euro"))

    assert model.pages[0].text_edits == []
    assert stack.count() == 0, "a step that changes nothing is dropped"


def test_an_edit_that_changes_nothing_is_not_a_step(qapp, tmp_path):
    model = _model(_write(tmp_path / "a.pdf", ["Testo"]))
    span = _span(model, 0, "Testo")
    stack = QUndoStack()
    stack.push(EditText(model, 0, span, "Testo"))
    assert stack.count() == 0


def test_edits_of_different_spans_keep_their_order(qapp, tmp_path):
    model = _model(_write(tmp_path / "a.pdf", ["Primo"]))
    first = _span(model, 0, "Primo")
    second = _span(model, 0, "Riga che")
    stack = QUndoStack()
    stack.push(EditText(model, 0, first, "Uno"))
    stack.push(EditText(model, 0, second, "Riga cambiata"))
    stack.push(RotatePage(model, 0, 90))
    stack.push(EditText(model, 0, first, "Due"))

    assert [edit.span for edit in model.pages[0].text_edits] == [first, second]
    stack.undo()
    stack.undo()
    assert [edit.new_text for edit in model.pages[0].text_edits] == ["Uno", "Riga cambiata"]


# --- the save -----------------------------------------------------------------


def test_save_writes_the_new_text_and_removes_the_old(qapp, tmp_path):
    model = _model(_write(tmp_path / "a.pdf", ["Importo 12.400 euro"]))
    EditText(model, 0, _span(model, 0, "12.400"), "Importo 13.950 euro").redo()
    out = str(tmp_path / "out.pdf")

    save_as(model, out)

    (text,) = _texts(out)
    assert "13.950" in text and "12.400" not in text
    assert "Riga che non si tocca" in text


def test_the_source_is_never_touched(qapp, tmp_path):
    source = _write(tmp_path / "a.pdf", ["Importo 12.400 euro"])
    model = _model(source)
    EditText(model, 0, _span(model, 0, "12.400"), "Importo 13.950 euro").redo()

    save_as(model, str(tmp_path / "out.pdf"))

    assert "12.400" in _texts(source)[0]


def test_undo_before_saving_writes_the_original(qapp, tmp_path):
    model = _model(_write(tmp_path / "a.pdf", ["Importo 12.400 euro"]))
    stack = QUndoStack()
    stack.push(EditText(model, 0, _span(model, 0, "12.400"), "Importo 13.950 euro"))
    stack.undo()
    out = str(tmp_path / "out.pdf")

    save_as(model, out)

    assert "12.400" in _texts(out)[0]


def test_a_redaction_over_an_edited_span_removes_the_new_text_too(qapp, tmp_path):
    """Edits run before redactions: the redaction has the last word."""
    model = _model(_write(tmp_path / "a.pdf", ["Importo 12.400 euro"]))
    span = _span(model, 0, "12.400")
    EditText(model, 0, span, "Importo 13.950 euro").redo()
    AddRedaction(model, 0, RedactionRect(*span.bbox)).redo()
    out = str(tmp_path / "out.pdf")

    save_as(model, out)

    (text,) = _texts(out)
    assert "13.950" not in text and "12.400" not in text
    assert "Riga che non si tocca" in text


@pytest.mark.parametrize("base", [0, 90])
def test_edit_follows_the_page_through_rotation_and_reorder(qapp, tmp_path, base):
    """Page space all the way: base /Rotate, user rotation and a move change nothing."""
    model = _model(_write(tmp_path / "a.pdf", ["Prima 1", "Seconda 2"], rotate=base))
    EditText(model, 1, _span(model, 1, "Seconda"), "Seconda modificata").redo()
    RotatePage(model, 1, 90).redo()
    MovePage(model, 1, 0).redo()
    out = str(tmp_path / "out.pdf")

    save_as(model, out)

    with pymupdf.open(out) as doc:
        assert "Seconda modificata" in doc[0].get_text()
        assert doc[0].rotation == (base + 90) % 360
        # Same place on the page as the original line.
        hit = doc[0].search_for("Seconda modificata")[0]
        assert (hit.x0, hit.y1) == pytest.approx((72, 100 + 4), abs=4)
        assert "Prima 1" in doc[1].get_text()


def test_a_deleted_page_takes_its_edit_with_it_and_undo_brings_it_back(qapp, tmp_path):
    model = _model(_write(tmp_path / "a.pdf", ["Prima", "Seconda"]))
    EditText(model, 0, _span(model, 0, "Prima"), "Prima modificata").redo()
    stack = QUndoStack()
    stack.push(DeletePage(model, 0))
    stack.undo()
    out = str(tmp_path / "out.pdf")

    save_as(model, out)

    assert "Prima modificata" in _texts(out)[0]


def test_extract_carries_the_edit_of_the_extracted_page(qapp, tmp_path):
    model = _model(_write(tmp_path / "a.pdf", ["Prima", "Seconda"]))
    EditText(model, 1, _span(model, 1, "Seconda"), "Seconda modificata").redo()
    out = str(tmp_path / "estratta.pdf")

    extract_pages(model, out, [1])

    (text,) = _texts(out)
    assert "Seconda modificata" in text


def test_compressed_save_carries_the_edit(qapp, tmp_path):
    model = _model(_write(tmp_path / "a.pdf", ["Importo 12.400 euro"]))
    EditText(model, 0, _span(model, 0, "12.400"), "Importo 13.950 euro").redo()
    out = str(tmp_path / "compresso.pdf")

    save_compressed(model, out, LEVELS_BY_KEY["light"])

    (text,) = _texts(out)
    assert "13.950" in text and "12.400" not in text


def test_saving_over_the_open_file_keeps_the_edit(qapp, tmp_path):
    source = _write(tmp_path / "a.pdf", ["Importo 12.400 euro"])
    model = _model(source)
    EditText(model, 0, _span(model, 0, "12.400"), "Importo 13.950 euro").redo()

    save_as(model, source)

    (text,) = _texts(source)
    assert "13.950" in text and "12.400" not in text


def test_new_fonts_are_subset_before_saving(qapp, tmp_path):
    """The font the edit embeds goes in as a subset, not as a whole program."""
    source = _write(tmp_path / "a.pdf", ["Importo 12.400 euro"])
    model = _model(source)
    EditText(model, 0, _span(model, 0, "12.400"), "Importo 13.950 euro").redo()
    out = str(tmp_path / "out.pdf")

    save_as(model, out)

    with pymupdf.open(out) as doc:
        embedded = [f for f in doc[0].get_fonts() if f[1] not in ("n/a", "")]
        assert embedded and all("+" in f[3] for f in embedded), embedded
    assert os.path.getsize(out) < os.path.getsize(source) + 60_000


def test_form_fields_survive_an_edit_on_the_same_page(qapp, tmp_path):
    """subset_fonts() runs on the whole document: the form must come through."""
    path = str(tmp_path / "modulo.pdf")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_font(fontname="F0", fontbuffer=pymupdf.Font("tiro").buffer)
    page.insert_text((72, 100), "Intestazione", fontname="F0", fontsize=14)
    widget = pymupdf.Widget()
    widget.field_name = "nome"
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT  # type: ignore[attr-defined]
    widget.rect = pymupdf.Rect(72, 200, 300, 220)
    widget.field_value = "Anna"
    page.add_widget(widget)
    doc.save(path)
    doc.close()

    model = _model(path)
    EditText(model, 0, _span(model, 0, "Intestazione"), "Intestazione nuova").redo()
    out = str(tmp_path / "out.pdf")
    save_as(model, out)

    with pymupdf.open(out) as saved:
        page = saved[0]
        assert "Intestazione nuova" in page.get_text()
        values = {w.field_name: w.field_value for w in page.widgets()}
        assert values == {"nome": "Anna"}
