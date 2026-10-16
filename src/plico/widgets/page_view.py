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

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtGui import QPalette as QPaletteColor
from PySide6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from ..model.document import PageItem
from ..model.forms import CHECKBOX, UNCHECKED, Field
from ..model.redact import RedactionRect, map_point, map_rect
from ..rendering.worker import RenderRequest

# --- constants ----------------------------------------------------------- #

ZOOM_STEPS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
PRELOAD = 200          # preload margin (px) beyond viewport
CACHE_BUDGET = 64 * 1024 * 1024  # 64 MB byte budget for page cache
FALLBACK_VIEWPORT_H = 800  # assumed height until the widget is sized

# Redaction marks: a dark fill, so a marked region never reads as page
# content, and a red frame so the mark itself is unmistakable.
REDACTION_FILL = QColor(0, 0, 0, 190)
REDACTION_BORDER = QColor(214, 48, 48)
REDACTION_DRAG = QColor(214, 48, 48, 170)

# Below this (in pixels) a press-and-release is a click, not a drag.
CLICK_SLOP = 4.0

# Form fields, drawn over the page: a light wash says "there is a field here",
# and the selected one is picked out so that the page and the panel agree.
FIELD_WASH = QColor(64, 120, 200, 26)
FIELD_BORDER = QColor(64, 120, 200, 150)
FIELD_SELECTED_WASH = QColor(230, 145, 40, 40)
FIELD_SELECTED_BORDER = QColor(214, 138, 48)
FIELD_TEXT = QColor(20, 20, 20)


# --- per-page canvas ----------------------------------------------------- #

