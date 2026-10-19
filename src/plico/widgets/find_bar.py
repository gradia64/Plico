"""The search bar: Ctrl+F, the way every reader and editor does it.

The README promised that a recognised scan could be searched with Ctrl+F, and
there was no Ctrl+F to press (reported by a review). The bar is the view part
only: it says what the user typed and which way they want to go, and shows the
"n of m" the window hands back. The searching itself is
:meth:`DocumentModel.find_text`, the same one *Cancella parola* uses -- so it
finds the words of an OCR run before they are saved, as the README says.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget

# Long enough not to search on every letter of a word typed at speed, short
# enough to feel immediate: the search reads every page of every source.
DELAY_MS = 250


class _Field(QLineEdit):
    """The text field: Enter goes forward, Shift+Enter back, Esc closes."""

    def __init__(self, bar: FindBar) -> None:
        super().__init__(bar)
        self._bar = bar

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._bar.previous_requested.emit()
            else:
                self._bar.next_requested.emit()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._bar.close_bar()
            return
        super().keyPressEvent(event)


class FindBar(QWidget):
    """A row under the page: the text, the count, back, forward, close."""

    # The text to look for, once the typing has paused; "" clears the hits.
    search_requested = Signal(str)
    next_requested = Signal()
    previous_requested = Signal()
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._field = _Field(self)
        self._field.setPlaceholderText(self.tr("Trova nel documento"))
        self._field.setClearButtonEnabled(True)
        self._count = QLabel()
        self._count.setMinimumWidth(120)

        self._previous = self._button("go-up", self.tr("Occorrenza precedente (Maiusc+F3)"))
        self._previous.clicked.connect(lambda: self.previous_requested.emit())
        self._next = self._button("go-down", self.tr("Occorrenza successiva (F3)"))
        self._next.clicked.connect(lambda: self.next_requested.emit())
        close = self._button("window-close", self.tr("Chiudi la ricerca (Esc)"))
        close.clicked.connect(lambda: self.close_bar())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(QLabel(self.tr("Trova:")))
        layout.addWidget(self._field, 1)
        layout.addWidget(self._previous)
        layout.addWidget(self._next)
        layout.addWidget(self._count)
        layout.addWidget(close)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DELAY_MS)
        self._timer.timeout.connect(lambda: self.search_requested.emit(self.text()))
        self._field.textChanged.connect(self._timer.start)
        self.set_count(0, 0)
        self.hide()

    def _button(self, icon_name: str, tip: str) -> QToolButton:
        button = QToolButton(self)
        icon = QIcon.fromTheme(icon_name)
        if icon.isNull():
            # No theme: an arrow or a cross still says what the button does.
            button.setText({"go-up": "▲", "go-down": "▼"}.get(icon_name, "✕"))
        else:
            button.setIcon(icon)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setAutoRaise(True)
        return button

    def text(self) -> str:
        return self._field.text().strip()

    def open_bar(self) -> None:
        """Show the bar with the field ready: the text already there selected."""
        self.show()
        self._field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._field.selectAll()
        if self.text():
            # Reopened on a word: search again, the document may have changed.
            self._timer.start()

    def close_bar(self) -> None:
        if self.isHidden():
            return
        self._timer.stop()
        self.hide()
        self.closed.emit()

    def refresh(self) -> None:
        """Search again, if there is a search: the document has changed."""
        if not self.isHidden() and self.text():
            self._timer.start()

    def has_focus(self) -> bool:
        return self._field.hasFocus()

    def set_count(self, current: int, total: int) -> None:
        """Show "current of total" (1-based), or that there is nothing."""
        has_hits = total > 0
        self._previous.setEnabled(has_hits)
        self._next.setEnabled(has_hits)
        if not self.text():
            self._count.setText("")
        elif has_hits:
            self._count.setText(self.tr("{0} di {1}").format(current, total))
        else:
            self._count.setText(self.tr("Nessun risultato"))
