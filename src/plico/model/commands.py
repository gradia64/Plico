"""QUndoCommand subclasses for page-level operations."""

from PySide6.QtGui import QUndoCommand

from .document import DocumentModel, PageItem


class RotatePage(QUndoCommand):
    """Rotate a single page by *delta* degrees (90-steps)."""

    def __init__(self, model: DocumentModel, index: int, delta: int) -> None:
        super().__init__(f"Ruota pagina {index + 1}")
        self._model = model
        self._index = index
        old = model.pages[index].rotation
        self._old = old
        self._new = (old + delta) % 360

    def redo(self) -> None:
        self._model.pages[self._index].rotation = self._new
        self._model.page_changed.emit(self._index)

    def undo(self) -> None:
        self._model.pages[self._index].rotation = self._old
        self._model.page_changed.emit(self._index)


class DeletePage(QUndoCommand):
    """Delete the page at *index*; restore it on undo."""

    def __init__(self, model: DocumentModel, index: int) -> None:
        super().__init__(f"Elimina pagina {index + 1}")
        self._model = model
        self._index = index
        self._item: PageItem | None = None

    def redo(self) -> None:
        if self._item is None:
            self._item = self._model.pages.pop(self._index)
        else:
            # Redo after an undo: undo() put the item back at _index, so
            # deleting it again is just another pop. (The previous version
            # inserted and popped at the same index, which is a no-op: redo
            # after undo silently did nothing.)
            self._model.pages.pop(self._index)
        self._model.changed.emit()

    def undo(self) -> None:
        assert self._item is not None
        self._model.pages.insert(self._index, self._item)
        self._model.changed.emit()


class MovePage(QUndoCommand):
    """Move a page from *from_index* to *to_index*."""

    def __init__(
        self, model: DocumentModel, from_index: int, to_index: int
    ) -> None:
        super().__init__(
            f"Sposta pagina {from_index + 1}"
        )
        self._model = model
        self._from = from_index
        self._to = to_index

    def redo(self) -> None:
        item = self._model.pages.pop(self._from)
        self._model.pages.insert(self._to, item)
        self._model.changed.emit()

    def undo(self) -> None:
        item = self._model.pages.pop(self._to)
        self._model.pages.insert(self._from, item)
        self._model.changed.emit()