"""ThumbnailBar — QListView with a QAbstractListModel over DocumentModel.

Thumbnails are rendered by the same RenderWorker as the main view, at a low
zoom, and land in a small LRU cache of QImage. The conversion to QPixmap
happens in the model's data() because QPixmap is GUI-thread-only.

The bar is also the ROUTER for thumbnail renders. It remembers every key it
asked for (``_pending``), so a render that arrives for a document we no
longer show -- or for a rotation that has since been undone -- is discarded
as stale instead of being cached against the wrong row.

Two things this widget deliberately does NOT do:
  - it never reorders itself (drag & drop is translated into a MovePage
    command emitted as `move_requested`), because a view that reorders
    itself and a model that doesn't would silently diverge;
  - it never touches PyMuPDF: every render goes through the worker's signals.
"""

from collections import OrderedDict

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QListView, QWidget

from ..model.document import DocumentModel, PageItem
from ..rendering.worker import RenderRequest

# Thumbnails are rendered at this logical scale.
THUMB_ZOOM = 0.2

THUMB_W, THUMB_H = 100, 140

# Module-level invalid index: avoids a function call in argument defaults
# (ruff B008) while keeping the standard Qt model signature.
_INVALID = QModelIndex()


def thumb_key(item: PageItem, zoom: float = THUMB_ZOOM, dpr: float = 1.0) -> tuple:
    """Cache/render key for a thumbnail.

    ("thumb", source_id, source_index, rotation, zoom, dpr) -- source_id is
    included so a merged document cannot reuse another source's pixmap.

    The rotation in the key is the USER offset, which is what the renderer
    applies on top of the page's own /Rotate. It is part of the key so a
    rotated page re-renders instead of reusing a stale thumbnail.
    """
    return (
        "thumb",
        item.source_id,
        item.source_index,
        item.rotation,
        zoom,
        dpr,
    )


