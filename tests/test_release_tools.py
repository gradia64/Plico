"""The release key and the check that only it can sign a release tag.

scripts/verify-tag.sh is what release.yml runs before building anything: a tag
that passes it is published and, through the PKGBUILD, built by every AUR user.
These tests sign tags with a throw-away key shaped like the real one -- a [C]
primary and [S] subkeys -- and check what passes and what does not.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VERIFY = ROOT / "scripts" / "verify-tag.sh"
PUBLIC_KEY = ROOT / "packaging" / "plico-release-key.asc"

pytestmark = pytest.mark.skipif(
    shutil.which("gpg") is None or shutil.which("git") is None, reason="servono gpg e git"
)


def _keys_file() -> dict[str, str]:
    values = {}
    for line in (ROOT / "scripts" / "release-keys.sh").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            name, _, rest = line.partition("=")
            values[name] = rest.split(":-", 1)[1].rstrip('}"')
    return values


def test_the_published_key_is_the_one_the_scripts_trust():
    """The .asc in the repository: a [C] primary, the tag subkey, nothing private."""
    keys = _keys_file()
    text = PUBLIC_KEY.read_text()
    assert "PRIVATE" not in text
    listing = subprocess.run(
        ["gpg", "--show-keys", "--with-colons", "--with-subkey-fingerprints", str(PUBLIC_KEY)],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    rows = [line.split(":") for line in listing]
    fingerprints = [r[9] for r in rows if r[0] == "fpr"]
    assert fingerprints == [keys["RELEASE_PRIMARY"], keys["TAG_SIGNING_SUBKEYS"]]
    primary = next(r for r in rows if r[0] == "pub")
    subkey = next(r for r in rows if r[0] == "sub")
    assert primary[11].lower().startswith("c") and "s" not in primary[11][:1]
    assert subkey[11] == "s", "la sottochiave dei tag firma e basta"


def _run(cmd: list[str], **kwargs) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True, **kwargs).stdout


@pytest.fixture
def signing(tmp_path):
    """A keyring with a release-shaped key (and a stranger), and a repository."""
    home = tmp_path / "g"
    home.mkdir(mode=0o700)
    env = {"GNUPGHOME": str(home), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}

    def gpg(*args: str) -> str:
        return _run(["gpg", "--batch", "--passphrase", "", "--pinentry-mode", "loopback", *args],
                    env=env)

    def fingerprints(uid: str) -> list[str]:
        out = gpg("--with-colons", "--with-subkey-fingerprints", "--list-keys", uid)
        return [line.split(":")[9] for line in out.splitlines() if line.startswith("fpr")]

    gpg("--quick-generate-key", "Release <release@example.org>", "ed25519", "cert", "1y")
    primary = fingerprints("release@example.org")[0]
    gpg("--quick-add-key", primary, "ed25519", "sign", "1y")
    gpg("--quick-add-key", primary, "ed25519", "sign", "1y")
    _, tag_subkey, other_subkey = fingerprints("release@example.org")
    gpg("--quick-generate-key", "Stranger <stranger@example.org>", "ed25519", "sign", "1y")
    stranger = fingerprints("stranger@example.org")[0]
    public = tmp_path / "release.asc"
    public.write_text(gpg("--armor", "--export", primary))

    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> str:
        return _run(["git", "-C", str(repo), *args], env=env)

    git("init", "-q")
    git("config", "user.name", "T")
    git("config", "user.email", "release@example.org")
    git("config", "gpg.format", "openpgp")
    git("commit", "-q", "--allow-empty", "-m", "release")

    def tag(name: str, key: str | None) -> None:
        if key is None:
            git("tag", name)
        else:
            git("-c", f"user.signingkey={key}!", "tag", "-s", name, "-m", name)

    def verify(name: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(VERIFY), name],
            capture_output=True, text=True, check=False,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(tmp_path),
                "PLICO_REPO": str(repo),
                "PLICO_RELEASE_KEY": str(public),
                "PLICO_RELEASE_PRIMARY": primary,
                "PLICO_TAG_SIGNING_SUBKEYS": tag_subkey,
            },
        )

    return tag, verify, {"tag": tag_subkey, "other": other_subkey, "stranger": stranger}


def test_a_tag_signed_by_the_tag_subkey_passes(signing):
    tag, verify, keys = signing
    tag("v1.0.0", keys["tag"])
    result = verify("v1.0.0")
    assert result.returncode == 0, result.stderr
    assert keys["tag"] in result.stdout


@pytest.mark.parametrize("who", ["other", "stranger"])
def test_a_tag_signed_by_any_other_key_is_refused(signing, who):
    """Another subkey of the same release key, or a key from outside it."""
    tag, verify, keys = signing
    tag("v1.0.0", keys[who])
    result = verify("v1.0.0")
    assert result.returncode == 1


def test_a_lightweight_tag_is_refused(signing):
    tag, verify, _ = signing
    tag("v1.0.0", None)
    result = verify("v1.0.0")
    assert result.returncode == 1
    assert "annotato" in result.stderr
