#!/bin/bash
# Costruisce l'AppImage di Plico: dist/Plico-<versione>-<arch>.AppImage
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
# packaging/appimage/requirements-<arch>.txt (pip --require-hashes) e passa per
# build/appimage/downloads/. La versione è letta da src/plico/__init__.py.
#
# Uso:  scripts/build-appimage.sh            AppImage x86_64
#       scripts/build-appimage.sh aarch64    AppImage ARM64, costruita anche da
#                                            una macchina x86_64
#       scripts/build-appimage.sh --lock     rigenera requirements-*.txt con
#                                            gli hash da requirements.in
#       scripts/build-appimage.sh --lock aarch64
#                                            solo requirements-aarch64.txt,
#                                            alle versioni del lock x86_64
#
# Ripreso da OllaDesk (stesso autore, stessa licenza): stesso Python, stesse
# librerie xcb, stessi controlli; la parte aarch64 è quella di Clonaut. Le
# wheel di PySide6 richiedono glibc >= 2.34 su x86_64 (Debian 12, Ubuntu 22.04,
# Fedora 35 o più recenti) e >= 2.39 su aarch64 (Debian 13, Ubuntu 24.04,
# Fedora 40 o più recenti).
#
# pip, lrelease, compileall e i controlli girano sempre sulla macchina che
# costruisce, che è x86_64: pip --platform sceglie le wheel dell'altra
# architettura, e i cataloghi li compila il lrelease di PySide6 x86_64. Così
# l'AppImage ARM si costruisce senza emulazione.
# Strumenti richiesti: curl, sha256sum, dpkg-deb, binutils (readelf), file
# (per appimagetool), git; appstreamcli è facoltativo (validazione dei
# metadati).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_ID="io.github.gradia64.plico"
HOST_ARCH="x86_64"

PBS_RELEASE="20260929"
PBS_PYTHON="3.12.14"
PYVER="${PBS_PYTHON%.*}"
pbs_url() {
    echo "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/cpython-${PBS_PYTHON}+${PBS_RELEASE}-$1-unknown-linux-gnu-install_only_stripped.tar.gz"
}
declare -A PBS_SHA256=(
    [x86_64]="ef605200f8174e87ecfc308e52a88127543f85dd5c940dc5e92cab244b98a003"
    [aarch64]="706111f834ae1557314f48b7293ddc72cc96e952aa75c5d31f56c2b7ddeac3d3"
)

APPIMAGETOOL_VERSION="1.9.1"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-${HOST_ARCH}.AppImage"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

# runtime type2 statico: l'AppImage non chiede libfuse2 al sistema
RUNTIME_VERSION="20251108"
declare -A RUNTIME_SHA256=(
    [x86_64]="2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"
    [aarch64]="00cbdfcf917cc6c0ff6d3347d59e0ca1f7f45a6df1a428a0d6d8a78664d87444"
)

# patchelf (wheel PyPI con il binario statico): dà RUNPATH $ORIGIN alle
# librerie xcb-util prese dai pacchetti Ubuntu, che non ne hanno
PATCHELF_URL="https://files.pythonhosted.org/packages/e7/03/afd9bdd2ba5f96997196109f25dadbe5141bc6e70dffd85f3f84cc85d69c/patchelf-0.19.1.0-py3-none-manylinux1_x86_64.manylinux_2_5_x86_64.musllinux_1_1_x86_64.whl"
PATCHELF_SHA256="a8f6331ccf40c345507279f755f4a38c2cb00b9efda746fd43c17713cce0aba4"

# glibc massima richiesta dai file dell'AppImage: quella delle wheel di PySide6
declare -A GLIBC_MAX=([x86_64]="2.34" [aarch64]="2.39")

WORK="$ROOT/build/appimage"
DOWNLOADS="$WORK/downloads"
REQ_IN="packaging/appimage/requirements.in"
req_txt() { echo "packaging/appimage/requirements-$1.txt"; }

if [ "$(uname -m)" != "$HOST_ARCH" ]; then
    echo "l'AppImage si costruisce solo su una macchina $HOST_ARCH (anche quella aarch64)" >&2
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

