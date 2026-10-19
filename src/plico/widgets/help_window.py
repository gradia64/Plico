"""The handbook: one HTML page per language, read in a window of Plico.

The pages live inside the package (``plico/help/<code>/index.html``) and are
shown by a QTextBrowser, not by the system's browser: inside the Flatpak a
file under /app is not visible to the host, and the handbook must work
offline anyway. One page per language, with the same section ids in all of
them, so that a link or a test can point at «redact» in any language.

The language is the interface's -- the one chosen in «Impostazioni», or the
system's -- with English for a language Plico has no handbook in.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QLocale, QUrl
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget

from .. import i18n

HELP_DIR = Path(__file__).resolve().parent.parent / "help"

# QTextBrowser understands a subset of CSS: enough for a readable page that
# still follows the desktop's colours (no colour is set here on purpose).
_STYLE = """
h1 { font-size: x-large; }
h2 { font-size: large; margin-top: 18px; }
code { font-family: monospace; }
table { border-collapse: collapse; margin-top: 6px; }
th, td { padding: 3px 12px 3px 0; }
th { text-align: left; }
"""


def help_language(locale: QLocale | None = None) -> str:
    """The language code of the handbook for *locale* (the default locale)."""
    locale = QLocale() if locale is None else locale
    if locale.language() == QLocale.Language.C:
        # No language chosen at all: the interface stays in its source
        # language, and so does the handbook.
        return i18n.SOURCE_LANGUAGE
    for tag in locale.uiLanguages():
        code = str(tag).replace("_", "-").split("-")[0].lower()
        if code in i18n.LANGUAGES:
            return code
    return "en"


def help_page(code: str) -> Path:
    """The handbook page for language *code*, English when there is none."""
    page = HELP_DIR / code / "index.html"
    return page if page.is_file() else HELP_DIR / "en" / "index.html"


class HelpWindow(QDialog):
    """A non-modal window with the handbook, kept open beside the document."""

    def __init__(self, parent: QWidget | None = None, code: str | None = None) -> None:
        super().__init__(parent)
        self.resize(760, 820)
        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(True)
        self.browser.document().setDefaultStyleSheet(_STYLE)
        self.page = help_page(code or help_language())
        self.browser.setSource(QUrl.fromLocalFile(str(self.page)))
        self.setWindowTitle(self.browser.documentTitle() or "Plico")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.browser)
        layout.addWidget(buttons)

    def show_section(self, anchor: str) -> None:
        """Scroll to the section with id *anchor* (the same in every language)."""
        self.browser.scrollToAnchor(anchor)
