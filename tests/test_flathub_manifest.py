"""tools/flathub_manifest.py: the manifest that goes to Flathub, and its checks.

What it guards is the release: a manifest that builds something other than the
tag, a tag that does not match the version, a signature nobody checked. Each
of those is silent until a user installs the wrong thing, so it fails here.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import flathub_manifest as fm  # noqa: E402 -- tools/ is on the path only from here

PYPROJECT = '[project]\nname = "plico"\nversion = "1.2.3"\n'
SHOT = "https://raw.githubusercontent.com/gradia64/Plico/{0}/flatpak/screenshots/main.png"
METAINFO = (
    "<component><screenshots><screenshot><image>"
    + SHOT.format("v1.2.3")
    + "</image></screenshot></screenshots><releases>"
    '<release version="1.2.3" date="2026-10-18"/>'
    '<release version="1.2.2" date="2026-10-01"/>'
    "</releases></component>"
)
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def test_versions_agree():
    assert fm.check_versions("v1.2.3", PYPROJECT, METAINFO) == "1.2.3"


@pytest.mark.parametrize(
    ("tag", "pyproject", "metainfo"),
    [
        ("1.2.3", PYPROJECT, METAINFO),  # no "v"
        ("v1.2", PYPROJECT, METAINFO),
        ("v1.2.4", PYPROJECT, METAINFO),  # pyproject left behind
        ("v1.2.3", PYPROJECT.replace("1.2.3", "1.2.4"), METAINFO),
        ("v1.2.3", PYPROJECT, METAINFO.replace("1.2.3", "1.2.4")),  # release note forgotten
        ("v1.2.3", PYPROJECT, "<component/>"),
    ],
)
def test_versions_disagree(tag, pyproject, metainfo):
    with pytest.raises(fm.ReleaseError):
        fm.check_versions(tag, pyproject, metainfo)


def test_screenshots_pinned():
    fm.check_screenshots("v1.2.3", METAINFO)


def test_screenshots_on_main_refused():
    with pytest.raises(fm.ReleaseError, match="main.png"):
        fm.check_screenshots("v1.2.3", METAINFO.replace("v1.2.3/", "main/"))


def test_only_the_local_source_changes():
    manifest = json.loads((ROOT / fm.MANIFEST).read_text())
    out = fm.to_flathub(manifest, "v1.2.3", COMMIT)

    plico = next(m for m in out["modules"] if isinstance(m, dict) and m["name"] == "plico")
    assert plico["sources"] == [
        {"type": "git", "url": fm.URL, "tag": "v1.2.3", "commit": COMMIT}
    ]
    # Nothing else moved, and the input was not touched.
    assert [m for m in out["modules"] if m is not plico] == [
        m for m in manifest["modules"] if not (isinstance(m, dict) and m["name"] == "plico")
    ]
    assert {k: v for k, v in out.items() if k != "modules"} == {
        k: v for k, v in manifest.items() if k != "modules"
    }
    def kinds(m):
        return [s.get("type") for x in m["modules"] if isinstance(x, dict)
                for s in x.get("sources", [])]

    assert "dir" in kinds(manifest)
    assert "dir" not in kinds(out)


def test_short_commit_refused():
    manifest = json.loads((ROOT / fm.MANIFEST).read_text())
    with pytest.raises(fm.ReleaseError):
        fm.to_flathub(manifest, "v1.2.3", COMMIT[:12])


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repository with Plico's packaging files and a release-shaped GPG key.

    The key is a [C] primary with a [S] subkey, like the real one; tags are
    signed with ``git("tag", "-s", ...)`` by the subkey, and scripts/verify-tag.sh
    is pointed at this key instead of packaging/plico-release-key.asc.
    """
    if shutil.which("gpg") is None:
        pytest.skip("gpg non disponibile")
    work = tmp_path / "repo"
    (work / "flatpak").mkdir(parents=True)
    for name in (f"{fm.APP_ID}.json", "python3-pymupdf.json", "python3-pikepdf.json",
                 "python3-pyhanko.json"):
        shutil.copy(ROOT / "flatpak" / name, work / "flatpak" / name)
    (work / "pyproject.toml").write_text(PYPROJECT)
    (work / fm.METAINFO).write_text(METAINFO)

    home = tmp_path / "g"
    home.mkdir(mode=0o700)
    env = {"GNUPGHOME": str(home), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}

    def run(*args: str) -> str:
        return subprocess.run(args, check=True, capture_output=True, text=True, env=env).stdout

    def gpg(*args: str) -> str:
        return run("gpg", "--batch", "--passphrase", "", "--pinentry-mode", "loopback", *args)

    def fingerprints(uid: str) -> list[str]:
        out = gpg("--with-colons", "--with-subkey-fingerprints", "--list-keys", uid)
        return [line.split(":")[9] for line in out.splitlines() if line.startswith("fpr")]

    gpg("--quick-generate-key", "Release <t@example.org>", "ed25519", "cert", "1y")
    primary = fingerprints("t@example.org")[0]
    gpg("--quick-add-key", primary, "ed25519", "sign", "1y")
    subkey = fingerprints("t@example.org")[1]
    gpg("--quick-generate-key", "Stranger <s@example.org>", "ed25519", "sign", "1y")
    public = tmp_path / "release.asc"
    public.write_text(gpg("--armor", "--export", primary))
    monkeypatch.setenv("PLICO_RELEASE_KEY", str(public))
    monkeypatch.setenv("PLICO_RELEASE_PRIMARY", primary)
    monkeypatch.setenv("PLICO_TAG_SIGNING_SUBKEYS", subkey)
    # The machine's keyring holds both keys, the stranger's too: what the
    # check trusts must be the release key alone.
    monkeypatch.setenv("GNUPGHOME", str(home))

    def git(*args):
        run("git", "-C", str(work), *args)

    git("init", "-q")
    git("config", "user.name", "T")
    git("config", "user.email", "t@example.org")
    git("config", "gpg.format", "openpgp")
    git("config", "user.signingkey", f"{subkey}!")
    git("config", "commit.gpgSign", "false")
    git("config", "tag.gpgSign", "false")
    git("add", ".")
    git("commit", "-q", "-m", "release")
    monkeypatch.setattr(fm, "ROOT", work)
    return work, git