unpack_python() {   # unpack_python <arch> <cartella>
    local tarball
    tarball="$(fetch "$(pbs_url "$1")" "${PBS_SHA256[$1]}")"
    rm -rf "$2"
    mkdir -p "$2"
    tar -xzf "$tarball" -C "$2" --strip-components=1
}

# Python della macchina che costruisce: pip, compileall e i controlli
HOSTPY_DIR="$WORK/hostpython"
if [ ! -x "$HOSTPY_DIR/bin/python3" ]; then
    unpack_python "$HOST_ARCH" "$HOSTPY_DIR"
fi
HOSTPY="$HOSTPY_DIR/bin/python3"

# pip per una piattaforma: wheel per <arch> e il Python dell'AppImage
pip_target() {   # pip_target <arch> <argomenti di pip install…>
    local arch="$1" y platforms=()
    shift
    # con --platform pip non scende da solo alle etichette più vecchie: tutte
    # le manylinux_2_y fino alla glibc massima, più i vecchi alias
    for ((y = ${GLIBC_MAX[$arch]#2.}; y >= 5; y--)); do
        platforms+=(--platform "manylinux_2_${y}_${arch}")
    done
    platforms+=(--platform "manylinux2014_${arch}")
    [ "$arch" = x86_64 ] && platforms+=(--platform manylinux2010_x86_64 --platform manylinux1_x86_64)
    "$HOSTPY" -m pip install --isolated --quiet --disable-pip-version-check \
        --root-user-action=ignore --no-cache-dir --only-binary=:all: \
        "${platforms[@]}" --python-version "$PYVER" \
        --implementation cp --abi "cp${PYVER/./}" --abi abi3 --abi none "$@"
}

if [ "${1:-}" = "--lock" ]; then
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    # le versioni di un lock, senza gli hash: vincoli per pip
    pins() { sed -n 's/^\([A-Za-z0-9_.-]*==[^ ]*\) .*/\1/p' "$(req_txt "$1")"; }
    case "${2:-}" in
        "") ARCHS=(x86_64 aarch64); : > "$TMP/constraints.txt" ;;
        aarch64) ARCHS=(aarch64); pins x86_64 > "$TMP/constraints.txt" ;;
        *) echo "uso: --lock [aarch64]" >&2; exit 1 ;;
    esac
    for arch in "${ARCHS[@]}"; do
        # stessa piattaforma dell'AppImage: il report di pip ha lo SHA-256 di
        # ogni wheel scelta. L'aarch64 è vincolato alle versioni dell'x86_64:
        # le stesse librerie sulle due architetture, solo le wheel cambiano
        pip_target "$arch" --dry-run --ignore-installed --target "$TMP/t-$arch" \
            --report "$TMP/report-$arch.json" -c "$TMP/constraints.txt" -r "$REQ_IN"
        "$HOSTPY" - "$TMP/report-$arch.json" "$arch" > "$(req_txt "$arch")" <<'EOF'
import json, sys
report = json.load(open(sys.argv[1]))
print("# Generato da scripts/build-appimage.sh --lock: non modificare a mano.")
print(f"# {sys.argv[2]}: versioni da packaging/appimage/requirements.in, dipendenze risolte da pip.")
for item in sorted(report["install"], key=lambda i: i["metadata"]["name"].lower()):
    meta, info = item["metadata"], item["download_info"]
    sha = info["archive_info"]["hashes"]["sha256"]
    print(f'{meta["name"]}=={meta["version"]} \\\n    --hash=sha256:{sha}')
EOF
        echo "scritto $(req_txt "$arch")"
        pins "$arch" > "$TMP/constraints.txt"
    done
    exit 0
fi

ARCH="${1:-x86_64}"
case "$ARCH" in
    x86_64|aarch64) ;;
    *) echo "architettura non supportata: $ARCH (x86_64 o aarch64)" >&2; exit 1 ;;
esac

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

