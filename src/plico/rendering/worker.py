"""RenderWorker — lives in its own QThread and owns every PyMuPDF handle.

Key design decisions:
  - The worker is the ONLY thing that renders. It opens each source document
    read-only, lazily, the first time a page from it is requested, and keeps
    a small LRU of open handles (merging several PDFs must not leak a file
    descriptor per document).
  - All communication is via signals: cross-thread connections are queued
    automatically by Qt.
  - QImage (NOT QPixmap) is emitted in signals — QPixmap is GUI-thread-only.
  - The request carries the source *path* rather than relying on an earlier
    "open" message: there is no cross-thread ordering to get wrong, and the
    same page is never rendered from a stale document.
  - Rendering applies ONLY the user's rotation offset. MuPDF already applies
    the page's own /Rotate, both when rendering and when reporting
    ``page.rect``, so adding ``base_rotation`` here would rotate a
    base-rotated page twice -- and base-rotated pages are everywhere (scans,
    phone exports, anything a viewer has "fixed" by writing /Rotate).
"""

from collections import OrderedDict

import pymupdf
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage

# Enough for the handful of documents a merged job realistically interleaves,
# while keeping the number of open files bounded.
MAX_OPEN_DOCUMENTS = 16


class RenderRequest:
    """A single render request emitted to the worker thread.

    key = ("page" | "thumb", source_id, source_index, rotation, zoom, dpr)

    ``source_id`` is part of the key so that merging a second PDF cannot be
    served a cached pixmap belonging to a different source document.
    """

    def __init__(
        self,
        key: tuple,
        source_path: str,
        source_index: int,
        zoom: float,
        rotation: int,
    ) -> None:
        self.key = key                      # cache/render identity
        self.source_path = source_path      # which PDF to render from
        self.source_index = source_index    # page position in that PDF
        self.zoom = zoom                    # zoom in real pixels (zoom × dpr)
        self.rotation = rotation            # user offset on top of /Rotate


class RenderWorker(QObject):
    """Owns the PyMuPDF document handles; communicates entirely via signals."""

    render_requested = Signal(object)
    rendered = Signal(object, QImage)   # emit QImage, NOT QPixmap
    # The key of a request that produced no image (missing source, page out
    # of range, document closed). Without it a requester that marks a key as
    # "in flight" would wait for it forever and never retry that page.
    render_failed = Signal(object)
    # Ask the worker to drop its cached handle for a source path. Needed
    # after saving over a file that is currently open: os.replace() swaps the
    # inode, and the handle we hold would keep reading the OLD document even
    # if the same path is re-opened.
    evict_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        # Keyed by path: the same file merged twice shares one handle, and a
        # reused source_id can never be confused with a different document.
        self._docs: OrderedDict[str, pymupdf.Document] = OrderedDict()
        self.render_requested.connect(self._render)
        self.evict_requested.connect(self._evict)

    def _doc_for(self, path: str) -> pymupdf.Document | None:
        """Return the open handle for *path*, opening it on first use."""
        doc = self._docs.get(path)
        if doc is not None:
            self._docs.move_to_end(path)
            return doc
        try:
            doc = pymupdf.open(path)
        # A file that vanished or is unreadable must not kill the thread;
        # the caller simply gets no image for this request.
        except Exception:  # noqa: BLE001
            return None
        self._docs[path] = doc
        while len(self._docs) > MAX_OPEN_DOCUMENTS:
            _, old = self._docs.popitem(last=False)
            old.close()
        return doc

    def _render(self, req: RenderRequest) -> None:
        doc = self._doc_for(req.source_path)
        if doc is None:
            self.render_failed.emit(req.key)
            return
        try:
            page = doc[req.source_index]
            mat = pymupdf.Matrix(req.zoom, req.zoom).prerotate(req.rotation)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            # QImage wraps the samples buffer; copy so the buffer can be freed
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            ).copy()
            self.rendered.emit(req.key, img)
        # Not just IndexError/RuntimeError/ValueError: MuPDF's own errors
        # (FzErrorLimit, FzErrorFormat, ...) derive straight from Exception.
        # A large-format page at high zoom raises FzErrorLimit ("Overly large
        # image"), and an exception escaping this slot would skip
        # render_failed, leaving the page "in flight" forever.
        except Exception:  # noqa: BLE001
            self.render_failed.emit(req.key)

    @Slot(str)
    def _evict(self, path: str) -> None:
        """Drop and close the cached handle for *path*."""
        doc = self._docs.pop(path, None)
        if doc is not None:
            doc.close()

    @Slot()
    def shutdown(self) -> None:
        """Close every document; called IN the worker thread via invokeMethod."""
        for doc in self._docs.values():
            doc.close()
        self._docs.clear()
