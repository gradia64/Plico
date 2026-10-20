#!/bin/bash
# Costruisce il pacchetto Debian di Plico: dist/plico_<versione>_amd64.deb
#
# Autosufficiente, come l'AppImage: è lo stesso albero (build/appimage/AppDir,
# da scripts/build-appimage.sh, già collaudato con la suite di test) messo in
# /opt/plico. Le librerie Python di Debian e Ubuntu non bastano: pyHanko 0.37
# vuole cryptography >= 48 (Debian 13 ha la 43, Ubuntu 26.04 la 46) e Ubuntu
# 24.04 e Debian 12 non hanno PySide6. Dal sistema vengono solo glibc e le
# librerie grafiche di base, quelle che l'AppImage lascia al sistema.
#
# Layout installato:
#   /opt/plico/                      l'AppDir: AppRun, usr/python (Python,
#                                    Qt, PyMuPDF, pikepdf, pyHanko),
#                                    usr/share/plico, usr/share/tessdata
#   /usr/bin/plico                   collegamento a /opt/plico/AppRun
#   /usr/share/applications/io.github.gradia64.plico.desktop
#   /usr/share/icons/hicolor/scalable/apps/io.github.gradia64.plico.svg
#   /usr/share/metainfo/io.github.gradia64.plico.metainfo.xml
#   /usr/share/doc/plico/{copyright,changelog.gz}
#
# Ripreso da build-deb.sh di OllaDesk (metadati, riproducibilità).
#
# Uso: scripts/build-deb.sh [AppDir]   (default build/appimage/AppDir)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
APP_ID="io.github.gradia64.plico"
APPDIR="${1:-build/appimage/AppDir}"

[ -x "$APPDIR/AppRun" ] || { echo "manca $APPDIR: esegui prima scripts/build-appimage.sh" >&2; exit 1; }

# la versione del codice e quella dell'albero devono coincidere: un AppDir
# rimasto da una build precedente non deve finire in un .deb più nuovo
VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/plico/__init__.py)"
TREE_VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$APPDIR/usr/share/plico/plico/__init__.py")"
if [ -z "$VERSION" ] || [ "$VERSION" != "$TREE_VERSION" ]; then
    echo "versione del codice '$VERSION', dell'AppDir '$TREE_VERSION': ricostruisci l'AppImage" >&2
    exit 1
fi

if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
    SOURCE_DATE_EPOCH="$(git log -1 --format=%ct 2>/dev/null || date +%s)"
fi
export SOURCE_DATE_EPOCH

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PKG="$STAGE/plico"
mkdir -p "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/doc/plico" "$PKG/DEBIAN"

# --- l'albero dell'AppImage ---------------------------------------------------
# senza i collegamenti in cima (servono solo ad appimagetool) e senza
# l'integrazione desktop, che va in /usr/share dove il sistema la cerca
cp -a "$APPDIR" "$PKG/opt/plico"
rm -f "$PKG/opt/plico/$APP_ID.desktop" "$PKG/opt/plico/$APP_ID.svg" "$PKG/opt/plico/.DirIcon"
for d in applications icons metainfo; do
    mv "$PKG/opt/plico/usr/share/$d" "$PKG/usr/share/$d"
done
rm -f "$PKG/usr/share/metainfo/$APP_ID.appdata.xml"   # il vecchio nome, per appimagetool
# l'AppRun ricava la sua cartella con readlink -f: dal collegamento arriva
# a /opt/plico
ln -s /opt/plico/AppRun "$PKG/usr/bin/plico"

