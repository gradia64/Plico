#!/bin/bash
# Prova di un'AppImage già costruita, senza FUSE e senza rete (salvo pytest,
# vedi sotto).
#
#   1. controlli con il Python dell'AppImage (smoke_check.py): icona, formati
#      immagine, cataloghi di Plico e di Qt, guida, OCR vero con i dati di
#      lingua inclusi, pikepdf, pyHanko
#   2. l'intera suite di test eseguita con il Python, Qt, PyMuPDF, pikepdf e
#      pyHanko dell'AppImage, e con il pacchetto plico che c'è dentro
#   3. avvio dell'app completa (offscreen e, con xvfb-run, su X11), che deve
#      essere ancora viva dopo qualche secondo
#
# pytest non è nell'AppImage: lo installa per l'occasione in una cartella
# temporanea il pip di sistema (rete o cache), e passa per PYTHONPATH.
# Impostazioni sempre in una cartella temporanea: niente di quelle dell'utente.
#
# Uso: packaging/appimage/smoke-test.sh dist/Plico-X.Y.Z-x86_64.AppImage
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APPIMAGE_FILE="$(readlink -f "${1:?uso: smoke-test.sh <file .AppImage>}")"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export QT_QPA_PLATFORM=offscreen

cd "$TMP"
"$APPIMAGE_FILE" --appimage-extract >/dev/null
APPDIR_X="$TMP/squashfs-root"
PY="$APPDIR_X/usr/python/bin/python3"

echo "== controlli nell'AppImage"
XDG_CONFIG_HOME="$TMP/config-check" APPDIR="$APPDIR_X" \
    PLICO_TESSDATA="$APPDIR_X/usr/share/tessdata" \
    "$PY" -E -s "$ROOT/packaging/appimage/smoke_check.py"

echo "== suite di test con il Python dell'AppImage"
# solo pytest: pytest-qt vorrebbe QtTest, che l'AppImage non ha, e nessun
# test lo usa
python3 -m pip install --quiet --disable-pip-version-check --target "$TMP/pytest" \
    "pytest>=8.0"
cd "$ROOT"
# il plico dell'AppImage davanti a tutto: si prova quello che si spedisce
# PLICO_TESSDATA: i test dell'OCR con i dati di lingua dell'AppImage, come li
# vede l'app (l'AppRun lo imposta allo stesso modo). Senza, sul runner della CI
# che non ha Tesseract, venivano saltati.
XDG_CONFIG_HOME="$TMP/config-tests" TMPDIR="$TMP" \
    PLICO_TESSDATA="$APPDIR_X/usr/share/tessdata" \
    PYTHONPATH="$APPDIR_X/usr/share/plico:$TMP/pytest" \
    "$PY" -s -m pytest -q -p no:cacheprovider --basetemp="$TMP/pytest-tmp" tests \
    > "$TMP/pytest.log" 2>&1 || {
        tail -40 "$TMP/pytest.log"
        echo "suite fallita con il Python dell'AppImage" >&2
        exit 1
    }
echo "suite: $(tail -1 "$TMP/pytest.log")"

# avvia l'AppImage per 10 secondi: deve essere ancora aperta e senza errori
run_app() {   # run_app <descrizione> [prefisso del comando…]
    local what="$1" rc
    shift
    echo "== avvio dell'app completa ($what)"
    mkdir -p "$TMP/run"
    set +e
    # TMPDIR: la copia estratta dal runtime resta se il processo viene ucciso
    XDG_CONFIG_HOME="$TMP/config-app" APPIMAGE_EXTRACT_AND_RUN=1 TMPDIR="$TMP/run" \
        "$@" timeout 10 "$APPIMAGE_FILE" > "$TMP/app.log" 2>&1
    rc=$?
    set -e
    if [ "$rc" -ne 124 ]; then
        cat "$TMP/app.log"
        echo "l'app è uscita da sola (codice $rc) invece di restare aperta" >&2
        exit 1
    fi
    if grep -Eq 'Traceback|Error|error' "$TMP/app.log"; then
        cat "$TMP/app.log"
        echo "errori nell'output dell'app" >&2
        exit 1
    fi
    echo "avvio OK"
}

run_app offscreen

# con un server X virtuale si carica davvero il plugin X11 di Qt, con le
# librerie xcb-util incluse nell'AppImage: offscreen non le tocca
if command -v xvfb-run >/dev/null; then
    QT_QPA_PLATFORM=xcb run_app "X11, xvfb" \
        xvfb-run -a sh -c '"$@"; rc=$?; sleep 3; exit $rc' sh
else
    echo "== X11 saltato: xvfb-run non installato (pacchetto xvfb)"
fi
