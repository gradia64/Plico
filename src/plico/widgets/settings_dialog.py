"""«Impostazioni»: the language, the icon in the notification area, updates.

Few choices on purpose, the same ones OllaDesk offers in the same words, so
that the two applications of the same author behave alike: a language follows
the system unless the user picks one, and the tray is an opt-in that can make
the window's X hide Plico instead of quitting it. The daily check for a new
version is an opt-in too, offered only where no package manager updates Plico
(see :mod:`plico.updates`).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import i18n, preferences, updates


@dataclass(frozen=True)
class Choices:
    """What the dialog collects; the window decides what each one changes."""

    language: str
    tray_icon: bool
    close_to_tray: bool
    check_updates: bool = False


class SettingsDialog(QDialog):
    """Language, tray and updates, with the current choices filled in."""

    def __init__(
        self,
        current: Choices,
        parent: QWidget | None = None,
        source: updates.Channel = updates.Channel.PYTHON,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Impostazioni"))

        self._language = QComboBox()
        self._language.addItem(self.tr("Automatica (lingua del sistema)"), preferences.AUTOMATIC)
        for code, name in i18n.LANGUAGES.items():
            self._language.addItem(name, code)
        index = self._language.findData(current.language)
        self._language.setCurrentIndex(max(0, index))
        self._language.setToolTip(self.tr("La nuova lingua vale dal prossimo avvio di Plico"))
        language_note = QLabel(
            self.tr(
                "Se la lingua del sistema non è tra queste, Plico usa l'inglese. "
                "La scelta vale dal prossimo avvio."
            )
        )
        language_note.setWordWrap(True)

        language_box = QGroupBox(self.tr("Lingua"))
        language_form = QFormLayout(language_box)
        language_form.addRow(self.tr("Lingua dell'interfaccia:"), self._language)
        language_form.addRow(language_note)

        self._tray_icon = QCheckBox(self.tr("Mostra l'icona nell'area di notifica"))
        self._tray_icon.setChecked(current.tray_icon)
        self._close_to_tray = QCheckBox(
            self.tr("Chiudendo la finestra, riducila nell'area di notifica invece di uscire")
        )
        self._close_to_tray.setChecked(current.close_to_tray)
        self._close_to_tray.setToolTip(
            self.tr(
                "La X nasconde la finestra e Plico resta attivo: clic sull'icona per "
                "riaprirla, «Esci» dal menu dell'icona o Ctrl+Q per chiudere davvero."
            )
        )
        # Hiding in a tray that is not shown would leave no way back to the
        # window but starting Plico again.
        self._tray_icon.toggled.connect(self._close_to_tray.setEnabled)
        self._close_to_tray.setEnabled(current.tray_icon)

        tray_box = QGroupBox(self.tr("Area di notifica"))
        tray_layout = QVBoxLayout(tray_box)
        tray_layout.addWidget(self._tray_icon)
        tray_layout.addWidget(self._close_to_tray)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray_icon.setEnabled(False)
            self._close_to_tray.setEnabled(False)
            missing = QLabel(self.tr("Questo desktop non offre un'area di notifica."))
            missing.setWordWrap(True)
            tray_layout.addWidget(missing)

        self._check_updates = QCheckBox(
            self.tr("Controlla una volta al giorno se c'è una nuova versione")
        )
        self._check_updates.setChecked(current.check_updates)
        updates_box = QGroupBox(self.tr("Aggiornamenti"))
        updates_layout = QVBoxLayout(updates_box)
        updates_layout.addWidget(self._check_updates)
        if updates.automatic_allowed(source):
            note = self.tr(
                "Plico chiede a GitHub il numero dell'ultima versione e non invia "
                "nient'altro. Finché la casella è vuota, non si collega a niente."
            )
        else:
            self._check_updates.setChecked(False)
            self._check_updates.setEnabled(False)
            if source is updates.Channel.FLATPAK:
                note = self.tr(
                    "Questo pacchetto Flatpak non ha accesso alla rete: «Aiuto → "
                    "Cerca aggiornamenti…» apre la pagina delle versioni."
                )
            else:
                note = self.tr(
                    "Plico è installato dal gestore dei pacchetti del sistema, che lo "
                    "tiene aggiornato."
                )
        updates_note = QLabel(note)
        updates_note.setWordWrap(True)
        updates_layout.addWidget(updates_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(language_box)
        layout.addWidget(tray_box)
        layout.addWidget(updates_box)
        layout.addWidget(buttons)

    def choices(self) -> Choices:
        """What the user set; close-to-tray only counts with the icon shown."""
        tray_icon = self._tray_icon.isChecked()
        return Choices(
            language=str(self._language.currentData() or preferences.AUTOMATIC),
            tray_icon=tray_icon,
            close_to_tray=tray_icon and self._close_to_tray.isChecked(),
            check_updates=self._check_updates.isEnabled() and self._check_updates.isChecked(),
        )
