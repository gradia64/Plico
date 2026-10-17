"""AcroForm form: read the fields, write them, find them again in the saved file.

The test forms are built here with PyMuPDF instead of fetching one from the
system: this way the tests also run where that file is missing, and every field
type has its own case.
"""

import pikepdf
import pymupdf
from PySide6.QtGui import QUndoStack

from plico.model import (
    LEVELS_BY_KEY,
    AddRedaction,
    DocumentModel,
    SetFieldValue,
)
from plico.model.forms import CHECKBOX, CHECKED, CHOICE, RADIO, TEXT, write_fields
from plico.model.redact import RedactionRect
from plico.model.save import save_as, save_compressed


def _add_fields(
    page: pymupdf.Page,
    name: str,
    kind: int,
    rect: tuple[float, float, float, float],
    value: str | None = None,
    choices: list[str] | None = None,
) -> None:
    """Add a field to the page. The page must already be alive."""
    widget = pymupdf.Widget()
    widget.field_name = name
    widget.field_type = kind
    widget.rect = pymupdf.Rect(*rect)
    if value is not None:
        widget.field_value = value
    if choices:
        widget.choice_values = list(choices)
    page.add_widget(widget)
    widget.update()


def _form_pdf(path: str, rotation: int = 0) -> None:
    """A text field, a note, a checkbox and a dropdown."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 60), "Modulo di prova", fontsize=16)
        _add_fields(page, "nome", pymupdf.PDF_WIDGET_TYPE_TEXT, (72, 100, 300, 128), "vecchio")
        _add_fields(page, "nota", pymupdf.PDF_WIDGET_TYPE_TEXT, (72, 140, 400, 210))
        _add_fields(page, "accetto", pymupdf.PDF_WIDGET_TYPE_CHECKBOX, (72, 230, 92, 250))
        _add_fields(
            page,
            "colore",
            pymupdf.PDF_WIDGET_TYPE_COMBOBOX,
            (72, 270, 300, 300),
            "rosso",
            ["rosso", "verde"],
        )
        if rotation:
            page.set_rotation(rotation)
        doc.save(path, garbage=4, deflate=True)


def _simple_pdf(path: str) -> None:
    """A PDF with no form at all."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "Nessun campo qui", fontsize=20)
        doc.save(path, deflate=True)


def _values(path: str, index: int = 0) -> dict[str, str]:
    """The values as they are in the file, re-read with PyMuPDF."""
    with pymupdf.open(path) as doc:
        page = doc[index]  # alive: the widgets reference it weakly
        return {w.field_name or "": w.field_value or "" for w in page.widgets() or ()}


def _values_in_order(path: str, index: int = 0) -> list[str]:
    """The values in widget order, without looking at the name.

    Needed where names cannot be used: MuPDF renames the second copy of
    a same-named field while it copies the pages, and the field becomes ``nome [12]``.
    """
    with pymupdf.open(path) as doc:
        page = doc[index]
        return [w.field_value or "" for w in (page.widgets() or ())]


def _ink(path: str, box: tuple[float, float, float, float]) -> int:
    """How many dark pixels are in *area*: needed to see the drawn appearance."""
    with pymupdf.open(path) as doc:
        page = doc[0]
        pix = page.get_pixmap(clip=pymupdf.Rect(*box), colorspace=pymupdf.csGRAY)
        return sum(1 for b in pix.samples if b < 240)


def _opened(tmp_path, **kwargs) -> tuple[DocumentModel, str]:
    source = str(tmp_path / "modulo.pdf")
    _form_pdf(source, **kwargs)
    model = DocumentModel()
    model.open(source)
    return model, source


def test_reads_the_fields_of_the_source(tmp_path):
    model, _ = _opened(tmp_path)

    fields = {field.name: field for field in model.pages[0].form_fields}
    assert set(fields) == {"nome", "nota", "accetto", "colore"}
    assert fields["nome"].kind == TEXT
    assert fields["nome"].value == "vecchio"
    assert fields["nome"].editable
    assert fields["accetto"].kind == CHECKBOX
    assert fields["accetto"].value == "Off"
    assert not fields["accetto"].checked
    assert fields["colore"].kind == CHOICE
    assert fields["colore"].options == ("rosso", "verde")
    assert fields["colore"].value == "rosso"


def test_opening_records_no_value(tmp_path):
    model, _ = _opened(tmp_path)
    assert model.pages[0].form_values == {}


def test_a_page_without_a_form_has_no_fields(tmp_path):
    source = str(tmp_path / "semplice.pdf")
    _simple_pdf(source)

    model = DocumentModel()
    model.open(source)

    assert model.pages[0].form_fields == []
    assert model.pages[0].form_values == {}


