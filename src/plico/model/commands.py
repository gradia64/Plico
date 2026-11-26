"""QUndoCommand subclasses for page-level operations.

The name a command shows in the Edit menu (and in QUndoView) is built with
``QCoreApplication.translate`` rather than ``self.tr``: the name has to exist
before ``super().__init__`` runs, and until then the QObject half of the
command is not there yet. The context is the class name, which is what
lupdate expects for a string that belongs to one class.
"""

import copy
import os
from dataclasses import replace

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QUndoCommand

from .annotate import Annotation, Color, FileAnnotation, FileAnnotationEdit
from .document import Bookmark, DocumentModel, PageItem, read_outline
from .ocr import OcrWord
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

    Undo takes the pages away but leaves the source REGISTERED, unused. A
    source id is part of every render key, and an id given back by an undo was
    handed to the next merge for a different file: its pages were then shown
    with the pixels of the file whose merge had been undone. Ids are never
    reused, so nothing keyed on one can answer for another file -- not even a
    render still on its way back from the worker.
    """

    def __init__(
        self,
        model: DocumentModel,
        source_id: int,
        path: str,
        items: list[PageItem],
        label: str | None = None,
    ) -> None:
        # *label* is what the user picked when that is not *path*: an image
        # merged through a temporary PDF should read «foto.jpg» in the Edit
        # menu, not the name of the temporary.
        name = QCoreApplication.translate("AppendDocument", "Unisci «{0}»")
        super().__init__(name.format(label or os.path.basename(path)))
        self._model = model
        self._source_id = source_id
        self._path = path
        self._items = items
        # The merged file's bookmarks follow it into the outline, after the
        # ones already there; undo puts the outline back as it was.
        self._bookmarks = read_outline(path, source_id, model.passwords.get(path))
        self._outline_before: list[Bookmark] = []

    def redo(self) -> None:
        sources = self._model.sources
        if self._source_id == len(sources):
            sources.append(self._path)
        else:
            # A redo after an undo: the source stayed registered (see above).
            assert sources[self._source_id] == self._path, (
                "a merge is redone against exactly the source it was read from"
            )
        self._model.pages.extend(self._items)
        self._outline_before = list(self._model.outline)
        self._model.outline = self._outline_before + self._bookmarks
        self._model.changed.emit()
        self._model.outline_changed.emit()

    def undo(self) -> None:
        count = len(self._items)
        del self._model.pages[len(self._model.pages) - count :]
        self._model.outline = list(self._outline_before)
        self._model.changed.emit()
        self._model.outline_changed.emit()


class DuplicatePage(QUndoCommand):
    """Put a copy of the page at *index* right after it.

    The copy is a second virtual page on the same source page, with its own
    copy of everything the user did to the first -- rotation, marks, form
    values, edits, OCR -- so changing one afterwards does not change the
    other. The save copies the source page once and places it twice (see
    assemble.py), which is what keeps its form fields.
    """

    def __init__(self, model: DocumentModel, index: int) -> None:
        name = QCoreApplication.translate("DuplicatePage", "Duplica pagina {0}")
        super().__init__(name.format(index + 1))
        self._model = model
        self._index = index
        self._copy = copy.deepcopy(model.pages[index])

    def redo(self) -> None:
        self._model.pages.insert(self._index + 1, self._copy)
        self._model.changed.emit()

    def undo(self) -> None:
        del self._model.pages[self._index + 1]
        self._model.changed.emit()


class InsertPage(QUndoCommand):
    """Insert the page *item*, read from the new source *path*, at *index*.

    A blank page is a page of its own small PDF, registered as a source like
    a merged file: the model has no other kind of page, and so the view, the
    worker and the save need nothing new. As with :class:`AppendDocument`,
    undo leaves the source registered: ids are never reused.
    """

    def __init__(
        self, model: DocumentModel, index: int, source_id: int, path: str, item: PageItem
    ) -> None:
        name = QCoreApplication.translate("InsertPage", "Inserisci pagina vuota {0}")
        super().__init__(name.format(index + 1))
        self._model = model
        self._index = index
        self._source_id = source_id
        self._path = path
        self._item = item

    def redo(self) -> None:
        sources = self._model.sources
        if self._source_id == len(sources):
            sources.append(self._path)
        else:
            assert sources[self._source_id] == self._path
        self._model.pages.insert(self._index, self._item)
        self._model.changed.emit()

    def undo(self) -> None:
        del self._model.pages[self._index]
        self._model.changed.emit()


class SetOutline(QUndoCommand):
    """Replace the outline: every edit of the bookmarks panel is one of these.

    The whole list, before and after, rather than one command per kind of
    edit: an outline is small, and add, rename, delete and move are then the
    same undo step with a different name.
    """

    def __init__(self, model: DocumentModel, outline: list[Bookmark], name: str) -> None:
        super().__init__(name)
        self._model = model
        self._before = list(model.outline)
        self._after = list(outline)

    def redo(self) -> None:
        self._model.outline = list(self._after)
        self._model.outline_changed.emit()

    def undo(self) -> None:
        self._model.outline = list(self._before)
        self._model.outline_changed.emit()


class AddAnnotation(QUndoCommand):
    """Put *annotation* on the page at *index* (written only when saving)."""

    def __init__(self, model: DocumentModel, index: int, annotation: Annotation) -> None:
        names = {
            "highlight": QCoreApplication.translate("AddAnnotation", "Evidenzia su pagina {0}"),
            "underline": QCoreApplication.translate("AddAnnotation", "Sottolinea su pagina {0}"),
            "strikeout": QCoreApplication.translate("AddAnnotation", "Barra su pagina {0}"),
            "note": QCoreApplication.translate("AddAnnotation", "Nota su pagina {0}"),
            "ink": QCoreApplication.translate("AddAnnotation", "Disegno su pagina {0}"),
        }
        super().__init__(names[annotation.kind].format(index + 1))
        self._model = model
        self._index = index
        self._annotation = annotation

    def redo(self) -> None:
        self._model.pages[self._index].annotations.append(self._annotation)
        self._model.page_changed.emit(self._index)

    def undo(self) -> None:
        self._model.pages[self._index].annotations.remove(self._annotation)
        self._model.page_changed.emit(self._index)


class RemoveAnnotation(QUndoCommand):
    """Take *annotation* back off the page at *index*."""

    def __init__(self, model: DocumentModel, index: int, annotation: Annotation) -> None:
        name = QCoreApplication.translate("RemoveAnnotation", "Togli annotazione su pagina {0}")
        super().__init__(name.format(index + 1))
        self._model = model
        self._index = index
        self._annotation = annotation
        # Back in the same place on undo: overlapping marks paint in order.
        self._position = model.pages[index].annotations.index(annotation)

    def redo(self) -> None:
        self._model.pages[self._index].annotations.pop(self._position)
        self._model.page_changed.emit(self._index)

    def undo(self) -> None:
        self._model.pages[self._index].annotations.insert(self._position, self._annotation)
        self._model.page_changed.emit(self._index)


class _FileAnnotationChange(QUndoCommand):
    """Change what happens to one of the file's annotations; undo puts back the old."""

    def __init__(
        self,
        name: str,
        model: DocumentModel,
        index: int,
        annotation: FileAnnotation,
        **change: object,
    ) -> None:
        super().__init__(name.format(index + 1))
        self._model = model
        self._index = index
        self._key = annotation.index
        self._before = model.pages[index].file_edit(annotation)
        self._after = replace(self._before, **change)  # type: ignore[arg-type]

    def _set(self, edit: FileAnnotationEdit) -> None:
        changes = self._model.pages[self._index].file_annotation_changes
        if edit.unchanged:
            changes.pop(self._key, None)
        else:
            changes[self._key] = edit
        self._model.page_changed.emit(self._index)

    def redo(self) -> None:
        self._set(self._after)

    def undo(self) -> None:
        self._set(self._before)


