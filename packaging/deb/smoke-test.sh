#!/bin/bash
# Collaudo del .deb. Prima lintian (in debian:13), che deve passare senza
# errori né avvisi oltre ai tag di packaging/deb/lintian-suppress: quelli che
# un pacchetto autosufficiente in /opt dà per forza (librerie incluse, .pyc,
# file dell'albero di Python). Poi in container puliti delle distribuzioni che
# deve servire (le stesse dell'AppImage: glibc >= 2.34). In ognuno:
#
#   1. apt installa il .deb e le sue Depends dai repository della distribuzione
#   2. nessuna libreria mancante (ldd) per i file ELF in /opt/plico: le
#      Depends coprono tutto ciò che l'albero chiede al sistema
#   3. i controlli dell'AppImage (packaging/appimage/smoke_check.py) con il
#      Python installato
#   4. plico, dal PATH, resta aperto 10 secondi (offscreen) senza errori
#   5. apt purge non lascia niente in /opt/plico né /usr/bin/plico
#
# L'intera suite di test non gira qui: è lo stesso albero che
# packaging/appimage/smoke-test.sh ha già provato con la suite.
#
# Uso: packaging/deb/smoke-test.sh dist/plico_X.Y.Z_amd64.deb [immagine…]
#      (default: ubuntu:22.04 ubuntu:24.04 debian:12 debian:13)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEB="$(readlink -f "${1:?uso: smoke-test.sh <file .deb> [immagine…]}")"
shift
IMAGES=("$@")
[ "${#IMAGES[@]}" -gt 0 ] || IMAGES=(ubuntu:22.04 ubuntu:24.04 debian:12 debian:13)

echo "== lintian"
docker run --rm \
    -v "$DEB:/tmp/plico.deb:ro" \
    -v "$ROOT/packaging/deb/lintian-suppress:/tmp/lintian-suppress:ro" \
    debian:13 bash -euo pipefail -c '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends lintian >/dev/null
# lintian non gira come root senza avvisare: utente qualsiasi
useradd -m lint
su lint -c "lintian --fail-on error,warning --suppress-tags-from-file /tmp/lintian-suppress /tmp/plico.deb"
'
echo "lintian OK"

for image in "${IMAGES[@]}"; do
    echo "== $image"
    docker run --rm \
        -v "$DEB:/tmp/plico.deb:ro" \
        -v "$ROOT/packaging/appimage/smoke_check.py:/tmp/smoke_check.py:ro" \
        "$image" bash -euo pipefail -c '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq /tmp/plico.deb >/dev/null

# le librerie xcb-util incluse non hanno RUNPATH e ldd non trova le loro
# sorelle, che a runtime sono già caricate da libQt6XcbQpa: contano solo le
# librerie assenti dal pacchetto, cioè quelle che deve dare il sistema
find /opt/plico -name "*.so*" -printf "%f\n" | sort -u > /tmp/bundled
missing=0
while IFS= read -r -d "" f; do
    head -c 4 "$f" | grep -q ELF || continue
    if LC_ALL=C ldd "$f" 2>/dev/null | awk "/not found/ { print \$1 }" \
            | grep -vxFf /tmp/bundled | sed "s|^|$f: |" | grep .; then
        missing=1
    fi
done < <(find /opt/plico -type f -print0)
if [ "$missing" -ne 0 ]; then
    echo "librerie mancanti: Depends incompleta" >&2
    exit 1
fi
echo "librerie: tutte presenti"

export QT_QPA_PLATFORM=offscreen XDG_CONFIG_HOME=/tmp/config
APPDIR=/opt/plico PLICO_TESSDATA=/opt/plico/usr/share/tessdata \
    PLICO_ICON=/usr/share/icons/hicolor/scalable/apps/io.github.gradia64.plico.svg \
    /opt/plico/usr/python/bin/python3 -E -s /tmp/smoke_check.py

[ "$(readlink -f "$(command -v plico)")" = /opt/plico/AppRun ]
set +e
timeout 10 plico > /tmp/app.log 2>&1
rc=$?
set -e
if [ "$rc" -ne 124 ] || grep -Eq "Traceback|Error|error" /tmp/app.log; then
    cat /tmp/app.log
    echo "avvio fallito (codice $rc)" >&2
    exit 1
fi
echo "avvio OK"

apt-get purge -y -qq plico >/dev/null
if [ -e /opt/plico ] || [ -e /usr/bin/plico ]; then
    echo "apt purge ha lasciato dei file" >&2
    exit 1
fi
echo "rimozione OK"
'
done
