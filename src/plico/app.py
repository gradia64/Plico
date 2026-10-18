"""Entry point — creates QApplication and MainWindow."""

import sys

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from .i18n import install_qt_translator, install_translators
from .main_window import MainWindow
from .model import is_image

#: The application id: the name of the .desktop file, of the Flatpak and of the
#: AppStream component. Told to Qt so that Wayland matches the window to its
#: launcher -- without it the compositor sees «plico», finds no plico.desktop,
#: and the dock shows a generic icon for the running window.
APP_ID = "io.github.gradia64.plico"


def local_path(argument: str) -> str:
    """A command-line argument as a path PyMuPDF can open.

    The desktop entry asks for paths (``%F``), but a launcher may still hand
    over ``file:///home/…/a%20b.pdf`` -- GIO does for ``%U``, and so do
    scripts and other entries -- and ``pymupdf.open`` takes that for a file
    name that does not exist. A URL that is not a local file stays as it is,
    so the error names what the user gave.
    """
    if argument.startswith("file:"):
        url = QUrl(argument)
        if url.isLocalFile():
            return url.toLocalFile()
    return argument


def open_arguments(window: MainWindow, paths: list[str]) -> None:
    """Open the first file and append the others, as "Unisci" would.

    A first argument that is a photo or a scan starts a document from it,
    exactly like *File → Crea da immagini*: opened as it was, MuPDF would
    read it as an image document and the first save would fail on it.
    The others can be images too, which "Unisci" already converts.
    """
    if not paths:
        return
    first = paths[0]
    opened = window.create_from_images([first]) if is_image(first) else window.open_path(first)
    if opened:
        for extra in paths[1:]:
            window.merge_path(extra)


def main() -> int:
    # Set on the class: these are application-wide statics and they must be
    # in place before QSettings or any window is created.
    QApplication.setOrganizationName("Plico")
    QApplication.setApplicationName("plico")
    QApplication.setApplicationDisplayName("Plico")
    QApplication.setDesktopFileName(APP_ID)

    app = QApplication.instance() or QApplication(sys.argv)
    # Before the first window: the strings are read while it is built.
    install_qt_translator(app)
    install_translators(app)
    window = MainWindow()
    window.show()

    # Desktop integration: the .desktop file declares ``Exec=plico %F``, so
    # the document the user double-clicked arrives as an argument. Qt strips
    # its own options from ``QApplication.arguments()``, leaving the file
    # names; several of them mean "open the first, append the rest", which is
    # exactly what "Unisci" does.
    open_arguments(window, [local_path(argument) for argument in app.arguments()[1:]])

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
