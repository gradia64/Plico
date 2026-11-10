#!/bin/bash
# Pubblica PKGBUILD e .SRCINFO di una cartella nel repository AUR del
# pacchetto «plico». Ripreso da OllaDesk. Non si lancia da solo: lo chiama
# scripts/aur-release.sh, che prima verifica tag e artefatto della CI.
#
# La chiave SSH è quella dell'utente (~/.ssh/config, Host aur.archlinux.org):
# vale per tutti i pacchetti dell'account, e per questo non sta nella CI.
#
# La chiave host di aur.archlinux.org è fissata qui sotto (verificata contro le
# impronte pubblicate su https://aur.archlinux.org): niente fiducia al primo
# contatto. Il primo push crea il pacchetto su AUR.
#
# Uso: scripts/publish-aur.sh [cartella]   (default build/aur)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
AUR="${1:-build/aur}"
AUR_REMOTE="${AUR_REMOTE:-ssh://aur@aur.archlinux.org/plico.git}"   # override solo per i test
AUR_HOSTKEY="aur.archlinux.org ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEuBKrPzbawxA/k2g6NcyV5jmqwJ2s+zpgZGZ7tpLIcN"

for f in PKGBUILD .SRCINFO; do
    [ -f "$AUR/$f" ] || { echo "manca $AUR/$f (prepare-aur.sh + build-arch.sh)" >&2; exit 1; }
done
VERSION="$(sed -n 's/^pkgver=//p' "$AUR/PKGBUILD")"

# il sorgente (tag v<versione> su GitHub) deve essere clonabile da CHIUNQUE,
# senza credenziali: con un repository privato, o un tag non ancora
# pubblicato, il pacchetto AUR sarebbe impossibile da costruire. Meglio non
# pubblicarlo.
if [ -z "${AUR_SKIP_SOURCE_CHECK:-}" ]; then
    url="$(sed -n 's/^url="\(.*\)"$/\1/p' "$AUR/PKGBUILD")"
    if ! GIT_TERMINAL_PROMPT=0 git -c credential.helper= ls-remote --exit-code --tags \
            "$url.git" "refs/tags/v$VERSION" >/dev/null 2>&1; then
        echo "tag v$VERSION non clonabile pubblicamente da $url.git" >&2
        echo "il repository GitHub è pubblico e il tag è stato pubblicato?" >&2
        exit 1
    fi
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
printf '%s\n' "$AUR_HOSTKEY" > "$TMP/known_hosts"
export GIT_SSH_COMMAND="ssh -o UserKnownHostsFile=$TMP/known_hosts -o StrictHostKeyChecking=yes"

git clone --quiet "$AUR_REMOTE" "$TMP/repo"
cp "$AUR/PKGBUILD" "$AUR/.SRCINFO" "$TMP/repo/"
cd "$TMP/repo"
git add PKGBUILD .SRCINFO
if git diff --cached --quiet; then
    echo "AUR già aggiornato a plico $VERSION: niente da pubblicare"
    exit 0
fi
git -c user.name="${AUR_GIT_NAME:-gradia}" -c user.email="${AUR_GIT_EMAIL:-gradia@disroot.org}" \
    commit --quiet -m "plico $VERSION"
git push --quiet origin HEAD:master
echo "pubblicato su AUR: plico $VERSION"
