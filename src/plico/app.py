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
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())