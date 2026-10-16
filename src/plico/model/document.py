"""Document model: a list of virtual pages over one or more immutable PDFs.

The model never writes to a PDF. It holds a list of *virtual pages*, each of
which points at a page of a source document, and the only state it adds is
what the user changed about that page: the rotation offset and the regions to
redact. Every other feature (undo/redo, rendering, saving, splitting) is
derived from that list.

An encrypted source is unlocked *before* anything reads a page from it, and
the password is kept for the session: the same file is opened again by the
worker (to render) and by the save (to copy the pages), and neither has a
chance to ask the user. See :func:`open_for_reading`.
"""

import os
from dataclasses import dataclass, field

import pymupdf
from PySide6.QtCore import QObject, Signal

from .forms import Field, read_fields
from .redact import (
    Matrix,
    RedactionRect,
    derotation_matrix,
    rotation_matrix,
    unrotated_size,
)
from .textedit import TextEdit, TextSpan, span_at


class PasswordRequired(Exception):
    """A PDF is encrypted and the password given was missing or wrong.

    ``wrong`` tells the two cases apart: both send the user to the same
    prompt, but only the second one has something to apologise for.
    """

    def __init__(self, path: str, wrong: bool = False) -> None:
        super().__init__(path)
        self.path = path
        self.wrong = wrong


def open_for_reading(path: str, password: str | None = None) -> pymupdf.Document:
    """Open *path* read-only, unlocking it BEFORE anything reads a page.

    The order is the whole point, and it is not a stylistic one. On a locked
    document the first page access raises ("document closed or encrypted"),
    and the failed access leaves the handle unable to decrypt its content
    streams afterwards: measured, a later ``authenticate("segreta")`` reports
    success and ``get_text()`` comes back empty, with MuPDF printing "aes
    padding out of range". A handle that cannot be unlocked here is closed and
    never handed out, so nobody can inherit that state.

    ``needs_pass`` is the question "is this file encrypted?", not "is it still
    locked?" -- it stays true after a successful authenticate. A file whose
    *user* password is empty opens without a prompt, which is the common case
    for a document that only carries an owner password.
    """
    doc = pymupdf.open(path)
    if doc.needs_pass and (password is None or doc.authenticate(password) == 0):
        doc.close()
        raise PasswordRequired(path, wrong=password is not None)
    return doc


@dataclass
class PageItem:
    """A virtual page entry — does NOT modify the source PDF.

    ``source_id`` indexes :attr:`DocumentModel.sources`, which makes merging
    a second PDF just a matter of appending pages that point somewhere else:
    no page is ever copied, rewritten or materialised.

    The oriented size lives here, on the item, and not in a list parallel to
    :attr:`DocumentModel.pages`: a parallel list has to be kept in sync by
    every structural command, and the one that forgets desynchronises the
    layout from the document. A page that carries its own size cannot drift.
    """

    source_index: int     # position in its own source document
    base_rotation: int    # /Rotate as stored in the original (0/90/180/270)
    rotation: int = 0     # user-supplied rotation offset
    source_id: int = 0    # index into DocumentModel.sources
    # Oriented size in points, with the base /Rotate ALREADY applied: it comes
    # from ``page.rect``, which MuPDF has rotated for us. Only the user offset
    # still has to be composed on top of these numbers.
    width_pt: float = 0.0
    height_pt: float = 0.0
    # Regions to blank out, in PAGE space (unrotated PDF points) -- not in
    # screen coordinates. A redaction marks a region of the *document*: kept
    # on screen it would rotate away from the words it was drawn over, and
    # the next save would blacken the wrong paragraph.
    redactions: list[RedactionRect] = field(default_factory=list)
    # The form fields the SOURCE page offers, read once when the document is
    # opened. A field is an annotation, not content: it belongs to the source,
    # so it is described here instead of being re-read on every repaint.
    form_fields: list[Field] = field(default_factory=list)
    # What the user typed into those fields, by field name. Only the fields
    # that were actually touched appear: an absent name means "leave whatever
    # the file already had", which is NOT the same as an empty value -- clearing
    # a field on purpose is a change, and it has to survive the save.
    form_values: dict[str, str] = field(default_factory=dict)
    # Text replacements, at most one per span of the SOURCE page. The spans
    # are captured from the source when the user picks them, so they stay
    # valid whatever else happens to the virtual page.
    text_edits: list[TextEdit] = field(default_factory=list)

    def edit_for(self, span: TextSpan) -> TextEdit | None:
        """The planned replacement of *span*, if there is one."""
        return next((edit for edit in self.text_edits if edit.span == span), None)

    def text_of(self, span: TextSpan) -> str:
        """What *span* reads now: the replacement, or the source's own text."""
        edit = self.edit_for(span)
        return span.text if edit is None else edit.new_text

    @property
    def total_rotation(self) -> int:
        """Composite rotation that gets written to the output PDF."""
        return (self.base_rotation + self.rotation) % 360

    @property
    def unrotated_size(self) -> tuple[float, float]:
        """Page size with the base /Rotate undone.

        ``width_pt``/``height_pt`` are already oriented by the page's own
        /Rotate, so for the odd quarter-turns the two are the other way
        round. This is the size a redaction rectangle lives in.
        """
        return unrotated_size(self.width_pt, self.height_pt, self.base_rotation)

    def view_matrix(self) -> Matrix:
        """Map page space to what is on screen, user rotation included."""
        width, height = self.unrotated_size
        return rotation_matrix(width, height, self.total_rotation)

    def page_matrix(self) -> Matrix:
        """The inverse of :meth:`view_matrix`: from the screen to the page."""
        width, height = self.unrotated_size
        return derotation_matrix(width, height, self.total_rotation)