class RemoveFileAnnotation(_FileAnnotationChange):
    """Take one of the file's annotations off the page at *index*."""

    def __init__(self, model: DocumentModel, index: int, annotation: FileAnnotation) -> None:
        # The same name as RemoveAnnotation: to the user it is the same act.
        name = QCoreApplication.translate("RemoveAnnotation", "Togli annotazione su pagina {0}")
        super().__init__(name, model, index, annotation, removed=True)


class EditFileNote(_FileAnnotationChange):
    """Give a note or a FreeText of the file new words."""

    def __init__(self, model: DocumentModel, index: int, annotation: FileAnnotation, text: str) -> None:
        name = QCoreApplication.translate("EditNote", "Modifica nota su pagina {0}")
        super().__init__(name, model, index, annotation, text=text)


class RecolorFileAnnotation(_FileAnnotationChange):
    """Draw one of the file's annotations in another colour."""

    def __init__(
        self, model: DocumentModel, index: int, annotation: FileAnnotation, color: Color
    ) -> None:
        name = QCoreApplication.translate("RecolorAnnotation", "Colore dell'annotazione su pagina {0}")
        super().__init__(name, model, index, annotation, color=color)


class MoveFileAnnotation(_FileAnnotationChange):
    """Move one of the file's annotations by (*dx*, *dy*) page points."""

    def __init__(
        self, model: DocumentModel, index: int, annotation: FileAnnotation, dx: float, dy: float
    ) -> None:
        name = QCoreApplication.translate("MoveAnnotation", "Sposta annotazione su pagina {0}")
        ox, oy = model.pages[index].file_edit(annotation).offset
        super().__init__(name, model, index, annotation, offset=(ox + dx, oy + dy))


class _ReplaceAnnotation(QUndoCommand):
    """Put *after* where *before* is in the page's list, and back on undo."""

    def __init__(
        self, name: str, model: DocumentModel, index: int, before: Annotation, after: Annotation
    ) -> None:
        super().__init__(name.format(index + 1))
        self._model = model
        self._index = index
        self._before = before
        self._after = after
        self._position = model.pages[index].annotations.index(before)

    def redo(self) -> None:
        self._model.pages[self._index].annotations[self._position] = self._after
        self._model.page_changed.emit(self._index)

    def undo(self) -> None:
        self._model.pages[self._index].annotations[self._position] = self._before
        self._model.page_changed.emit(self._index)


