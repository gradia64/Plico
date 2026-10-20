#!/bin/bash
# Prepara il PKGBUILD per AUR dal modello packaging/arch/PKGBUILD.in.
# Ripreso da OllaDesk.
#
# Sostituisce la versione e l'impronta della primaria di rilascio
# (RELEASE_PRIMARY in scripts/release-keys.sh). Il sorgente è il tag
# v<versione> firmato, che makepkg clona da GitHub e verifica: il tag deve
# essere già pubblicato per costruire il pacchetto. Se makepkg è disponibile
# genera anche .SRCINFO.
#
# Uso: scripts/prepare-aur.sh [cartella di uscita]   (default build/aur)
#
# La versione è quella di src/plico/__init__.py; PLICO_VERSION la sostituisce
# (release.yml a mano, per pubblicare su AUR un tag già uscito).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${1:-build/aur}"
# shellcheck source=scripts/release-keys.sh
. "$ROOT/scripts/release-keys.sh"

VERSION="${PLICO_VERSION:-$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/plico/__init__.py)}"
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "versione non valida: '$VERSION'" >&2
    exit 1
fi

mkdir -p "$OUT"
sed -e '/^#@/d' \
    -e "s/@PKGVER@/$VERSION/" \
    -e "s/@FINGERPRINT@/$RELEASE_PRIMARY/" \
    packaging/arch/PKGBUILD.in > "$OUT/PKGBUILD"
if grep -qE '@(PKGVER|FINGERPRINT)@' "$OUT/PKGBUILD"; then
    echo "segnaposto non sostituiti in $OUT/PKGBUILD" >&2
    exit 1
fi

# makepkg rifiuta di girare come root (anche solo per --printsrcinfo): nel
# container della CI .SRCINFO lo genera build-arch.sh con l'utente builder
rm -f "$OUT/.SRCINFO"
if command -v makepkg >/dev/null 2>&1 && [ "$(id -u)" -ne 0 ]; then
    (cd "$OUT" && makepkg --printsrcinfo > .SRCINFO.tmp && mv .SRCINFO.tmp .SRCINFO)
fi
echo "$OUT/PKGBUILD (plico $VERSION dal tag v$VERSION firmato, chiave $RELEASE_PRIMARY)"
