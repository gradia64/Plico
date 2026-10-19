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
    """A repository with Plico's packaging files and an SSH key that signs tags."""
    if shutil.which("ssh-keygen") is None:
        pytest.skip("ssh-keygen non disponibile")
    work = tmp_path / "repo"
    (work / "flatpak").mkdir(parents=True)
    for name in (f"{fm.APP_ID}.json", "python3-pymupdf.json", "python3-pikepdf.json",
                 "python3-pyhanko.json"):
        shutil.copy(ROOT / "flatpak" / name, work / "flatpak" / name)
    (work / "pyproject.toml").write_text(PYPROJECT)
    (work / fm.METAINFO).write_text(METAINFO)

    key = tmp_path / "key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "t@example.org",
                    "-f", str(key)], check=True)
    (work / ".github").mkdir()
    (work / fm.ALLOWED_SIGNERS).write_text(
        "t@example.org " + " ".join(key.with_suffix(".pub").read_text().split()[:2]) + "\n"
    )

    def git(*args):
        subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.name", "T")
    git("config", "user.email", "t@example.org")
    git("config", "gpg.format", "ssh")
    git("config", "user.signingkey", str(key))
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


def test_lightweight_tag_refused(repo, tmp_path):
    _, git = repo
    git("tag", "v1.2.3")
    assert fm.main(["v1.2.3", str(tmp_path / "out"), "--offline", "--allow-unsigned"]) == 1


def test_tag_without_remote_refused(repo, tmp_path):
    _, git = repo
    git("tag", "-s", "-m", "Plico 1.2.3", "v1.2.3")
    # No origin at all: the tag is certainly not where Flathub would look.
    assert fm.main(["v1.2.3", str(tmp_path / "out")]) == 1
