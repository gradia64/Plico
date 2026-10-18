"""The Flatpak keeps host web fonts away from fontconfig.

Without it the app crashed (SIGSEGV in libfontconfig) as soon as Qt looked for
a fallback glyph, the password bullet first of all, on a host with .woff2
fonts in /usr/share/fonts. Nothing in the test suite runs inside the sandbox,
so what is checked here is that the fix is still shipped.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "flatpak" / "fontconfig-local.conf"
MANIFEST = ROOT / "flatpak" / "io.github.gradia64.plico.json"


def test_web_fonts_rejected():
    globs = {g.text for g in ET.parse(CONF).getroot().iterfind("selectfont/rejectfont/glob")}
    assert {"*.woff", "*.woff2"} <= globs


def test_installed_where_the_runtime_reads_it():
    manifest = json.loads(MANIFEST.read_text())
    plico = next(m for m in manifest["modules"] if isinstance(m, dict) and m["name"] == "plico")
    assert (
        "install -Dm644 flatpak/fontconfig-local.conf /app/etc/fonts/local.conf"
        in plico["build-commands"]
    )