APPDIR="$WORK/AppDir-$ARCH"
rm -rf "$APPDIR"
mkdir -p "$APPDIR"

# --- Python e dipendenze ----------------------------------------------------
unpack_python "$ARCH" "$APPDIR/usr/python"
SITE="$APPDIR/usr/python/lib/python$PYVER/site-packages"
STDLIB="$APPDIR/usr/python/lib/python$PYVER"
pip_target "$ARCH" --no-compile --require-hashes --no-deps --upgrade \
    --target "$SITE" -r "$(req_txt "$ARCH")"

# pip, Tk, IDLE e i test servono solo a costruire o non servono affatto; bin/
# ha gli script delle wheel (pyside6-*), che con --target finiscono lì
rm -rf "$SITE"/pip "$SITE"/pip-*.dist-info "$SITE"/bin \
       "$STDLIB"/{ensurepip,idlelib,tkinter,turtledemo,test,unittest/test,lib2to3} \
       "$STDLIB"/lib-dynload/_tkinter*.so \
       "$APPDIR"/usr/python/lib/{tcl,tk,itcl,thread}* \
       "$APPDIR"/usr/python/lib/libtcl* "$APPDIR"/usr/python/lib/libtk* \
       "$APPDIR"/usr/python/share \
       "$APPDIR"/usr/python/include
find "$APPDIR/usr/python/bin" -mindepth 1 \
    ! -name python3 ! -name "python$PYVER" -delete

# --- Plico, con i cataloghi compilati ----------------------------------------
# lrelease della PySide6 x86_64 (stessa versione, stessi hash del lock x86_64)
# in una cartella di strumenti: quello nell'AppDir aarch64 qui non gira, e
# trim-qt toglie comunque Qt/libexec dove sta
SHARE="$APPDIR/usr/share/plico"
mkdir -p "$SHARE"
cp -r src/plico "$SHARE/plico"
find "$SHARE" -type d -name __pycache__ -exec rm -rf {} +
find "$SHARE" -type f -name '*.pyc' -delete
PYSIDE_PIN="$(grep -A1 '^PySide6_Essentials==' "$(req_txt "$HOST_ARCH")")"
PYSIDE_TOOLS="$WORK/tools/$(head -n 1 <<< "$PYSIDE_PIN" | cut -d' ' -f1)-$HOST_ARCH"
if [ ! -d "$PYSIDE_TOOLS" ]; then
    printf '%s\n' "$PYSIDE_PIN" > "$WORK/pyside-pin.txt"
    pip_target "$HOST_ARCH" --no-compile --require-hashes --no-deps \
        --target "$PYSIDE_TOOLS.part" -r "$WORK/pyside-pin.txt"
    rm -f "$WORK/pyside-pin.txt"
    mv "$PYSIDE_TOOLS.part" "$PYSIDE_TOOLS"
fi
LRELEASE="$(find "$PYSIDE_TOOLS/PySide6" -name lrelease -type f | head -n 1)"
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
"$HOSTPY" -E -s packaging/appimage/trim-qt.py "$SITE/PySide6"

