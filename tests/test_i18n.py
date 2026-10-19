"""Translations: extracted from the sources, compiled, loaded.

Nothing here depends on what the catalogs say: test_translations.py checks
the English, Spanish, French and German ones. What is tested is the machinery
-- the strings are extractable, the shipped catalog is the one the sources
produce, the loader asks for the right names -- so that a new language is only
a matter of filling a file in.
"""

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication

from plico import i18n

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "src" / "plico"
CATALOG = SOURCES / "translations" / "plico_en.ts"

#: A string the code shows that no refactor is likely to move.
A_VISIBLE_STRING = "Nessuna occorrenza di «{0}»."


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _messages(path: Path) -> set[tuple[str, str]]:
    """Every (context, source) a catalog holds."""
    root = ET.parse(path).getroot()
    found = set()
    for context in root.findall("context"):
        name = context.findtext("name") or ""
        for message in context.findall("message"):
            found.add((name, message.findtext("source") or ""))
    return found


def _extract(tmp_path: Path) -> Path:
    """Run the extractor over the sources, as the release does."""
    tool = shutil.which("pylupdate6")
    if tool is None:
        pytest.skip("pylupdate6 non c'e`: l'estrazione gira dove ci sono i tool Qt")
    output = tmp_path / "estratto.ts"
    subprocess.run(
        [tool, str(SOURCES), "-ts", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return output


def test_the_sources_still_hold_the_strings_we_show(tmp_path):
    """The extractor understands how this code calls tr()."""
    messages = _messages(_extract(tmp_path))

    assert len(messages) > 150, f"solo {len(messages)} messaggi estratti"
    assert any(source == A_VISIBLE_STRING for _, source in messages)


def test_the_shipped_catalog_is_the_one_the_sources_produce(tmp_path):
    """A new tr() string must not stay out of the catalog translators edit."""
    extracted = _messages(_extract(tmp_path))
    shipped = _messages(CATALOG)

    assert shipped == extracted, (
        "il catalogo non e` aggiornato: rigenera con "
        f"`pylupdate6 src/plico -ts {CATALOG.relative_to(ROOT)}`"
    )


def test_the_catalog_says_which_language_it_translates_to():
    root = ET.parse(CATALOG).getroot()

    assert root.get("language") == "en_US"
    assert root.get("sourcelanguage") == "it", "le stringhe nel codice sono italiane"


def test_the_c_locale_asks_for_no_catalog():
    """`C` is not a language: it means nobody chose one."""
    assert i18n.catalog_names(QLocale.c()) == []


def test_a_locale_falls_back_to_its_language():
    names = i18n.catalog_names(QLocale("it_IT"))

    assert "plico_it_IT" in names
    assert names[-1] == "plico_it", names
    assert len(names) == len(set(names))


def test_the_environment_variable_comes_first(tmp_path, monkeypatch):
    monkeypatch.setenv(i18n.ENV_DIR, str(tmp_path))

    directories = i18n.catalog_dirs()

    assert directories[0] == tmp_path
    assert i18n.PACKAGE_DIR in directories, "un checkout resta una sorgente valida"


def test_without_a_catalog_nothing_is_loaded(qapp, monkeypatch):
    """No catalogs installed is the normal case, and it must not raise."""
    monkeypatch.setenv(i18n.ENV_DIR, str(Path("/nonexistent/plico")))

    assert i18n.install_translators(qapp) == []


def test_a_compiled_catalog_is_loaded_and_translates(qapp, tmp_path, monkeypatch):
    """The whole way round: a .ts with a translation becomes a .qm that is used."""
    tool = shutil.which("lrelease") or shutil.which("pyside6-lrelease")
    if tool is None:
        pytest.skip("lrelease sta solo nell'ambiente di build di Qt (vedi CONTESTO §11)")

    source = tmp_path / "plico_it.ts"
    source.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="it_IT" sourcelanguage="en">
<context>
    <name>Prova</name>
    <message>
        <source>Livello</source>
        <translation>Livello tradotto</translation>
    </message>
</context>
</TS>
""",
        encoding="utf-8",
    )
    subprocess.run(
        [tool, str(source), "-qm", str(tmp_path / "plico_it.qm")],
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(i18n, "catalog_names", lambda locale: ["plico_it"])
    monkeypatch.setattr(i18n, "catalog_dirs", lambda: [tmp_path])

    loaded = i18n.install_translators(qapp)

    try:
        assert len(loaded) == 1
        assert qapp.translate("Prova", "Livello") == "Livello tradotto"
    finally:
        for translator in loaded:
            qapp.removeTranslator(translator)
