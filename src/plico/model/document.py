"""Document model: a list of virtual pages over one or more immutable PDFs.

The model never writes to a PDF. It holds a list of *virtual pages*, each of
which points at a page of a source document, and the only state it adds is
what the user changed about that page: the rotation offset and the regions to
redact. Every other feature (undo/redo, rendering, saving, splitting) is
derived from that list.
"""

from dataclasses import dataclass, field

import fitz
from PySide6.QtCore import QObject, Signal

from .forms import Field, read_fields
from .redact import (
    Matrix,
    RedactionRect,
    derotation_matrix,
    rotation_matrix,
    unrotated_size,
)


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

    def coperto(rect: RedactionRect) -> bool:
        return any(
            mark.x0 <= rect.x0
            and mark.y0 <= rect.y0
            and rect.x1 <= mark.x1
            and rect.y1 <= mark.y1
            for mark in item.redactions
        )

    return [rect for rect in rects if not coperto(rect)]


class DocumentModel(QObject):
    """Holds the virtual page list; the real PDF is never mutated until save."""

    changed = Signal()
    page_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.pages: list[PageItem] = []
        self.sources: list[str] = []
        self.path: str | None = None

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

    def _items_for(self, source_id: int, path: str) -> list[PageItem]:
        """Read *path* read-only and describe it as virtual pages."""
        items: list[PageItem] = []
        with fitz.open(path) as doc:
            # A document with no form at all does not earn a per-page widget
            # scan, and this is a document-level property.
            modulo = bool(doc.is_form_pdf)
            for i in range(doc.page_count):
                # The page must stay alive in a local: a widget keeps a weak
                # reference to the page it came from, so ``read_fields(doc[i])``
                # would hand back fields that can never be written.
                pagina = doc[i]
                items.append(
                    PageItem(
                        source_index=i,
                        base_rotation=pagina.rotation,
                        source_id=source_id,
                        # page.rect already includes the base /Rotate, so these
                        # are the oriented dimensions the view must lay out with.
                        width_pt=pagina.rect.width,
                        height_pt=pagina.rect.height,
                        form_fields=read_fields(pagina) if modulo else [],
                    )
                )
        return items

    def open(self, path: str) -> None:
        """Open *path* read-only, replacing the virtual page list entirely."""
        self.pages = self._items_for(0, path)
        self.sources = [path]
        self.path = path
        self.changed.emit()

    def append_document(self, path: str) -> int:
        """Merge: append every page of *path* after the current ones.

        Returns the number of pages added. The new source is registered only
        after it has been read successfully, so a corrupt file leaves the
        model exactly as it was.
        """
        items = self._items_for(len(self.sources), path)
        if not items:
            return 0
        self.sources.append(path)
        self.pages.extend(items)
        self.changed.emit()
        return len(items)

    def source_for(self, item: PageItem) -> str:
        """Path of the document that *item* points into."""
        return self.sources[item.source_id]

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
        handles: dict[int, fitz.Document] = {}
        trovati: dict[int, list[RedactionRect]] = {}
        try:
            for indice, item in enumerate(self.pages):
                doc = handles.get(item.source_id)
                if doc is None:
                    doc = fitz.open(self.sources[item.source_id])
                    handles[item.source_id] = doc
                # Bound to a local on purpose: a widget-like object read from a
                # temporary page would be collected with it.
                pagina = doc[item.source_index]
                larghezza, altezza = item.unrotated_size
                rects = [
                    RedactionRect.from_corners(r.x0, r.y0, r.x1, r.y1).clamped_to(
                        larghezza, altezza
                    )
                    for r in pagina.search_for(text)
                ]
                if nuovi := _not_already_marked(item, rects):
                    trovati[indice] = nuovi
        finally:
            for doc in handles.values():
                doc.close()
        return trovati

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def close(self) -> None:
        self.pages.clear()
        self.sources.clear()
        self.path = None
        self.changed.emit()
