"""Controlla la glibc richiesta dai file ELF dell'AppDir.

Uso: python3 check-glibc.py <AppDir> <versione massima, es. 2.34>

Le wheel di PySide6 chiedono glibc 2.34 (manylinux_2_34): nessun altro file
dell'AppImage deve chiederne una più recente, altrimenti l'AppImage non
partirebbe sulle distribuzioni che PySide6 supporta. Serve soprattutto per
le librerie copiate dal sistema che costruisce l'AppImage.
"""
import re
import subprocess
import sys
from pathlib import Path


def version(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in s.split("."))


def main(appdir: Path, limit: tuple[int, ...]) -> int:
    worst, bad = (0, 0), []
    for f in sorted(appdir.rglob("*")):
        if not f.is_file() or f.is_symlink():
            continue
        with f.open("rb") as fh:
            if fh.read(4) != b"\x7fELF":
                continue
        out = subprocess.run(["objdump", "-T", str(f)], capture_output=True,
                             text=True, check=False).stdout
        vers = [version(v) for v in re.findall(r"GLIBC_(\d+(?:\.\d+)+)", out)]
        if not vers:
            continue
        top = max(vers)
        if top > limit:
            bad.append(f"{f.relative_to(appdir)}: GLIBC_{'.'.join(map(str, top))}")
        worst = max(worst, top)
    if bad:
        print("richiedono una glibc troppo recente:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    print("glibc richiesta:", ".".join(map(str, worst)))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), version(sys.argv[2])))