def test_the_value_ends_up_in_the_file(tmp_path):
    model, _ = _opened(tmp_path)
    output = str(tmp_path / "out.pdf")

    model.pages[0].form_values["nome"] = "Anna"
    model.pages[0].form_values["nota"] = "due righe\nscritte a mano"
    save_as(model, output)

    values = _values(output)
    assert values["nome"] == "Anna"
    assert values["nota"] == "due righe\nscritte a mano"


def test_the_checkbox_gets_ticked(tmp_path):
    model, _ = _opened(tmp_path)
    output = str(tmp_path / "out.pdf")

    model.pages[0].form_values["accetto"] = CHECKED
    save_as(model, output)

    assert _values(output)["accetto"] == "Yes"


def test_the_choice_field_changes_value(tmp_path):
    model, _ = _opened(tmp_path)
    output = str(tmp_path / "out.pdf")

    model.pages[0].form_values["colore"] = "verde"
    save_as(model, output)

    assert _values(output)["colore"] == "verde"


def test_clearing_a_field_is_an_edit(tmp_path):
    """Clearing is a change: it must reach the file."""
    model, _ = _opened(tmp_path)
    output = str(tmp_path / "out.pdf")

    model.pages[0].form_values["nome"] = ""
    save_as(model, output)

    assert _values(output)["nome"] == ""


def test_the_source_is_not_touched(tmp_path):
    model, source = _opened(tmp_path)
    output = str(tmp_path / "out.pdf")

    model.pages[0].form_values["nome"] = "Anna"
    save_as(model, output)

    assert _values(source)["nome"] == "vecchio"
    assert _values(output)["nome"] == "Anna"


def test_undo_restores_the_value_from_the_file(tmp_path):
    model, _ = _opened(tmp_path)
    output = str(tmp_path / "out.pdf")
    stack = QUndoStack()

    stack.push(SetFieldValue(model, 0, "nome", "Anna"))
    assert model.pages[0].form_values["nome"] == "Anna"

    stack.undo()
    assert "nome" not in model.pages[0].form_values

    save_as(model, output)
    assert _values(output)["nome"] == "vecchio"


def test_edits_to_the_same_field_are_merged(tmp_path):
    """A QLineEdit emits one signal per keystroke: they must not be ten undos."""
    model, _ = _opened(tmp_path)
    stack = QUndoStack()

    for value in ("A", "An", "Ann", "Anna"):
        stack.push(SetFieldValue(model, 0, "nome", value))

    assert stack.count() == 1, "i tasti dello stesso campo sono un solo comando"
    assert model.pages[0].form_values["nome"] == "Anna"

    stack.undo()
    assert "nome" not in model.pages[0].form_values


def test_different_fields_are_not_merged(tmp_path):
    model, _ = _opened(tmp_path)
    stack = QUndoStack()

    stack.push(SetFieldValue(model, 0, "nome", "A"))
    stack.push(SetFieldValue(model, 0, "nota", "B"))

    assert stack.count() == 2


def test_fields_survive_compression(tmp_path):
    """The clean=True step of compression must not eat the form."""
    model, _ = _opened(tmp_path)
    output = str(tmp_path / "compresso.pdf")

    model.pages[0].form_values["nome"] = "Anna"
    model.pages[0].form_values["accetto"] = CHECKED
    save_compressed(model, output, LEVELS_BY_KEY["light"])

    values = _values(output)
    assert values["nome"] == "Anna"
    assert values["accetto"] == "Yes"


def test_fields_survive_a_redaction_elsewhere(tmp_path):
    """A redaction far from the fields must not take them away."""
    model, _ = _opened(tmp_path)
    output = str(tmp_path / "out.pdf")
    stack = QUndoStack()

    model.pages[0].form_values["nome"] = "Anna"
    stack.push(AddRedaction(model, 0, RedactionRect.from_corners(72, 400, 300, 430)))
    save_as(model, output)

    assert _values(output)["nome"] == "Anna"


def test_geometry_does_not_change_with_a_rotated_page(tmp_path):
    """A field's rectangle lives in page space, like the redaction one."""
    upright = str(tmp_path / "dritto.pdf")
    rotated = str(tmp_path / "ruotato.pdf")
    _form_pdf(upright)
    _form_pdf(rotated, rotation=90)

    first, second = DocumentModel(), DocumentModel()
    first.open(upright)
    second.open(rotated)

    one = {field.name: field.rect for field in first.pages[0].form_fields}
    two = {field.name: field.rect for field in second.pages[0].form_fields}
    assert one == two, "ruotare la pagina non deve spostare i campi"

    assert second.pages[0].unrotated_size == (595, 842)
    assert second.pages[0].width_pt == 842, "la dimensione orientata si scambia"


