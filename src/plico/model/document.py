"""Document model: a list of virtual pages over one or more immutable PDFs.

The model never writes to a PDF. It holds a list of *virtual pages*, each of
which points at a page of a source document, and the only state it adds is the
rotation offset the user chose. Every other feature (undo/redo, rendering,
saving, splitting) is derived from that list.
"""

from dataclasses import dataclass

import fitz
from PySide6.QtCore import QObject, Signal


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

    @property
    def total_rotation(self) -> int:
        """Composite rotation that gets written to the output PDF."""
        return (self.base_rotation + self.rotation) % 360


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
        with fitz.open(path) as doc:
            return [
                PageItem(
                    source_index=i,
                    base_rotation=p.rotation,
                    source_id=source_id,
                    # page.rect already includes the base /Rotate, so these
                    # are the oriented dimensions the view must lay out with.
                    width_pt=p.rect.width,
                    height_pt=p.rect.height,
                )
                for i, p in enumerate(doc)
            ]

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

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def close(self) -> None:
        self.pages.clear()
        self.sources.clear()
        self.path = None
        self.changed.emit()
