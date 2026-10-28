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


def test_the_tray_can_reach_the_notification_area():
    """Without it, inside the sandbox ``isSystemTrayAvailable()`` is False.

    Measured on KDE Plasma: no permission, no icon; this one name, and Qt
    registers its StatusNotifierItem under its unique bus name, nothing else
    to own. The icon is opt-in (Impostazioni), so the permission stays idle
    for whoever does not want it.
    """
    manifest = json.loads(MANIFEST.read_text())
    assert "--talk-name=org.kde.StatusNotifierWatcher" in manifest["finish-args"]
    assert not any(arg.startswith("--filesystem") for arg in manifest["finish-args"])


def test_the_arch_package_vendors_the_appimage_s_pyhanko():
    """PKGBUILD and AppImage ship the same pyHanko, certvalidator and uritools.

    The three pure-Python wheels Arch does not package are pinned in
    packaging/arch/PKGBUILD.in by file name and SHA-256; the AppImage pins them
    in its lock. One version for both, or a signature made with one package
    could behave differently from the other.
    """
    import re

    pkgbuild = (ROOT / "packaging" / "arch" / "PKGBUILD.in").read_text()
    lock = (ROOT / "packaging" / "appimage" / "requirements.txt").read_text()
    pinned = {
        m.group(1).lower().replace("_", "-"): (m.group(2), m.group(3))
        for m in re.finditer(r"^([A-Za-z0-9_.-]+)==(\S+) \\\n\s+--hash=sha256:([0-9a-f]{64})", lock, re.MULTILINE)
    }
    wheels = re.findall(r"^_\w+=([A-Za-z0-9_]+)-([0-9.]+)-py3-none-any\.whl$", pkgbuild, re.MULTILINE)
    sums = re.findall(r"'([0-9a-f]{64})'", pkgbuild)
    assert len(wheels) == 3 and len(sums) == 3
    for (name, version), sha in zip(wheels, sums, strict=True):
        assert pinned[name.lower().replace("_", "-")] == (version, sha), name


def test_the_arch_package_suggests_qt_s_own_translations():
    """Arch's PySide6 reads Qt's catalogs from the system, not from a wheel.

    They are in qt6-translations, which nothing else pulls in: without it OK,
    Annulla, Sì and No stay in English on a desktop that is not a full KDE.
    """
    pkgbuild = (ROOT / "packaging" / "arch" / "PKGBUILD.in").read_text()
    optdepends = pkgbuild.split("optdepends=(", 1)[1].split("\n)", 1)[0]
    assert '"qt6-translations: ' in optdepends


def test_a_manual_release_run_publishes_nothing():
    """Only the push of a tag publishes, not a run started by hand on a tag.

    The README promises that a manual run only builds and tests; on a tag it
    used to upload the files again (--clobber) and push the PKGBUILD to AUR.
    """
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    publish = workflow.split("\n  publish:\n", 1)[1].split("\n  aur:\n", 1)[0]
    condition = next(line for line in publish.splitlines() if line.strip().startswith("if:"))
    assert "github.event_name == 'push'" in condition
