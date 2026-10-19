"""Loading the compiled catalogs, when there are any.

The strings the user reads are Italian in the source, so Plico runs in Italian
even with nothing loaded: a catalog is what turns it into another language, and
an empty catalog changes nothing. The `.ts` files a translator edits live in
``translations/`` next to this package; ``lrelease`` turns them into the `.qm`
files loaded here. That tool lives only in the Qt *build* environment, so the
Flatpak manifest compiles the catalogs while it builds (§11) and a plain
``pip install`` ships the sources, for whoever wants to compile one.
"""

import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

#: Where to look before the usual places: a translator points it at a
#: directory to try a catalog without installing anything.
ENV_DIR = "PLICO_TRANSLATIONS"

FLATPAK_DIR = Path("/app/share/plico/translations")

#: Next to this file, which is where a checkout keeps them and where a
#: translator working on the sources compiles them.
PACKAGE_DIR = Path(__file__).parent / "translations"

#: The source language: a user who reads it needs no catalog.
SOURCE_LANGUAGE = "it"

#: For a language Plico has no catalog for. Italian is what the code says,
#: and far fewer people read it than English.
FALLBACK = "plico_en"

#: The languages Plico speaks, each named in itself, as the «Impostazioni»
#: dialog lists them. Italian needs no catalog: it is the source.
LANGUAGES = {
    "it": "Italiano",
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
}


def chosen_locale(language: str | None) -> QLocale | None:
    """The locale for a language chosen in the settings; None means the system's.

    A code Plico does not know -- a setting written by a later version, a
    hand-edited file -- counts as "automatic" rather than as an error.
    """
    if language in LANGUAGES:
        return QLocale(language)
    return None


def catalog_dirs() -> list[Path]:
    """Every place a compiled catalog may be, most specific first."""
    directories = [PACKAGE_DIR, FLATPAK_DIR]
    override = os.environ.get(ENV_DIR)
    if override:
        directories.insert(0, Path(override))
    return directories


def catalog_names(locale: QLocale) -> list[str]:
    """The catalog names to try, best match first.

    ``it_IT`` asks for ``plico_it_IT`` and then for ``plico_it``: a catalog
    written for the language is better than none, and the source strings may
    well be in that language already. The ``C`` locale means "no language was
    chosen" and asks for nothing.
    """
    if locale.language() == QLocale.Language.C:
        return []
    names: list[str] = []
    for tag in locale.uiLanguages():
        name = str(tag).replace("-", "_")
        if name and name not in names:
            names.append(name)
    return [f"plico_{name}" for name in names]


def install_translators(
    app: QCoreApplication, locale: QLocale | None = None
) -> list[QTranslator]:
    """Load the catalogs that answer *locale* (the system's); return what was loaded.

    The translators are kept alive by the application, so the caller does not
    have to hold on to them. A catalog that is missing, empty or unreadable
    leaves its strings in the source language, which is also what happens when
    no catalog exists at all: there is nothing to report to the user.

    A language Plico has no catalog for gets the English one, when there is
    one: someone who reads Portuguese is far likelier to read English than the
    Italian the code is written in. The ``C`` locale and Italian get nothing.
    """
    locale = QLocale.system() if locale is None else locale
    names = catalog_names(locale)
    loaded: list[QTranslator] = []
    for name in names:
        translator = _load(app, name)
        if translator is not None:
            loaded.append(translator)
    speaks_source = any(name.startswith(f"plico_{SOURCE_LANGUAGE}") for name in names)
    if not loaded and names and not speaks_source:
        translator = _load(app, FALLBACK)
        if translator is not None:
            loaded.append(translator)
    return loaded


def _load(app: QCoreApplication, name: str) -> QTranslator | None:
    """Install the catalog *name* from the first directory that has it."""
    for directory in catalog_dirs():
        if not (directory / f"{name}.qm").is_file():
            continue
        translator = QTranslator(app)
        if translator.load(name, str(directory)):
            app.installTranslator(translator)
            return translator
    return None


def install_qt_translator(
    app: QCoreApplication, locale: QLocale | None = None
) -> QTranslator | None:
    """Load Qt's own catalog, for the buttons and dialogs Qt draws itself.

    «Save», «Cancel», the file dialog: their text comes from Qt, in English,
    and without its catalog an Italian user read «Discard» under an Italian
    question. Qt ships the catalogs (``qtbase_it.qm`` …) where QLibraryInfo
    says; in the Flatpak that is the runtime's copy.
    """
    locale = QLocale.system() if locale is None else locale
    if locale.language() == QLocale.Language.C:
        return None
    translator = QTranslator(app)
    directory = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not translator.load(locale, "qtbase", "_", directory):
        return None
    app.installTranslator(translator)
    return translator
