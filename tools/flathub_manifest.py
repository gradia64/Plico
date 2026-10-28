"""Make the manifest to submit to Flathub from a signed release tag.

    python tools/flathub_manifest.py v0.1.0 ~/flathub/io.github.gradia64.plico

The manifest in ``flatpak/`` builds the ``plico`` module from the checkout
(``"type": "dir"``), which is what a developer and the CI want and what Flathub
refuses: it builds from a git source pinned to a tag *and* to its commit, so
that moving the tag afterwards breaks the build instead of changing what it
builds. This writes that manifest, and the module files it includes, into the
given directory -- the Flathub repository of the app, typically.

Everything is read from the TAG, not from the working tree: the manifest that
goes out describes the code the tag points at, uncommitted edits included in
neither. And before writing anything the release is checked, because each of
these mistakes is cheap now and a new release later:

- the tag is ``v`` + the version in ``pyproject.toml`` and the newest
  ``<release>`` of the AppStream metainfo, all three the same;
- the store screenshots in the metainfo point at the tag, not at ``main``:
  Flathub mirrors them at build time, and ``main`` keeps moving;
- the tag is annotated and signed by a tag subkey of the release key in
  ``packaging/plico-release-key.asc``, checked by ``scripts/verify-tag.sh``
  as release.yml does (``--allow-unsigned`` to skip, for a dry run);
- the remote has the same tag object (``--offline`` to skip): a tag only on
  this machine cannot be fetched by Flathub's builders.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
APP_ID = "io.github.gradia64.plico"
MANIFEST = f"flatpak/{APP_ID}.json"
METAINFO = f"flatpak/{APP_ID}.metainfo.xml"
URL = "https://github.com/gradia64/Plico.git"
# Of this checkout, never of ROOT: the tests point ROOT at a scratch repository.
VERIFY_TAG = Path(__file__).resolve().parent.parent / "scripts" / "verify-tag.sh"


class ReleaseError(Exception):
    """The tag is not something that can be shipped as it is."""


def check_versions(tag: str, pyproject: str, metainfo: str) -> str:
    """The version *tag* releases, if the three places agree on it."""
    match = re.fullmatch(r"v(\d+\.\d+\.\d+)", tag)
    if match is None:
        raise ReleaseError(f"il tag {tag!r} non è nella forma vX.Y.Z")
    version = match.group(1)
    declared = tomllib.loads(pyproject)["project"]["version"]
    if declared != version:
        raise ReleaseError(f"pyproject.toml dice {declared}, il tag {version}")
    # The newest release comes first: that is the order AppStream requires.
    release = ET.fromstring(metainfo).find("releases/release")
    if release is None or release.get("version") != version:
        found = None if release is None else release.get("version")
        raise ReleaseError(f"l'ultima <release> della metainfo è {found}, il tag {version}")
    return version


def check_screenshots(tag: str, metainfo: str) -> None:
    """Every store screenshot is pinned to *tag*."""
    images = [i.text or "" for i in ET.fromstring(metainfo).iter("image")]
    unpinned = [url for url in images if f"/{tag}/" not in url]
    if unpinned:
        raise ReleaseError(
            f"screenshot non fissati a {tag} nella metainfo: " + ", ".join(unpinned)
        )


def to_flathub(manifest: dict[str, Any], tag: str, commit: str) -> dict[str, Any]:
    """*manifest* with the plico module built from *tag* at *commit*.

    Only the ``"type": "dir"`` source of the ``plico`` module changes; the
    other modules, already pinned by URL and sha256, are left as they are.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseError(f"{commit!r} non è l'hash completo di un commit")
    out: dict[str, Any] = json.loads(json.dumps(manifest))
    modules = [m for m in out["modules"] if isinstance(m, dict) and m.get("name") == "plico"]
    if len(modules) != 1:
        raise ReleaseError("il manifest non ha un solo modulo «plico»")
    sources = modules[0]["sources"]
    local = [s for s in sources if s.get("type") == "dir"]
    if len(local) != 1:
        raise ReleaseError("il modulo «plico» non ha una sola sorgente di tipo dir")
    sources[sources.index(local[0])] = {
        "type": "git",
        "url": URL,
        "tag": tag,
        "commit": commit,
    }
    return out


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def _check_tag(tag: str, allow_unsigned: bool, offline: bool) -> str:
    """The commit *tag* points at, after checking the tag itself."""
    ref = f"refs/tags/{tag}"
    obj = _git("rev-parse", "--verify", "--quiet", ref).strip()
    if _git("cat-file", "-t", obj).strip() != "tag":
        raise ReleaseError(f"{tag} è un tag leggero: serve un tag annotato (git tag -s)")
    if not allow_unsigned:
        # The key of the working tree, not of the tagged tree, which would let
        # a tag vouch for itself; and in a keyring of its own, not the
        # machine's, where any key could be.
        result = subprocess.run(
            [str(VERIFY_TAG), tag], capture_output=True, text=True, check=False,
            env={**os.environ, "PLICO_REPO": str(ROOT)},
        )
        if result.returncode != 0:
            raise ReleaseError(result.stderr.strip())
    if not offline:
        remote = _git("ls-remote", "origin", ref).split()
        if not remote or remote[0] != obj:
            raise ReleaseError(f"{tag} non è su origin, o lì è un altro oggetto: git push origin {tag}")
    return _git("rev-parse", f"{ref}^{{commit}}").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tag", help="il tag di rilascio, per esempio v0.1.0")
    parser.add_argument("out", type=Path, help="dove scrivere il manifest per Flathub")
    parser.add_argument("--allow-unsigned", action="store_true", help="non verificare la firma")
    parser.add_argument("--offline", action="store_true", help="non confrontare con origin")
    args = parser.parse_args(argv)

    try:
        commit = _check_tag(args.tag, args.allow_unsigned, args.offline)
        metainfo = _git("show", f"{args.tag}:{METAINFO}")
        version = check_versions(args.tag, _git("show", f"{args.tag}:pyproject.toml"), metainfo)
        check_screenshots(args.tag, metainfo)
        manifest = json.loads(_git("show", f"{args.tag}:{MANIFEST}"))
        flathub = to_flathub(manifest, args.tag, commit)
        # The included modules travel with the manifest: Flathub resolves
        # them next to it, exactly as flatpak-builder does here.
        included = {
            m: _git("show", f"{args.tag}:flatpak/{m}")
            for m in flathub["modules"]
            if isinstance(m, str)
        }
    except ReleaseError as error:
        print(f"errore: {error}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{APP_ID}.json").write_text(json.dumps(flathub, indent=2) + "\n")
    for name, text in included.items():
        (args.out / name).write_text(text)
    print(f"{APP_ID} {version} @ {commit[:12]} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
