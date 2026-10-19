#!/bin/bash
# Verifica che un tag di rilascio sia annotato e firmato da una sottochiave
# di firma dei TAG (scripts/release-keys.sh), cioè dal maintainer. Non basta
# una chiave qualunque: nemmeno la primaria, che resta offline e certifica
# soltanto, deve poter firmare un tag che passi da qui.
#
# La verifica usa un portachiavi temporaneo con la SOLA chiave pubblica del
# repository (packaging/plico-release-key.asc): una chiave presente nel
# portachiavi della macchina non conta. Ripreso da OllaDesk.
#
# I tag fino a v0.1.3 sono firmati con la chiave SSH di .github/allowed_signers
# (git tag -v con gpg.ssh.allowedSignersFile); da v0.1.4 con questa chiave.
#
# Uso: scripts/verify-tag.sh v0.1.4
# PLICO_REPO, PLICO_RELEASE_KEY, PLICO_RELEASE_PRIMARY e
# PLICO_TAG_SIGNING_SUBKEYS esistono per i test (tests/test_release_tools.py).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:?uso: scripts/verify-tag.sh <tag>}"
REPO="${PLICO_REPO:-$ROOT}"
PUBKEY="${PLICO_RELEASE_KEY:-$ROOT/packaging/plico-release-key.asc}"
# shellcheck source=scripts/release-keys.sh
. "$ROOT/scripts/release-keys.sh"

if [ "$(git -C "$REPO" cat-file -t "refs/tags/$TAG" 2>/dev/null)" != "tag" ]; then
    echo "$TAG non è un tag annotato (git tag -s): niente da verificare" >&2
    exit 1
fi

GNUPGHOME="$(mktemp -d)"
export GNUPGHOME
trap 'gpgconf --kill gpg-agent >/dev/null 2>&1 || true; rm -rf "$GNUPGHOME"' EXIT
chmod 700 "$GNUPGHOME"
gpg --batch --quiet --import "$PUBKEY"

# VALIDSIG <impronta di chi ha firmato> ... <impronta della primaria>: si
# controllano entrambe. Una firma revocata o scaduta non produce VALIDSIG.
status="$(git -C "$REPO" -c gpg.format=openpgp verify-tag --raw "$TAG" 2>&1 || true)"
signer="$(printf '%s\n' "$status" | awk -v p="$RELEASE_PRIMARY" '$2 == "VALIDSIG" && $NF == p { print $3 }')"
for allowed in $TAG_SIGNING_SUBKEYS; do
    if [ -n "$signer" ] && [ "$signer" = "$allowed" ]; then
        echo "$TAG: firmato dal maintainer (sottochiave $signer della chiave di rilascio $RELEASE_PRIMARY)"
        exit 0
    fi
done
if [ -n "$signer" ]; then
    echo "il tag $TAG è firmato da $signer, che non è una sottochiave dei tag ($TAG_SIGNING_SUBKEYS)" >&2
else
    echo "il tag $TAG non ha una firma valida della chiave di rilascio $RELEASE_PRIMARY" >&2
    printf '%s\n' "$status" | grep -E '^\[GNUPG:\] (ERRSIG|BADSIG|NO_PUBKEY|VALIDSIG|EXPKEYSIG|REVKEYSIG)' >&2 || true
fi
exit 1
