#!/bin/bash
# Costruisce l'AppImage di Plico: dist/Plico-<versione>-x86_64.AppImage
#
# Contenuto (AppDir):
#   AppRun                           avvio (packaging/appimage/AppRun)
#   usr/python/                      Python portatile (python-build-standalone)
#                                    con PySide6-Essentials, PyMuPDF (con
#                                    Tesseract dentro MuPDF), pikepdf, pyHanko
#   usr/share/plico/plico/           pacchetto Python, con i cataloghi .qm
#   usr/share/plico/launcher.py      lo stesso avvio dei pacchetti .deb e Arch
#   usr/share/tessdata/              dati di lingua dell'OCR (it, en, fr, de, es)
#   usr/share/{applications,icons,metainfo}/  e in cima .desktop e icona
#
# Tutto ciò che si scarica ha la versione e lo SHA-256 fissati qui o in
# packaging/appimage/requirements.txt (pip --require-hashes) e passa per
# build/appimage/downloads/. La versione è letta da src/plico/__init__.py.
#
# Uso:  scripts/build-appimage.sh          costruisce l'AppImage
#       scripts/build-appimage.sh --lock   rigenera requirements.txt con gli
#                                          hash da requirements.in
#
# Ripreso da OllaDesk (stesso autore, stessa licenza): stesso Python, stesse
# librerie xcb, stessi controlli. Le wheel di PySide6 richiedono glibc >= 2.34
# (Debian 12, Ubuntu 22.04, Fedora 35 o più recenti). Serve solo x86_64.
# Strumenti richiesti: curl, sha256sum, dpkg-deb, binutils (readelf, objdump),
# file (per appimagetool), git; appstreamcli è facoltativo (validazione dei
# metadati).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_ID="io.github.gradia64.plico"
ARCH="x86_64"

PBS_RELEASE="20260929"
PBS_PYTHON="3.12.14"
PBS_FILE="cpython-${PBS_PYTHON}+${PBS_RELEASE}-${ARCH}-unknown-linux-gnu-install_only_stripped.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/${PBS_FILE}"
PBS_SHA256="ef605200f8174e87ecfc308e52a88127543f85dd5c940dc5e92cab244b98a003"

APPIMAGETOOL_VERSION="1.9.1"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-${ARCH}.AppImage"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

RUNTIME_VERSION="20251108"
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/${RUNTIME_VERSION}/runtime-${ARCH}"
RUNTIME_SHA256="2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"

WORK="$ROOT/build/appimage"
DOWNLOADS="$WORK/downloads"
REQ_IN="packaging/appimage/requirements.in"
REQ_TXT="packaging/appimage/requirements.txt"

if [ "$(uname -m)" != "$ARCH" ]; then
    echo "l'AppImage si costruisce solo su $ARCH" >&2
    exit 1
fi

sha_ok() {   # sha_ok <sha256> <file>
    echo "$1  $2" | sha256sum -c --quiet - >/dev/null 2>&1
}

# scarica una volta sola e verifica lo SHA-256 a ogni uso: un file in cache
# con l'hash sbagliato (disco, copia interrotta) si riscarica una volta, un
# download con l'hash sbagliato non entra mai in cache
fetch() {
    local url="$1" sha="$2" out="$DOWNLOADS/$(basename "$1")"
    mkdir -p "$DOWNLOADS"
    if [ -f "$out" ] && ! sha_ok "$sha" "$out"; then
        echo "$(basename "$out") in cache con SHA-256 errato: lo riscarico" >&2
        rm -f "$out"
    fi
    if [ ! -f "$out" ]; then
        curl -fsSL --proto '=https' --tlsv1.2 -o "$out.part" "$url"
        if ! sha_ok "$sha" "$out.part"; then
            rm -f "$out.part"
            echo "SHA-256 errato per $url: download rifiutato" >&2
            exit 1
        fi
        mv "$out.part" "$out"
    fi
    printf '%s\n' "$out"
}

# Python portatile estratto in $1 (python/ dentro l'archivio)
unpack_python() {
    local tarball
    tarball="$(fetch "$PBS_URL" "$PBS_SHA256")"
    mkdir -p "$1"
    tar -xzf "$tarball" -C "$1" --strip-components=1
}

