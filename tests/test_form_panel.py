"""The «Modulo» dock: what its editors show before the user touches them.

An editor that shows a value the file does not hold is a lie the user may then
save. Review 2026-10-19 (R-06): a choice field with no value showed its first
option, as if it had been picked.
"""

import pytest
from PySide6.QtWidgets import QApplication, QComboBox

from plico.model.forms import CHOICE, Field
from plico.widgets.form_panel import FormPanel


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _choice(value: str) -> Field:
    return Field(
        name="colore", kind=CHOICE, value=value, rect=(0, 0, 100, 20), options=("Rosso", "Verde")
    )


def _combo(panel: FormPanel) -> QComboBox:
    combo = panel._editors["colore"]
    assert isinstance(combo, QComboBox)
    return combo


def test_an_empty_choice_shows_nothing_chosen(qapp):
    panel = FormPanel()
    changed: list[tuple[str, str]] = []
    panel.value_changed.connect(lambda name, value: changed.append((name, value)))

    panel.set_page(0, [_choice("")], {})

    combo = _combo(panel)
    assert combo.currentText() == ""
    assert [combo.itemText(i) for i in range(combo.count())] == ["", "Rosso", "Verde"]
    assert changed == [], "costruire il pannello non scrive niente nel modello"


def test_a_stored_choice_is_shown_as_it_is(qapp):
    panel = FormPanel()
    panel.set_page(0, [_choice("Verde")], {})
    assert _combo(panel).currentText() == "Verde"
    assert _combo(panel).count() == 2


def test_a_value_outside_the_options_is_kept_visible(qapp):
    panel = FormPanel()
    panel.set_page(0, [_choice("Blu")], {})
    assert _combo(panel).currentText() == "Blu"
