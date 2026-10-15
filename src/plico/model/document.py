"""Document model: a list of virtual pages over an immutable PDF."""

from dataclasses import dataclass

import fitz
from PySide6.QtCore import QObject, Signal


@dataclass
class PageItem:
    """A virtual page entry — does NOT modify the source PDF."""

    source_index: int     # position in the original file
    base_rotation: int    # /Rotate as stored in the original (0/90/180/270)
    rotation: int = 0     # user-supplied rotation offset

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
        self.path: str | None = None

    def open(self, path: str) -> None:
        """Open *path* read-only and build the virtual page list."""
        with fitz.open(path) as doc:
            self.pages = [
                PageItem(source_index=i, base_rotation=p.rotation)
                for i, p in enumerate(doc)
            ]
        self.path = path
        self.changed.emit()

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def close(self) -> None:
        self.pages.clear()
        self.path = None
        self.changed.emit()