# Il plugin X11 di Qt 6 vuole le librerie xcb-util, che mancano in molte
# installazioni (libxcb-cursor0 su Ubuntu 22.04, per esempio): vanno nella
# cartella delle librerie Qt, dove il RUNPATH dei plugin le trova. Vengono
# dai pacchetti di Ubuntu 22.04 (glibc 2.35, simboli fino alla 2.34), non dal
# sistema che costruisce: quelle di Debian sid o Ubuntu 24.04 chiedono una
# glibc più recente. Le librerie di base (libxcb, libX11, libxkbcommon, GL,
# fontconfig, Wayland…) restano quelle del sistema, come in ogni AppImage.
#
# Le estensioni di libxcb (render, shape, xkb) e libxkbcommon-x11 NON vanno
# incluse, anche se mancano nei sistemi minimi: fino alla 0.1.6 c'erano quelle
# di Ubuntu 22.04, e libxkbcommon-x11 1.4.0 accanto alla libxkbcommon molto più
# recente del sistema (Arch, Fedora 45) fa andare in segfault il plugin xcb di
# Qt al primo QApplication (codice 139). libxkbcommon-x11 deve avere la stessa
# versione di libxkbcommon, quindi viene dal sistema insieme a lei e alle
# estensioni di libxcb su cui poggia; le xcb-util qui sotto non hanno questo
# legame e restano. Su Wayland il plugin xcb non si carica e il problema non si
# vedeva.
XCB_DEBS_x86_64=(
    "https://archive.ubuntu.com/ubuntu/pool/universe/x/xcb-util-cursor/libxcb-cursor0_0.1.1-4ubuntu1_amd64.deb c9b5d1ad4af57397b1bd77e0a92750e34419def134c0282a0836ae9efc07cf64 libxcb-cursor.so.0"
    "https://archive.ubuntu.com/ubuntu/pool/main/x/xcb-util-wm/libxcb-icccm4_0.4.1-1.1build2_amd64.deb 4dfe14a0ce681b823b740dabb3de84b3ce0958c9a404af61823b11f64047b0ef libxcb-icccm.so.4"
    "https://archive.ubuntu.com/ubuntu/pool/main/x/xcb-util-image/libxcb-image0_0.4.0-2_amd64.deb b52babc3b4f2aa5241cac3a7888ce3b37d25a7f18867cae180e8cd11ec945cb9 libxcb-image.so.0"
    "https://archive.ubuntu.com/ubuntu/pool/main/x/xcb-util-keysyms/libxcb-keysyms1_0.4.0-1build3_amd64.deb 1d62f96a793cc1aa0df860de3f7d83edea2fa461d97e2b3d4d7f7e7a10e55f42 libxcb-keysyms.so.1"
    "https://archive.ubuntu.com/ubuntu/pool/main/x/xcb-util-renderutil/libxcb-render-util0_0.3.9-1build3_amd64.deb f87659a2369430ed2acb1cdae54a06fa9d60727a6545594e213173ddb4377727 libxcb-render-util.so.0"
    "https://archive.ubuntu.com/ubuntu/pool/main/x/xcb-util/libxcb-util1_0.4.0-1build2_amd64.deb 237d51a378b93c1669ff193084ebeb6422fe1e2ea96c2e9a0099eac40992a345 libxcb-util.so.1"
)
XCB_DEBS_aarch64=(
    "https://ports.ubuntu.com/ubuntu-ports/pool/universe/x/xcb-util-cursor/libxcb-cursor0_0.1.1-4ubuntu1_arm64.deb cd51860d7a40be6fe72bf9f69aac60e7cf7ae70994d5a7ea3aa82dfe0232f96a libxcb-cursor.so.0"
    "https://ports.ubuntu.com/ubuntu-ports/pool/main/x/xcb-util-wm/libxcb-icccm4_0.4.1-1.1build2_arm64.deb c9717fa2b7bbf77fd013094443e9fd6254a6400951c2f322f35bbd58c5ca3a08 libxcb-icccm.so.4"
    "https://ports.ubuntu.com/ubuntu-ports/pool/main/x/xcb-util-image/libxcb-image0_0.4.0-2_arm64.deb 5a66b078bcc423768c26422db0f3acb0556d06ec8266a472a6352153600f0e42 libxcb-image.so.0"
    "https://ports.ubuntu.com/ubuntu-ports/pool/main/x/xcb-util-keysyms/libxcb-keysyms1_0.4.0-1build3_arm64.deb f2ccc3dbfd81b409a43a72488e1f8ac2f65e46723e71ab408d94d50a21628374 libxcb-keysyms.so.1"
    "https://ports.ubuntu.com/ubuntu-ports/pool/main/x/xcb-util-renderutil/libxcb-render-util0_0.3.9-1build3_arm64.deb 6b6d181a909aa96287d90498a49ccfad41a9837326986936e9b53ec385e5b7e2 libxcb-render-util.so.0"
    "https://ports.ubuntu.com/ubuntu-ports/pool/main/x/xcb-util/libxcb-util1_0.4.0-1build2_arm64.deb ee67ecc591a1aab0490b74adf188e1d4ed509077a1c7b84f68dc6fddeb1fb2c0 libxcb-util.so.1"
)
declare -A DEB_LIBDIR=([x86_64]="x86_64-linux-gnu" [aarch64]="aarch64-linux-gnu")
XCB_DEBS_VAR="XCB_DEBS_${ARCH}[@]"

