"""Where Plico keeps what the user chose, and under which names.

One QSettings file for everything -- window layout, zoom, trusted roots, and
the choices of the «Impostazioni» dialog -- read by the window and, for the
language, by ``app.main()`` before any window exists: a catalog must be loaded
before the first string is read.
"""

from PySide6.QtCore import QSettings

#: "auto" for the system's language, or one of :data:`plico.i18n.LANGUAGES`.
LANGUAGE = "interfaccia/lingua"
#: Whether an icon sits in the notification area (the tray).
TRAY_ICON = "tray/icona"
#: Whether the window's X hides it in the tray instead of quitting.
CLOSE_TO_TRAY = "tray/chiudi_nella_tray"

#: Whether Plico asks GitHub, once a day, if a newer version is out. Off by
#: default: Plico makes no request the user did not ask for.
CHECK_UPDATES = "aggiornamenti/controlla"
#: When GitHub was last asked (seconds since the epoch), answered or not.
UPDATES_LAST = "aggiornamenti/ultimo_controllo"
#: The newer version the last check found, so the menu offers it at once.
UPDATES_FOUND = "aggiornamenti/versione_trovata"
#: The version the toast already announced: once per version, not per start.
UPDATES_ANNOUNCED = "aggiornamenti/versione_annunciata"

AUTOMATIC = "auto"


def store() -> QSettings:
    """The settings file. Explicit org/app: no reliance on global QApplication state."""
    return QSettings("Plico", "plico")


def flag(settings: QSettings, key: str, default: bool = False) -> bool:
    """A boolean setting, whatever form the INI backend hands it back in.

    QSettings returns the string "true" for a bool written on an earlier run,
    and ``bool("false")`` is True.
    """
    value = settings.value(key, default)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def language(settings: QSettings) -> str:
    """The language chosen in the dialog, or :data:`AUTOMATIC`."""
    value = settings.value(LANGUAGE, AUTOMATIC)
    return value if isinstance(value, str) and value else AUTOMATIC
