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
