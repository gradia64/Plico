"""AcroForm fields: what a page offers, and what the user wrote in them.

A form field is not page content. It is an *annotation* whose value lives in
the field dictionary, and MuPDF exposes it through the page that carries it —
which is why every function here takes a live ``Page`` object rather than a
document plus an index. See :func:`read_fields` for what happens when that
rule is broken.
"""

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

# Kinds Plico knows how to write back. Radio buttons are deliberately missing:
# PyMuPDF cannot build them (``ValueError: bad xref``) and reads them with an
# inverted, absurd rectangle, so offering an editor for them would be a
# promise the save path could not keep. Signature fields belong to the signing
# milestone, not to this one.
_EDITABLE = (TEXT, CHECKBOX, CHOICE)


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
    for widget in page.widgets() or ():
        field = _describe_safely(widget)
        if field is not None:
            fields.append(field)
    return fields


def _describe_safely(widget: pymupdf.Widget) -> Field | None:
    """Like :func:`_describe`, but a broken field yields ``None`` instead.

    PyMuPDF does not refuse a malformed field: it hands back radio buttons with
    an inverted, absurd rectangle, and it raises on the odd widget whose page
    has gone away. Neither may make a whole document unreadable.
    """
    try:
        return _describe(widget)
    except (AttributeError, ReferenceError, RuntimeError, ValueError):
        return None


def _describe(widget: pymupdf.Widget) -> Field | None:
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
    return Field(
        name=name,
        kind=kind,
        value=widget.field_value or "",
        rect=(area.x0, area.y0, area.x1, area.y1),
        options=tuple(widget.choice_values or ()),
        multiline=bool(widget.field_flags & _FLAG_MULTILINE),
        read_only=(
            bool(widget.field_flags & _FLAG_READ_ONLY) or kind not in _EDITABLE
        ),
    )


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
        widget.field_value = value
        if value == "":
            _clear_value(doc, widget)
        widget.update()
        written += 1
    return written


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
