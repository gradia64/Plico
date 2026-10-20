"""Controlli dentro l'AppImage, eseguiti con il suo Python (smoke-test.sh).

APPDIR viene dall'ambiente, come lo imposterebbe il runtime, e così
PLICO_TESSDATA, che l'AppRun punta ai dati di lingua inclusi. Li usa anche il
collaudo del .deb (packaging/deb/smoke-test.sh), con APPDIR=/opt/plico e
l'icona, che lì sta in /usr/share, in PLICO_ICON.
"""
import os
import sys
from pathlib import Path

APPDIR = Path(os.environ["APPDIR"])
sys.path.insert(0, str(APPDIR / "usr" / "share" / "plico"))

from PySide6.QtCore import QLibraryInfo, QLocale  # noqa: E402
from PySide6.QtGui import QIcon, QImageReader  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import pikepdf  # noqa: E402
import pymupdf  # noqa: E402
from pyhanko.sign import signers  # noqa: E402,F401  firma PAdES

from plico import __version__, i18n  # noqa: E402
from plico.main_window import MainWindow  # noqa: E402,F401
from plico.model import ocr  # noqa: E402
from plico.widgets.help_window import help_page  # noqa: E402

# l'icona e i formati che servono a «Crea da immagini»
icon = Path(os.environ.get(
    "PLICO_ICON", APPDIR / "usr/share/icons/hicolor/scalable/apps/io.github.gradia64.plico.svg"))
assert not QIcon(str(icon)).pixmap(64, 64).isNull(), "icona SVG non caricata"
formats = {bytes(f).decode() for f in QImageReader.supportedImageFormats()}
assert {"svg", "png", "jpeg", "gif"} <= formats, formats

# i cataloghi di Plico compilati, e quelli di Qt per i suoi pulsanti
compiled = sorted(p.name for p in i18n.PACKAGE_DIR.glob("plico_*.qm"))
assert compiled == ["plico_de.qm", "plico_en.qm", "plico_es.qm", "plico_fr.qm"], compiled
qt = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
assert {f"qtbase_{c}.qm" for c in ("it", "fr", "de", "es")} <= {p.name for p in qt.iterdir()}
loaded = i18n.install_translators(app, QLocale("fr"))
assert app.translate("MainWindow", "&Impostazioni") == "&Configuration", "catalogo non caricato"
for translator in loaded:
    app.removeTranslator(translator)

# la guida in ogni lingua
for code in i18n.LANGUAGES:
    assert help_page(code).name == "index.html" and help_page(code).parent.name == code

# OCR vero: Tesseract è dentro MuPDF, i dati di lingua sono nell'immagine
assert ocr.unavailable_reason() is None, ocr.unavailable_reason()
assert set(ocr.languages()) >= {"ita", "eng", "fra", "deu", "spa"}, ocr.languages()
doc = pymupdf.open()
page = doc.new_page()
page.insert_text((72, 100), "Plico riconosce questo testo", fontsize=28)
scan = pymupdf.open()
picture = scan.new_page(width=page.rect.width, height=page.rect.height)
picture.insert_image(picture.rect, pixmap=page.get_pixmap(dpi=200))
words = " ".join(w.text for w in ocr.recognise(picture, "ita"))
assert "riconosce" in words, words

# pikepdf: aprire e salvare
with pikepdf.new() as pdf:
    pdf.add_blank_page()
    assert len(pdf.pages) == 1

print(f"AppImage di Plico {__version__}: controlli OK (OCR: {words!r})")
