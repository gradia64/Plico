"""The handbook: five languages, one structure, and the app it describes.

A handbook goes stale without anyone noticing: a shortcut changes, a menu
entry is renamed in a catalog, a section is added in one language only. These
tests read the pages and the real window, so that each of those fails here.
"""

import html
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
from PySide6.QtCore import QLocale, QTranslator
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from plico import i18n
from plico.widgets.help_window import HELP_DIR, HelpWindow, help_language, help_page

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = sorted(i18n.LANGUAGES)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class _Page(HTMLParser):
    """The ids, the table of contents and the rows of the shortcuts table."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.toc: list[str] = []
        self.rows = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if tag == "a" and (attributes.get("href") or "").startswith("#"):
            self.toc.append(attributes["href"][1:])
        if tag == "tr":
            self.rows += 1


def _read(code: str) -> tuple[_Page, str]:
    source = (HELP_DIR / code / "index.html").read_text(encoding="utf-8")
    page = _Page()
    page.feed(source)
    text = html.unescape(re.sub(r"<[^>]+>", " ", source))
    return page, " ".join(text.split())


@pytest.mark.parametrize("code", LANGUAGES)
def test_every_language_has_the_same_handbook(code):
    page, _ = _read(code)
    italian, _ = _read("it")
    assert page.ids == italian.ids, "le sezioni devono essere le stesse, nello stesso ordine"
    assert page.toc == page.ids, "l'indice punta a ogni sezione, e solo a quelle"
    assert page.rows == italian.rows, "la tabella delle scorciatoie ha le stesse righe"


def test_every_shortcut_of_the_menus_is_in_the_handbook(qapp):
    """The Italian page against the real window: a changed shortcut fails here."""
    from plico.main_window import MainWindow

    _, text = _read("it")
    window = MainWindow()
    try:
        keys = {
            action.shortcut().toString(QKeySequence.SequenceFormat.PortableText)
            for menu in (a.menu() for a in window.menuBar().actions())
            for action in menu.actions()
            if not action.shortcut().isEmpty()
        }
        keys |= {"Ctrl+R", "Ctrl+Shift+R", "F3", "Shift+F3", "Esc"}
        portable = text.replace("Canc", "Del")
        missing = sorted(key for key in keys if key not in portable)
        assert not missing, f"scorciatoie assenti dalla guida: {missing}"
    finally:
        window.shutdown_worker()
        window.deleteLater()


def _compiled(tmp_path: Path, code: str) -> Path:
    tool = shutil.which("lrelease") or shutil.which("pyside6-lrelease")
    if tool is None:
        pytest.skip("lrelease sta solo nell'ambiente di build di Qt (vedi CONTESTO §11)")
    target = tmp_path / f"plico_{code}.qm"
    subprocess.run(
        [tool, str(ROOT / "src/plico/translations" / f"plico_{code}.ts"), "-qm", str(target)],
        check=True,
        capture_output=True,
    )
    return target


@pytest.mark.parametrize("code", LANGUAGES)
def test_the_handbook_names_the_commands_as_the_menus_do(qapp, tmp_path, code):
    """A menu entry renamed in a catalog must be renamed in the handbook too."""
    from plico.main_window import MainWindow

    translator = None
    if code != "it":
        translator = QTranslator(qapp)
        assert translator.load(str(_compiled(tmp_path, code)))
        qapp.installTranslator(translator)
    _, text = _read(code)
    window = MainWindow()
    try:
        menus = [a.menu() for a in window.menuBar().actions()][:-1]  # not «Help»
        names = {
            action.text().replace("&", "").rstrip("…").strip()
            for menu in menus
            for action in menu.actions()
            if action.text()
        }
        lowered = text.lower()
        missing = sorted(name for name in names if name.lower() not in lowered)
        assert not missing, f"{code}: comandi non nominati nella guida: {missing}"
    finally:
        window.shutdown_worker()
        window.deleteLater()
        if translator is not None:
            qapp.removeTranslator(translator)


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("it_IT", "it"),
        ("fr_CH", "fr"),
        ("de_DE", "de"),
        ("es_MX", "es"),
        ("en_GB", "en"),
        ("pt_BR", "en"),  # no handbook in Portuguese: English, like the interface
        ("C", "it"),  # no language at all: the interface's source language
    ],
)
def test_the_handbook_follows_the_interface_language(locale, expected):
    assert help_language(QLocale(locale)) == expected


def test_a_language_without_a_page_falls_back_to_english():
    assert help_page("pt") == HELP_DIR / "en" / "index.html"
    assert help_page("fr") == HELP_DIR / "fr" / "index.html"


def test_f1_opens_one_handbook_window(qapp):
    from plico.main_window import MainWindow

    window = MainWindow()
    try:
        assert window._help_act.shortcut() == QKeySequence(QKeySequence.StandardKey.HelpContents)
        window._open_help()
        first = window._help_window
        window._open_help()
        assert window._help_window is first, "F1 due volte non apre due finestre"
        assert isinstance(first, HelpWindow)
        assert "Plico" in first.windowTitle()
        assert "Ctrl+F" in first.browser.toPlainText()
        first.show_section("redact")  # an id that exists in every language
        first.close()
    finally:
        window.shutdown_worker()
        window.deleteLater()
