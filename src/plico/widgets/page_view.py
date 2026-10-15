"""PageView — QScrollArea with on-demand HiDPI rendering and fit-width mode.

Key design:
  - Rendering happens at zoom × devicePixelRatio (real pixels)
  - QImage is tagged with setDevicePixelRatio so the QPixmap is crisp on HiDPI
  - Old pixmap stays visible until the new one arrives (no flash)
  - Scroll position is preserved across reflows by anchoring on content offset
  - Cache is byte-budgeted, not count-limited (high-zoom pages are big)
"""

from collections import OrderedDict
from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPalette as QPaletteColor
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from ..model.document import PageItem
from ..rendering.worker import RenderRequest

# --- constants ----------------------------------------------------------- #

ZOOM_STEPS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
PRELOAD = 200          # preload margin (px) beyond viewport
CACHE_BUDGET = 64 * 1024 * 1024  # 64 MB byte budget for page cache
FALLBACK_VIEWPORT_H = 800  # assumed height until the widget is sized


# --- per-page canvas ----------------------------------------------------- #

@dataclass
class _Canvas:
    """One QLabel per page inside the scroll area's content widget."""
    item: PageItem
    label: QLabel
    current_key: tuple | None = None
    pending_key: tuple | None = None
    width_pt: float = 0.0   # page width in points (post-rotation)
    height_pt: float = 0.0  # page height in points (post-rotation)
    y_px: int = 0           # layout offset, computed by _relayout()
    height_px: int = 0      # laid-out height, computed by _relayout()


# --- PageView ----------------------------------------------------------- #

