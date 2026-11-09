#!/bin/bash
# Prova un'AppImage già costruita su più distribuzioni, in container Docker.
#
#   packaging/appimage/test-distros.sh dist/Plico-X.Y.Z-<arch>.AppImage [immagine…]
#
# In ogni container: le sole librerie di base di un desktop (X11, GL,
# fontconfig, xkbcommon e xkbcommon-x11, estensioni di libxcb, D-Bus) più
# Xvfb, niente FUSE (APPIMAGE_EXTRACT_AND_RUN). GLib c'è su ogni desktop ma
# non nelle immagini minime: fa parte della base, come X11 e GL, e così tzdata
# (assente nelle immagini Ubuntu; pyHanko apre un fuso orario già all'import).
# L'app parte sul plugin X11 vero di Qt e deve essere viva dopo 10 secondi,
# senza errori.
# Se il plugin xcb non trova una libreria, la si vede qui (ldd), prima che la
# veda un utente; se l'AppImage torna a includere libxkbcommon-x11 (segfault
# del plugin xcb accanto a una libxkbcommon di sistema più recente, vedi
# scripts/build-appimage.sh), la prova si ferma prima di avviarla.
#
# Per l'x86_64 non è nella CI: serve Docker e scarica sei immagini. Va
# lanciata a mano prima di un tag che tocca le librerie incluse. L'aarch64 la
# fa girare il job test-aarch64 di release.yml, su una macchina ARM; da una
# macchina x86_64 serve l'emulazione di Docker (binfmt + qemu-user-static, per
# esempio il pacchetto qemu-user-binfmt), e i tempi si allungano.
set -euo pipefail

APPIMAGE_FILE="$(readlink -f "${1:?uso: test-distros.sh <file .AppImage> [immagine…]}")"
shift
IMAGES=("$@")
case "$APPIMAGE_FILE" in
    *-aarch64.AppImage)
        PLATFORM=linux/arm64 ARCH=aarch64
        # glibc >= 2.39 (wheel PySide6 aarch64); archlinux non ha immagini arm64
        DEFAULT=(debian:13 ubuntu:24.04 fedora:latest opensuse/tumbleweed:latest) ;;
    *)
        PLATFORM=linux/amd64 ARCH=x86_64
        DEFAULT=(debian:12 ubuntu:22.04 ubuntu:24.04 fedora:latest
                 archlinux:latest opensuse/tumbleweed:latest) ;;
esac
[ ${#IMAGES[@]} -gt 0 ] || IMAGES=("${DEFAULT[@]}")
# sotto emulazione qemu la regola binfmt vuole a zero i byte 8-10
# dell'intestazione ELF, dove le AppImage scrivono «AI\x02»: nel container si
# prova una copia con quei byte azzerati (il runtime non li legge)
ZERO_MAGIC=0 RUN_SECS=10
[ "$(uname -m)" = "$ARCH" ] || { ZERO_MAGIC=1; RUN_SECS=60; }

INNER="$(mktemp)"
trap 'rm -f "$INNER"' EXIT
cat > "$INNER" <<'EOF'
#!/bin/sh
set -eu
q() { "$@" >/tmp/install.log 2>&1 || { tail -20 /tmp/install.log; exit 1; }; }
if command -v apt-get >/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    q apt-get update
    q apt-get install -y --no-install-recommends xvfb libgl1 libegl1 libfontconfig1 \
        libxkbcommon0 libxkbcommon-x11-0 libxcb-render0 libxcb-shape0 libdbus-1-3 libx11-xcb1 libglib2.0-0 libxcb-xkb1 tzdata procps fonts-dejavu-core
elif command -v dnf >/dev/null; then
    q dnf install -y xorg-x11-server-Xvfb mesa-libGL mesa-libEGL fontconfig \
        libxkbcommon libxkbcommon-x11 dbus-libs glib2 procps-ng findutils dejavu-sans-fonts
elif command -v pacman >/dev/null; then
    q pacman -Syu --noconfirm --needed xorg-server-xvfb mesa fontconfig libxkbcommon \
        libxkbcommon-x11 dbus glib2 procps-ng findutils ttf-dejavu
elif command -v zypper >/dev/null; then
    q zypper --non-interactive install --no-recommends xorg-x11-server-Xvfb Mesa-libGL1 \
        Mesa-libEGL1 fontconfig libxkbcommon0 libxkbcommon-x11-0 \
        libxcb-render0 libxcb-shape0 libSM6 libICE6 libdbus-1-3 libX11-xcb1 libglib-2_0-0 \
        libgthread-2_0-0 procps findutils dejavu-fonts
fi
. /etc/os-release
echo "== $PRETTY_NAME, glibc $(ldd --version | head -1 | sed 's/.* //')"

cd /tmp
cp /app/Plico.AppImage ./a.AppImage
if [ "$ZERO_MAGIC" = 1 ]; then
    printf '\000\000\000' | dd of=a.AppImage bs=1 seek=8 conv=notrunc 2>/dev/null
fi
./a.AppImage --appimage-extract >/dev/null
bundled="$(find squashfs-root -name 'libxkbcommon*' -o -name 'libxcb-xkb.so*' \
    -o -name 'libxcb-render.so*' -o -name 'libxcb-shape.so*')"
if [ -n "$bundled" ]; then echo "librerie che devono venire dal sistema:"; echo "$bundled"; exit 1; fi
missing="$(find squashfs-root -path '*plugins/platforms/libqxcb.so' -exec ldd {} \; | grep 'not found' || true)"
if [ -n "$missing" ]; then echo "librerie mancanti per il plugin X11:"; echo "$missing"; exit 1; fi
rm -rf squashfs-root

Xvfb :99 -nolisten tcp >/dev/null 2>&1 &
sleep 2
export DISPLAY=:99 QT_QPA_PLATFORM=xcb XDG_CONFIG_HOME=/tmp/cfg XDG_CACHE_HOME=/tmp/cache \
       APPIMAGE_EXTRACT_AND_RUN=1
set +e
# il codice di uscita su file: in alcune sh «wait <pid>» dà 127 per un
# processo già terminato, e il codice vero si perderebbe
(timeout "$RUN_SECS" ./a.AppImage > app.log 2>&1; echo $? > rc) &
pid=$!
wait $pid
rc="$(cat rc)"
set -e
if [ "$rc" -ne 124 ]; then cat app.log; echo "uscita da sola (codice $rc)"; exit 1; fi
if grep -Eq 'Traceback|Error|error|Cannot load|could not' app.log; then cat app.log; exit 1; fi
echo "OK: finestra su X11 per $RUN_SECS s"
EOF
chmod 755 "$INNER"

fail=()
for image in "${IMAGES[@]}"; do
    if docker run --rm --platform "$PLATFORM" -e ZERO_MAGIC="$ZERO_MAGIC" -e RUN_SECS="$RUN_SECS" \
            -v "$APPIMAGE_FILE:/app/Plico.AppImage:ro" -v "$INNER:/inner.sh:ro" \
            "$image" /inner.sh; then
        :
    else
        echo "!! $image: FALLITO"
        fail+=("$image")
    fi
done
if [ ${#fail[@]} -gt 0 ]; then
    echo "falliti: ${fail[*]}" >&2
    exit 1
fi
echo "tutte le distribuzioni: OK"