class _PageLabel(QLabel):
    """One page: the rendered pixmap, with the redaction marks drawn on top.

    Painting the marks here, rather than in a widget floating above the page,
    buys three things at once: they are clipped to the page for free, they
    follow the page through zoom and fit-width with no extra bookkeeping, and
    a mouse coordinate arrives already in the page's own pixels.

    The label never touches the model. It reports gestures to the view, which
    reports them to the window, which pushes an undoable command — the same
    route the thumbnail bar's drag & drop takes.
    """

    def __init__(self, view: "PageView") -> None:
        super().__init__()
        self._view = view
        # Set by _rebuild_canvases(); None only between construction and that.
        self.canvas: _Canvas | None = None
        self._drag_from: QPointF | None = None
        self._drag_to: QPointF | None = None

    # -- coordinates ---------------------------------------------------- #

    def _scale(self) -> float:
        """Logical pixels per point, as laid out by the view."""
        canvas = self.canvas
        if canvas is None or canvas.scale <= 0.0:
            return 1.0
        return canvas.scale

    def _to_page(self, point: QPointF) -> tuple[float, float]:
        """Widget pixels → page space (unrotated PDF points)."""
        canvas = self.canvas
        assert canvas is not None
        scale = self._scale()
        return map_point(
            point.x() / scale, point.y() / scale, canvas.item.page_matrix()
        )

    def _rect_pixels(self, rect: tuple[float, float, float, float]) -> QRectF:
        """A page-space rectangle → the widget rectangle to paint it in."""
        canvas = self.canvas
        assert canvas is not None
        view_rect = map_rect(RedactionRect(*rect), canvas.item.view_matrix())
        scale = self._scale()
        return QRectF(
            view_rect.x0 * scale,
            view_rect.y0 * scale,
            view_rect.width * scale,
            view_rect.height * scale,
        )

    def _to_pixels(self, rect: RedactionRect) -> QRectF:
        """Like :meth:`_rect_pixels`, for a redaction rectangle."""
        return self._rect_pixels(rect.as_tuple())

    # -- painting ------------------------------------------------------- #

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        canvas = self.canvas
        if canvas is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Fields are always drawn: they are how the user finds what can be
        # filled in. Redactions only while the tool is on, so that a page
        # carrying marks still reads as a page.
        self._paint_fields(painter)
        if self._view.redaction_mode():
            self._paint_redactions(painter)
        painter.end()

    def _paint_redactions(self, painter: QPainter) -> None:
        canvas = self.canvas
        assert canvas is not None
        for rect in canvas.item.redactions:
            area = self._to_pixels(rect)
            painter.fillRect(area, QBrush(REDACTION_FILL))
            painter.setPen(QPen(REDACTION_BORDER, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(area)
        if self._drag_from is not None and self._drag_to is not None:
            painter.setPen(QPen(REDACTION_DRAG, 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(self._drag_from, self._drag_to).normalized())

    def _paint_fields(self, painter: QPainter) -> None:
        """Draw this page's form fields, each with the value it will hold.

        The value comes from the MODEL, not from the widget: after a save the
        two agree, but before it the model is the only thing that knows what is
        about to be written into the file.
        """
        canvas = self.canvas
        assert canvas is not None
        item = canvas.item
        if not item.form_fields:
            return
        scelto = self._view.selected_field()
        for campo in item.form_fields:
            area = self._rect_pixels(campo.rect)
            acceso = scelto == (canvas.index, campo.name)
            painter.fillRect(
                area, QBrush(FIELD_SELECTED_WASH if acceso else FIELD_WASH)
            )
            spessore = 2 if acceso else 1
            bordo = FIELD_SELECTED_BORDER if acceso else FIELD_BORDER
            painter.setPen(QPen(bordo, spessore))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(area)
            testo = self._valore_mostrato(item, campo)
            if testo:
                self._paint_value(painter, area, campo, testo)

    @staticmethod
    def _valore_mostrato(item: PageItem, campo: Field) -> str:
        valore = item.form_values.get(campo.name, campo.value)
        if campo.kind == CHECKBOX:
            # A checkbox has no text of its own: it is ticked, or it is not.
            return "X" if valore not in ("", UNCHECKED) else ""
        return valore

    @staticmethod
    def _paint_value(
        painter: QPainter, area: QRectF, campo: Field, testo: str
    ) -> None:
        """Write *testo* inside *area*, clipped so it can never spill out."""
        dentro = area.adjusted(3.0, 2.0, -3.0, -2.0)
        if dentro.width() <= 1.0 or dentro.height() <= 1.0:
            return
        painter.save()
        painter.setClipRect(dentro)
        painter.setPen(QPen(FIELD_TEXT))
        font = painter.font()
        font.setPixelSize(max(6, min(int(dentro.height() * 0.7), 18)))
        painter.setFont(font)
        bandiere = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if campo.multiline:
            painter.drawText(dentro, bandiere | int(Qt.TextFlag.TextWordWrap), testo)
        else:
            painter.drawText(dentro, bandiere, testo)
        painter.restore()

    # -- the gesture ---------------------------------------------------- #

    def _select_field_under(self, point: QPointF) -> None:
        """Tell the view which form field, if any, sits under *point*.

        Last match wins, because that is the one painted on top.
        """
        canvas = self.canvas
        if canvas is None:
            return
        for campo in reversed(canvas.item.form_fields):
            if self._rect_pixels(campo.rect).contains(point):
                self._view.report_field_click(canvas.index, campo.name)
                return

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if not self._view.redaction_mode():
            self._select_field_under(event.position())
            super().mousePressEvent(event)
            return
        self._drag_from = event.position()
        self._drag_to = self._drag_from
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_from is None:
            super().mouseMoveEvent(event)
            return
        self._drag_to = event.position()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_from is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        start = self._drag_from
        end = event.position()
        self._drag_from = None
        self._drag_to = None
        self.update()
        if (end - start).manhattanLength() < CLICK_SLOP:
            # A click rather than a drag: take back the mark under the cursor,
            # if there is one. Topmost first, so the visible one wins.
            canvas = self.canvas
            assert canvas is not None
            for rect in reversed(canvas.item.redactions):
                if self._to_pixels(rect).contains(end):
                    self._view.forget_redaction(canvas, rect)
                    break
            return
        canvas = self.canvas
        assert canvas is not None
        self._view.commit_redaction(canvas, *self._to_page(start), *self._to_page(end))


@dataclass
class _Canvas:
    """One QLabel per page inside the scroll area's content widget."""
    item: PageItem
    label: _PageLabel
    index: int = 0          # position in the page list, set on every rebuild
    scale: float = 1.0      # logical pixels per point, set by _relayout()
    current_key: tuple | None = None
    pending_key: tuple | None = None
    width_pt: float = 0.0   # page width in points (post-rotation)
    height_pt: float = 0.0  # page height in points (post-rotation)
    y_px: int = 0           # layout offset, computed by _relayout()
    height_px: int = 0      # laid-out height, computed by _relayout()


# --- PageView ----------------------------------------------------------- #

class PageView(QScrollArea):
    """Central view: scrollable, zoomable, HiDPI-aware page rendering."""

    # (page index, RedactionRect in page space). The view never mutates the
    # model: it reports the gesture and MainWindow pushes an undoable command.
    redaction_added = Signal(int, object)
    redaction_removed = Signal(int, object)
    # (page index, field name): a click landed on a form field drawn on the
    # page. The view fills nothing — it only says where the user pointed.
    field_clicked = Signal(int, str)

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
        self._redaction_mode = False
        # The (page index, field name) the form panel is editing, so the field
        # can be picked out on the page. None when nothing is selected.
        self._selected_field: tuple[int, str] | None = None
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

    def _on_page_changed(self, row: int) -> None:
        """A page changed in place (rotation, redaction): re-measure, repaint."""
        self.refresh_geometry()
        # A redaction changes no size, so setFixedSize() leaves the label
        # exactly as it was and nothing would repaint without this nudge.
        if 0 <= row < len(self._canvases):
            self._canvases[row].label.update()

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

    def _redaction_cursor(self) -> Qt.CursorShape:
        if self._redaction_mode:
            return Qt.CursorShape.CrossCursor
        return Qt.CursorShape.ArrowCursor

    # ------------------------------------------------------------------ #
    #  Form fields
    # ------------------------------------------------------------------ #

    def selected_field(self) -> tuple[int, str] | None:
        """The (page index, field name) the panel is editing, if any."""
        return self._selected_field

    def set_selected_field(self, row: int, name: str | None) -> None:
        """Highlight field *name* of page *row*; ``None`` clears it."""
        self._selected_field = None if name is None else (row, name)
        for canvas in self._canvases:
            canvas.label.update()

    def report_field_click(self, row: int, name: str) -> None:
        """A click landed on a form field: the window decides what happens."""
        self.field_clicked.emit(row, name)

    def _make_label(self) -> _PageLabel:
        label = _PageLabel(self)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setBackgroundRole(QPaletteColor.ColorRole.Base)
        label.setAutoFillBackground(True)
        label.setText("Caricamento…")
        label.setStyleSheet("background-color: #f0f0f0;")
        label.setCursor(self._redaction_cursor())
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
        for index, item in enumerate(self._items):
            page_id = self._identity(item)
            canvas = existing.pop(page_id) if page_id in existing else None
            if canvas is None:
                label = self._make_label()
                canvas = _Canvas(item=item, label=label)
                # The label paints its own marks, so it needs the way back to
                # the item, the scale and the redaction list.
                label.canvas = canvas
            else:
                canvas.item = item
            canvas.index = index
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
            # Logical pixels per point, for the redaction overlay: it has to
            # convert in both directions, and fit-width changes this without
            # touching `_zoom`.
            c.scale = w_px / c.width_pt if c.width_pt > 0 else 1.0
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
    #  Redazione
    # ------------------------------------------------------------------ #

    def redaction_mode(self) -> bool:
        """Whether a drag on a page draws a mark instead of doing nothing."""
        return self._redaction_mode

    def set_redaction_mode(self, active: bool) -> None:
        """Turn the redaction tool on or off, for every page at once."""
        self._redaction_mode = bool(active)
        cursor = self._redaction_cursor()
        for c in self._canvases:
            c.label.setCursor(cursor)
            # The marks are painted only while the tool is on, so leaving it
            # has to wipe them off the screen immediately.
            c.label.update()

    def commit_redaction(
        self, canvas: _Canvas, x0: float, y0: float, x1: float, y1: float
    ) -> None:
        """A rectangle was dragged on *canvas*: report it, in page space."""
        width, height = canvas.item.unrotated_size
        rect = RedactionRect.from_corners(x0, y0, x1, y1).clamped_to(width, height)
        # A stray click, or a rectangle dragged entirely off the page, is not
        # a mark: refusing it here keeps an invisible box in the undo stack.
        if rect.width < 1.0 or rect.height < 1.0:
            return
        self.redaction_added.emit(canvas.index, rect)

    def forget_redaction(self, canvas: _Canvas, rect: RedactionRect) -> None:
        """Ask for *rect* to be taken back off *canvas*."""
        self.redaction_removed.emit(canvas.index, rect)

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