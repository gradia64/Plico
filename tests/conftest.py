"""Fixtures every test file shares."""

import pytest


@pytest.fixture(autouse=True)
def _deferred_deletes_are_delivered():
    """Really destroy what a test handed to ``deleteLater()``.

    ``deleteLater()`` only posts a DeferredDelete, and ``processEvents()``
    outside an event loop never delivers it: the windows of every earlier test
    stayed alive, timers included. Five seconds after its creation a window
    runs the update check against the settings of whichever test is running
    then -- and the settings are each test's own INI, so a window left over
    from a test that never asked for a check could make a request in one that
    counts them. Autouse and outermost, so it runs after the test's own
    fixtures have shut their windows down.
    """
    yield
    from PySide6.QtCore import QCoreApplication, QEvent

    if QCoreApplication.instance() is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(autouse=True)
def _burn_without_asking(monkeypatch):
    """Answer «Elimina e salva» to the confirmation before redactions are burnt.

    The question is a modal dialog, and a modal dialog offscreen waits forever.
    The tests that are about the question replace the answer themselves.
    """
    from plico.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_ask_to_burn", lambda self, text: True)


@pytest.fixture(autouse=True)
def _private_settings(monkeypatch, tmp_path):
    """Every window reads and writes a throwaway INI, never ~/.config/Plico.

    Without it the suite started with the developer's zoom and geometry, and a
    window closed by a test wrote them back (reported by a review). The test
    about settings redirects them itself, to a file it can reopen.
    """
    from PySide6.QtCore import QSettings

    from plico.main_window import MainWindow

    ini = str(tmp_path / "plico-test.ini")
    monkeypatch.setattr(
        MainWindow, "_settings", lambda self: QSettings(ini, QSettings.Format.IniFormat)
    )


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No test asks GitHub: the update checks get a network that is down.

    The tests about the checks put their own answer in its place.
    """
    from plico import updates

    def offline(timeout: float = updates.TIMEOUT_S) -> updates.Release:
        raise updates.UpdateError("network disabled in the tests")

    monkeypatch.setattr(updates, "fetch_latest", offline)
