"""Entry point — creates QApplication and MainWindow."""

import sys

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from .i18n import install_translators
from .main_window import MainWindow


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


def main() -> int:
    # Set on the class: these are application-wide statics and they must be
    # in place before QSettings or any window is created.
    QApplication.setOrganizationName("Plico")
    QApplication.setApplicationName("plico")
    QApplication.setApplicationDisplayName("Plico")

    app = QApplication.instance() or QApplication(sys.argv)
    # Before the first window: the strings are read while it is built.
    install_translators(app)
    window = MainWindow()
    window.show()

    # Desktop integration: the .desktop file declares ``Exec=plico %F``, so
    # the document the user double-clicked arrives as an argument. Qt strips
    # its own options from ``QApplication.arguments()``, leaving the file
    # names; several of them mean "open the first, append the rest", which is
    # exactly what "Unisci" does.
    paths = [local_path(argument) for argument in app.arguments()[1:]]
    if paths and window.open_path(paths[0]):
        for extra in paths[1:]:
            window.merge_path(extra)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