def test_a_rotated_page_saves_the_value(tmp_path):
    model, _ = _opened(tmp_path, rotation=90)
    output = str(tmp_path / "out.pdf")

    model.pages[0].form_values["nome"] = "Anna"
    save_as(model, output)

    assert _values(output)["nome"] == "Anna"
    with pymupdf.open(output) as doc:
        assert doc[0].rotation == 90


def test_write_fields_ignores_unknown_names(tmp_path):
    _, source = _opened(tmp_path)

    with pymupdf.open(source) as doc:
        page = doc[0]
        assert write_fields(page, {"inesistente": "x"}) == 0
        assert write_fields(page, {"nome": "Anna"}) == 1
        assert write_fields(page, {}) == 0


def test_in_a_merged_document_fields_stay_with_their_page(tmp_path):
    """Merging two PDFs must not mix the fields of the first with those of the second."""
    first, _ = _opened(tmp_path)
    second = str(tmp_path / "secondo.pdf")
    _simple_pdf(second)

    first.append_document(second)
    assert len(first.pages) == 2
    assert len(first.pages[0].form_fields) == 4
    assert first.pages[1].form_fields == []


def test_clearing_a_field_repaints_it_empty(tmp_path):
    """Clearing must also remove the *drawn* text.

    An empty /V with the old appearance would leave the word printed on the
    page, and that is exactly what ``field_value = ""`` does on its own. The
    first ink check is there so the area does not come out empty by
    accident: without it the test would also pass on a form never drawn.
    """
    model, source = _opened(tmp_path)
    output = str(tmp_path / "out.pdf")

    model.pages[0].form_values["nome"] = ""
    save_as(model, output)

    assert _values(output)["nome"] == ""
    assert _ink(source, (72, 100, 300, 128)) > 0, "il file aveva del testo"
    assert _ink(output, (72, 100, 300, 128)) == 0


def test_a_ticked_checkbox_can_be_unticked(tmp_path):
    model, _ = _opened(tmp_path)
    checked = str(tmp_path / "spuntato.pdf")
    empty = str(tmp_path / "vuoto.pdf")

    model.pages[0].form_values["accetto"] = CHECKED
    save_as(model, checked)
    assert _values(checked)["accetto"] == "Yes"

    second = DocumentModel()
    second.open(checked)
    assert second.pages[0].form_fields[2].checked, "la casella risulta spuntata"
    second.pages[0].form_values["accetto"] = "Off"
    save_as(second, empty)

    assert _values(empty)["accetto"] == "Off"


# --- a field repeated over several pages ------------------------------------

def _repeated_form(path: str) -> None:
    """Two pages with the same field «nome»: it is one field, not two."""
    with pymupdf.open() as doc:
        for i in range(2):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 60), f"pagina {i}", fontsize=16)
            _add_fields(
                page,
                "nome",
                pymupdf.PDF_WIDGET_TYPE_TEXT,
                (72, 100, 300, 128),
                "vecchio",
            )
        doc.save(path, garbage=4, deflate=True)


def test_a_repeated_field_changes_on_every_page_that_shows_it(tmp_path):
    """A field's name holds for the document, not for the page.

    MuPDF renames the second copy while it copies the pages (`nome [12]`), so
    the name typed by the user no longer identifies the field: the value must be
    written on the source, in memory, before copying it.
    """
    source = str(tmp_path / "ripetuto.pdf")
    _repeated_form(source)
    model = DocumentModel()
    model.open(source)
    model.pages[0].form_values["nome"] = "nuovo"

    output = str(tmp_path / "out.pdf")
    save_as(model, output)

    assert _values(output, 0)["nome"] == "nuovo"
    # The copy of the second page carries the name renamed by MuPDF
    # (`nome [x]`): this is why the value is written before the copy.
    assert _values_in_order(output, 1) == ["nuovo"]
    assert _values(source, 1)["nome"] == "vecchio", "la sorgente e` intatta"


def test_a_repeated_field_survives_page_reordering(tmp_path):
    """The value does not depend on which page ends up first in the file.

    It is the case that used to lose the edit: once the copy was renamed, the
    reordered page no longer carried a field with the name typed by the user.
    """
    source = str(tmp_path / "ripetuto.pdf")
    _repeated_form(source)
    model = DocumentModel()
    model.open(source)
    model.pages.reverse()
    model.pages[0].form_values["nome"] = "nuovo"

    output = str(tmp_path / "rovesciato.pdf")
    save_as(model, output)

    assert _values(output, 0)["nome"] == "nuovo"
    # The copy of the second page carries the name renamed by MuPDF
    # (`nome [x]`): this is why the value is written before the copy.
    assert _values_in_order(output, 1) == ["nuovo"]

