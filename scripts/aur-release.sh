#!/bin/bash
# Pubblica su AUR il PKGBUILD di una release, dalla macchina del maintainer.
# Ripreso da OllaDesk.
#
# La chiave SSH dell'account AUR non sta nella CI: vale per tutti i pacchetti
# dell'account, e chi ne ottenesse i secret potrebbe pubblicare un PKGBUILD
# qualsiasi. La CI costruisce e prova il pacchetto (job «arch» di
# release.yml); il push lo fa il maintainer con questo script:
#
# 1. verifica il tag con scripts/verify-tag.sh (firmato dalla sottochiave dei
#    tag);
# 2. trova la run riuscita di release.yml che ha costruito il pacchetto: quella
#    del push del tag, oppure la run indicata come secondo argomento, lanciata
#    a mano con aur_tag (un PKGBUILD.in corretto dopo il rilascio, dal ramo
#    main);
# 3. rigenera il PKGBUILD dal commit di quella run (git archive +
#    prepare-aur.sh) e controlla che quello dell'artefatto «arch» sia identico:
#    si pubblica solo ciò che la CI ha costruito e provato, e la CI non può
#    cambiare ciò che si pubblica;
# 4. controlla che .SRCINFO (generato da makepkg nella CI) descriva lo stesso
#    PKGBUILD: versione, sorgenti, somme e chiave;
# 5. pubblica con scripts/publish-aur.sh e la chiave SSH dell'utente
#    (~/.ssh/config, Host aur.archlinux.org).
#
# Uso: scripts/aur-release.sh vX.Y.Z [id della run di release.yml]
# Per i test: PLICO_ARCH_ARTIFACT=<cartella> salta gh (e il commit è il tag,
# o PLICO_SOURCE_COMMIT); PLICO_REPO e le variabili di verify-tag.sh come lì.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${PLICO_REPO:-$ROOT}"
TAG="${1:?uso: scripts/aur-release.sh vX.Y.Z [id della run]}"
RUN="${2:-}"
VERSION="${TAG#v}"
[[ $TAG =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "tag non valido: $TAG" >&2; exit 1; }
[[ -z $RUN || $RUN =~ ^[0-9]+$ ]] || { echo "id della run non valido: $RUN" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# 1. il tag è del maintainer
"$ROOT/scripts/verify-tag.sh" "$TAG"
tag_sha="$(git -C "$REPO" rev-parse "refs/tags/$TAG^{commit}")"

# 2. la run che ha costruito il pacchetto, e il commit da cui l'ha costruito
if [ -n "${PLICO_ARCH_ARTIFACT:-}" ]; then
    ART="$PLICO_ARCH_ARTIFACT"
    source_sha="${PLICO_SOURCE_COMMIT:-$tag_sha}"
else
    if [ -z "$RUN" ]; then
        RUN="$(cd "$REPO" && gh run list --workflow release.yml --branch "$TAG" --event push \
                --status success --json databaseId,headSha \
                --jq "map(select(.headSha == \"$tag_sha\"))[0].databaseId")"
        if [ -z "$RUN" ] || [ "$RUN" = "null" ]; then
            echo "nessuna run riuscita di release.yml per $TAG ($tag_sha): la release è stata pubblicata?" >&2
            exit 1
        fi
    fi
    read -r conclusion source_sha workflow < <(cd "$REPO" && gh run view "$RUN" \
        --json conclusion,headSha,workflowName --jq '"\(.conclusion) \(.headSha) \(.workflowName)"')
    if [ "$conclusion" != "success" ] || [ "$workflow" != "Release" ]; then
        echo "la run $RUN non è una run riuscita di release.yml ($workflow: $conclusion)" >&2
        exit 1
    fi
    # una run a mano costruisce dal ramo: il commit deve essere già in main
    if [ "$source_sha" != "$tag_sha" ] \
            && ! git -C "$REPO" merge-base --is-ancestor "$source_sha" refs/heads/main 2>/dev/null; then
        echo "la run $RUN ha costruito $source_sha, che non è il tag né un commit di main" >&2
        exit 1
    fi
    (cd "$REPO" && gh run download "$RUN" --name arch --dir "$TMP/artifact")
    ART="$TMP/artifact/build/aur"
fi
for f in PKGBUILD .SRCINFO; do
    [ -f "$ART/$f" ] || { echo "manca $f nell'artefatto della CI ($ART)" >&2; exit 1; }
done

# 3. PKGBUILD dal commit della run, con gli script di quel commit
mkdir "$TMP/src"
git -C "$REPO" archive "$source_sha" | tar -x -C "$TMP/src"
PLICO_VERSION="$VERSION" "$TMP/src/scripts/prepare-aur.sh" "$TMP/aur" >/dev/null
rm -f "$TMP/aur/.SRCINFO"   # se c'è makepkg: conta quello della CI, controllato sotto
if ! cmp -s "$TMP/aur/PKGBUILD" "$ART/PKGBUILD"; then
    echo "il PKGBUILD della CI è diverso da quello generato da $source_sha:" >&2
    diff -u "$TMP/aur/PKGBUILD" "$ART/PKGBUILD" >&2 || true
    exit 1
fi

# 4. .SRCINFO coerente con il PKGBUILD (è quello che AUR mostra e indicizza)
pkgbuild="$TMP/aur/PKGBUILD"
srcinfo="$ART/.SRCINFO"
primary="$(sed -n "s/^validpgpkeys=('\([0-9A-F]*\)').*/\1/p" "$pkgbuild")"
url="$(sed -n 's/^url="\(.*\)"$/\1/p' "$pkgbuild")"
expect=(
    "pkgbase = plico"
    "	pkgver = $VERSION"
    "	source = plico::git+$url.git#tag=v$VERSION?signed"
    "	validpgpkeys = $primary"
)
for line in "${expect[@]}"; do
    grep -qxF "$line" "$srcinfo" || { echo ".SRCINFO della CI senza «${line#	}»" >&2; exit 1; }
done
sums_pkgbuild="$(sed -n '/^sha256sums=(/,/)/p' "$pkgbuild" | grep -o "'[0-9a-fA-FSKIP]*'" | tr -d "'")"
sums_srcinfo="$(sed -n 's/^	sha256sums = //p' "$srcinfo")"
if [ "$sums_pkgbuild" != "$sums_srcinfo" ] \
        || [ "$(grep -c '^	source = ' "$srcinfo")" -ne "$(grep -c . <<< "$sums_pkgbuild")" ] \
        || [ "$(grep -c '^	validpgpkeys = ' "$srcinfo")" -ne 1 ]; then
    echo ".SRCINFO della CI con sorgenti, somme o chiavi diverse dal PKGBUILD" >&2
    exit 1
fi
cp "$srcinfo" "$TMP/aur/.SRCINFO"

# 5. pubblicazione con la chiave SSH dell'utente
"$ROOT/scripts/publish-aur.sh" "$TMP/aur"
