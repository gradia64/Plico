"""The shipped translations: complete, faithful to their placeholders, usable.

Plico is written in Italian and translated into English, Spanish, French and
German. A catalog that is out of date, that drops a ``{0}`` or that gives two
menu entries the same accelerator does not fail anywhere by itself -- it
shows the user a half-Italian window, a message with a hole in it, or an Alt
key that picks the wrong entry. These tests are where it fails instead.
"""

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from plico import i18n

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS = ROOT / "src" / "plico" / "translations"
LANGUAGES = {"en": "en_US", "es": "es_ES", "fr": "fr_FR", "de": "de_DE"}
PLACEHOLDER = re.compile(r"\{\d+\}|%\([a-z]+\)s")


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _messages(code: str) -> list[tuple[str, str, ET.Element]]:
    root = ET.parse(TRANSLATIONS / f"plico_{code}.ts").getroot()
    return [
        (context.findtext("name") or "", message.findtext("source") or "", message)
        for context in root.findall("context")
        for message in context.findall("message")
    ]


def test_every_language_has_a_catalog():
    shipped = sorted(path.stem for path in TRANSLATIONS.glob("plico_*.ts"))
    assert shipped == sorted(f"plico_{code}" for code in LANGUAGES)


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_the_catalog_names_its_language(code):
    root = ET.parse(TRANSLATIONS / f"plico_{code}.ts").getroot()
    assert root.get("language") == LANGUAGES[code]
    assert root.get("sourcelanguage") == "it"


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_every_message_is_translated(code):
    untranslated = [
        source
        for _, source, message in _messages(code)
        if message.find("translation").get("type") == "unfinished"
        or not (message.findtext("translation") or "").strip()
    ]
    assert untranslated == []


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_the_catalogs_hold_the_same_messages(code):
    """All four are made from the same sources: none may lag behind."""
    english = {(context, source) for context, source, _ in _messages("en")}
    assert {(context, source) for context, source, _ in _messages(code)} == english


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_placeholders_and_accelerators_survive(code):
    """A dropped ``{0}`` makes ``format()`` print a sentence with a hole."""
    for context, source, message in _messages(code):
        text = message.findtext("translation") or ""
        assert sorted(PLACEHOLDER.findall(text)) == sorted(PLACEHOLDER.findall(source)), (
            f"{context}: {source!r} -> {text!r}"
        )
        assert ("&" in text) == ("&" in source), f"{context}: {source!r} -> {text!r}"


def _compiled(tmp_path: Path, code: str) -> Path:
    tool = shutil.which("lrelease") or shutil.which("pyside6-lrelease")
    if tool is None:
        pytest.skip("lrelease sta solo nell'ambiente di build di Qt")
    target = tmp_path / f"plico_{code}.qm"
    subprocess.run(
        [tool, str(TRANSLATIONS / f"plico_{code}.ts"), "-qm", str(target)],
        check=True,
        capture_output=True,
    )
    return target


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_the_window_speaks_the_language(qapp, tmp_path, code):
    """Loaded for real: menus translated, and no menu with two equal accelerators."""
    from plico.main_window import MainWindow

    compiled = _compiled(tmp_path, code)
    translator = QTranslator(qapp)
    assert translator.load(str(compiled))
    qapp.installTranslator(translator)
    window = MainWindow()
    try:
        menus = [action.menu() for action in window.menuBar().actions()]
        titles = [action.text() for action in window.menuBar().actions()]
        assert titles[0] != "&File" or code == "en", titles
        assert "&Modifica" not in titles, titles
        for menu in menus:
            letters = []
            for action in menu.actions():
                text = action.text()
                assert not any(
                    italian in text for italian in ("Salva", "Cancella", "Unisci", "Riconosci")
                ), f"{code}: «{text}» non tradotto"
                if "&" in text:
                    letters.append(text[text.index("&") + 1].lower())
            assert len(letters) == len(set(letters)), f"{code}: acceleratori doppi {letters}"
        top = [title[title.index("&") + 1].lower() for title in titles if "&" in title]
        assert len(top) == len(set(top)), f"{code}: acceleratori doppi nei menu {top}"
    finally:
        window.shutdown_worker()
        window.deleteLater()
        qapp.processEvents()
        qapp.removeTranslator(translator)


def test_a_language_without_a_catalog_gets_english(qapp, tmp_path, monkeypatch):
    """Italian is what the code says; English is what more people read."""
    _compiled(tmp_path, "en")
    monkeypatch.setattr(i18n, "catalog_dirs", lambda: [tmp_path])

    loaded = i18n.install_translators(qapp, QLocale("pt_BR"))
    try:
        assert len(loaded) == 1
        assert QCoreApplication.translate("MainWindow", "Pronto") == "Ready"
    finally:
        for translator in loaded:
            qapp.removeTranslator(translator)


def test_italian_needs_no_catalog(qapp, tmp_path, monkeypatch):
    _compiled(tmp_path, "en")
    monkeypatch.setattr(i18n, "catalog_dirs", lambda: [tmp_path])

    assert i18n.install_translators(qapp, QLocale("it_IT")) == []
    assert QCoreApplication.translate("MainWindow", "Pronto") == "Pronto"


def test_qt_s_own_buttons_follow_the_language(qapp):
    """«Discard» under an Italian question was Qt's catalog not being loaded."""
    translator = i18n.install_qt_translator(qapp, QLocale("it_IT"))
    if translator is None:
        pytest.skip("i cataloghi di Qt non sono installati qui")
    try:
        assert QCoreApplication.translate("QPlatformTheme", "Cancel") != "Cancel"
    finally:
        qapp.removeTranslator(translator)


def test_a_language_chosen_in_the_settings_beats_the_system(qapp, tmp_path, monkeypatch):
    """«Impostazioni»: French chosen on any system loads the French catalog."""
    from plico.app import apply_language

    compiled = _compiled(tmp_path, "fr")
    monkeypatch.setenv(i18n.ENV_DIR, str(compiled.parent))
    before = QLocale()
    try:
        loaded = apply_language(qapp, "fr")
        assert [Path(t.filePath()).name for t in loaded] == ["plico_fr.qm"]
        assert QLocale().language() == QLocale.Language.French
        assert qapp.translate("MainWindow", "&Impostazioni") == "&Configuration"
    finally:
        for translator in loaded:
            qapp.removeTranslator(translator)
        QLocale.setDefault(before)


def test_italian_chosen_loads_nothing_at_all(qapp):
    from plico.app import apply_language

    before = QLocale()
    try:
        assert apply_language(qapp, "it") == []
    finally:
        QLocale.setDefault(before)
