"""ThumbnailBar — QListView with a QAbstractListModel over DocumentModel.

Thumbnails are rendered by the same RenderWorker as the main view, at a low
zoom, and land in a small LRU cache of QImage. The conversion to QPixmap
happens in the model's data() because QPixmap is GUI-thread-only.

Two things this widget deliberately does NOT do:
  - it never reorders itself (drag & drop is translated into a MovePage
    command emitted as `move_requested`), because a view that reorders
    itself and a model that doesn't would silently diverge;
  - it never touches fitz: every render goes through the worker's signals.
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

    def set_device_pixel_ratio(self, dpr: float) -> None:
        """Keep thumbnail keys consistent with the device we render for."""
        self._dpr = dpr or 1.0

    def _on_doc_changed(self) -> None:
        self.beginResetModel()
        self.endResetModel()

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

    def index_for_page(self, source_id: int, source_index: int) -> QModelIndex:
        """Find the model index for a page identity (may differ from row).

        Both parts are needed: after a merge, two pages routinely share a
        source_index and only (source_id, source_index) identifies one.
        """
        for row, item in enumerate(self._doc_model.pages):
            if item.source_id == source_id and item.source_index == source_index:
                return self.createIndex(row, 0)
        return _INVALID


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

        # Structural changes (delete/reorder) refresh the list and request
        # whatever thumbnails are still missing.
        self._doc_model.changed.connect(self.refresh)
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

    def _visible_rows(self) -> list[int]:
        """Rows whose cell intersects the viewport, plus a margin.

        If layout has not happened yet (the model was just reset), fall back
        to the first screenful so the initial view is never left grey.
        """
        count = self._model.rowCount()
        if count == 0:
            return []
        cell_h = self.gridSize().height() or 1
        area = self.viewport().rect().adjusted(0, -2 * cell_h, 0, 2 * cell_h)
        rows = []
        for row in range(count):
            rect = self.visualRect(self._model.index(row, 0))
            if rect.isValid() and area.intersects(rect):
                rows.append(row)
        if not rows:
            per_screen = max(1, self.viewport().height() // cell_h)
            rows = list(range(min(count, per_screen + 2)))
        return rows

    def _request_visible_thumbnails(self) -> None:
        """Ask the worker for the thumbnails in view that we don't have yet."""
        dpr = self.devicePixelRatioF() or 1.0
        # The model builds the same keys from data(), so its dpr must match
        # the one used to request renders.
        self._model.set_device_pixel_ratio(dpr)
        pages = self._doc_model.pages
        for row in self._visible_rows():
            item = pages[row]
            key = thumb_key(item, THUMB_ZOOM, dpr)
            if key not in self._cache:
                self._worker.render_requested.emit(
                    RenderRequest(
                        key,
                        self._doc_model.source_for(item),
                        item.source_index,
                        THUMB_ZOOM * dpr,
                        item.rotation,
                    )
                )

    # ------------------------------------------------------------------ #
    #  Selection
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self) -> None:
        row = self.current_row()
        if row >= 0:
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

    def dropEvent(self, event) -> None:
        """Translate a drag into a MovePage request instead of self-reordering.

        Letting QListView perform an InternalMove would reorder the view's
        rows without touching DocumentModel.pages, so the sidebar and the
        real document would disagree. We emit the intent and let the main
        window push an undoable command.
        """
        from_row = self.current_row()
        pos = event.position().toPoint()
        target = self.indexAt(pos)
        to_row = target.row() if target.isValid() else self._model.rowCount() - 1
        # We handled the gesture; the default InternalMove must not run.
        event.ignore()
        if from_row < 0 or to_row < 0 or from_row == to_row:
            return
        self.move_requested.emit(from_row, to_row)


class ThumbnailCache(OrderedDict):
    """Simple LRU cache for thumbnail QImages."""

    def __init__(self, maxsize: int = 60) -> None:
        super().__init__()
        self._maxsize = maxsize

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self._maxsize:
            self.popitem(last=False)