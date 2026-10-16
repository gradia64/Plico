"""The «Modulo» dock: one editor per form field of the page in view.

The panel is deliberately thin. It shows the fields the model already
describes and reports what the user writes; it never *keeps* the truth. The
values live in ``PageItem.form_values``, so a page change, an undo or a
rotation all just re-render the same function of the model.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..model.forms import CHECKBOX, CHECKED, CHOICE, UNCHECKED, Field


def _clear(layout: QFormLayout) -> None:
    """Remove every row of *layout*, widgets included."""
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            break
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class FormPanel(QWidget):
    """Editors for the form fields of one page."""

    # (field name, new value) — emitted only when the user really changes one.
    value_changed = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = 0
        self._editors: dict[str, QWidget] = {}
        # The value the editor was last seen carrying. It is updated on every
        # accepted change, so typing a value and then typing it back still
        # reports a change instead of quietly keeping the old one.
        self._seen: dict[str, str] = {}

        self._notice = QLabel(self.tr("Questa pagina non ha campi compilabili."))
        self._notice.setWordWrap(True)
        self._notice.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._content = QWidget()
        self._form = QFormLayout(self._content)
        self._form.setContentsMargins(8, 8, 8, 8)
        self._form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setWidget(self._content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._notice)
        layout.addWidget(self._area)

        self.set_page(0, [], {})

    # ------------------------------------------------------------------ #
    #  What the window asks
    # ------------------------------------------------------------------ #

    def page(self) -> int:
        """The page these editors belong to."""
        return self._row

    def set_page(self, row: int, fields: list[Field], values: dict[str, str]) -> None:
        """Rebuild the editors for page *row*.

        Read-only fields are not shown at all: an editor that cannot be saved
        would be a promise we do not keep. They are still in the model, and
        the page view still paints where they are.
        """
        self._row = row
        self._editors = {}
        self._seen = {}
        _clear(self._form)

        editable = [field for field in fields if field.editable]
        if not editable:
            self._area.hide()
            self._notice.show()
            return

        self._notice.hide()
        self._area.show()
        for field in editable:
            value = values.get(field.name, field.value)
            self._seen[field.name] = value
            editor = self._make_editor(field, value)
            self._editors[field.name] = editor
            self._form.addRow(field.name or self.tr("(senza nome)"), editor)

    def select_field(self, name: str) -> None:
        """Put the cursor in the editor of *name*, if it is on this page."""
        editor = self._editors.get(name)
        if editor is None:
            return
        editor.setFocus(Qt.FocusReason.OtherFocusReason)

    # ------------------------------------------------------------------ #
    #  Editors
    # ------------------------------------------------------------------ #

    def _make_editor(self, field: Field, value: str) -> QWidget:
        """Build the editor for *field* and start listening to it.

        The value is set BEFORE the signal is connected: filling an editor
        programmatically must not look like the user typing, or every page
        change would push an undo command.
        """
        if field.kind == CHECKBOX:
            box = QCheckBox()
            box.setChecked(value not in ("", UNCHECKED))
            box.toggled.connect(
                lambda checked, name=field.name: self._changed(
                    name, CHECKED if checked else UNCHECKED
                )
            )
            return box

        if field.kind == CHOICE:
            combo = QComboBox()
            options = list(field.options)
            if value and value not in options:
                # A choice whose stored value is not among the options: keep it
                # visible rather than silently dropping what the file says.
                options.insert(0, value)
            combo.addItems(options)
            combo.setCurrentText(value)
            combo.currentTextChanged.connect(
                lambda text, name=field.name: self._changed(name, text)
            )
            return combo

        if field.multiline:
            multiline = QPlainTextEdit()
            multiline.setPlainText(value)
            multiline.setMinimumHeight(72)
            multiline.textChanged.connect(
                lambda name=field.name, editor=multiline: self._changed(
                    name, editor.toPlainText()
                )
            )
            return multiline

        line = QLineEdit(value)
        # textEdited, not textChanged: only the user's keystrokes.
        line.textEdited.connect(
            lambda text, name=field.name: self._changed(name, text)
        )
        return line

    def _changed(self, name: str, value: str) -> None:
        """Report a real change; remember it so a round trip still counts."""
        if self._seen.get(name) == value:
            return
        self._seen[name] = value
        self.value_changed.emit(name, value)
