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

SENZA_NOME = "(senza nome)"
NESSUN_CAMPO = "Questa pagina non ha campi compilabili."


def _svuota(layout: QFormLayout) -> None:
    """Remove every row of *layout*, widgets included."""
    while layout.count():
        voce = layout.takeAt(0)
        if voce is None:
            break
        widget = voce.widget()
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

        self._avviso = QLabel(NESSUN_CAMPO)
        self._avviso.setWordWrap(True)
        self._avviso.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._contenuto = QWidget()
        self._form = QFormLayout(self._contenuto)
        self._form.setContentsMargins(8, 8, 8, 8)
        self._form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setWidget(self._contenuto)

        disposizione = QVBoxLayout(self)
        disposizione.setContentsMargins(0, 0, 0, 0)
        disposizione.addWidget(self._avviso)
        disposizione.addWidget(self._area)

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
        _svuota(self._form)

        compilabili = [campo for campo in fields if campo.editable]
        if not compilabili:
            self._area.hide()
            self._avviso.show()
            return

        self._avviso.hide()
        self._area.show()
        for campo in compilabili:
            valore = values.get(campo.name, campo.value)
            self._seen[campo.name] = valore
            editor = self._make_editor(campo, valore)
            self._editors[campo.name] = editor
            self._form.addRow(campo.name or SENZA_NOME, editor)

    def select_field(self, name: str) -> None:
        """Put the cursor in the editor of *name*, if it is on this page."""
        editor = self._editors.get(name)
        if editor is None:
            return
        editor.setFocus(Qt.FocusReason.OtherFocusReason)

    # ------------------------------------------------------------------ #
    #  Editors
    # ------------------------------------------------------------------ #

    def _make_editor(self, campo: Field, valore: str) -> QWidget:
        """Build the editor for *campo* and start listening to it.

        The value is set BEFORE the signal is connected: filling an editor
        programmatically must not look like the user typing, or every page
        change would push an undo command.
        """
        if campo.kind == CHECKBOX:
            casella = QCheckBox()
            casella.setChecked(valore not in ("", UNCHECKED))
            casella.toggled.connect(
                lambda acceso, nome=campo.name: self._changed(
                    nome, CHECKED if acceso else UNCHECKED
                )
            )
            return casella

        if campo.kind == CHOICE:
            tendina = QComboBox()
            scelte = list(campo.options)
            if valore and valore not in scelte:
                # A choice whose stored value is not among the options: keep it
                # visible rather than silently dropping what the file says.
                scelte.insert(0, valore)
            tendina.addItems(scelte)
            tendina.setCurrentText(valore)
            tendina.currentTextChanged.connect(
                lambda testo, nome=campo.name: self._changed(nome, testo)
            )
            return tendina

        if campo.multiline:
            area = QPlainTextEdit()
            area.setPlainText(valore)
            area.setMinimumHeight(72)
            area.textChanged.connect(
                lambda nome=campo.name, editor=area: self._changed(
                    nome, editor.toPlainText()
                )
            )
            return area

        riga = QLineEdit(valore)
        # textEdited, not textChanged: only the user's keystrokes.
        riga.textEdited.connect(
            lambda testo, nome=campo.name: self._changed(nome, testo)
        )
        return riga

    def _changed(self, name: str, value: str) -> None:
        """Report a real change; remember it so a round trip still counts."""
        if self._seen.get(name) == value:
            return
        self._seen[name] = value
        self.value_changed.emit(name, value)