# --- metadati del pacchetto ---------------------------------------------------
# Depends: le librerie che l'albero chiede al sistema (le stesse dell'AppImage),
# con il nome t64 di Debian 13 / Ubuntu 24.04 e quello precedente; tzdata
# perché il Python incluso legge i fusi orari del sistema e pyHanko ne apre
# uno già all'import. Nel control su una riga sola (lintian: multiline-field)
DEPENDS=(
    "libc6 (>= 2.34)" libstdc++6 libgcc-s1 zlib1g libzstd1 libcrypt1
    "libglib2.0-0t64 | libglib2.0-0" libdbus-1-3 libfontconfig1 libfreetype6
    libbrotli1 libgssapi-krb5-2 libegl1 libgl1 libxkbcommon0 libx11-6
    libx11-xcb1 libxcb1 libxcb-glx0 libxcb-randr0 libxcb-shm0 libxcb-sync1
    libxcb-xfixes0 libwayland-client0 libwayland-cursor0 libwayland-egl1
    tzdata
)
DEPENDS_LINE="$(printf '%s, ' "${DEPENDS[@]}")"
cat > "$PKG/DEBIAN/control" <<EOF
Package: plico
Version: $VERSION
Section: text
Priority: optional
Architecture: amd64
Depends: ${DEPENDS_LINE%, }
Recommends: fonts-dejavu-core | fonts-noto-core
Installed-Size: @INSTALLED_SIZE@
Maintainer: gradia <gradia@disroot.org>
Homepage: https://github.com/gradia64/Plico
Description: Editor PDF nativo per Linux (PySide6/Qt)
 Plico lavora sulle pagine (ruotare, eliminare, riordinare, unire PDF e
 immagini, estrarre), cancella davvero il contenuto sotto una zona invece di
 coprirlo, compila i moduli, corregge il testo, rende cercabili le scansioni
 con l'OCR e firma in PAdES.
 .
 Il pacchetto è autosufficiente: Python, Qt, PyMuPDF, pikepdf, pyHanko e i
 dati di lingua dell'OCR (italiano, inglese, francese, tedesco, spagnolo) sono
 in /opt/plico, gli stessi dell'AppImage.
EOF

cat > "$PKG/usr/share/doc/plico/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: Plico
Source: https://github.com/gradia64/Plico

Files: *
Copyright: 2026 gradia <gradia@disroot.org>
License: GPL-3.0-or-later
 Plico è software libero: puoi ridistribuirlo e modificarlo secondo i
 termini della GNU General Public License pubblicata dalla Free Software
 Foundation, versione 3 o successiva.
 .
 Il testo completo della licenza è in /usr/share/common-licenses/GPL-3
 oppure su https://www.gnu.org/licenses/gpl-3.0.html

Files: opt/plico/usr/python/*
Copyright: i rispettivi autori
License: various
 Python (PSF-2.0), Qt e PySide6 (LGPL-3.0), PyMuPDF e MuPDF (AGPL-3.0),
 pikepdf (MPL-2.0) e qpdf (Apache-2.0), pyHanko e pyhanko-certvalidator
 (MIT), con le loro dipendenze. Ogni pacchetto ha il testo della sua licenza
 in opt/plico/usr/python/lib/python3.*/site-packages/*.dist-info/, Python in
 opt/plico/usr/python/lib/python3.*/LICENSE.txt.

Files: opt/plico/usr/share/tessdata/*
Copyright: Google e i contributori di Tesseract
License: Apache-2.0
 https://github.com/tesseract-ocr/tessdata_fast
 Il testo della licenza è in /usr/share/common-licenses/Apache-2.0
EOF

cat > "$STAGE/changelog" <<EOF
plico ($VERSION) unstable; urgency=medium

  * Release $VERSION: vedi https://github.com/gradia64/Plico/releases

 -- gradia <gradia@disroot.org>  $(date -R -u -d "@$SOURCE_DATE_EPOCH")
EOF
gzip -9n -c "$STAGE/changelog" > "$PKG/usr/share/doc/plico/changelog.gz"

chmod -R u=rwX,go=rX "$PKG"

# dimensione installata come la calcola dpkg-gencontrol (vedi OllaDesk): ogni
# file arrotondato al KiB, 1 KiB per directory e collegamento
INSTALLED_SIZE="$(find "$PKG" -path "$PKG/DEBIAN" -prune -o -mindepth 1 -printf '%y %s\n' \
    | awk '$1 == "f" { s += int(($2 + 1023) / 1024); next } { s += 1 } END { print s + 0 }')"
sed -i "s/@INSTALLED_SIZE@/$INSTALLED_SIZE/" "$PKG/DEBIAN/control"

(cd "$PKG" && find opt usr -type f -print0 | LC_ALL=C sort -z | xargs -0 md5sum) \
    > "$PKG/DEBIAN/md5sums"
chmod 644 "$PKG/DEBIAN/md5sums"

find "$PKG" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +

mkdir -p dist
OUT="dist/plico_${VERSION}_amd64.deb"
dpkg-deb --build --root-owner-group -Zxz "$PKG" "$OUT" >/dev/null
echo "$OUT ($(du -h "$OUT" | cut -f1))"