class PageView(QScrollArea):
    """Central view: scrollable, zoomable, HiDPI-aware page rendering."""

    def __init__(self, worker, model=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.worker = worker
        self._model = model

        # --- state ---
        self._items: list[PageItem] = []
        self._canvases: list[_Canvas] = []
        # Identity is (source_id, source_index), never source_index alone:
        # once a second PDF is merged, two pages can share a source_index.
        self._by_page: dict[tuple[int, int], _Canvas] = {}
        self._zoom = 1.0
        # Scroll offset we are still trying to reach, if the scrollbar range
        # was too small when it was asked for.
        self._pending_scroll: int | None = None
        self._fit_mode = False
        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._cache_bytes = 0

        # --- layout container ---
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(10)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self.setWidget(self._container)
        self.setWidgetResizable(True)

        # --- signals ---
        self.worker.rendered.connect(self._on_rendered)
        # A request that produced nothing must clear its pending key, or the
        # page would wait for a render that will never arrive and never be
        # retried (a missing source, or a page index out of range).
        self.worker.render_failed.connect(self._on_render_failed)
        # Load further pages as the user scrolls through the document.
        self.verticalScrollBar().valueChanged.connect(lambda _v: self._request_visible())
        # The view observes the model instead of being poked by the window:
        # that way undo/redo (which mutates the model directly) is reflected
        # automatically, with no chance of a missed refresh.
        if model is not None:
            model.changed.connect(self._on_model_changed)
            model.page_changed.connect(self._on_page_changed)

    # ------------------------------------------------------------------ #
    #  Model observation
    # ------------------------------------------------------------------ #

    def _on_model_changed(self) -> None:
        """The page list changed shape (open/delete/reorder): rebuild."""
        if self._model is None:
            return
        first_page = self._first_visible_page()
        self._items = list(self._model.pages)
        # No size list to copy: each item carries its own oriented size.
        self._rebuild_canvases()
        self._relayout()
        self._anchor_on(first_page)

    def _on_page_changed(self, _row: int) -> None:
        """A page changed in place (rotation): re-measure and re-render."""
        self.refresh_geometry()

    @staticmethod
    def _identity(item: PageItem) -> tuple[int, int]:
        """Page identity: (source_id, source_index) — stable across edits."""
        return (item.source_id, item.source_index)

    def _anchor_on(self, page_id: tuple[int, int] | None) -> None:
        """Scroll back to the page the user was looking at, if still present."""
        if page_id is None:
            return
        c = self._by_page.get(page_id)
        if c is not None:
            self._scroll_to(c)

    # ------------------------------------------------------------------ #
    #  Document lifecycle
    # ------------------------------------------------------------------ #

    def _oriented_size(self, item: PageItem) -> tuple[float, float]:
        """Page size in points as displayed, user rotation included.

        Falls back to A4 when the item has no size (a hand-built PageItem, or
        a source that reported nothing) so the placeholder still has a sane
        box.

        The swap is driven by the USER offset only. ``item.width_pt`` /
        ``item.height_pt`` come from ``page.rect``, which MuPDF has already
        rotated by the page's own /Rotate, so the base rotation is baked into
        those numbers already; swapping on ``total_rotation`` would apply it a
        second time and every scan would be laid out the wrong way round.
        """
        w_pt, h_pt = item.width_pt, item.height_pt
        if w_pt <= 0.0 or h_pt <= 0.0:
            return 595.0, 842.0
        if item.rotation % 180 == 0:
            return w_pt, h_pt
        return h_pt, w_pt

    def _make_label(self) -> QLabel:
        label = QLabel()
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setBackgroundRole(QPaletteColor.ColorRole.Base)
        label.setAutoFillBackground(True)
        label.setText("Caricamento…")
        label.setStyleSheet("background-color: #f0f0f0;")
        return label

    def _rebuild_canvases(self) -> None:
        """Rebuild the page list, REUSING labels for surviving pages.

        source_index is stable across reorder and delete, so a reused
        label keeps its rendered pixmap: reordering or deleting a page
        never forces a re-render, and never flashes grey.
        """
        existing = {self._identity(c.item): c for c in self._canvases}

        # Detach every label so they can be re-added in the new order.
        for c in self._canvases:
            self._layout.removeWidget(c.label)
            c.label.setParent(None)

        self._canvases = []
        self._by_page = {}
        for item in self._items:
            page_id = self._identity(item)
            canvas = existing.pop(page_id) if page_id in existing else None
            if canvas is None:
                canvas = _Canvas(item=item, label=self._make_label())
            else:
                canvas.item = item
            canvas.width_pt, canvas.height_pt = self._oriented_size(item)
            self._layout.addWidget(canvas.label)
            self._canvases.append(canvas)
            self._by_page[page_id] = canvas

        # Pages that no longer exist in the document.
        for stale in existing.values():
            stale.label.deleteLater()

    def refresh_geometry(self) -> None:
        """Recompute oriented page sizes after in-place edits (rotation).

        Rotation changes an existing page rather than restructuring the
        list, so the canvases must be re-measured before the relayout.
        """
        for c in self._canvases:
            c.width_pt, c.height_pt = self._oriented_size(c.item)
        self._relayout()

    # ------------------------------------------------------------------ #
    #  Zoom controls
    # ------------------------------------------------------------------ #

    def zoom(self) -> float:
        """Current zoom factor (1.0 = 100%)."""
        return self._zoom

    def set_zoom_fit_width(self) -> None:
        self._fit_mode = True
        self._relayout()

    def set_zoom(self, z: float) -> None:
        self._fit_mode = False
        z = min(max(z, ZOOM_STEPS[0]), ZOOM_STEPS[-1])
        old = self._zoom
        sb = self.verticalScrollBar()
        center = sb.value() + self.viewport().height() / 2  # content y at center
        self._zoom = z
        self._relayout()
        sb.setValue(round(center * z / old - self.viewport().height() / 2))

    def zoom_in(self) -> None:
        self._set_step(+1)

    def zoom_out(self) -> None:
        self._set_step(-1)

    def _set_step(self, direction: int) -> None:
        z = self._zoom
        if direction > 0:
            target = next((s for s in ZOOM_STEPS if s > z + 0.01), ZOOM_STEPS[-1])
        else:
            target = next((s for s in reversed(ZOOM_STEPS) if s < z - 0.01), ZOOM_STEPS[0])
        self.set_zoom(target)

    def _relayout(self) -> None:
        """Resize all canvas labels to the current zoom level.

        Sizes here are LOGICAL pixels: Qt scales the label itself by the
        device pixel ratio, while the render request asks for zoom × dpr
        real pixels. Keeping the two separate is what makes HiDPI crisp.

        Each canvas also records the y-offset it will occupy, computed here
        rather than read back from ``label.geometry()``. The geometry of a
        widget is only trustworthy after Qt has run a layout pass; before
        that (an unshown window, or the very first layout) every label
        reports the same stale rectangle, which would make every page look
        visible and trigger a render of the whole document.
        """
        margin_top = self._layout.contentsMargins().top()
        spacing = self._layout.spacing()
        y_px = margin_top
        avail = max(1, self.viewport().width() - 20)  # margins
        for c in self._canvases:
            # Convert points → pixels at current zoom
            w_px = int(c.width_pt * self._zoom)
            h_px = int(c.height_pt * self._zoom)
            if self._fit_mode and c.width_pt > 0:
                w_px = int(avail)
                h_px = int(avail * c.height_pt / c.width_pt)
            w_px = max(1, w_px)
            h_px = max(1, h_px)
            c.label.setFixedSize(QSize(w_px, h_px))
            c.y_px = y_px
            c.height_px = h_px
            y_px += h_px + spacing

        # Request visible renders
        self._apply_pending_scroll()
        self._request_visible()

    def resizeEvent(self, event) -> None:
        self._relayout()
        super().resizeEvent(event)

    # ------------------------------------------------------------------ #
    #  Render on demand
    # ------------------------------------------------------------------ #

    def _visible_range(self) -> tuple[int, int]:
        """Half-open [first, last) index range of pages worth rendering.

        Derived from the scroll offset and the recorded layout offsets, so
        it is correct even before Qt's first layout pass. A window that has
        not been sized yet falls back to a screenful, never to everything.
        """
        total = len(self._canvases)
        if total == 0:
            return 0, 0
        viewport_h = self.viewport().height()
        if viewport_h <= 0:
            viewport_h = FALLBACK_VIEWPORT_H
        top = self.verticalScrollBar().value() - PRELOAD
        bottom = self.verticalScrollBar().value() + viewport_h + PRELOAD
        first = total
        last = 0
        for i, c in enumerate(self._canvases):
            if c.y_px + c.height_px < top or c.y_px > bottom:
                continue
            first = min(first, i)
            last = max(last, i + 1)
        if first >= last:
            # Nothing matched (a degenerate viewport): show the first page.
            return 0, min(total, max(1, viewport_h // 200 + 1))
        return first, last

    def _request_visible(self) -> None:
        if not self._canvases:
            return
        first, last = self._visible_range()
        dpr = self.devicePixelRatioF() or 1.0
        for c in self._canvases[first:last]:
            key = (
                "page",
                c.item.source_id,
                c.item.source_index,
                c.item.rotation,
                self._zoom,
                dpr,
            )
            if c.current_key == key or c.pending_key == key:
                continue
            pix = self._cache.get(key)
            if pix is not None:
                self._cache.move_to_end(key)
                c.current_key = key
                c.pending_key = None
                c.label.setPixmap(pix)
                c.label.setText("")
                continue
            c.pending_key = key
            self.worker.render_requested.emit(
                RenderRequest(
                    key,
                    self._model.source_for(c.item),
                    c.item.source_index,
                    self._zoom * dpr,   # zoom in real pixels
                    c.item.rotation,    # user offset only: MuPDF has already
                )                       # applied the page's own /Rotate
            )

    def _on_rendered(self, key, img) -> None:
        """Slot for RenderWorker.rendered signal (GUI thread).

        Only handles page renders (keys tagged "page"); thumbnail renders
        are tagged "thumb" and handled by the ThumbnailBar, which is also
        the router that knows which of them it asked for.
        """
        if not key or key[0] != "page":
            return  # not a page render
        page_id = (key[1], key[2])
        dpr = key[5]
        c = self._by_page.get(page_id)
        if c is None or c.pending_key != key:
            return  # stale result
        img.setDevicePixelRatio(dpr)  # crisp HiDPI
        pix = QPixmap.fromImage(img)
        self._cache_put(key, pix, img)
        c.current_key = key
        c.pending_key = None
        c.label.setPixmap(pix)
        c.label.setText("")

    def _on_render_failed(self, key) -> None:
        """Slot for RenderWorker.render_failed (GUI thread).

        Clear the pending marker so the page is retried the next time it is
        scrolled into view, instead of waiting forever on a dead request.
        """
        if not key or key[0] != "page":
            return  # not a page render
        c = self._by_page.get((key[1], key[2]))
        if c is not None and c.pending_key == key:
            c.pending_key = None

    def _cache_put(self, key, pix, img) -> None:
        self._cache[key] = pix
        self._cache.move_to_end(key)
        self._cache_bytes += img.width() * img.height() * 4
        while self._cache_bytes > CACHE_BUDGET and len(self._cache) > 1:
            _, old = self._cache.popitem(last=False)
            self._cache_bytes -= old.width() * old.height() * 4

    # ------------------------------------------------------------------ #
    #  Selection / navigation helpers
    # ------------------------------------------------------------------ #

    def _first_visible_page(self) -> tuple[int, int] | None:
        """Identity of the topmost page near the viewport, for anchoring."""
        first, _last = self._visible_range()
        if 0 <= first < len(self._canvases):
            return self._identity(self._canvases[first].item)
        return None

    def _scroll_to(self, canvas: "_Canvas") -> None:
        """Put the top of *canvas* at the top of the viewport.

        The offset is computed from the layout we recorded ourselves
        (``y_px``) rather than delegated to ``ensureWidgetVisible``: that
        call depends on Qt having already run a layout pass, which is not
        true right after a rebuild, and it silently does nothing in a
        window that is not on screen yet.
        """
        self._pending_scroll = canvas.y_px
        self._apply_pending_scroll()
        if self._pending_scroll is not None:
            # Qt widens the scrollbar range in its own layout pass, which
            # has not run yet: one deferred retry lands on the real target.
            QTimer.singleShot(0, self._finish_pending_scroll)

    def _apply_pending_scroll(self) -> None:
        """Scroll as far towards the requested offset as the range allows."""
        if self._pending_scroll is None:
            return
        sb = self.verticalScrollBar()
        sb.setValue(max(0, min(self._pending_scroll, sb.maximum())))
        if self._pending_scroll <= sb.maximum():
            self._pending_scroll = None

    def _finish_pending_scroll(self) -> None:
        """Last chance to reach the target, then forget it.

        Dropping the request matters: a stale offset re-applied on a later
        resize would yank the view back to where the user no longer is.
        """
        self._apply_pending_scroll()
        self._pending_scroll = None

    def ensure_page_visible(self, index: int) -> None:
        """Scroll the view so the page at *index* is on screen."""
        if 0 <= index < len(self._canvases):
            self._scroll_to(self._canvases[index])

    def clear(self) -> None:
        for c in self._canvases:
            self._layout.removeWidget(c.label)
            c.label.deleteLater()
        self._items.clear()
        self._canvases.clear()
        self._by_page.clear()
        self._cache.clear()
        self._cache_bytes = 0
        self.update()

    def reset(self) -> None:
        """Drop the current document entirely (before opening another).

        Wipes the render cache too: keys are built from source identity, so
        a re-opened document would otherwise hit the old document's pixmaps.
        """
        self.clear()
        if self._model is not None:
            self._items = list(self._model.pages)