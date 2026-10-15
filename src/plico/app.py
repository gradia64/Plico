"""Entry point — creates QApplication and MainWindow."""

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main() -> int:
    # Set on the class: these are application-wide statics and they must be
    # in place before QSettings or any window is created.
    QApplication.setOrganizationName("Plico")
    QApplication.setApplicationName("plico")
    QApplication.setApplicationDisplayName("Plico")

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()

    # Desktop integration: the .desktop file declares ``Exec=plico %U``, so
    # the document the user double-clicked arrives as an argument. Qt strips
    # its own options from ``QApplication.arguments()``, leaving the file
    # names; several of them mean "open the first, append the rest", which is
    # exactly what "Unisci" does.
    paths = app.arguments()[1:]
    if paths and window.open_path(paths[0]):
        for extra in paths[1:]:
            window.merge_path(extra)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