def test_signed_tag_becomes_a_manifest(repo, tmp_path):
    work, git = repo
    git("tag", "-s", "-m", "Plico 1.2.3", "v1.2.3")
    out = tmp_path / "flathub"

    assert fm.main(["v1.2.3", str(out), "--offline"]) == 0

    head = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    written = json.loads((out / f"{fm.APP_ID}.json").read_text())
    plico = next(m for m in written["modules"] if isinstance(m, dict) and m["name"] == "plico")
    assert plico["sources"][0]["commit"] == head
    for name in ("python3-pymupdf.json", "python3-pikepdf.json", "python3-pyhanko.json"):
        assert (out / name).read_text() == (ROOT / "flatpak" / name).read_text()


def test_unsigned_tag_refused(repo, tmp_path):
    _, git = repo
    git("tag", "-a", "-m", "Plico 1.2.3", "v1.2.3")
    out = tmp_path / "flathub"

    assert fm.main(["v1.2.3", str(out), "--offline"]) == 1
    assert not out.exists()
    # The dry run is still possible, on purpose.
    assert fm.main(["v1.2.3", str(out), "--offline", "--allow-unsigned"]) == 0


def test_tag_signed_by_another_key_refused(repo, tmp_path):
    """A valid signature is not enough: it must be the release key's.

    The old check ran ``git tag -v``, which trusts any key in the machine's
    keyring -- and the release tags, OpenPGP since 0.1.4, were not even
    compared with the key in the repository.
    """
    _, git = repo
    git("-c", "user.signingkey=s@example.org", "tag", "-s", "-m", "Plico 1.2.3", "v1.2.3")
    out = tmp_path / "flathub"

    assert fm.main(["v1.2.3", str(out), "--offline"]) == 1
    assert not out.exists()


def test_lightweight_tag_refused(repo, tmp_path):
    _, git = repo
    git("tag", "v1.2.3")
    assert fm.main(["v1.2.3", str(tmp_path / "out"), "--offline", "--allow-unsigned"]) == 1


def test_tag_without_remote_refused(repo, tmp_path):
    _, git = repo
    git("tag", "-s", "-m", "Plico 1.2.3", "v1.2.3")
    # No origin at all: the tag is certainly not where Flathub would look.
    assert fm.main(["v1.2.3", str(tmp_path / "out")]) == 1
