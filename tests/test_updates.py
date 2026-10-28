"""The notice of a newer Plico: where it is offered, what is asked, what is said.

No test reaches the network: ``conftest.py`` puts a network that is down in
place of :func:`plico.updates.fetch_latest`, and the tests that need an answer
put their own. The real function is kept here, imported before the fixture
replaces it, and tried against a fake ``urlopen``.
"""

import io
import json
import threading
import time
import urllib.error
from pathlib import Path

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from plico import __version__, preferences, updates
from plico.main_window import MainWindow
from plico.updates import Channel, Release, UpdateError
from plico.updates import fetch_latest as real_fetch_latest
from plico.widgets.settings_dialog import Choices, SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _pump(condition, seconds: float = 5.0) -> None:
    app = QApplication.instance()
    end = time.monotonic() + seconds
    while not condition() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def _next(version: str = __version__) -> str:
    major, minor, patch = (updates.parse_version(version) or (0, 0, 0))[:3]
    return f"{major}.{minor}.{patch + 1}"


# -- where it comes from ----------------------------------------------------- #


def test_where_plico_comes_from(tmp_path):
    missing = tmp_path / "no-flatpak-info"
    checkout = tmp_path / "plico" / "src" / "plico"
    assert updates.channel({}, checkout, missing) is Channel.PYTHON
    assert updates.channel({}, Path("/opt/plico/usr/share/plico/plico"), missing) is Channel.DEB
    assert updates.channel({}, Path("/usr/share/plico/plico"), missing) is Channel.SYSTEM
    info = tmp_path / ".flatpak-info"
    info.write_text("[Application]\n")
    assert updates.channel({}, Path("/app/lib/python3.13/site-packages/plico"), info) is (
        Channel.FLATPAK
    )


def test_the_appimage_is_not_taken_for_the_aur(tmp_path):
    """Its package is under <mount>/usr/share/plico: the variable decides first."""
    mounted = Path("/tmp/.mount_PlicoX/usr/share/plico/plico")
    env = {"APPIMAGE": "/home/u/Plico-0.1.5-x86_64.AppImage"}
    assert updates.channel(env, mounted, tmp_path / "none") is Channel.APPIMAGE


def test_the_daily_check_is_only_where_nothing_else_updates_plico():
    assert {c for c in Channel if updates.automatic_allowed(c)} == {
        Channel.APPIMAGE, Channel.DEB, Channel.PYTHON
    }
    assert not updates.can_fetch(Channel.FLATPAK), "la sandbox non ha la rete"
    assert updates.can_fetch(Channel.SYSTEM)


# -- versions and the answer -------------------------------------------------- #


def test_versions_compare_as_numbers():
    assert updates.parse_version("v0.1.6") == (0, 1, 6)
    assert updates.is_newer("0.1.10", "0.1.9")
    assert updates.is_newer("v0.2", "0.1.5")
    assert not updates.is_newer("0.1.5", "0.1.5")
    assert not updates.is_newer("0.1.5.0", "0.1.5")
    assert not updates.is_newer("0.1.4", "0.1.5")
    assert updates.parse_version("0.2.0rc1") is None
    assert not updates.is_newer("latest", "0.1.5")


def test_at_most_one_request_a_day():
    now = 1_000_000.0
    assert updates.due(None, now)
    assert not updates.due(now - 60, now)
    assert updates.due(now - updates.INTERVAL_S, now)
    assert updates.due(now + 3600, now), "un orologio tornato indietro non blocca per sempre"


def test_the_page_is_built_here_not_taken_from_the_answer():
    release = updates.release_from_json(
        {"tag_name": "v0.1.6", "html_url": "https://example.com/evil", "draft": False}
    )
    assert release == Release("0.1.6", "https://github.com/gradia64/Plico/releases/tag/v0.1.6")


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"tag_name": "nightly"},
        {"tag_name": "v0.2.0", "prerelease": True},
        {"tag_name": "v0.2.0", "draft": True},
        {"tag_name": 2},
    ],
)
def test_an_unusable_answer_is_an_error(data):
    with pytest.raises(UpdateError):
        updates.release_from_json(data)


class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetching_asks_github_with_plico_as_user_agent(monkeypatch):
    seen = {}

    def urlopen(request, timeout, context):
        seen["url"] = request.full_url
        seen["agent"] = request.get_header("User-agent")
        seen["timeout"] = timeout
        return _Reply(json.dumps({"tag_name": "v9.0.0"}).encode())

    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)

    assert real_fetch_latest() == Release("9.0.0", updates.release_page("9.0.0"))
    assert seen == {
        "url": "https://api.github.com/repos/gradia64/Plico/releases/latest",
        "agent": f"Plico/{__version__}",
        "timeout": updates.TIMEOUT_S,
    }


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.URLError("Name or service not known"),
        urllib.error.HTTPError(updates.RELEASES_API, 403, "rate limited", {}, None),  # type: ignore[arg-type]
        TimeoutError("timed out"),
    ],
)
def test_no_network_is_an_update_error(monkeypatch, failure):
    def urlopen(request, timeout, context):
        raise failure

    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
    with pytest.raises(UpdateError):
        real_fetch_latest()


