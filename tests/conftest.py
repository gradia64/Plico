"""Fixtures every test file shares."""

import pytest


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