if [ "${1:-}" = "--lock" ]; then
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    unpack_python "$TMP/python"
    # risoluzione con lo stesso Python e la stessa piattaforma dell'AppImage:
    # il report di pip ha lo SHA-256 di ogni wheel scelta
    "$TMP/python/bin/python3" -m pip install --isolated --quiet --dry-run \
        --ignore-installed --only-binary=:all: --report "$TMP/report.json" -r "$REQ_IN"
    "$TMP/python/bin/python3" - "$TMP/report.json" > "$REQ_TXT" <<'EOF'
import json, sys
report = json.load(open(sys.argv[1]))
print("# Generato da scripts/build-appimage.sh --lock: non modificare a mano.")
print("# Versioni da packaging/appimage/requirements.in, dipendenze risolte da pip.")
for item in sorted(report["install"], key=lambda i: i["metadata"]["name"].lower()):
    meta, info = item["metadata"], item["download_info"]
    sha = info["archive_info"]["hashes"]["sha256"]
    print(f'{meta["name"]}=={meta["version"]} \\\n    --hash=sha256:{sha}')
EOF
    echo "scritto $REQ_TXT"
    exit 0
fi

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/plico/__init__.py)"
if [ -z "$VERSION" ]; then
    echo "versione non trovata in src/plico/__init__.py" >&2
    exit 1
fi

# build riproducibile: mtime, .pyc e squashfs dall'ultimo commit
if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
    SOURCE_DATE_EPOCH="$(git log -1 --format=%ct 2>/dev/null || date +%s)"
fi
export SOURCE_DATE_EPOCH

APPDIR="$WORK/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR"

# --- Python e dipendenze ----------------------------------------------------
unpack_python "$APPDIR/usr/python"
PY="$APPDIR/usr/python/bin/python3"
# root-user-action: nei container si costruisce da root, ed è voluto
"$PY" -m pip install --isolated --quiet --root-user-action=ignore --no-cache-dir --no-compile \
    --require-hashes --only-binary=:all: --no-deps -r "$REQ_TXT"

SITE="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
STDLIB="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["stdlib"])')"

# pip, Tk, IDLE e i test servono solo a costruire o non servono affatto
"$PY" -m pip uninstall --isolated --quiet --root-user-action=ignore --yes pip
rm -rf "$STDLIB"/{ensurepip,idlelib,tkinter,turtledemo,test,unittest/test,lib2to3} \
       "$STDLIB"/lib-dynload/_tkinter*.so \
       "$APPDIR"/usr/python/lib/{tcl,tk,itcl,thread}* \
       "$APPDIR"/usr/python/lib/libtcl* "$APPDIR"/usr/python/lib/libtk* \
       "$APPDIR"/usr/python/share \
       "$APPDIR"/usr/python/include
find "$APPDIR/usr/python/bin" -mindepth 1 \
    ! -name python3 ! -name "python${PBS_PYTHON%.*}" -delete

# --- Plico, con i cataloghi compilati ----------------------------------------
# prima di sfoltire Qt: lrelease sta in PySide6/Qt/libexec, che trim-qt toglie
SHARE="$APPDIR/usr/share/plico"
mkdir -p "$SHARE"
cp -r src/plico "$SHARE/plico"
find "$SHARE" -type d -name __pycache__ -exec rm -rf {} +
find "$SHARE" -type f -name '*.pyc' -delete
LRELEASE="$(find "$SITE/PySide6" -name lrelease -type f | head -n 1)"
if [ -z "$LRELEASE" ]; then
    echo "lrelease non trovato in PySide6: i cataloghi non si compilano" >&2
    exit 1
