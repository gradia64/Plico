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

from PySide6.QtCore import QCoreApplication, QLocale, QTranslator

#: Where to look before the usual places: a translator points it at a
#: directory to try a catalog without installing anything.
ENV_DIR = "PLICO_TRANSLATIONS"

FLATPAK_DIR = Path("/app/share/plico/translations")

#: Next to this file, which is where a checkout keeps them and where a
#: translator working on the sources compiles them.
PACKAGE_DIR = Path(__file__).parent / "translations"


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


def install_translators(app: QCoreApplication) -> list[QTranslator]:
    """Load the catalogs that answer the system locale; return what was loaded.

    The translators are kept alive by the application, so the caller does not
    have to hold on to them. A catalog that is missing, empty or unreadable
    leaves its strings in the source language, which is also what happens when
    no catalog exists at all: there is nothing to report to the user.
    """
    loaded: list[QTranslator] = []
    for name in catalog_names(QLocale.system()):
        for directory in catalog_dirs():
            if not (directory / f"{name}.qm").is_file():
                continue
            translator = QTranslator(app)
            if translator.load(name, str(directory)):
                app.installTranslator(translator)
                loaded.append(translator)
                break
    return loaded
