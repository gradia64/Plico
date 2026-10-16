"""QUndoCommand subclasses for page-level operations."""

from PySide6.QtGui import QUndoCommand

from .document import DocumentModel, PageItem
from .redact import RedactionRect


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


class AddRedaction(QUndoCommand):
    """Mark a region of the page at *index* for redaction.

    Nothing is burned into the PDF here: the rectangle is state of the
    virtual page, and it only becomes a real redaction when the document is
    materialised on save. That is what makes it undoable -- applying it
    eagerly would rewrite the source page's content streams, and no undo
    stack can put those back.
    """

    def __init__(self, model: DocumentModel, index: int, rect: RedactionRect) -> None:
        super().__init__(f"Redazione su pagina {index + 1}")
        self._model = model
        self._index = index
        self._rect = rect

    def redo(self) -> None:
        self._model.pages[self._index].redactions.append(self._rect)
        self._model.page_changed.emit(self._index)

    def undo(self) -> None:
        # remove() matches by value; RedactionRect is frozen and comparable,
        # so this finds the rectangle the command pushed and not a twin that
        # happens to sit elsewhere in the list.
        self._model.pages[self._index].redactions.remove(self._rect)
        self._model.page_changed.emit(self._index)


class RemoveRedaction(QUndoCommand):
    """Take back the redaction *rect* from the page at *index*."""

    def __init__(self, model: DocumentModel, index: int, rect: RedactionRect) -> None:
        super().__init__(f"Annulla redazione su pagina {index + 1}")
        self._model = model
        self._index = index
        self._rect = rect
        # Remember where it was, so undo puts it back in the same position
        # (overlapping rectangles are painted in order).
        self._position = model.pages[index].redactions.index(rect)

    def redo(self) -> None:
        self._model.pages[self._index].redactions.pop(self._position)
        self._model.page_changed.emit(self._index)

    def undo(self) -> None:
        self._model.pages[self._index].redactions.insert(self._position, self._rect)
        self._model.page_changed.emit(self._index)


class SetFieldValue(QUndoCommand):
    """Write *value* into the form field *name* of the page at *index*.

    Like a redaction, this touches nothing on disk: it records what the user
    typed, and ``save.py`` writes it into the widget when the document is
    materialised. Only the fields that were touched end up in
    ``PageItem.form_values``, so "leave the file's value alone" and "the user
    emptied this field" stay distinguishable.
    """

    # Any non-zero id tells Qt the command may be merged; mergeWith decides.
    _ID = 0x504C

    def __init__(
        self, model: DocumentModel, index: int, name: str, value: str
    ) -> None:
        super().__init__(f"Campo «{name}» su pagina {index + 1}")
        self._model = model
        self._index = index
        self._name = name
        self._new = value
        self._was_set = name in model.pages[index].form_values
        self._old = model.pages[index].form_values.get(name, "")

    def id(self) -> int:
        return self._ID

    def mergeWith(self, other: QUndoCommand) -> bool:
        """Fold a later edit of the SAME field into this command.

        A QLineEdit emits one signal per keystroke: without merging, typing a
        ten-character value would cost ten Ctrl+Z presses to take back. The
        original value is kept from the first command, so the merged entry
        still undoes the whole field in one step.
        """
        if not isinstance(other, SetFieldValue):
            return False
        if other._index != self._index or other._name != self._name:
            return False
        self._new = other._new
        return True

    def redo(self) -> None:
        self._model.pages[self._index].form_values[self._name] = self._new
        self._model.page_changed.emit(self._index)

    def undo(self) -> None:
        valori = self._model.pages[self._index].form_values
        if self._was_set:
            valori[self._name] = self._old
        else:
            # The field had no entry before this command: drop it again, so
            # that "untouched" does not become "set to the file's own value".
            valori.pop(self._name, None)
        self._model.page_changed.emit(self._index)