fi
for ts in "$SHARE"/plico/translations/*.ts; do
    "$LRELEASE" -silent "$ts" -qm "${ts%.ts}.qm"
    rm "$ts"
done
install -m 644 packaging/common/launcher.py "$SHARE/launcher.py"
install -m 755 packaging/appimage/AppRun "$APPDIR/AppRun"

# --- dati di lingua dell'OCR (tessdata_fast, gli stessi del Flatpak) -----------
# Tesseract è dentro MuPDF (libmupdf della wheel): non serve libtesseract,
# servono i dati, che l'AppRun indica con PLICO_TESSDATA
TESSDATA_COMMIT="87416418657359cb625c412a48b6e1d6d41c29bd"
TESSDATA=(
    "eng 7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
    "ita b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827"
    "spa 6f2e04d02774a18f01bed44b1111f2cd7f3ba7ac9dc4373cd3f898a40ea6b464"
    "fra ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca"
    "deu 19d219bbb6672c869d20a9636c6816a81eb9a71796cb93ebe0cb1530e2cdb22d"
)
for entry in "${TESSDATA[@]}"; do
    read -r code sha <<< "$entry"
    data="$(fetch "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$TESSDATA_COMMIT/$code.traineddata" "$sha")"
    install -D -m 644 "$data" "$APPDIR/usr/share/tessdata/$code.traineddata"
done

# --- Qt: solo ciò che Plico usa ---------------------------------------------
"$PY" -E -s packaging/appimage/trim-qt.py "$SITE/PySide6"

# Il plugin X11 di Qt 6 vuole le librerie xcb-util, che mancano in molte
# installazioni (libxcb-cursor0 su Ubuntu 22.04, per esempio): vanno nella
# cartella delle librerie Qt, dove il RUNPATH dei plugin le trova. Vengono
# dai pacchetti di Ubuntu 22.04 (glibc 2.35, simboli fino alla 2.34), non dal
# sistema che costruisce: quelle di Debian sid o Ubuntu 24.04 chiedono una
# glibc più recente. Le librerie di base (libxcb, libX11, libxkbcommon, GL,
# fontconfig, Wayland…) restano quelle del sistema, come in ogni AppImage.
UBUNTU_POOL="https://archive.ubuntu.com/ubuntu/pool"
XCB_DEBS=(
    "universe/x/xcb-util-cursor/libxcb-cursor0_0.1.1-4ubuntu1_amd64.deb c9b5d1ad4af57397b1bd77e0a92750e34419def134c0282a0836ae9efc07cf64 libxcb-cursor.so.0"
    "main/x/xcb-util-wm/libxcb-icccm4_0.4.1-1.1build2_amd64.deb 4dfe14a0ce681b823b740dabb3de84b3ce0958c9a404af61823b11f64047b0ef libxcb-icccm.so.4"
    "main/x/xcb-util-image/libxcb-image0_0.4.0-2_amd64.deb b52babc3b4f2aa5241cac3a7888ce3b37d25a7f18867cae180e8cd11ec945cb9 libxcb-image.so.0"
    "main/x/xcb-util-keysyms/libxcb-keysyms1_0.4.0-1build3_amd64.deb 1d62f96a793cc1aa0df860de3f7d83edea2fa461d97e2b3d4d7f7e7a10e55f42 libxcb-keysyms.so.1"
    "main/x/xcb-util-renderutil/libxcb-render-util0_0.3.9-1build3_amd64.deb f87659a2369430ed2acb1cdae54a06fa9d60727a6545594e213173ddb4377727 libxcb-render-util.so.0"
    "main/x/xcb-util/libxcb-util1_0.4.0-1build2_amd64.deb 237d51a378b93c1669ff193084ebeb6422fe1e2ea96c2e9a0099eac40992a345 libxcb-util.so.1"
    # estensioni di libxcb e xkbcommon-x11: ci sono su ogni desktop X11, ma
    # non nei sistemi minimi (container, sessioni solo Wayland)
    "main/libx/libxcb/libxcb-render0_1.14-3ubuntu3_amd64.deb 26d331ed6e1219485dbd6a35b7c9cf552e1470f41bf2158b44a1331405f05250 libxcb-render.so.0"
    "main/libx/libxcb/libxcb-shape0_1.14-3ubuntu3_amd64.deb 71666977d7aa11877d7af663231cabf4bde60b033947b83358522c6f43873b3d libxcb-shape.so.0"
    "main/libx/libxcb/libxcb-xkb1_1.14-3ubuntu3_amd64.deb 4cf69af3ff6a60b63f9f6ea6e7d27471114c6bcbcf3f981f7b88f361029e5eb8 libxcb-xkb.so.1"
    "main/libx/libxkbcommon/libxkbcommon-x11-0_1.4.0-1_amd64.deb e29c40fab6e0f055218aee4c7e60cd61ea82283229d7ac7ac02e226e92a5b0d5 libxkbcommon-x11.so.0"
)
XCB_TMP="$WORK/xcb"
rm -rf "$XCB_TMP"
for entry in "${XCB_DEBS[@]}"; do
    read -r path sha so <<< "$entry"
    deb="$(fetch "$UBUNTU_POOL/$path" "$sha")"
    dpkg-deb -x "$deb" "$XCB_TMP"
    install -m 644 "$(readlink -f "$XCB_TMP/usr/lib/x86_64-linux-gnu/$so")" "$SITE/PySide6/Qt/lib/$so"
done
rm -rf "$XCB_TMP"

# --- integrazione desktop -----------------------------------------------------
install -D -m 644 "flatpak/$APP_ID.desktop" "$APPDIR/usr/share/applications/$APP_ID.desktop"
install -D -m 644 "flatpak/$APP_ID.svg" \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
install -D -m 644 "flatpak/$APP_ID.metainfo.xml" "$APPDIR/usr/share/metainfo/$APP_ID.metainfo.xml"
# appimagetool (e AppImageHub) cercano ancora il vecchio nome .appdata.xml
ln -s "$APP_ID.metainfo.xml" "$APPDIR/usr/share/metainfo/$APP_ID.appdata.xml"
ln -s "usr/share/applications/$APP_ID.desktop" "$APPDIR/$APP_ID.desktop"
ln -s "usr/share/icons/hicolor/scalable/apps/$APP_ID.svg" "$APPDIR/$APP_ID.svg"
ln -s "$APP_ID.svg" "$APPDIR/.DirIcon"

# --- bytecode e date --------------------------------------------------------
# l'immagine è in sola lettura: senza .pyc Python ricompilerebbe tutto a ogni
# avvio. unchecked-hash: .pyc identici a ogni build, validi senza mtime;
# -s/-p: nei .pyc il percorso è /usr/…, non la cartella in cui si costruisce.
# Con -q compileall stampa solo gli errori
# -B e i __pycache__ cancellati prima: i .pyc scritti dagli import durante la
# build (pip, compileall stesso) cambiano da una macchina all'altra
find "$APPDIR" -type d -name __pycache__ -prune -exec rm -rf {} +
"$PY" -B -E -s -m compileall -q -f -j 0 --invalidation-mode unchecked-hash \
    -s "$APPDIR" -p / "$APPDIR/usr/python/lib" "$SHARE"
# RECORD serve solo a pip uninstall e contiene gli hash degli script con il
# percorso assoluto della build nello shebang (script già rimossi)
find "$SITE" -path '*.dist-info/RECORD' -delete
# permessi indipendenti dall'umask di chi costruisce (squashfs li conserva)
chmod -R u+rwX,go+rX,go-w "$APPDIR"
find "$APPDIR" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +

# --- compatibilità: nessun file oltre glibc 2.34, come le wheel di PySide6 ---
"$PY" -E -s "$ROOT/packaging/appimage/check-glibc.py" "$APPDIR" 2.34

# --- immagine -----------------------------------------------------------------
TOOL="$(fetch "$APPIMAGETOOL_URL" "$APPIMAGETOOL_SHA256")"
RUNTIME="$(fetch "$RUNTIME_URL" "$RUNTIME_SHA256")"
chmod +x "$TOOL"
mkdir -p dist
# percorso assoluto: appimagetool fa chdir($OWD) se OWD è nell'ambiente
# (la lasciano le AppImage, per esempio un terminale avviato da una di esse)
OUT="$ROOT/dist/Plico-${VERSION}-${ARCH}.AppImage"
rm -f "$OUT"
# metadati validati qui senza rete: appimagetool userebbe appstreamcli con
# la rete, e gli screenshot su GitHub esistono solo dopo il push
if command -v appstreamcli >/dev/null; then
    appstreamcli validate-tree --no-net "$APPDIR" >/dev/null
fi
# extract-and-run: niente FUSE richiesto per appimagetool (CI, container);
# la copia estratta va in una cartella nostra, non in /tmp
rm -rf "$WORK/tmp"
mkdir -p "$WORK/tmp"
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 TMPDIR="$WORK/tmp" "$TOOL" --no-appstream \
    --runtime-file "$RUNTIME" "$APPDIR" "$OUT" >/dev/null
rm -rf "$WORK/tmp"
echo "dist/$(basename "$OUT") ($(du -h "$OUT" | cut -f1))"
