"""«Impostazioni»: the language, the tray icon, and what the window's X does.

The choices are the ones OllaDesk offers: a language that follows the system
unless one is picked (English when the system's has no catalog), an icon in
the notification area, and an X that hides the window there instead of
quitting. Offscreen there is no notification area, so the tests that need one
pretend there is.
"""

import pytest
from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon

from plico import i18n, preferences
from plico.main_window import MainWindow
from plico.widgets.settings_dialog import Choices, SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def tray_available(monkeypatch, qapp):
    """A desktop with a notification area, and the app's quit policy put back."""
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    before = qapp.quitOnLastWindowClosed()
    quits: list[int] = []
    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: quits.append(1)))
    yield quits
    qapp.setQuitOnLastWindowClosed(before)


@pytest.fixture
def window(qapp):
    created: list[MainWindow] = []

    def factory(**settings) -> MainWindow:
        # The same INI the window will read (tests/conftest.py redirects it).
        store = MainWindow._settings(None)  # type: ignore[arg-type]
        for key, value in settings.items():
            store.setValue(key, value)
        store.sync()
        mw = MainWindow()
        created.append(mw)
        return mw

    yield factory
    for mw in created:
        mw._really_quit = True
        mw.shutdown_worker()
        mw.deleteLater()
    qapp.processEvents()


# -- the language ----------------------------------------------------------- #


def test_a_chosen_language_is_a_locale_and_auto_is_the_system():
    assert i18n.chosen_locale("fr").language() == QLocale.Language.French
    assert i18n.chosen_locale(preferences.AUTOMATIC) is None
    assert i18n.chosen_locale("xx") is None, "un codice sconosciuto vale «automatica»"
    assert i18n.chosen_locale(None) is None


def test_italian_chosen_on_any_system_loads_no_catalog(qapp):
    """The source language needs nothing, even with an English system."""
    assert i18n.install_translators(qapp, i18n.chosen_locale("it")) == []


def test_a_stored_flag_reads_back_as_a_bool():
    store = MainWindow._settings(None)  # type: ignore[arg-type]
    store.setValue("prova/sì", "true")
    store.setValue("prova/no", "false")
    assert preferences.flag(store, "prova/sì") is True
    assert preferences.flag(store, "prova/no") is False
    assert preferences.flag(store, "prova/mai-scritta") is False


# -- the dialog ------------------------------------------------------------- #


def test_the_dialog_offers_automatic_and_every_language(qapp):
    dialog = SettingsDialog(Choices("de", tray_icon=False, close_to_tray=False))
    combo = dialog._language
    assert [combo.itemData(i) for i in range(combo.count())] == [
        preferences.AUTOMATIC, "it", "en", "fr", "de", "es"
    ]
    assert combo.currentData() == "de"
    assert combo.itemText(combo.findData("de")) == "Deutsch"
    dialog.deleteLater()


def test_close_to_tray_needs_the_icon(qapp, tray_available):
    dialog = SettingsDialog(Choices(preferences.AUTOMATIC, tray_icon=True, close_to_tray=True))
    assert dialog._close_to_tray.isEnabled()

    dialog._tray_icon.setChecked(False)

    assert not dialog._close_to_tray.isEnabled()
    assert dialog.choices() == Choices(preferences.AUTOMATIC, False, False)
    dialog.deleteLater()


def test_without_a_notification_area_the_tray_cannot_be_chosen(qapp, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))
    dialog = SettingsDialog(Choices(preferences.AUTOMATIC, False, False))
    assert not dialog._tray_icon.isEnabled()
    assert not dialog._close_to_tray.isEnabled()
    dialog.deleteLater()


def test_ok_saves_the_choices_and_says_when_the_language_applies(
    window, tray_available, monkeypatch
):
    mw = window()
    told: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a: told.append(a[2])))
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(SettingsDialog, "choices", lambda self: Choices("es", True, True))

    mw._open_settings()

    assert mw._choices() == Choices("es", True, True)
    assert mw._tray is not None, "l'icona compare subito, senza riavviare"
    assert told == ["La nuova lingua sarà usata al prossimo avvio di Plico."]


# -- the tray --------------------------------------------------------------- #


def test_without_the_tray_the_x_quits_as_always(window, qapp):
    mw = window()
    assert mw._tray is None
    assert qapp.quitOnLastWindowClosed()


def test_with_close_to_tray_the_x_only_hides(window, tray_available):
    mw = window(**{preferences.TRAY_ICON: True, preferences.CLOSE_TO_TRAY: True})
    mw.show()

    mw.close()

    assert not mw.isVisible()
    assert mw._thread.isRunning(), "Plico resta attivo"
    assert tray_available == [], "nascondere non esce"
    assert not QApplication.instance().quitOnLastWindowClosed()


def test_the_icon_alone_leaves_the_x_quitting(window, tray_available):
    mw = window(**{preferences.TRAY_ICON: True, preferences.CLOSE_TO_TRAY: False})
    mw.show()

    mw.close()
    QApplication.processEvents()  # the quit is deferred by one turn of the loop

    assert not mw._thread.isRunning()
    assert tray_available == [1], "con l'icona l'uscita passa da closeEvent"


def test_esci_quits_even_from_the_tray(window, tray_available):
    mw = window(**{preferences.TRAY_ICON: True, preferences.CLOSE_TO_TRAY: True})
    mw.show()
    mw.close()  # hidden in the tray

    mw._quit()
    QApplication.processEvents()

    assert not mw._thread.isRunning()
    assert tray_available == [1]


def test_a_refused_quit_leaves_close_to_tray_working(window, tray_available, monkeypatch):
    """Esci, then «Annulla» on unsaved changes: the next X hides again."""
    mw = window(**{preferences.TRAY_ICON: True, preferences.CLOSE_TO_TRAY: True})
    mw.show()
    monkeypatch.setattr(mw, "_confirm_discard", lambda: False)

    mw._quit()
    assert mw.isVisible() and not mw._really_quit

    mw.close()
    assert not mw.isVisible()
    assert mw._thread.isRunning()


def test_turning_the_tray_off_brings_a_hidden_window_back(window, tray_available):
    mw = window(**{preferences.TRAY_ICON: True, preferences.CLOSE_TO_TRAY: True})
    mw.show()
    mw.close()
    store = mw._settings()
    store.setValue(preferences.TRAY_ICON, False)

    mw._sync_tray()

    assert mw._tray is None
    assert mw.isVisible(), "senza icona non ci sarebbe più modo di raggiungerla"
