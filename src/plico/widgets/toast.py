"""A short message over the page, for the outcome of an action.

The status bar is where Plico has always said what happened, and it stays the
record. But it is a line of grey text at the bottom edge, far from where the
user is looking: an OCR run that finished, or a redaction that will only take
effect at the next save, went by unnoticed there. The toast says the same thing
where the eyes are, for a few seconds, and then gets out of the way.

It never takes focus and never asks anything: a question belongs in a dialog.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QLabel, QWidget

# Long enough to read two lines without hurrying, short enough not to linger
# over the page once the user has moved on.
DURATION_MS = 4500
MARGIN = 24


class Toast(QLabel):
    """A rounded label floating at the bottom centre of its parent."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("plico-toast")
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # The tooltip colours of the current theme: the look the desktop
        # already uses for "a short note about what just happened".
        palette = self.palette()
        background = palette.color(QPalette.ColorRole.ToolTipBase)
        foreground = palette.color(QPalette.ColorRole.ToolTipText)
        self.setStyleSheet(
            f"#plico-toast {{ background: {background.name()}; color: {foreground.name()};"
            f" border: 1px solid {foreground.name()}; border-radius: 8px; padding: 10px 16px; }}"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        parent.installEventFilter(self)

    def show_message(self, text: str, duration_ms: int = DURATION_MS) -> None:
        """Show *text*; a new message replaces the one on screen."""
        self.setText(text)
        self.setAccessibleName(text)
        self._place()
        self.raise_()
        self.show()
        self._timer.start(duration_ms)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.parent() and event.type() == QEvent.Type.Resize and self.isVisible():
            self._place()
        return False

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        width = min(520, max(160, parent.width() - 2 * MARGIN))
        self.setFixedWidth(width)
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - MARGIN
        self.move(max(0, x), max(0, y))