@pytest.mark.parametrize("body", [b"<html>captive portal</html>", b" " * (updates.MAX_BYTES + 1)])
def test_an_answer_that_is_not_githubs_is_an_update_error(monkeypatch, body):
    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda *a, **k: _Reply(body))
    with pytest.raises(UpdateError):
        real_fetch_latest()


# -- the checker -------------------------------------------------------------- #


def test_the_checker_answers_in_the_gui_thread_one_request_at_a_time(qapp, monkeypatch):
    release_it = threading.Event()
    calls: list[str] = []

    def fetch(timeout: float = updates.TIMEOUT_S) -> Release:
        calls.append(threading.current_thread().name)
        release_it.wait(5)
        return Release("9.0.0", updates.release_page("9.0.0"))

    monkeypatch.setattr(updates, "fetch_latest", fetch)
    checker = updates.UpdateChecker()
    answers: list[tuple[Release, bool, bool]] = []
    checker.answered.connect(
        lambda release, manual: answers.append(
            (release, manual, threading.current_thread() is threading.main_thread())
        )
    )

    assert checker.start(manual=True)
    assert not checker.start(manual=False), "una richiesta alla volta"
    release_it.set()
    _pump(lambda: answers)

    assert answers == [(Release("9.0.0", updates.release_page("9.0.0")), True, True)]
    assert calls == ["plico-updates"]
    assert not checker.is_running()
    assert checker.start(manual=False), "finita la prima, se ne può fare un'altra"
    _pump(lambda: len(answers) == 2)


def test_a_failure_is_reported_and_frees_the_checker(qapp):
    checker = updates.UpdateChecker()
    failures: list[tuple[str, bool]] = []
    checker.failed.connect(lambda reason, manual: failures.append((reason, manual)))
    checker.start(manual=False)  # conftest: the network is down
    _pump(lambda: failures)
    assert failures == [("network disabled in the tests", False)]
    assert not checker.is_running()


# -- the window --------------------------------------------------------------- #


@pytest.fixture
def window(qapp):
    created: list[MainWindow] = []

    def factory(source: Channel = Channel.PYTHON, **settings) -> MainWindow:
        store = MainWindow._settings(None)  # type: ignore[arg-type]
        for key, value in settings.items():
            store.setValue(key, value)
        store.sync()
        mw = MainWindow()
        mw._update_source = source
        created.append(mw)
        return mw

    yield factory
    for mw in created:
        _pump(lambda mw=mw: not mw._update_checker.is_running())
        mw.shutdown_worker()
        mw.deleteLater()
    qapp.processEvents()


@pytest.fixture
def github(monkeypatch):
    """GitHub's answer, and the count of requests."""
    state = {"latest": _next(), "requests": 0}

    def fetch(timeout: float = updates.TIMEOUT_S) -> Release:
        state["requests"] += 1
        return Release(state["latest"], updates.release_page(state["latest"]))

    monkeypatch.setattr(updates, "fetch_latest", fetch)
    return state


@pytest.fixture
def opened(monkeypatch):
    urls: list[str] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", staticmethod(lambda url: urls.append(url.toString()) or True)
    )
    return urls


def _check(mw: MainWindow) -> None:
    mw._maybe_check_updates()
    _pump(lambda: not mw._update_checker.is_running())
    QApplication.processEvents()


def test_off_by_default_nothing_is_asked(window, github):
    mw = window()
    assert not mw._choices().check_updates
    _check(mw)
    assert github["requests"] == 0
    assert mw._settings().value(preferences.UPDATES_LAST) is None


def test_a_newer_version_is_announced_once_and_stays_in_the_menu(window, github, opened):
    mw = window(**{preferences.CHECK_UPDATES: True})
    toasts: list[str] = []
    mw._toast.show_message = lambda text, *a: toasts.append(text)  # type: ignore[method-assign]

    _check(mw)

    new = github["latest"]
    assert github["requests"] == 1
    assert toasts == [f"È disponibile Plico {new}: Aiuto → Scarica Plico {new}."]
    assert mw._download_act.isVisible()
    assert mw._download_act.text() == f"&Scarica Plico {new}…"
    mw._download_act.trigger()
    assert opened == [f"https://github.com/gradia64/Plico/releases/tag/v{new}"]

    # The next day, the same version: the menu still offers it, no new toast.
    mw._settings().setValue(preferences.UPDATES_LAST, time.time() - updates.INTERVAL_S)
    _check(mw)
    assert github["requests"] == 2
    assert len(toasts) == 1


