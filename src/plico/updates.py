"""Whether a newer Plico is out, asked of GitHub's releases.

Plico made no network request before this module, and it still makes none
unless the user asks: «Aiuto → Cerca aggiornamenti…» is one request, and the
daily check is a setting that is off until it is turned on. The request is a
plain GET of the latest release, with no data about the user or the document;
what GitHub sees is the address and ``Plico/<version>`` as user agent.

Only some packages need it. Where Plico came from decides (:func:`channel`):

- the **AppImage** and the **.deb** are files downloaded from a release page,
  and nothing updates them: the .deb is installed with ``apt install ./…``,
  from no repository;
- **pip** and a **checkout** are updated by whoever installed them, and are
  told nothing either;
- the **AUR** package (``/usr/share/plico``) is updated by pacman and the AUR
  helper, so a daily check would only repeat what they already say;
- the **Flatpak bundle** has no ``--repo-url``, so ``flatpak update`` never
  updates it -- but its sandbox has no network, on purpose (a PDF editor that
  can reach the network can leak what a malicious file reads), and a check is
  not worth widening it. There the command opens the releases page, through
  the portal, and the version is compared by eye.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import threading
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Signal

from . import __version__

RELEASES_API = "https://api.github.com/repos/gradia64/Plico/releases/latest"
RELEASES_PAGE = "https://github.com/gradia64/Plico/releases"
#: At most one automatic request a day, failed ones included.
INTERVAL_S = 24 * 60 * 60
TIMEOUT_S = 8.0
# A release is a few KB of JSON; anything far larger is not GitHub's answer.
MAX_BYTES = 1 << 20

_VERSION = re.compile(r"v?(\d+(?:\.\d+){0,3})")


class Channel(Enum):
    """How this Plico was installed, as far as it decides updates."""

    APPIMAGE = "appimage"
    DEB = "deb"
    FLATPAK = "flatpak"
    SYSTEM = "system"
    PYTHON = "python"


def channel(
    environ: Mapping[str, str] | None = None,
    package: Path | None = None,
    flatpak_info: Path = Path("/.flatpak-info"),
) -> Channel:
    """Where this Plico came from: the environment first, then where it lives.

    The AppImage first, because its package sits under
    ``<mount>/usr/share/plico`` and would otherwise pass for the AUR's.
    """
    env = os.environ if environ is None else environ
    if package is None:
        package = Path(__file__).resolve().parent
    if env.get("APPIMAGE"):
        return Channel.APPIMAGE
    if flatpak_info.exists():
        return Channel.FLATPAK
    if package.is_relative_to("/opt/plico"):
        return Channel.DEB
    if package.is_relative_to("/usr/share/plico"):
        return Channel.SYSTEM
    return Channel.PYTHON


def automatic_allowed(source: Channel) -> bool:
    """Whether the daily check makes sense here: nothing else updates Plico."""
    return source in (Channel.APPIMAGE, Channel.DEB, Channel.PYTHON)


def can_fetch(source: Channel) -> bool:
    """Whether Plico can ask GitHub at all: the Flatpak sandbox has no network."""
    return source is not Channel.FLATPAK


def parse_version(text: str) -> tuple[int, ...] | None:
    """``"v0.1.6"`` → ``(0, 1, 6)``; None for anything else (``"0.2.0rc1"`` too)."""
    match = _VERSION.fullmatch(text.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(candidate: str, current: str = __version__) -> bool:
    """Whether *candidate* comes after *current*; an unreadable one never does."""
    new, old = parse_version(candidate), parse_version(current)
    if new is None or old is None:
        return False
    width = max(len(new), len(old))
    return new + (0,) * (width - len(new)) > old + (0,) * (width - len(old))


def due(last: float | None, now: float) -> bool:
    """Whether a day has gone by since the last request (or the clock went back)."""
    return last is None or not 0 <= now - last < INTERVAL_S


def release_page(version: str) -> str:
    """The page of *version*, built here: no address from the network is opened."""
    return f"{RELEASES_PAGE}/tag/v{version}"


@dataclass(frozen=True)
class Release:
    """The latest release: its version without the ``v``, and its page."""

    version: str
    url: str


class UpdateError(Exception):
    """GitHub could not be asked, or its answer could not be read."""


def _invalid() -> UpdateError:
    return UpdateError(
        QCoreApplication.translate("UpdateChecker", "Risposta di GitHub non valida.")
    )


def release_from_json(data: object) -> Release:
    """The release in GitHub's answer; drafts and pre-releases are not one."""
    if not isinstance(data, dict):
        raise _invalid()
    tag = data.get("tag_name")
    version = parse_version(tag) if isinstance(tag, str) else None
    if version is None or data.get("draft") or data.get("prerelease"):
        raise _invalid()
    text = ".".join(str(part) for part in version)
    return Release(text, release_page(text))


def _ssl_context() -> ssl.SSLContext:
    """certifi's roots where they are bundled, the system's otherwise.

    The AppImage's portable Python looks for roots where its build machine kept
    them, not where this system does; certifi comes with pyHanko in every
    package, at a version the release fixes.
    """
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def fetch_latest(timeout: float = TIMEOUT_S) -> Release:
    """Ask GitHub for the latest release. Blocks: call it off the GUI thread."""
    request = urllib.request.Request(
        RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Plico/{__version__}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as reply:
            body = reply.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        text = QCoreApplication.translate("UpdateChecker", "GitHub ha risposto {0}.")
        raise UpdateError(text.format(error.code)) from error
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        text = QCoreApplication.translate("UpdateChecker", "GitHub non è raggiungibile ({0}).")
        raise UpdateError(text.format(reason)) from error
    if len(body) > MAX_BYTES:
        raise _invalid()
    try:
        data = json.loads(body)
    except ValueError as error:
        raise _invalid() from error
    return release_from_json(data)


class UpdateChecker(QObject):
    """One request at a time, in a thread of its own, answered by a signal.

    A daemon thread and not the global thread pool: closing the window waits
    for the pool (a compression must finish writing), and must not wait for
    GitHub to answer -- or not -- over a slow network.
    """

    #: the latest release, newer or not, and whether the user asked
    answered = Signal(object, bool)
    #: why GitHub could not be asked, and whether the user asked
    failed = Signal(str, bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = False
        # Connected first, so it runs before the window's slots: one of them
        # may start the next request.
        self.answered.connect(self._done)
        self.failed.connect(self._done)

    def is_running(self) -> bool:
        return self._running

    def start(self, manual: bool) -> bool:
        """Ask GitHub in the background; False if a request is already out."""
        if self._running:
            return False
        self._running = True
        threading.Thread(
            target=self._run, args=(manual,), name="plico-updates", daemon=True
        ).start()
        return True

    def _done(self, *_args: object) -> None:
        self._running = False

    def _run(self, manual: bool) -> None:
        try:
            release = fetch_latest()
        except Exception as error:  # noqa: BLE001
            # UpdateError, or anything unforeseen: a thread that dies silently
            # would leave the checker running for ever.
            self._emit(self.failed, str(error), manual)
        else:
            self._emit(self.answered, release, manual)

    @staticmethod
    def _emit(signal, *args: object) -> None:
        # The window may be gone by the time GitHub answers: nobody to tell.
        if QCoreApplication.instance() is None:
            return
        try:
            signal.emit(*args)
        except RuntimeError:
            pass
