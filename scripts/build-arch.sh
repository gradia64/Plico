#!/bin/bash
# Build e controllo del pacchetto Arch a partire da build/aur/ (prepare-aur.sh).
# Ripreso da OllaDesk.
#
# Da eseguire come root in un container archlinux:base-devel (CI o locale):
#   docker run --rm -v "$PWD":/src -w /src archlinux:base-devel scripts/build-arch.sh
#
# - installa le dipendenze (makepkg non può usare sudo in un container)
# - builda come utente non privilegiato, con la chiave pubblica di release
#   nel suo portachiavi: makepkg clona il tag v<versione> da GitHub e ne
#   VERIFICA la firma (?signed + validpgpkeys), come ogni utente AUR. Il tag
#   deve quindi essere già pubblicato
# - esegue check() (l'intera suite di test), namcap su PKGBUILD e pacchetto
# - rigenera .SRCINFO e copia il pacchetto in dist/
# - installa il pacchetto e controlla che l'app parta (offscreen)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
AUR="build/aur"
PUBKEY="${PLICO_RELEASE_KEY:-packaging/plico-release-key.asc}"

if [ "$(id -u)" -ne 0 ]; then
    echo "da eseguire come root in un container Arch (vedi l'intestazione)" >&2
    exit 1
fi
[ -f "$AUR/PKGBUILD" ] || { echo "manca $AUR/PKGBUILD: esegui prima prepare-aur.sh" >&2; exit 1; }

# dipendenze lette dal PKGBUILD stesso: nessun elenco da tenere allineato
# shellcheck disable=SC1091,SC2154
DEPS="$(bash -c 'source "$1"; echo "${depends[@]} ${makedepends[@]} ${checkdepends[@]}"' _ "$AUR/PKGBUILD")"
# shellcheck disable=SC2086
pacman -Syu --noconfirm --needed namcap $DEPS >/dev/null

id builder >/dev/null 2>&1 || useradd -m builder
WORK="$(mktemp -d)"
cp "$AUR"/PKGBUILD "$WORK/"
cp "$PUBKEY" "$WORK/release-key.asc"
chown -R builder: "$WORK"

# la cartella come argomento, non dentro il comando: nessun apice da sfuggire
su builder -s /bin/bash -c '
    set -euo pipefail
    cd "$1"
    gpg --batch --quiet --import release-key.asc
    makepkg --printsrcinfo > .SRCINFO
    makepkg -f --noconfirm
' _ "$WORK"

# namcap: gli errori (E:) bloccano, gli avvisi (W:) no. Avvisi attesi e
# innocui: i moduli plico.* e quelli di vendor/ sono privati in /usr/share
# (namcap li cerca in site-packages), «sh» è fornito da bash.
PKGFILE="$(ls "$WORK"/plico-*-any.pkg.tar.zst)"
NAMCAP="$(namcap "$WORK/PKGBUILD" "$PKGFILE")"
[ -n "$NAMCAP" ] && printf '%s\n' "$NAMCAP"
if printf '%s\n' "$NAMCAP" | grep -q ' E: '; then
    echo "namcap ha trovato errori" >&2
    exit 1
fi

mkdir -p dist
cp "$PKGFILE" dist/
cp "$WORK/.SRCINFO" "$AUR/.SRCINFO"

echo '--- installazione di prova'
pacman -U --noconfirm "$PKGFILE" >/dev/null
# pyHanko viene da vendor/, non dal sistema: la firma deve essere importabile
PYTHONPATH=/usr/share/plico/vendor python3 -c "import pyhanko, pyhanko_certvalidator, uritools"
# l'app deve arrivare all'event loop: timeout (124) = avviata e ancora viva
set +e
QT_QPA_PLATFORM=offscreen XDG_CONFIG_HOME="$(mktemp -d)" timeout 8 plico
rc=$?
set -e
if [ "$rc" -ne 124 ]; then
    echo "plico è uscito subito (codice $rc)" >&2
    exit 1
fi
echo "pacchetto Arch OK: dist/$(basename "$PKGFILE")"