class ThumbnailModel(QAbstractListModel):
    """Thin model wrapping the DocumentModel's page list."""

    SourceIndexRole = Qt.ItemDataRole.UserRole + 1
    SourceIdRole = Qt.ItemDataRole.UserRole + 2

    def __init__(
        self,
        doc_model: DocumentModel,
        cache: OrderedDict[tuple, object],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._doc_model = doc_model
        self._cache = cache  # shared LRU: render key → QImage
        self._dpr = 1.0
        self._doc_model.changed.connect(self._on_doc_changed)
        # An in-place edit (rotation, or the undo of one) keeps the row
        # count, so the whole model must NOT be reset -- but the row must be
        # repainted, because its decoration is keyed on the rotation and the
        # view would otherwise keep showing the old orientation.
        self._doc_model.page_changed.connect(self._on_page_changed)

    def set_device_pixel_ratio(self, dpr: float) -> None:
        """Keep thumbnail keys consistent with the device we render for."""
        self._dpr = dpr or 1.0

    def _on_doc_changed(self) -> None:
        self.beginResetModel()
        self.endResetModel()

    def _on_page_changed(self, row: int) -> None:
        """Repaint one row after an in-place edit (rotation, or its undo)."""
        if 0 <= row < self.rowCount():
            index = self.createIndex(row, 0)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])

    def rowCount(self, parent=_INVALID) -> int:
        return self._doc_model.page_count

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._doc_model.pages[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"Pagina {index.row() + 1}"
        if role == self.SourceIndexRole:
            return item.source_index
        if role == self.SourceIdRole:
            return item.source_id
        if role == Qt.ItemDataRole.DecorationRole:
            key = thumb_key(item, THUMB_ZOOM, self._dpr)
            img = self._cache.get(key)
            if img is not None:
                return QPixmap.fromImage(img)
            icon = QIcon.fromTheme("document-page")
            return icon if not icon.isNull() else None
        return None

    def index(self, row, column=0, parent=_INVALID):
        if column != 0 or row < 0 or row >= len(self._doc_model.pages):
            return _INVALID
        return self.createIndex(row, column)


class ThumbnailBar(QListView):
    """Thumbnail sidebar with async rendering and command-based reordering."""

    move_requested = Signal(int, int)   # (from_row, to_row) → MovePage
    page_selected = Signal(int)         # row the user clicked

    def __init__(
        self,
        doc_model,
        worker,
        cache,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._doc_model = doc_model
        self._worker = worker
        self._cache = cache
        self._model = ThumbnailModel(doc_model, cache, self)
        # Render keys this bar is waiting for → destination row. Doubles as
        # the stale-result filter: a key that is not in here is not ours.
        self._pending: dict[tuple, int] = {}
        self._dpr = 1.0
        # Last row the user (or a command) selected. A model reset clears the
        # current index, so this is what survives a delete/reorder and lets
        # the selection be restored instead of silently dying.
        self._last_row = 0
        self._restoring = False
        self.setModel(self._model)
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(THUMB_W + 20, THUMB_H + 40))
        self.setIconSize(QSize(THUMB_W, THUMB_H))
        self.setMovement(QListView.Movement.Static)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # Drag & drop: we accept the gesture but handle the reorder ourselves.
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListView.DragDropMode.InternalMove)

        # Structural changes (delete/reorder) refresh the list, restore the
        # selection and request whatever thumbnails are still missing.
        self._doc_model.changed.connect(self._on_doc_changed)
        # In-place changes (rotation, including its undo) keep the row but
        # invalidate its thumbnail: the render key embeds the rotation, so
        # the image rendered before the rotation can never be reused.
        self._doc_model.page_changed.connect(self._on_page_changed)
        # This widget owns the thumbnail half of the worker's output.
        self._worker.rendered.connect(self._on_rendered)
        self._worker.render_failed.connect(self._on_render_failed)
        # Thumbnails are loaded lazily as the user scrolls.
        self.verticalScrollBar().valueChanged.connect(lambda _v: self.refresh())

    # ------------------------------------------------------------------ #
    #  Thumbnails
    # ------------------------------------------------------------------ #

    def refresh(self) -> None:
        """Request thumbnails for the rows near the viewport.

        Deliberately NOT "every page": on a 300-page document, queueing 300
        renders would keep the worker busy for seconds and delay the page the
        user is actually looking at. Rows are requested as they scroll into
        view instead.
        """
        self._request_visible_thumbnails()

    def _request_row(self, row: int) -> None:
        """Ask the worker for one row's thumbnail, at most once per key.

        Without the ``_pending`` guard every scroll tick would re-emit the
        requests for the whole visible band, filling the worker's queue with
        duplicates and delaying the page the user is waiting for.
        """
        pages = self._doc_model.pages
        if not 0 <= row < len(pages):
            return
        item = pages[row]
        key = thumb_key(item, THUMB_ZOOM, self._dpr)
        if key in self._cache or key in self._pending:
            return
        self._pending[key] = row
        self._worker.render_requested.emit(
            RenderRequest(
                key,
                self._doc_model.source_for(item),
                item.source_index,
                THUMB_ZOOM * self._dpr,
                item.rotation,
            )
        )

    def _on_rendered(self, key: tuple, image) -> None:
        """Route a thumbnail render back to its row, or drop it as stale."""
        row = self._pending.pop(key, None)
        if row is None:
            # Not ours: either a page render (the PageView handles those) or
            # a request issued for a document we no longer show.
            return
        image.setDevicePixelRatio(key[5])  # crisp on HiDPI
        self._cache[key] = image
        # Repaint just the row that got its picture.
        index = self._model.index(row, 0)
        if index.isValid():
            self._model.dataChanged.emit(
                index, index, [Qt.ItemDataRole.DecorationRole]
            )

    def _on_render_failed(self, key: tuple) -> None:
        """Forget a failed request so the row can be retried later."""
        self._pending.pop(key, None)

    def _on_page_changed(self, row: int) -> None:
        """Drop a page's stale thumbnail after an in-place edit.

        The render key embeds the user rotation, so the entry produced before
        the rotation is unreachable by ``data()`` — it would just sit in the
        LRU until it aged out, once per rotation. Dropping it is what keeps
        rotating a page back and forth from leaking an image each time.
        """
        pages = self._doc_model.pages
        if not 0 <= row < len(pages):
            return
        item = pages[row]
        stale = [
            key
            for key in self._cache
            if _is_stale_thumb_key(key, item)
        ]
        for key in stale:
            del self._cache[key]
        # A render of the OLD rotation may still be in flight. Forget it, so
        # it is discarded on arrival instead of repainting the row with the
        # orientation the user just undid.
        for key in [k for k in self._pending if _is_stale_thumb_key(k, item)]:
            del self._pending[key]
        # Ask for the new one only if it is on screen; otherwise the next
        # refresh() (on scroll) will pick it up.
        self._request_visible_thumbnails()

    def _on_doc_changed(self) -> None:
        """Handle a structural change: delete, reorder, open, merge."""
        self._pending.clear()  # rows have moved; old deliveries are stale
        self.refresh()
        # beginResetModel/endResetModel cleared the current index. Without
        # restoring it, the first delete would silently kill the selection
        # and Ctrl+R would act on nothing until the user clicked again.
        row = min(self._last_row, self._model.rowCount() - 1)
        if row >= 0:
            self._restoring = True
            try:
                self.set_current_row(row)
            finally:
                self._restoring = False

    def _visible_rows(self) -> list[int]:
        """Rows whose cell intersects the viewport, plus a margin.

        Walks down from the row under the top of the viewport, so the cost is
        O(visible rows) rather than O(pages) on every scroll tick. If layout
        has not happened yet, fall back to the first screenful so the initial
        view is never left grey.
        """
        count = self._model.rowCount()
        if count == 0:
            return []
        cell_h = self.gridSize().height() or 1
        per_screen = max(1, self.viewport().height() // cell_h)
        area = self.viewport().rect().adjusted(0, -2 * cell_h, 0, 2 * cell_h)
        first = self.indexAt(area.topLeft())
        if not first.isValid():
            return list(range(min(count, per_screen + 2)))
        rows = []
        for row in range(first.row(), min(count, first.row() + per_screen + 4)):
            rect = self.visualRect(self._model.index(row, 0))
            if rect.isValid() and area.intersects(rect):
                rows.append(row)
            elif rows:
                break
        if not rows:
            return list(range(min(count, per_screen + 2)))
        return rows

    def _request_visible_thumbnails(self) -> None:
        """Ask the worker for the thumbnails in view that we don't have yet."""
        self._dpr = self.devicePixelRatioF() or 1.0
        # The model builds the same keys from data(), so its dpr must match
        # the one used to request renders.
        self._model.set_device_pixel_ratio(self._dpr)
        for row in self._visible_rows():
            self._request_row(row)

    # ------------------------------------------------------------------ #
    #  Selection
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self) -> None:
        row = self.current_row()
        if row < 0:
            return
        self._last_row = row
        if self._restoring:
            # Programmatic restore (after a model reset): do not drag the
            # main view to this row, the user is already where they were.
            return
        self.page_selected.emit(row)

    def current_row(self) -> int:
        index = self.currentIndex()
        return index.row() if index.isValid() else -1

    def set_current_row(self, row: int) -> None:
        if 0 <= row < self._model.rowCount():
            self.setCurrentIndex(self._model.index(row, 0))

    # ------------------------------------------------------------------ #
    #  Drag & drop → command
    # ------------------------------------------------------------------ #

    @staticmethod
    def drop_target_row(from_row: int, target_row: int, below: bool) -> int:
        """Final index for a drop, in the list WITHOUT the dragged row.

        MovePage pops and then re-inserts, so the destination must be
        expressed in the shortened list: when the target sits after the
        dragged row it shifts up by one once the row is popped. Without that
        correction, dragging a row downwards onto the UPPER half of X would
        still land it after X.
        """
        target = target_row if target_row < from_row else target_row - 1
        return target + 1 if below else target

    def dropEvent(self, event) -> None:
        """Translate a drag into a MovePage request instead of self-reordering.

        Letting QListView perform an InternalMove would reorder the view's
        rows without touching DocumentModel.pages, so the sidebar and the
        real document would disagree. We emit the intent and let the main
        window push an undoable command.
        """
        from_row = self.current_row()
        target = self.indexAt(event.position().toPoint())
        target_row = target.row() if target.isValid() else self._model.rowCount() - 1
        # Dropping past the last row always means "after it"; on a row, Qt
        # already tells us which half the pointer is over.
        below = (
            not target.isValid()
            or self.dropIndicatorPosition()
            == QListView.DropIndicatorPosition.BelowItem
        )
        # We handled the gesture; the default InternalMove must not run.
        event.ignore()
        if from_row < 0 or target_row < 0:
            return
        to_row = self.drop_target_row(from_row, target_row, below)
        if to_row == from_row:
            return
        self.move_requested.emit(from_row, to_row)


def _is_stale_thumb_key(key: tuple, item: PageItem) -> bool:
    """True for a thumbnail key of *item* rendered at a different rotation."""
    return (
        len(key) == 6
        and key[0] == "thumb"
        and key[1] == item.source_id
        and key[2] == item.source_index
        and key[3] != item.rotation
    )


class ThumbnailCache(OrderedDict):
    """LRU cache for thumbnail QImages.

    Genuinely LRU, not FIFO: every access through ``get`` or ``[]`` moves the
    entry to the most-recent end, because the rows around the viewport are
    re-read on every repaint and are exactly the ones worth keeping.
    """

    def __init__(self, maxsize: int = 60) -> None:
        super().__init__()
        self._maxsize = maxsize

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def get(self, key, default=None):
        if key in self:
            self.move_to_end(key)
            return super().__getitem__(key)
        return default

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self._maxsize:
            self.popitem(last=False)