def test_one_request_a_day_even_when_it_failed(window, github, monkeypatch):
    mw = window(**{preferences.CHECK_UPDATES: True})
    warnings: list[object] = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a)))
    monkeypatch.setattr(updates, "fetch_latest", _offline_counting(github))

    _check(mw)
    _check(mw)

    assert github["requests"] == 1, "il secondo controllo aspetta domani"
    assert warnings == [], "senza rete il controllo automatico tace"
    assert not mw._download_act.isVisible()


def _offline_counting(state):
    def fetch(timeout: float = updates.TIMEOUT_S) -> Release:
        state["requests"] += 1
        raise UpdateError("offline")

    return fetch


@pytest.mark.parametrize("source", [Channel.SYSTEM, Channel.FLATPAK])
def test_no_daily_check_where_something_else_updates_plico(window, github, source):
    mw = window(source, **{preferences.CHECK_UPDATES: True})
    _check(mw)
    assert github["requests"] == 0
    assert not mw._choices().check_updates


def test_the_found_version_is_offered_at_the_next_start_without_asking(window, github):
    newer = window(**{preferences.UPDATES_FOUND: _next()})
    assert newer._download_act.isVisible()
    # Updated since: the version found is this one, or older.
    current = window(**{preferences.UPDATES_FOUND: __version__})
    assert not current._download_act.isVisible()
    assert github["requests"] == 0


def test_asking_by_hand_says_up_to_date_and_offers_the_daily_check(
    window, github, monkeypatch, opened
):
    github["latest"] = __version__
    mw = window(**{preferences.UPDATES_FOUND: _next()})
    shown: list[str] = []

    def answer(box):
        shown.append(box.text())
        box.checkBox().setChecked(True)
        return 0

    monkeypatch.setattr(QMessageBox, "exec", answer)
    mw._check_updates()
    _pump(lambda: shown)

    assert shown == [f"Plico {__version__} è la versione più recente."]
    assert mw._choices().check_updates, "la casella accende il controllo giornaliero"
    assert not mw._download_act.isVisible(), "una versione trovata prima non vale più"
    assert opened == []


def test_asking_by_hand_opens_the_page_of_the_newer_version(window, github, monkeypatch, opened):
    mw = window(**{preferences.CHECK_UPDATES: True})
    shown: list[str] = []

    def answer(box):
        shown.append(box.text())
        assert box.checkBox() is None, "il controllo giornaliero è già acceso"
        box.buttons()[0].click()  # «Apri la pagina»
        return 0

    monkeypatch.setattr(QMessageBox, "exec", answer)
    mw._check_updates()
    _pump(lambda: shown)

    new = github["latest"]
    assert shown == [f"È disponibile Plico {new} (questo è {__version__})."]
    assert opened == [updates.release_page(new)]


def test_asking_by_hand_without_network_says_so(window, monkeypatch):
    mw = window()
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: warnings.append(a[2])))
    mw._check_updates()
    _pump(lambda: warnings)
    assert warnings == [
        "Non è stato possibile controllare gli aggiornamenti.\nnetwork disabled in the tests"
    ]


def test_the_flatpak_opens_the_releases_page_and_asks_nothing(
    window, github, monkeypatch, opened
):
    mw = window(Channel.FLATPAK)
    shown: list[str] = []

    def answer(box):
        shown.append(box.text())
        box.buttons()[0].click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", answer)
    mw._check_updates()

    assert github["requests"] == 0
    assert __version__ in shown[0]
    assert opened == ["https://github.com/gradia64/Plico/releases"]


def test_turning_it_on_in_the_settings_checks_at_once(window, github, monkeypatch):
    mw = window()
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: 1)
    monkeypatch.setattr(
        SettingsDialog, "choices", lambda self: Choices("auto", False, False, check_updates=True)
    )
    mw._open_settings()
    _pump(lambda: github["requests"])
    assert github["requests"] == 1
    assert mw._choices().check_updates


# -- the dialog --------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("source", "offered"),
    [(Channel.APPIMAGE, True), (Channel.DEB, True), (Channel.PYTHON, True),
     (Channel.SYSTEM, False), (Channel.FLATPAK, False)],
)
def test_the_dialog_offers_the_daily_check_where_it_makes_sense(qapp, source, offered):
    dialog = SettingsDialog(Choices("auto", False, False, check_updates=True), None, source)
    assert dialog._check_updates.isEnabled() is offered
    assert dialog.choices().check_updates is offered
    dialog.deleteLater()