class EditNote(_ReplaceAnnotation):
    """Give a note made in Plico new words, in the same place in the list."""

    def __init__(self, model: DocumentModel, index: int, note: Annotation, text: str) -> None:
        name = QCoreApplication.translate("EditNote", "Modifica nota su pagina {0}")
        super().__init__(name, model, index, note, replace(note, text=text))


class RecolorAnnotation(_ReplaceAnnotation):
    """Draw an annotation made in Plico in another colour."""

    def __init__(self, model: DocumentModel, index: int, annotation: Annotation, color: Color) -> None:
        name = QCoreApplication.translate("RecolorAnnotation", "Colore dell'annotazione su pagina {0}")
        super().__init__(name, model, index, annotation, replace(annotation, tint=color))


class MoveAnnotation(_ReplaceAnnotation):
    """Move an annotation made in Plico by (*dx*, *dy*) page points."""

    def __init__(
        self, model: DocumentModel, index: int, annotation: Annotation, dx: float, dy: float
    ) -> None:
        name = QCoreApplication.translate("MoveAnnotation", "Sposta annotazione su pagina {0}")
        super().__init__(name, model, index, annotation, annotation.moved(dx, dy))


class CropPages(QUndoCommand):
    """Set the visible part of some pages (Pagine → Ritaglia margini).

    *crops* gives, for each index, the new crop in page space or None for the
    whole page. One command for the whole dialog, however many pages: it was
    one decision.
    """

    def __init__(
        self,
        model: DocumentModel,
        indices: list[int],
        crops: list[RedactionRect | None],
    ) -> None:
        if len(indices) == 1:
            name = QCoreApplication.translate("CropPages", "Ritaglia pagina {0}").format(
                indices[0] + 1
            )
        else:
            name = QCoreApplication.translate("CropPages", "Ritaglia {0} pagine").format(
                len(indices)
            )
        super().__init__(name)
        self._model = model
        self._indices = list(indices)
        self._after = list(crops)
        self._before = [model.pages[i].crop for i in indices]

    def _set(self, crops: list[RedactionRect | None]) -> None:
        for index, crop in zip(self._indices, crops, strict=True):
            self._model.pages[index].crop = crop
            self._model.page_changed.emit(index)

    def redo(self) -> None:
        self._set(self._after)

    def undo(self) -> None:
        self._set(self._before)


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


class AdjustRedaction(QUndoCommand):
    """Move or resize a redaction already on the page at *index*.

    ``before`` and ``after`` are the same rectangle at the two ends of one
    gesture: the drag itself touches nothing, so a Ctrl+Z takes back the whole
    move and not the last mouse step of it.
    """

    def __init__(
        self,
        model: DocumentModel,
        index: int,
        position: int,
        before: RedactionRect,
        after: RedactionRect,
        moved: bool,
    ) -> None:
        # Two literal calls, not one with variables: lupdate only extracts
        # the strings it can read in the source.
        if moved:
            name = QCoreApplication.translate("MoveRedaction", "Sposta zona su pagina {0}")
        else:
            name = QCoreApplication.translate("ResizeRedaction", "Ridimensiona zona su pagina {0}")
        super().__init__(name.format(index + 1))
        self._model = model
        self._index = index
        self._position = position
        self._before = before
        self._after = after

    def redo(self) -> None:
        self._model.pages[self._index].redactions[self._position] = self._after
        self._model.page_changed.emit(self._index)

    def undo(self) -> None:
        self._model.pages[self._index].redactions[self._position] = self._before
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


class OcrPage(QUndoCommand):
    """Record the words OCR read on the page at *index*.

    Like a redaction or a text edit, nothing is written here: the words are
    state of the virtual page, and ``save.py`` turns them into the invisible
    text layer when the document is materialised. Recognising the page again
    replaces the reading, and the command keeps the previous one, so undo goes
    back to what the page read before -- including "nothing", which is also
    what a page that was never read carries.
    """

    _ID = 0x4F43

    def __init__(self, model: DocumentModel, index: int, words: list[OcrWord]) -> None:
        label = QCoreApplication.translate("OcrPage", "Riconosci testo su pagina {0}")
        super().__init__(label.format(index + 1))
        self._model = model
        self._index = index
        self._words = list(words)
        self._before: list[OcrWord] = []

    def id(self) -> int:
        return self._ID

    def redo(self) -> None:
        item = self._model.pages[self._index]
        # Read on every redo, not in __init__: after an undo the page holds the
        # older reading again, and that is the state redo must replace.
        self._before = list(item.ocr_words)
        item.ocr_words = list(self._words)
        self._model.page_changed.emit(self._index)

    def undo(self) -> None:
        self._model.pages[self._index].ocr_words = list(self._before)
        self._model.page_changed.emit(self._index)
