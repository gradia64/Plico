"""RenderWorker — lives in its own QThread and owns every fitz handle.

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

import fitz
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
    """Owns the fitz document handles; communicates entirely via signals."""

    render_requested = Signal(object)
    rendered = Signal(object, QImage)   # emit QImage, NOT QPixmap

    def __init__(self) -> None:
        super().__init__()
        # Keyed by path: the same file merged twice shares one handle, and a
        # reused source_id can never be confused with a different document.
        self._docs: OrderedDict[str, fitz.Document] = OrderedDict()
        self.render_requested.connect(self._render)

    def _doc_for(self, path: str) -> fitz.Document | None:
        """Return the open handle for *path*, opening it on first use."""
        doc = self._docs.get(path)
        if doc is not None:
            self._docs.move_to_end(path)
            return doc
        try:
            doc = fitz.open(path)
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
            return
        try:
            page = doc[req.source_index]
            mat = fitz.Matrix(req.zoom, req.zoom).prerotate(req.rotation)
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
        except (IndexError, RuntimeError, ValueError):
            # Page index out of range or document already closed
            return

    @Slot()
    def shutdown(self) -> None:
        """Close every document; called IN the worker thread via invokeMethod."""
        for doc in self._docs.values():
            doc.close()
        self._docs.clear()
