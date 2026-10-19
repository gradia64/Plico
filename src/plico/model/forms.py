"""AcroForm fields: what a page offers, and what the user wrote in them.

A form field is not page content. It is an *annotation* whose value lives in
the field dictionary, and MuPDF exposes it through the page that carries it —
which is why every function here takes a live ``Page`` object rather than a
document plus an index. See :func:`read_fields` for what happens when that
rule is broken.
"""

import re
from dataclasses import dataclass

import pymupdf

# The kinds we know how to edit. PyMuPDF's numeric field types are mapped here
# once, so the rest of the project never has to import pymupdf just to ask what a
# field is.
TEXT = "text"
CHECKBOX = "checkbox"
CHOICE = "choice"
RADIO = "radio"
SIGNATURE = "signature"
UNKNOWN = "unknown"

# PyMuPDF's own ``py.typed`` marker is a promise its generated module cannot
# keep: the widget-type numbers reach the package namespace through a loop over
# the extension module, so a type checker never sees them. The ignores below
# are the whole price of reading MuPDF's constants instead of hard-coding them.
_KINDS = {
    pymupdf.PDF_WIDGET_TYPE_TEXT: TEXT,  # type: ignore[attr-defined]
    pymupdf.PDF_WIDGET_TYPE_CHECKBOX: CHECKBOX,  # type: ignore[attr-defined]
    pymupdf.PDF_WIDGET_TYPE_COMBOBOX: CHOICE,  # type: ignore[attr-defined]
    pymupdf.PDF_WIDGET_TYPE_LISTBOX: CHOICE,  # type: ignore[attr-defined]
    pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: RADIO,  # type: ignore[attr-defined]
    pymupdf.PDF_WIDGET_TYPE_SIGNATURE: SIGNATURE,  # type: ignore[attr-defined]
}

# /Ff bit positions, as PDF defines them.
_FLAG_READ_ONLY = 1 << 0
_FLAG_MULTILINE = 1 << 12

# How PDF spells the two states of a checkbox.
CHECKED = "Yes"
UNCHECKED = "Off"

# Kinds Plico knows how to write back. Radio buttons are here even though
# PyMuPDF cannot *create* one -- ``page.add_widget`` on a radio fails with
# ``ValueError: bad xref`` -- because writing an existing group works, and
# nothing in Plico creates fields: it only fills in what the file already
# has. (An old note here said PyMuPDF also *read* radios with an absurd
# rectangle, and offered that as a second reason to leave them out; a group
# built by another tool reads with a correct one, and the absurd values came
# from a malformed field.) Signature fields belong to the signing milestone,
# not to this one.
_EDITABLE = (TEXT, CHECKBOX, CHOICE, RADIO)


@dataclass(frozen=True)
class Field:
    """A form field as found on one page of a source document."""

    name: str
    kind: str
    value: str
    # PAGE space (unrotated PDF points), exactly like RedactionRect: a field
    # belongs to the document, so it must not move when the page is rotated.
    rect: tuple[float, float, float, float]
    options: tuple[str, ...] = ()
    multiline: bool = False
    read_only: bool = False

    @property
    def editable(self) -> bool:
        """Whether Plico offers an editor for this field."""
        return not self.read_only and self.kind in _EDITABLE

    @property
    def checked(self) -> bool:
        """Whether a checkbox field is ticked."""
        return self.value not in ("", UNCHECKED)


def read_fields(page: pymupdf.Page) -> list[Field]:
    """Describe the form fields of *page*, ignoring the unusable ones.

    *page* must be a **live** object, never ``doc[0]``: a widget keeps a weak
    reference to the page it was read from, so a temporary page is collected
    straight away and the widgets become useless — reading still works, but
    the first ``update()`` afterwards fails with ``RuntimeError: Annot is not
    bound to a page``. Keeping the page in a local variable is the difference
    between a form that saves and a form that raises.
    """
    fields: list[Field] = []
    doc = page.parent
    for widget in page.widgets() or ():
        field = _describe_safely(widget, doc)
        if field is not None:
            fields.append(field)
    return fields


def _describe_safely(widget: pymupdf.Widget, doc: pymupdf.Document) -> Field | None:
    """Like :func:`_describe`, but a broken field yields ``None`` instead.

    PyMuPDF does not refuse a malformed field: it hands back radio buttons
    with an inverted, absurd rectangle, and it raises on the odd widget whose
    page has gone away. Neither may make a whole document unreadable.
    """
    try:
        return _describe(widget, doc)
    except (AttributeError, ReferenceError, RuntimeError, ValueError):
        return None


def _describe(widget: pymupdf.Widget, doc: pymupdf.Document) -> Field | None:
    """Turn one widget into a :class:`Field`, or ``None`` if it is unusable."""
    name = widget.field_name or ""
    if not name:
        return None

    area = widget.rect
    if not area.is_valid or area.is_empty or area.is_infinite:
        return None
    if area.width <= 0 or area.height <= 0:
        return None

    kind = _KINDS.get(widget.field_type, UNKNOWN)
    raw = widget.field_value
    # PyMuPDF 1.28 answers a checkbox with its state name ("Yes"/"Off"), but
    # the type is not promised and older releases gave a bool: a True that
    # reached Field.value would break the first caller treating it as text.
    if isinstance(raw, bool):
        raw = CHECKED if raw else ""
    value = raw or ""
    options = tuple(widget.choice_values or ())
    if kind == RADIO:
        # One button of a group: the one state it can show is its own entry in
        # the appearance, and the value worth showing is the group's choice,
        # not this button's ``Off``.
        value = _radio_value(doc, widget, value)
        options = (_radio_option(widget),)
    return Field(
        name=name,
        kind=kind,
        value=value,
        rect=(area.x0, area.y0, area.x1, area.y1),
        options=options,
        multiline=bool(widget.field_flags & _FLAG_MULTILINE),
        read_only=(
            bool(widget.field_flags & _FLAG_READ_ONLY) or kind not in _EDITABLE
        ),
    )