PATCHELF="$WORK/tools/patchelf"
if [ ! -x "$PATCHELF" ]; then
    whl="$(fetch "$PATCHELF_URL" "$PATCHELF_SHA256")"
    mkdir -p "$WORK/tools"
    "$HOSTPY" -E -s - "$whl" "$PATCHELF" <<'EOF'
import shutil, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    name = next(n for n in z.namelist() if n.endswith("/scripts/patchelf"))
    with z.open(name) as src, open(sys.argv[2], "wb") as dst:
        shutil.copyfileobj(src, dst)
EOF
    chmod 755 "$PATCHELF"
fi

XCB_TMP="$WORK/xcb-$ARCH"
rm -rf "$XCB_TMP"
for entry in "${!XCB_DEBS_VAR}"; do
    read -r url sha so <<< "$entry"
    deb="$(fetch "$url" "$sha")"
    dpkg-deb -x "$deb" "$XCB_TMP"
    install -m 644 "$(readlink -f "$XCB_TMP/usr/lib/${DEB_LIBDIR[$ARCH]}/$so")" "$SITE/PySide6/Qt/lib/$so"
    # senza RUNPATH una di queste che ne vuole un'altra (libxcb-image →
    # libxcb-util) la cerca solo nel sistema: su x86_64 la trova perché Qt
    # l'ha già caricata, sulle wheel aarch64 no (lo stesso in Clonaut)
    "$PATCHELF" --set-rpath '$ORIGIN' "$SITE/PySide6/Qt/lib/$so"
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
# avvio. Li scrive il Python x86_64 della macchina che costruisce, stessa
# versione: validi anche per l'aarch64. unchecked-hash: .pyc identici a ogni
# build, validi senza mtime;
# -s/-p: nei .pyc il percorso è /usr/…, non la cartella in cui si costruisce.
# Con -q compileall stampa solo gli errori
# -B e i __pycache__ cancellati prima: i .pyc scritti dagli import durante la
# build (pip, compileall stesso) cambiano da una macchina all'altra
find "$APPDIR" -type d -name __pycache__ -prune -exec rm -rf {} +
"$HOSTPY" -B -E -s -m compileall -q -f -j 0 --invalidation-mode unchecked-hash \
    -s "$APPDIR" -p / "$APPDIR/usr/python/lib" "$SHARE"
# RECORD serve solo a pip uninstall e contiene gli hash degli script con il
# percorso assoluto della build nello shebang (script già rimossi)
find "$SITE" -path '*.dist-info/RECORD' -delete
# permessi indipendenti dall'umask di chi costruisce (squashfs li conserva).
# Le librerie tutte eseguibili, come le vuole ldd: le wheel PySide6 aarch64
# (e i .deb delle xcb-util) le portano a 644, quelle x86_64 a 755
find "$APPDIR" -type f -name '*.so*' -exec chmod 755 {} +
chmod -R u+rwX,go+rX,go-w "$APPDIR"
find "$APPDIR" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +

# --- compatibilità: nessun file oltre la glibc delle wheel di PySide6 --------
"$HOSTPY" -E -s "$ROOT/packaging/appimage/check-glibc.py" "$APPDIR" "${GLIBC_MAX[$ARCH]}"

# --- immagine -----------------------------------------------------------------
TOOL="$(fetch "$APPIMAGETOOL_URL" "$APPIMAGETOOL_SHA256")"
RUNTIME="$(fetch "https://github.com/AppImage/type2-runtime/releases/download/${RUNTIME_VERSION}/runtime-${ARCH}" \
    "${RUNTIME_SHA256[$ARCH]}")"
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