def _not_already_marked(
    item: PageItem, rects: list[RedactionRect]
) -> list[RedactionRect]:
    """Drop the occurrences that a redaction on this page already covers.

    Searching twice for the same word must not stack two rectangles on the
    same spot: the user would then have to undo the page one command at a
    time, and the second mark would hide the first.
    """

    def marked(rect: RedactionRect) -> bool:
        return any(
            mark.x0 <= rect.x0
            and mark.y0 <= rect.y0
            and rect.x1 <= mark.x1
            and rect.y1 <= mark.y1
            for mark in item.redactions
        )

    return [rect for rect in rects if not marked(rect)]


class DocumentModel(QObject):
    """Holds the virtual page list; the real PDF is never mutated until save."""

    changed = Signal()
    page_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.pages: list[PageItem] = []
        self.sources: list[str] = []
        self.path: str | None = None
        # path -> password, only for the files that needed one. Session
        # scoped, and deliberately NOT cleared when another document is
        # opened: re-opening the same protected file must not ask again.
        self.passwords: dict[str, str] = {}

    @property
    def page_sizes(self) -> list[tuple[float, float]]:
        """Oriented page sizes, derived from :attr:`pages`.

        Read-only on purpose. This used to be a list filled alongside
        ``pages``, and every command that mutated one without the other
        (``DeletePage``, ``MovePage``) silently desynchronised the layout:
        pages moved, sizes stayed. Deriving it makes the alignment an
        invariant of the data structure instead of a discipline every future
        command has to remember.
        """
        return [(item.width_pt, item.height_pt) for item in self.pages]

    def _items_for(
        self, source_id: int, path: str, password: str | None = None
    ) -> list[PageItem]:
        """Read *path* read-only and describe it as virtual pages."""
        items: list[PageItem] = []
        with open_for_reading(path, password) as doc:
            # A document with no form at all does not earn a per-page widget
            # scan, and this is a document-level property.
            has_form = bool(doc.is_form_pdf)
            for i in range(doc.page_count):
                # The page must stay alive in a local: a widget keeps a weak
                # reference to the page it came from, so ``read_fields(doc[i])``
                # would hand back fields that can never be written.
                page = doc[i]
                items.append(
                    PageItem(
                        source_index=i,
                        base_rotation=page.rotation,
                        source_id=source_id,
                        # page.rect already includes the base /Rotate, so these
                        # are the oriented dimensions the view must lay out with.
                        width_pt=page.rect.width,
                        height_pt=page.rect.height,
                        form_fields=read_fields(page) if has_form else [],
                    )
                )
        return items

    def read_source(
        self, source_id: int, path: str, password: str | None = None
    ) -> list[PageItem]:
        """Describe *path* as virtual pages, without touching the model.

        The caller gets the pages first and decides afterwards: a merge can
        find out that the file brings no page *before* it becomes an undo
        step, and a file that refuses to open leaves the document untouched.

        Remembers *password* on success. The same file is opened again by the
        worker (to render it) and by the save (to copy the pages), and neither
        of them has anybody to ask.
        """
        items = self._items_for(source_id, path, password)
        if password is not None:
            self.passwords[path] = password
        return items

    def open(self, path: str, password: str | None = None) -> None:
        """Open *path* read-only, replacing the virtual page list entirely.

        Raises :class:`PasswordRequired` when the file is encrypted and the
        password is missing or wrong. Nothing is written before that point, so
        a document that refuses to open leaves the model exactly as it was.
        """
        self.set_pages(self.read_source(0, path, password), path)

    def set_pages(self, items: list[PageItem], path: str) -> None:
        """Install *items* as the whole document, without opening anything.

        The counterpart of :meth:`read_source`, for a caller that has to look
        at the pages before committing to them: the window reads the new file
        first and resets its views only afterwards, so a password that never
        arrives cannot leave it showing an empty page 1.
        """
        self.pages = list(items)
        self.sources = [path]
        self.path = path
        self.changed.emit()

    def append_document(self, path: str, password: str | None = None) -> int:
        """Merge: append every page of *path* after the current ones.

        Returns the number of pages added. The new source is registered only
        after it has been read successfully, so a corrupt file leaves the
        model exactly as it was.
        """
        items = self.read_source(len(self.sources), path, password)
        if not items:
            return 0
        self.sources.append(path)
        self.pages.extend(items)
        self.changed.emit()
        return len(items)

    def source_for(self, item: PageItem) -> str:
        """Path of the document that *item* points into."""
        return self.sources[item.source_id]

    def sources_at(self, path: str) -> list[str]:
        """The sources that *path* is the same file as, compared by inode.

        Writing to one of them invalidates every page that points into it:
        the file is replaced by the materialised document, so its page
        numbers and its /Rotate values are no longer those the items were
        read with. Comparing by inode and not by string catches another
        spelling of the same path and hard links alike.
        """
        if not os.path.exists(path):
            return []
        found: list[str] = []
        for source in self.sources:
            try:
                if os.path.exists(source) and os.path.samefile(path, source):
                    found.append(source)
            except OSError:
                continue
        return found

    def find_text(self, text: str) -> dict[int, list[RedactionRect]]:
        """Every occurrence of *text*, as redaction rectangles by page index.

        ``Page.search_for`` answers in the page's UNROTATED space, which is
        exactly the space a redaction is stored in, so the rectangles are used
        as they come -- the same reason the drawing tool hands them over
        untouched. The sources are opened read-only, one handle each, and
        closed again: searching is a read, and the model owns nothing.
        """
        if not text:
            return {}
        handles: dict[int, pymupdf.Document] = {}
        found: dict[int, list[RedactionRect]] = {}
        try:
            for index, item in enumerate(self.pages):
                doc = handles.get(item.source_id)
                if doc is None:
                    source = self.sources[item.source_id]
                    doc = open_for_reading(source, self.passwords.get(source))
                    handles[item.source_id] = doc
                # Bound to a local on purpose: a widget-like object read from a
                # temporary page would be collected with it.
                page = doc[item.source_index]
                width, height = item.unrotated_size
                rects = [
                    RedactionRect.from_corners(r.x0, r.y0, r.x1, r.y1).clamped_to(
                        width, height
                    )
                    for r in page.search_for(text)
                ]
                if fresh := _not_already_marked(item, rects):
                    found[index] = fresh
        finally:
            for doc in handles.values():
                doc.close()
        return found

    def text_span_at(self, index: int, x: float, y: float) -> TextSpan | None:
        """The span of the SOURCE page under the page-space point (*x*, *y*).

        Always the source, never what the user has already typed: a span
        edited before is found again as itself, so ``PageItem.edit_for()``
        recognises it and the second edit replaces the first. Opened and
        closed on the spot, like :meth:`find_text`: the model owns no handle.
        """
        item = self.pages[index]
        source = self.sources[item.source_id]
        with open_for_reading(source, self.passwords.get(source)) as doc:
            # Bound to a local: get_text() on a temporary page is fine, but the
            # habit costs nothing and keeps one rule for every page access.
            page = doc[item.source_index]
            return span_at(page, x, y)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def close(self) -> None:
        self.pages.clear()
        self.sources.clear()
        self.passwords.clear()
        self.path = None
        self.changed.emit()