def _radio_option(widget: pymupdf.Widget) -> str:
    """The one state a radio button can show.

    PDF spells the options of a group in each button's appearance dictionary:
    ``/AP /N`` holds ``/Off`` and the name of the option that button stands
    for, and that name is what the field's ``/V`` is set to when the user
    picks it. A button with nothing but ``Off`` belongs to no option.
    """
    states = widget.button_states() or {}
    for state in states.get("normal") or ():
        name = str(state)
        if name and name.lower() != "off":
            return name
    return ""


def _radio_value(doc: pymupdf.Document, widget: pymupdf.Widget, fallback: str) -> str:
    """What a radio group has chosen.

    The choice belongs to the *field*, which for a group is the parent object,
    while MuPDF hands back each button's own appearance state -- ``Off`` for
    every button the group did not choose. Reading ``/V`` where PDF keeps it
    is the only way to tell a group's value from a button's.
    """
    kind, reference = doc.xref_get_key(widget.xref, "Parent")
    if kind == "xref" and reference:
        value_kind, value = doc.xref_get_key(int(reference.split()[0]), "V")
        # PDF says a button field's /V is a name; MuPDF writes a string here,
        # and files in the wild carry both, so both are accepted.
        if value_kind in ("name", "string") and value:
            return str(value).lstrip("/")
    return fallback


def write_fields(page: pymupdf.Page, values: dict[str, str]) -> int:
    """Write *values* (field name → value) into the widgets of *page*.

    Returns how many fields were written. *page* must stay alive for the whole
    loop, for the reason told in :func:`read_fields`.

    An empty value needs more than ``field_value = ""``. Measured on MuPDF
    1.28: ``field_value = ""`` followed by ``update()`` leaves /V at its old
    text, forcing /V on its own clears the value but leaves the *appearance*
    stream painting the old text over a now-empty field, and the only sequence
    that both clears the value and repaints the field blank is
    ``field_value = ""`` → /V emptied → ``update()``. Hence the three steps
    below, which are not a stylistic choice.
    """
    doc = page.parent
    written = 0
    for widget in page.widgets() or ():
        name = widget.field_name or ""
        if name not in values:
            continue
        value = values[name]
        if _KINDS.get(widget.field_type, UNKNOWN) == RADIO:
            written += _write_radio(doc, widget, value)
            continue
        widget.field_value = value
        if value == "":
            _clear_value(doc, widget)
        widget.update()
        written += 1
    return written


def _write_radio(doc: pymupdf.Document, widget: pymupdf.Widget, value: str) -> int:
    """Choose one option of a radio group, from the button that stands for it.

    The buttons of a group all carry the group's name, so a value written to
    every one of them would be written to the wrong ones too: MuPDF turns the
    other buttons off by itself, but pointing a button at a state it does not
    have leaves it painting something it never shows. Only the button whose
    own state *is* the wanted value may be turned on; the others are skipped.
    """
    if value == "":
        _clear_radio(doc, widget)
        return 1
    if _radio_option(widget) != value:
        return 0
    widget.field_value = value
    widget.update()
    _name_the_choice(doc, widget, value)
    return 1


def _name_the_choice(doc: pymupdf.Document, widget: pymupdf.Widget, value: str) -> None:
    """Write the group's ``/V`` as the *name* PDF asks for.

    MuPDF stores the choice as a string, and PDF says a button field's ``/V``
    is a name; a reader that follows the rule finds a string where it wanted a
    name and shows no choice at all. One call after ``update()`` makes the
    file say what the format says, and costs nothing.
    """
    kind, reference = doc.xref_get_key(widget.xref, "Parent")
    target = int(reference.split()[0]) if kind == "xref" and reference else widget.xref
    doc.xref_set_key(target, "V", f"/{value}")


def _clear_radio(doc: pymupdf.Document, widget: pymupdf.Widget) -> None:
    """Take the choice away from a button group.

    ``/V`` on the field says which option is chosen and each button's ``/AS``
    says what it draws: emptying one of the two leaves the old button painting
    as if it were still chosen.
    """
    kind, reference = doc.xref_get_key(widget.xref, "Parent")
    if kind != "xref" or not reference:
        doc.xref_set_key(widget.xref, "V", "()")
        doc.xref_set_key(widget.xref, "AS", "/Off")
        return
    parent = int(reference.split()[0])
    doc.xref_set_key(parent, "V", "()")
    kids_kind, kids = doc.xref_get_key(parent, "Kids")
    if kids_kind != "array":
        return
    for kid in re.findall(r"(\d+)\s+0\s+R", kids):
        doc.xref_set_key(int(kid), "AS", "/Off")


def _clear_value(doc: pymupdf.Document, widget: pymupdf.Widget) -> None:
    """Force a field's /V to an empty string, so ``update()`` repaints it blank.

    A text field and its widget are usually the same object, but PDF also
    allows a separate field object with the widget as a kid, and then /V
    belongs to the parent — writing it on the annotation would add a second,
    ignored /V.
    """
    kind, reference = doc.xref_get_key(widget.xref, "Parent")
    target = widget.xref
    if kind == "xref" and reference:
        target = int(reference.split()[0])
    doc.xref_set_key(target, "V", "()")