# --------------------------------------------------------------------- #
#  Radio buttons: built by hand, because PyMuPDF cannot create them
# --------------------------------------------------------------------- #
# `radio_forms` writes the group the way PDF describes it: one field (the
# parent) holding the buttons as kids, each kid carrying the one state it can
# show. Its drawn states are what names the options.

from radio_forms import radio_pdf as _radio_pdf


def _radio_raw(path: str) -> tuple[str, list[str]]:
    """What the file itself says: the group's /V and every button's /AS."""
    with pikepdf.Pdf.open(path) as pdf:
        parent = pdf.Root["/AcroForm"]["/Fields"][0]
        return str(parent.get("/V")), [str(kid.get("/AS")) for kid in parent["/Kids"]]


def _radio_opened(tmp_path, **kwargs) -> tuple[DocumentModel, str]:
    source = str(tmp_path / "radio.pdf")
    _radio_pdf(source, **kwargs)
    model = DocumentModel()
    model.open(source)
    return model, source


def test_a_radio_group_is_read_as_the_question_it_is(tmp_path):
    """Every button knows its own option; the choice belongs to the group."""
    model, _ = _radio_opened(tmp_path)

    buttons = model.pages[0].form_fields
    assert [button.kind for button in buttons] == [RADIO, RADIO]
    assert [button.options for button in buttons] == [("primo",), ("secondo",)]
    # Both buttons report the group's choice, not their own Off.
    assert [button.value for button in buttons] == ["primo", "primo"]
    assert all(button.editable for button in buttons)


def test_the_buttons_are_where_the_page_draws_them(tmp_path):
    model, _ = _radio_opened(tmp_path)

    boxes = [field.rect for field in model.pages[0].form_fields]
    assert boxes[0][0] < boxes[1][0], "il primo bottone sta a sinistra del secondo"
    assert boxes[0][1] == boxes[1][1]


def test_the_geometry_does_not_change_on_a_rotated_page(tmp_path):
    """A field belongs to the document: rotating the page must not move it."""
    straight_dir = tmp_path / "dritta"
    turned_dir = tmp_path / "girata"
    straight_dir.mkdir()
    turned_dir.mkdir()
    straight, _ = _radio_opened(straight_dir)
    turned, _ = _radio_opened(turned_dir, rotation=90)

    assert [f.rect for f in straight.pages[0].form_fields] == [
        f.rect for f in turned.pages[0].form_fields
    ]


def test_choosing_a_button_names_the_choice(tmp_path):
    """PDF wants a *name* in /V, and MuPDF writes a string: the file must say
    what the format says, or a reader that follows the rule shows no choice."""
    model, source = _radio_opened(tmp_path)
    model.pages[0].form_values["pasto"] = "secondo"

    output = str(tmp_path / "scelto.pdf")
    save_as(model, output)

    assert _radio_raw(output) == ("/secondo", ["/Off", "/secondo"])
    assert _values(output)["pasto"] == "secondo"
    assert _radio_raw(source)[0] == "/primo", "la sorgente non si tocca"


def test_only_the_button_that_stands_for_the_option_is_turned_on(tmp_path):
    """Writing the value to every button would point a button at a state it
    does not have, and it would paint something it never shows."""
    model, _ = _radio_opened(tmp_path)
    model.pages[0].form_values["pasto"] = "secondo"

    output = str(tmp_path / "uno.pdf")
    save_as(model, output)

    assert _radio_raw(output)[1] == ["/Off", "/secondo"]


def test_a_value_no_button_offers_changes_nothing(tmp_path):
    model, _ = _radio_opened(tmp_path)
    model.pages[0].form_values["pasto"] = "inesistente"

    output = str(tmp_path / "strano.pdf")
    save_as(model, output)

    assert _radio_raw(output) == ("/primo", ["/primo", "/Off"])


def test_taking_the_choice_away_turns_every_button_off(tmp_path):
    """/V lives on the field and /AS on each button: emptying one of the two
    leaves the old button painted as chosen."""
    model, _ = _radio_opened(tmp_path)
    model.pages[0].form_values["pasto"] = ""

    output = str(tmp_path / "vuoto.pdf")
    save_as(model, output)

    assert _radio_raw(output) == ("", ["/Off", "/Off"])


def test_a_rotated_page_saves_the_choice(tmp_path):
    model, _ = _radio_opened(tmp_path, rotation=90)
    model.pages[0].form_values["pasto"] = "secondo"

    output = str(tmp_path / "girata.pdf")
    save_as(model, output)

    assert _radio_raw(output)[0] == "/secondo"
