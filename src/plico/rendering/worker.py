"""RenderWorker — lives in its own QThread, owns the single fitz handle.

Key design decisions:
  - The worker is the ONLY thing that touches fitz (the PDF is opened
    read-only here, in this thread).
  - All communication is via signals: cross-thread connections are queued
    automatically by Qt.
  - QImage (NOT QPixmap) is emitted in signals — QPixmap is GUI-thread-only.
  - On open, the worker emits page sizes so the UI can lay out before any
    rendering happens.
  - Rendering uses the composite rotation (item.total_rotation) so that
    page.rect (which already includes base rotation) and our user rotation
    offset are combined correctly.
"""

import fitz
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage


class RenderRequest:
    """A single render request emitted to the worker thread.

    key = (source_index, rotation, zoom, dpr)
    """

    def __init__(
        self,
        key: tuple,
        source_index: int,
        zoom: float,
        rotation: int,
    ) -> None:
        self.key = key                  # (source_index, rotation, zoom, dpr)
        self.source_index = source_index
        self.zoom = zoom                # zoom in real pixels (zoom × dpr)
        self.rotation = rotation        # composite rotation for rendering


class RenderWorker(QObject):
    """Owns the fitz document handle; communicates entirely via signals."""

    open_requested = Signal(str)
    render_requested = Signal(object)
    rendered = Signal(object, QImage)   # emit QImage, NOT QPixmap
    opened = Signal(str, list)          # (path, [(width_pt, height_pt), ...])

    def __init__(self) -> None:
        super().__init__()
        self._doc: fitz.Document | None = None
        self.open_requested.connect(self._open)
        self.render_requested.connect(self._render)

    def _open(self, path: str) -> None:
        if self._doc:
            self._doc.close()
        self._doc = fitz.open(path)
        # page.rect includes the base /Rotate → these are "oriented" dimensions
        sizes = [(p.rect.width, p.rect.height) for p in self._doc]
        self.opened.emit(path, sizes)

    def _render(self, req: RenderRequest) -> None:
        if self._doc is None:
            # Worker hasn't opened a document yet or has been shut down.
            # Silently drop the request — the caller will re-request after open.
            return
        try:
            page = self._doc[req.source_index]
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
        except (IndexError, RuntimeError):
            # Page index out of range or document already closed
            return

    @Slot()
    def shutdown(self) -> None:
        """Close the document; called IN the worker thread via invokeMethod."""
        if self._doc:
            self._doc.close()
            self._doc = None