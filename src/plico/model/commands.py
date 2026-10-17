"""QUndoCommand subclasses for page-level operations.

The name a command shows in the Edit menu (and in QUndoView) is built with
``QCoreApplication.translate`` rather than ``self.tr``: the name has to exist
before ``super().__init__`` runs, and until then the QObject half of the
command is not there yet. The context is the class name, which is what
lupdate expects for a string that belongs to one class.
"""

import os

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QUndoCommand

from .document import DocumentModel, PageItem
from .redact import RedactionRect
from .textedit import TextEdit, TextSpan


class RotatePage(QUndoCommand):
    """Rotate a single page by *delta* degrees (90-steps)."""

    def __init__(self, model: DocumentModel, index: int, delta: int) -> None:
        name = QCoreApplication.translate("RotatePage", "Ruota pagina {0}")
        super().__init__(name.format(index + 1))
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
        name = QCoreApplication.translate("DeletePage", "Elimina pagina {0}")
        super().__init__(name.format(index + 1))
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
        name = QCoreApplication.translate("MovePage", "Sposta pagina {0}")
        super().__init__(name.format(from_index + 1))
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


class AppendDocument(QUndoCommand):
    """Merge: append the pages of another document after the current ones.

    The pages are read *before* the command is constructed, and handed over
    as ``items``: that is what lets a file that brings no page -- or that
    refuses to open -- leave the document untouched instead of parking an
    empty step on the undo stack. Reading them once also means ``redo`` never
    goes back to a file the user may have changed in the meantime, and it is
    why the source is registered here rather than by the model.
    """

    def __init__(
        self, model: DocumentModel, source_id: int, path: str, items: list[PageItem]
    ) -> None:
        name = QCoreApplication.translate("AppendDocument", "Unisci «{0}»")
        super().__init__(name.format(os.path.basename(path)))
        self._model = model
        self._source_id = source_id
        self._path = path
        self._items = items

    def redo(self) -> None:
        assert self._source_id == len(self._model.sources), (
            "the undo stack is LIFO: a merge can only be redone on top of "
            "exactly the sources it was read against"
        )
        self._model.sources.append(self._path)
        self._model.pages.extend(self._items)
        self._model.changed.emit()

    def undo(self) -> None:
        count = len(self._items)
        del self._model.pages[len(self._model.pages) - count :]
        self._model.sources.pop()
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
        name = QCoreApplication.translate("AddRedaction", "Cancella zona su pagina {0}")
        super().__init__(name.format(index + 1))
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
        name = QCoreApplication.translate("RemoveRedaction", "Ripristina zona su pagina {0}")
        super().__init__(name.format(index + 1))
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
        label = QCoreApplication.translate("SetFieldValue", "Campo «{0}» su pagina {1}")
        super().__init__(label.format(name, index + 1))
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
        values = self._model.pages[self._index].form_values
        if self._was_set:
            values[self._name] = self._old
        else:
            # The field had no entry before this command: drop it again, so
            # that "untouched" does not become "set to the file's own value".
            values.pop(self._name, None)
        self._model.page_changed.emit(self._index)

class EditText(QUndoCommand):
    """Replace the text of *span* on the page at *index* with *new_text*.

    Like a redaction, this only records the intent: ``save.py`` removes the
    old words and writes the new ones when the document is materialised.

    The command remembers what the span read *before* it -- nothing, or an
    earlier replacement -- and undo goes back to exactly that, so editing
    the same words twice and undoing once returns to the first edit, not to
    the original. Typing the original text back removes the edit altogether:
    "unchanged" must not linger as a replacement that rewrites the span with
    itself (and re-embeds a font) on every save.
    """

    _ID = 0x5445

    def __init__(
        self, model: DocumentModel, index: int, span: TextSpan, new_text: str
    ) -> None:
        label = QCoreApplication.translate("EditText", "Modifica testo su pagina {0}")
        super().__init__(label.format(index + 1))
        self._model = model
        self._index = index
        self._span = span
        item = model.pages[index]
        self._before = item.edit_for(span)
        # Where the edit sits (or will sit) in the list: a replacement keeps
        # its place, so undo/redo never reorders the edits of a page.
        self._position = (
            item.text_edits.index(self._before)
            if self._before is not None
            else len(item.text_edits)
        )
        self._after = self._state(new_text)

    def _state(self, new_text: str) -> TextEdit | None:
        return None if new_text == self._span.text else TextEdit(self._span, new_text)

    def _install(self, state: TextEdit | None) -> None:
        edits = self._model.pages[self._index].text_edits
        current = next(
            (i for i, edit in enumerate(edits) if edit.span == self._span), None
        )
        if current is not None:
            del edits[current]
        if state is not None:
            edits.insert(min(self._position, len(edits)), state)
        self._model.page_changed.emit(self._index)

    def id(self) -> int:
        return self._ID

    def mergeWith(self, other: QUndoCommand) -> bool:
        """Fold a later edit of the SAME span into this one.

        Confirming the same words twice in a row is one correction, not two
        steps. When the merged result is what the span read before this
        command, the command is marked obsolete and Qt drops it from the
        stack: an undo step that changes nothing is noise.
        """
        if not isinstance(other, EditText):
            return False
        if other._index != self._index or other._span != self._span:
            return False
        self._after = other._after
        self.setObsolete(self._after == self._before)
        return True

    def redo(self) -> None:
        self._install(self._after)
        # Pushing a "change" to what the span already reads is not a step.
        self.setObsolete(self._after == self._before)

    def undo(self) -> None:
        self._install(self._before)
