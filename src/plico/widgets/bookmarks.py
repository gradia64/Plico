"""The «Segnalibri» panel: the document's outline, to read and to edit.

The panel never changes the model itself: every edit is handed to the window
as the outline it would produce (``edited``), and the window pushes it as a
``SetOutline`` command, so Ctrl+Z takes it back like any other change.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMenu,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..model import outline as ops
from ..model.document import Bookmark, DocumentModel

_INDEX = Qt.ItemDataRole.UserRole
_SYMBOLS = {
    "add": "+", "rename": "✎", "up": "↑", "down": "↓",
    "outdent": "←", "indent": "→", "remove": "✕",
}


class BookmarkPanel(QWidget):
    """A tree of the bookmarks, with buttons to add, rename, move and delete.

    *current_page* tells the panel which page a new bookmark is for.
    """

    # The outline after an edit, and the name of the edit for the undo stack.
    edited = Signal(list, str)
    # A bookmark was chosen: show the page at this position.
    go_to = Signal(int)

    def __init__(
        self, model: DocumentModel, current_page: Callable[[], int], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._current_page = current_page
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context_menu)
        self._tree.itemClicked.connect(self._chosen)
        self._tree.itemActivated.connect(self._chosen)
        self._tree.currentItemChanged.connect(lambda *_: self._update_buttons())

        self._buttons: dict[str, QToolButton] = {}
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        move = self.tr("Sposta segnalibro")
        level = self.tr("Cambia livello del segnalibro")
        for key, icon, text, slot in (
            ("add", "bookmark-new", self.tr("Aggiungi un segnalibro per la pagina corrente"),
             self.add),
            ("rename", "edit-rename", self.tr("Rinomina"), self.rename),
            ("up", "go-up", self.tr("Sposta su"), lambda: self._apply(ops.move_up, move)),
            ("down", "go-down", self.tr("Sposta giù"), lambda: self._apply(ops.move_down, move)),
            ("outdent", "format-indent-less", self.tr("Livello superiore"),
             lambda: self._apply(ops.outdent, level)),
            ("indent", "format-indent-more", self.tr("Livello inferiore"),
             lambda: self._apply(ops.indent, level)),
            ("remove", "edit-delete", self.tr("Elimina"), self.remove),
        ):
            button = QToolButton()
            button.setToolTip(text)
            button.setAccessibleName(text)
            themed = QIcon.fromTheme(icon)
            if themed.isNull():
                # No icon theme (a bare desktop, the AppImage elsewhere): a
                # symbol keeps the row narrow, the tooltip says the rest.
                button.setText(_SYMBOLS[key])
            else:
                button.setIcon(themed)
            button.clicked.connect(slot)
            row.addWidget(button)
            self._buttons[key] = button
        row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self._tree)

        model.outline_changed.connect(self.refresh)
        # A page deleted or moved changes what a bookmark points at.
        model.changed.connect(self.refresh)
        self.refresh()

    # -- reading ----------------------------------------------------------- #

    def _positions(self) -> list[int | None]:
        """Where each bookmark's page is now (None: deleted)."""
        where: dict[tuple[int, int], int] = {}
        for position, item in enumerate(self._model.pages):
            where.setdefault((item.source_id, item.source_index), position)
        return [where.get((b.source_id, b.source_index)) for b in self._model.outline]

    def refresh(self) -> None:
        """Rebuild the tree from the model, keeping the entry that was current."""
        current = self.current_index()
        self._tree.clear()
        positions = self._positions()
        parents: list[tuple[int, QTreeWidgetItem]] = []
        chosen: QTreeWidgetItem | None = None
        for index, bookmark in enumerate(self._model.outline):
            while parents and parents[-1][0] >= bookmark.level:
                parents.pop()
            item = QTreeWidgetItem([bookmark.title])
            item.setData(0, _INDEX, index)
            position = positions[index]
            if position is None:
                item.setForeground(0, self.palette().placeholderText())
                item.setToolTip(0, self.tr("La pagina di questo segnalibro è stata eliminata"))
            else:
                item.setToolTip(0, self.tr("Pagina {0}").format(position + 1))
            if parents:
                parents[-1][1].addChild(item)
            else:
                self._tree.addTopLevelItem(item)
            parents.append((bookmark.level, item))
            if index == current:
                chosen = item
        self._tree.expandAll()
        if chosen is not None:
            self._tree.setCurrentItem(chosen)
        self._update_buttons()

    def current_index(self) -> int | None:
        item = self._tree.currentItem()
        return None if item is None else int(item.data(0, _INDEX))

    def select(self, index: int) -> None:
        """Make the bookmark at *index* the current one (for the window and tests)."""
        every = Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive
        for item in self._tree.findItems("", every):
            if int(item.data(0, _INDEX)) == index:
                self._tree.setCurrentItem(item)
                return

    def _update_buttons(self) -> None:
        index = self.current_index()
        outline = self._model.outline
        has_document = bool(self._model.pages)
        self._buttons["add"].setEnabled(has_document)
        for key in ("rename", "remove"):
            self._buttons[key].setEnabled(index is not None)
        for key, op in (
            ("up", ops.move_up),
            ("down", ops.move_down),
            ("indent", ops.indent),
            ("outdent", ops.outdent),
        ):
            self._buttons[key].setEnabled(index is not None and op(outline, index) is not None)

    def _chosen(self, item: QTreeWidgetItem) -> None:
        position = self._positions()[int(item.data(0, _INDEX))]
        if position is not None:
            self.go_to.emit(position)

    def _context_menu(self, point) -> None:
        menu = QMenu(self)
        for key in ("add", "rename", "up", "down", "outdent", "indent", "remove"):
            button = self._buttons[key]
            action = menu.addAction(button.icon(), button.toolTip())  # full text
            action.setEnabled(button.isEnabled())
            action.triggered.connect(button.click)
        menu.exec(self._tree.viewport().mapToGlobal(point))

    # -- editing ----------------------------------------------------------- #

    def _ask_title(self, title: str, text: str) -> str | None:
        name, accepted = QInputDialog.getText(
            self, title, self.tr("Titolo del segnalibro:"), QLineEdit.EchoMode.Normal, text
        )
        name = name.strip()
        return name if accepted and name else None

    def add(self) -> None:
        page = self._current_page()
        if not 0 <= page < len(self._model.pages):
            return
        suggested = self.tr("Pagina {0}").format(page + 1)
        name = self._ask_title(self.tr("Aggiungi segnalibro"), suggested)
        if name is None:
            return
        item = self._model.pages[page]
        outline = self._model.outline
        point = ops.insertion_point(outline, self._positions(), page)
        new = ops.add(outline, point, Bookmark(1, name, item.source_id, item.source_index))
        self.edited.emit(new, self.tr("Aggiungi segnalibro «{0}»").format(name))
        self.select(point)

    def rename(self) -> None:
        index = self.current_index()
        if index is None:
            return
        old = self._model.outline[index].title
        name = self._ask_title(self.tr("Rinomina segnalibro"), old)
        if name is None or name == old:
            return
        self.edited.emit(
            ops.rename(self._model.outline, index, name),
            self.tr("Rinomina segnalibro «{0}»").format(name),
        )

    def remove(self) -> None:
        index = self.current_index()
        if index is None:
            return
        title = self._model.outline[index].title
        self.edited.emit(
            ops.remove(self._model.outline, index),
            self.tr("Elimina segnalibro «{0}»").format(title),
        )

    def _apply(self, op: Callable[[list[Bookmark], int], list[Bookmark] | None], name: str) -> None:
        index = self.current_index()
        if index is None:
            return
        result = op(self._model.outline, index)
        if result is None:
            return
        moved = self._model.outline[index]
        self.edited.emit(result, name)
        # Keep the moved entry current: find it by identity in the new list.
        for position, bookmark in enumerate(self._model.outline):
            if (bookmark.title, bookmark.source_id, bookmark.source_index) == (
                moved.title, moved.source_id, moved.source_index
            ):
                self.select(position)
                break
