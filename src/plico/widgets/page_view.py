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

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtGui import QPalette as QPaletteColor
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..model.document import PageItem
from ..model.forms import CHECKBOX, CHECKED, RADIO, TEXT, UNCHECKED, Field
from ..model.redact import RedactionRect, map_point, map_rect
from ..model.textedit import TextEdit, TextSpan
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

# Handles of an existing mark: a square this wide sits on each corner, and a
# press within that distance of a corner resizes instead of moving. In pixels,
# because it is a target for a mouse and must not shrink with the zoom.
MARK_HANDLE = 8.0
# A mark smaller than this (in points) hides nothing worth hiding.
MIN_MARK = 2.0

# Form fields, drawn over the page: a light wash says "there is a field here",
# and the selected one is picked out so that the page and the panel agree.
FIELD_WASH = QColor(64, 120, 200, 26)
FIELD_BORDER = QColor(64, 120, 200, 150)
FIELD_SELECTED_WASH = QColor(230, 145, 40, 40)
FIELD_SELECTED_BORDER = QColor(214, 138, 48)
FIELD_TEXT = QColor(20, 20, 20)

# Text editing: an edited span is outlined while the tool is on, so the user
# can find what was changed; the replacement itself is always painted.
TEXT_EDIT_BORDER = QColor(46, 140, 87, 170)
TEXT_EDIT_REFUSED = "border: 2px solid #d63030;"
# Why a click opened no editor, written on the page next to the click. A
# widget of the page and not a QToolTip: a tooltip is a separate window, and
# on Wayland it may simply not appear -- which is how the first two versions
# of this message went unseen.
NOTICE_STYLE = (
    "background-color: #fff4ce; color: #3d3000; border: 1px solid #d9b44a;"
    "border-radius: 4px; padding: 4px 8px;"
)
NOTICE_MS = 4000
# The preview font is laid out at this pixel size and then scaled by the
# painter: QFont sizes are integers, and a 10.5 pt span at 150% would round.
_PREVIEW_PX = 100

# get_text("dict") span flags, for the preview font.
_ITALIC = 1 << 1
_SERIF = 1 << 2
_MONO = 1 << 3
_BOLD = 1 << 4


def _preview_font(span: TextSpan) -> QFont:
    """A Qt font that looks like *span*'s: its family when installed, else the style.

    "LiberationSerif-Bold" names the family "Liberation Serif"; when Qt does
    not have it, the style hint picks a serif, sans or monospaced stand-in
    instead of whatever the default happens to be.
    """
    name = span.font.split("+")[-1].split("-")[0]
    family = "".join(
        f" {c}" if c.isupper() and i and not name[i - 1].isupper() else c
        for i, c in enumerate(name)
    )
    font = QFont(family)
    if span.flags & _MONO:
        font.setStyleHint(QFont.StyleHint.TypeWriter)
    elif span.flags & _SERIF:
        font.setStyleHint(QFont.StyleHint.Serif)
    else:
        font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setBold(bool(span.flags & _BOLD))
    font.setItalic(bool(span.flags & _ITALIC))
    font.setPixelSize(_PREVIEW_PX)
    return font


def _span_color(span: TextSpan) -> QColor:
    c = span.color
    return QColor((c >> 16) & 255, (c >> 8) & 255, c & 255)


class _SpanEditor(QLineEdit):
    """The line edit that floats over a span while the user corrects it.

    Enter confirms and Esc cancels. Esc has to be claimed from the window:
    the window binds Esc to "leave the tool", and a window shortcut wins over
    the focused widget unless the widget accepts the ShortcutOverride first.
    Losing the focus to another widget of the window confirms, like leaving
    a form field; losing it because the whole window was left does not, so
    switching to another program for a second does not close the editor.
    """

    committed = Signal()
    cancelled = Signal()
    focus_left = Signal()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride and event.key() == Qt.Key.Key_Escape:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.committed.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if event.reason() not in (
            Qt.FocusReason.ActiveWindowFocusReason,
            Qt.FocusReason.PopupFocusReason,
        ):
            self.focus_left.emit()


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
        # A mark being moved or resized: (position in the page's list, the
        # corner handle grabbed or None for a move, the rectangle as it was
        # before the gesture started, and where the grab happened in page
        # space -- the last one so a move keeps the distance the user grabbed).
        self._adjust: tuple[int, str | None, RedactionRect, tuple[float, float]] | None = None
        # Background colour behind each edited span, sampled from the render
        # it was painted over. Keyed by the render too: a new pixmap (zoom,
        # rotation) may sample differently, and toImage() is too costly to
        # run on every repaint.
        self._backgrounds: dict[tuple[TextSpan, tuple | None], QColor] = {}

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
        # Text edits are always painted: the page must read the way it will
        # be saved, tool or no tool.
        self._paint_text_edits(painter)
        if self._view.redaction_mode():
            self._paint_redactions(painter)
        elif self._view.selection_mode():
            self._paint_selection(painter)
        painter.end()

    def _page_transform(self) -> QTransform:
        """Page space → widget pixels, user and base rotation included.

        With this on the painter, a span is drawn with its own page-space
        numbers -- baseline, size, box -- and comes out turned and scaled
        exactly like the render under it.
        """
        canvas = self.canvas
        assert canvas is not None
        a, b, c, d, e, f = canvas.item.view_matrix()
        s = self._scale()
        return QTransform(a * s, b * s, c * s, d * s, e * s, f * s)

    def _background(self, span: TextSpan) -> QColor:
        """The page colour around *span*, sampled at a corner of its box.

        A box corner sits above the ascenders or left of the first glyph, so
        it shows what the text was printed on: white paper, a shaded table
        cell, a coloured banner.
        """
        canvas = self.canvas
        assert canvas is not None
        key = (span, canvas.current_key)
        cached = self._backgrounds.get(key)
        if cached is not None:
            return cached
        colour = QColor("white")
        pixmap = self.pixmap()
        if not pixmap.isNull():
            image = pixmap.toImage()
            ratio = pixmap.devicePixelRatio()
            corner = self._rect_pixels(span.bbox).topLeft() + QPointF(1.0, 1.0)
            x, y = int(corner.x() * ratio), int(corner.y() * ratio)
            if 0 <= x < image.width() and 0 <= y < image.height():
                colour = image.pixelColor(x, y)
        self._backgrounds[key] = colour
        return colour

    def _paint_text_edits(self, painter: QPainter) -> None:
        """Paint each replacement over the text it replaces.

        A preview, not the file: the font is Qt's closest match and the save
        decides the exact one. What it does guarantee is the place, the size,
        the colour and the fact that the old words are no longer visible.
        """
        canvas = self.canvas
        assert canvas is not None
        if not canvas.item.text_edits:
            return
        painter.save()
        painter.setTransform(self._page_transform())
        outline = self._view.text_mode()
        for edit in canvas.item.text_edits:
            self._paint_text_edit(painter, edit, outline)
        painter.restore()

    def _paint_text_edit(self, painter: QPainter, edit: TextEdit, outline: bool) -> None:
        span = edit.span
        x0, y0, x1, y1 = span.bbox
        box = QRectF(x0, y0, x1 - x0, y1 - y0)
        painter.fillRect(box, self._background(span))
        if edit.new_text:
            font = _preview_font(span)
            unit = span.size / _PREVIEW_PX
            needed = QFontMetricsF(font).horizontalAdvance(edit.new_text) * unit
            available = span.width + span.room
            fit = min(1.0, available / needed) if needed > 0 else 1.0
            painter.save()
            painter.translate(span.origin[0], span.origin[1])
            painter.scale(unit * fit, unit * fit)
            painter.setFont(font)
            painter.setPen(QPen(_span_color(span)))
            painter.drawText(QPointF(0.0, 0.0), edit.new_text)
            painter.restore()
        if outline:
            pen = QPen(TEXT_EDIT_BORDER, 0)  # cosmetic: one pixel at any zoom
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(box)

    def _paint_redactions(self, painter: QPainter) -> None:
        canvas = self.canvas
        assert canvas is not None
        for rect in canvas.item.redactions:
            area = self._to_pixels(rect)
            painter.fillRect(area, QBrush(REDACTION_FILL))
            painter.setPen(QPen(REDACTION_BORDER, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(area)
            # Drawn only here, and this is only ever called while a tool that
            # works on marks is on: the corners are what a press can grab, so
            # showing them is the only way to tell that a mark can be moved
            # and resized instead of only removed.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(REDACTION_BORDER))
            half = MARK_HANDLE / 2
            for corner in (
                area.topLeft(),
                area.topRight(),
                area.bottomLeft(),
                area.bottomRight(),
            ):
                painter.drawRect(
                    QRectF(corner.x() - half, corner.y() - half, MARK_HANDLE, MARK_HANDLE)
                )
        if self._drag_from is not None and self._drag_to is not None:
            painter.setPen(QPen(REDACTION_DRAG, 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(self._drag_from, self._drag_to).normalized())

    def _paint_selection(self, painter: QPainter) -> None:
        """Light up the words the drag is covering.

        The highlight is the point of the tool: it shows WHICH words will go,
        and the answer is whole words, not the rectangle the mouse traced.
        The marks already made are painted afterwards, on top.
        """
        canvas = self.canvas
        assert canvas is not None
        if self._drag_from is not None and self._drag_to is not None:
            area = QRectF(self._drag_from, self._drag_to).normalized()
            top_left = self._to_page(area.topLeft())
            bottom_right = self._to_page(area.bottomRight())
            words = self._view.words_under(canvas, *top_left, *bottom_right)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(REDACTION_FILL))
            for rect in words:
                painter.drawRect(self._to_pixels(rect))
        self._paint_redactions(painter)

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
        picked = self._view.selected_field()
        for field in item.form_fields:
            area = self._rect_pixels(field.rect)
            is_selected = picked == (canvas.index, field.name)
            painter.fillRect(
                area, QBrush(FIELD_SELECTED_WASH if is_selected else FIELD_WASH)
            )
            thickness = 2 if is_selected else 1
            border = FIELD_SELECTED_BORDER if is_selected else FIELD_BORDER
            painter.setPen(QPen(border, thickness))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(area)
            text = self._value_shown(item, field)
            if text:
                self._paint_value(painter, area, field, text)

    @staticmethod
    def _value_shown(item: PageItem, field: Field) -> str:
        value = item.form_values.get(field.name, field.value)
        if field.kind == CHECKBOX:
            # A checkbox has no text of its own: it is ticked, or it is not.
            return "X" if value not in ("", UNCHECKED) else ""
        return value

    @staticmethod
    def _paint_value(
        painter: QPainter, area: QRectF, field: Field, text: str
    ) -> None:
        """Write *text* inside *area*, clipped so it can never spill out."""
        inside = area.adjusted(3.0, 2.0, -3.0, -2.0)
        if inside.width() <= 1.0 or inside.height() <= 1.0:
            return
        painter.save()
        painter.setClipRect(inside)
        painter.setPen(QPen(FIELD_TEXT))
        font = painter.font()
        font.setPixelSize(max(6, min(int(inside.height() * 0.7), 18)))
        painter.setFont(font)
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if field.multiline:
            painter.drawText(inside, flags | int(Qt.TextFlag.TextWordWrap), text)
        else:
            painter.drawText(inside, flags, text)
        painter.restore()

    # -- the gesture ---------------------------------------------------- #

    def _select_field_under(self, point: QPointF) -> None:
        """Edit the form field under *point*, in place where that is possible.

        A single-line text field opens its editor right on the page, and a
        checkbox flips where it was clicked, while a radio button chooses the
        option it stands for: all three are what the user means by clicking
        them. Everything else -- a choice, a multiline or a read-only field --
        is selected in the panel, which is where an editor for those kinds
        lives: it can offer the options, grow, or say no.

        Last match wins, because that is the one painted on top.
        """
        canvas = self.canvas
        if canvas is None:
            return
        for field in reversed(canvas.item.form_fields):
            if not self._rect_pixels(field.rect).contains(point):
                continue
            if field.editable and field.kind == TEXT and not field.multiline:
                self._view.begin_field_edit(canvas, field)
            elif field.editable and field.kind == CHECKBOX:
                self._view.toggle_field(canvas, field)
            elif field.editable and field.kind == RADIO:
                self._view.choose_field(canvas, field)
            else:
                self._view.report_field_click(canvas.index, field.name)
            return

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self._view.text_mode():
            canvas = self.canvas
            if canvas is not None:
                self._view.begin_text_edit(
                    canvas, *self._to_page(event.position()), event.position()
                )
            return
        if not (self._view.redaction_mode() or self._view.selection_mode()):
            self._select_field_under(event.position())
            super().mousePressEvent(event)
            return
        hit = self._mark_under(event.position())
        if hit is not None:
            position, corner = hit
            canvas = self.canvas
            assert canvas is not None
            self._adjust = (
                position,
                corner,
                canvas.item.redactions[position],
                self._to_page(event.position()),
            )
        self._drag_from = event.position()
        self._drag_to = self._drag_from
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_from is None:
            super().mouseMoveEvent(event)
            return
        self._drag_to = event.position()
        if self._adjust is not None:
            self._move_mark(event.position())
        self.update()

    def _mark_under(self, point: QPointF) -> tuple[int, str | None] | None:
        """The mark under *point*, and the corner handle it was grabbed by.

        Last match first, so the mark the user sees is the one that answers.
        A corner grabs a resize; anywhere else inside the mark moves the whole
        rectangle. ``None`` means the click was outside every mark, which is
        how a new zone gets drawn.
        """
        canvas = self.canvas
        if canvas is None:
            return None
        for position in range(len(canvas.item.redactions) - 1, -1, -1):
            area = self._to_pixels(canvas.item.redactions[position])
            for name, corner in (
                ("tl", area.topLeft()),
                ("tr", area.topRight()),
                ("bl", area.bottomLeft()),
                ("br", area.bottomRight()),
            ):
                if (
                    abs(point.x() - corner.x()) <= MARK_HANDLE
                    and abs(point.y() - corner.y()) <= MARK_HANDLE
                ):
                    return position, name
            if area.contains(point):
                return position, None
        return None

    def _move_mark(self, point: QPointF) -> None:
        """Show an adjustment as it happens.

        The model is written here only so the page repaints while the mouse
        moves: the command that makes the change undoable is pushed when the
        drag ends, and until then ``forget_drag()`` can put everything back.
        """
        canvas = self.canvas
        if canvas is None or self._adjust is None:
            return
        position, corner, before, start = self._adjust
        now = self._to_page(point)
        width, height = canvas.item.unrotated_size
        if corner is None:
            # Keep the size and slide it back inside the page if the mouse
            # leaves it, so a mark cannot be pushed off the edge.
            dx = min(max(now[0] - start[0], -before.x0), width - before.x1)
            dy = min(max(now[1] - start[1], -before.y0), height - before.y1)
            rect = before.translated(dx, dy)
        else:
            rect = before.with_corner(corner, now[0], now[1]).clamped_to(width, height)
        # A zone narrower than a point hides nothing: refusing the step leaves
        # the previous rectangle on screen instead of an unusable one.
        if rect.width < MIN_MARK or rect.height < MIN_MARK:
            return
        canvas.item.redactions[position] = rect

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_from is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        start = self._drag_from
        end = event.position()
        if self._adjust is not None:
            position, corner, before, _start = self._adjust
            canvas = self.canvas
            assert canvas is not None
            # What the drag wrote straight into the model so the page could
            # follow the mouse -- read before forget_drag() puts the old
            # rectangle back. The command must own the change: letting redo()
            # apply the new one keeps the whole gesture a single undo step,
            # and a click must leave nothing behind at all. (Reading it after
            # used to keep the few pixels a click had nudged the mark by, a
            # change no Ctrl+Z knew about.)
            after = canvas.item.redactions[position]
            self.forget_drag()
            self.update()
            if (end - start).manhattanLength() < CLICK_SLOP:
                # A click on a mark still takes it back: moving it is a drag.
                for rect in reversed(canvas.item.redactions):
                    if self._to_pixels(rect).contains(end):
                        self._view.forget_redaction(canvas, rect)
                        break
                return
            if after == before:
                return
            self._view.adjust_redaction(canvas, position, before, after, corner is None)
            return
        self.forget_drag()
        self.update()
        canvas = self.canvas
        assert canvas is not None
        if (end - start).manhattanLength() < CLICK_SLOP:
            # A click rather than a drag: take back the mark under the cursor,
            # if there is one. Topmost first, so the visible one wins.
            for rect in reversed(canvas.item.redactions):
                if self._to_pixels(rect).contains(end):
                    self._view.forget_redaction(canvas, rect)
                    break
            return
        if self._view.selection_mode():
            self._view.commit_selection(canvas, *self._to_page(start), *self._to_page(end))
            return
        self._view.commit_redaction(canvas, *self._to_page(start), *self._to_page(end))

    def forget_drag(self) -> None:
        """Drop the rectangle being dragged, if any (a tool was left).

        An adjustment still in the air is put back the way it was: the drag
        has written into the model only to show itself, and a change that no
        Ctrl+Z can take back must not survive a gesture nobody finished.
        """
        if self._adjust is not None:
            canvas = self.canvas
            position, _corner, before, _start = self._adjust
            if canvas is not None and position < len(canvas.item.redactions):
                canvas.item.redactions[position] = before
        self._adjust = None
        self._drag_from = None
        self._drag_to = None


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
    # Words of the source page, read once when a selection first asks for
    # them: the sources are read-only until a save, and a mouse move must not
    # reopen a file.
    words: list[RedactionRect] | None = None


# --- PageView ----------------------------------------------------------- #

class PageView(QScrollArea):
    """Central view: scrollable, zoomable, HiDPI-aware page rendering."""

    # (page index, RedactionRect in page space). The view never mutates the
    # model: it reports the gesture and MainWindow pushes an undoable command.
    redaction_added = Signal(int, object)
    redaction_removed = Signal(int, object)
    # (page index, position in that page's list, the rectangle before, the one
    # after, whether the mark was moved rather than resized): a mark the user
    # nudged with the mouse. One signal for the whole gesture, so it is one
    # step to undo.
    redaction_adjusted = Signal(int, int, object, object, bool)
    # (page index, list of RedactionRect): the words a selection covered. One
    # signal for the whole selection, because the window makes it ONE undo
    # step: words are what the user picked, not the rectangle they dragged.
    selection_made = Signal(int, object)
    # (page index, field name): a click landed on a form field drawn on the
    # page. The view fills nothing — it only says where the user pointed.
    field_clicked = Signal(int, str)
    # (page index, field name, value): a form field was filled in on the page
    # itself — typed into, or a checkbox flipped. Same shape for both, because
    # the window records both with the same command.
    field_value_committed = Signal(int, str, str)
    # (page index, TextSpan, new text): the user confirmed a correction that
    # check_text_edit() accepted. The window turns it into an EditText.
    text_edited = Signal(int, object, str)
    # Why the text tool did nothing: a correction the save could not write,
    # or a click that found no editable text. Shown in the status bar.
    text_edit_refused = Signal(str)

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
        self._selection_mode = False
        self._text_mode = False
        # The editor open over a span, and which span of which page it edits.
        self._editor: _SpanEditor | None = None
        self._editing: tuple[_Canvas, TextSpan] | None = None
        # The same, for a form field filled in on the page: a text field gets
        # an editor exactly where the field is drawn.
        self._field_editor: _SpanEditor | None = None
        self._editing_field: tuple[_Canvas, Field] | None = None
        # The note that says why a click opened no editor, and its timer.
        self._notice: QLabel | None = None
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._hide_notice)
        # The (page index, field name) the form panel is editing, so the field
        # can be picked out on the page. None when nothing is selected.
        self._selected_field: tuple[int, str] | None = None
        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._cache_bytes = 0
        # Requests are held back while the GUI thread opens a modal dialog
        # whose answer the worker cannot produce on its own.
        self._paused = False

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
        # The page list changed shape: the editor's page index may now point
        # elsewhere, and its label may be about to go.
        self._close_text_editor()
        self._close_field_editor()
        self._hide_notice()
        first_page = self._first_visible_page()
        self._items = list(self._model.pages)
        # No size list to copy: each item carries its own oriented size.
        self._rebuild_canvases()
        self._relayout()
        self._anchor_on(first_page)

    def _on_page_changed(self, row: int) -> None:
        """A page changed in place (rotation, redaction, OCR): re-measure, repaint."""
        self.refresh_geometry()
        # A redaction changes no size, so setFixedSize() leaves the label
        # exactly as it was and nothing would repaint without this nudge.
        if 0 <= row < len(self._canvases):
            canvas = self._canvases[row]
            # The OCR layer is text as well, and it lives on the item rather
            # than in the file: a list of words read before it was recognised
            # would leave that page impossible to select.
            canvas.words = None
            canvas.label.update()

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

    def _tool_cursor(self) -> Qt.CursorShape:
        if self._text_mode or self._selection_mode:
            return Qt.CursorShape.IBeamCursor
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

    def begin_field_edit(self, canvas: _Canvas, field: Field) -> None:
        """Fill a form field in where it is drawn, instead of in the panel.

        Only single-line text fields arrive here: a multiline one needs a box
        that grows, and a choice needs its list of options -- the panel has
        both, and it is one glance away from the page.
        """
        self._commit_field_edit()
        self._hide_notice()
        item = canvas.item
        editor = _SpanEditor(canvas.label)
        # The model's value, not the widget's: before a save the model is the
        # only thing that knows what will end up in the file.
        editor.setText(item.form_values.get(field.name, field.value))
        editor.committed.connect(self._commit_field_edit)
        editor.cancelled.connect(self._close_field_editor)
        # Leaving the field confirms, like leaving a form box on a web page:
        # the value is what the user sees, and there is a Ctrl+Z if it is not.
        editor.focus_left.connect(self._commit_field_edit)
        self._field_editor = editor
        self._editing_field = (canvas, field)
        self._place_field_editor()
        editor.show()
        editor.setFocus(Qt.FocusReason.MouseFocusReason)
        editor.selectAll()

    def toggle_field(self, canvas: _Canvas, field: Field) -> None:
        """Flip a checkbox where it was clicked."""
        current = canvas.item.form_values.get(field.name, field.value)
        self.field_value_committed.emit(
            canvas.index, field.name, UNCHECKED if current not in ("", UNCHECKED) else CHECKED
        )

    def choose_field(self, canvas: _Canvas, field: Field) -> None:
        """Choose the radio button that was clicked.

        A group of radio buttons all carry the same name, and each button
        stands for one option: which one was clicked is written in the button,
        so the click is the whole answer and there is nothing to type.
        """
        option = field.options[0] if field.options else ""
        if not option:
            return
        self.field_value_committed.emit(canvas.index, field.name, option)

    def _make_label(self) -> _PageLabel:
        label = _PageLabel(self)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setBackgroundRole(QPaletteColor.ColorRole.Base)
        label.setAutoFillBackground(True)
        label.setText(self.tr("Caricamento…"))
        label.setStyleSheet("background-color: #f0f0f0;")
        label.setCursor(self._tool_cursor())
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
                # Same page identity, but a different PageItem: after a save
                # the session reads the file it has just written, and the
                # words read from the old one describe a page that is gone.
                canvas.words = None
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

        # The editor is a child of its page, so scrolling moves it for free;
        # a new size or zoom has to move it explicitly.
        self._place_text_editor()

        # Request visible renders
        self._apply_pending_scroll()
        self._request_visible()

    def resizeEvent(self, event) -> None:
        self._relayout()
        super().resizeEvent(event)

    # ------------------------------------------------------------------ #
    #  Render on demand
    # ------------------------------------------------------------------ #

    def set_paused(self, paused: bool) -> None:
        """Hold render requests back, and let them go again when resumed.

        The window pauses the view while it opens a modal dialog whose answer
        the worker cannot produce by itself -- the password of an encrypted
        file. A request emitted in that window would be answered "failed", and
        nothing would ask for those pages again: the page would stay blank
        until the user scrolled it out of view and back. Releasing the pause
        re-requests everything visible, which is also what refreshes the pages
        that had already failed while the file was still locked.
        """
        self._paused = paused
        if not paused:
            self._request_visible()

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
        if self._paused or not self._canvases:
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
        self._cache_put(key, pix)
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

    def _cache_put(self, key, pix) -> None:
        """Store *pix* under *key*, keeping the byte budget honest.

        The same key can be put twice -- a page re-rendered after a failure,
        or after the window moved to a screen with another density -- and the
        entry it displaces still owns its bytes. Forgetting to give them back
        shrinks the budget by that much on every re-render, so the cache ends
        up evicting pages it could have kept.
        """
        displaced = self._cache.pop(key, None)
        if displaced is not None:
            self._cache_bytes -= displaced.width() * displaced.height() * 4
        # Re-inserting puts the key at the end, which is the recency order the
        # eviction below relies on.
        self._cache[key] = pix
        self._cache_bytes += pix.width() * pix.height() * 4
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
        # A field being filled in on the page is confirmed before the tool
        # takes the mouse over: the click that follows is a redaction.
        self._commit_field_edit()
        cursor = self._tool_cursor()
        for c in self._canvases:
            c.label.setCursor(cursor)
            # A mark moved with the mouse is in the model before the button is
            # released: leaving the tool mid-gesture has to put it back, or the
            # change would sit there with nothing to undo.
            c.label.forget_drag()
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

    def adjust_redaction(
        self,
        canvas: _Canvas,
        position: int,
        before: RedactionRect,
        after: RedactionRect,
        moved: bool,
    ) -> None:
        """A mark was moved or resized: report it, in page space.

        The view says only what the gesture was; the window decides what it
        means and pushes the command that makes it undoable.
        """
        self.redaction_adjusted.emit(canvas.index, position, before, after, moved)

    # ------------------------------------------------------------------ #
    #  Selecting text to redact
    # ------------------------------------------------------------------ #

    def selection_mode(self) -> bool:
        """Whether a drag on a page selects the words it covers."""
        return self._selection_mode

    def set_selection_mode(self, active: bool) -> None:
        """Turn the selection tool on or off, for every page at once."""
        self._selection_mode = bool(active)
        self._commit_field_edit()
        cursor = self._tool_cursor()
        for c in self._canvases:
            c.label.setCursor(cursor)
            c.label.forget_drag()
            c.label.update()

    def page_words(self, canvas: _Canvas) -> list[RedactionRect]:
        """The words of *canvas*, read once and kept on it.

        The source is read-only until a save, so the words cannot change
        while the document is open, and a mouse move must not reopen a file
        to draw the highlight. A canvas is rebuilt with its page, which is
        what discards the cache.
        """
        if canvas.words is None and self._model is not None:
            words: list[RedactionRect] = self._model.words_on(canvas.index)
            canvas.words = words
        return canvas.words or []

    def words_under(
        self, canvas: _Canvas, x0: float, y0: float, x1: float, y1: float
    ) -> list[RedactionRect]:
        """The words a page-space rectangle covers, as redaction rectangles.

        A redaction that follows whole words is a better redaction than the
        rectangle that was dragged: covering half a line would leave the rest
        of it readable, and a word caught by the edge would be cut in two.
        """
        width, height = canvas.item.unrotated_size
        rect = RedactionRect.from_corners(x0, y0, x1, y1).clamped_to(width, height)
        if rect.width < 1.0 or rect.height < 1.0:
            return []
        covered = [
            word
            for word in self.page_words(canvas)
            if word.x0 < rect.x1 and rect.x0 < word.x1 and word.y0 < rect.y1 and rect.y0 < word.y1
        ]
        if self._model is None:
            return covered
        # A word already marked would only add a second rectangle on the same
        # spot: one more undo step for a mark that changes nothing.
        fresh: list[RedactionRect] = self._model.unmarked(canvas.index, covered)
        return fresh

    def commit_selection(
        self, canvas: _Canvas, x0: float, y0: float, x1: float, y1: float
    ) -> None:
        """A selection was dragged on *canvas*: report the words it covered."""
        words = self.words_under(canvas, x0, y0, x1, y1)
        if words:
            self.selection_made.emit(canvas.index, words)
            return
        # An empty selection is not an error, but silence would look like one.
        self.text_edit_refused.emit(
            QCoreApplication.translate("PageView", "Nessuna parola nella selezione.")
        )

    def forget_redaction(self, canvas: _Canvas, rect: RedactionRect) -> None:
        """Ask for *rect* to be taken back off *canvas*."""
        self.redaction_removed.emit(canvas.index, rect)

    # ------------------------------------------------------------------ #
    #  Text editing
    # ------------------------------------------------------------------ #

    def text_mode(self) -> bool:
        """Whether a click on a page opens the text editor."""
        return self._text_mode

    def set_text_mode(self, active: bool) -> None:
        """Turn the text tool on or off. Leaving it confirms an open edit."""
        if not active:
            self._commit_text_edit(keep_open=False)
        self._commit_field_edit()
        self._text_mode = bool(active)
        cursor = self._tool_cursor()
        for c in self._canvases:
            c.label.setCursor(cursor)
            # The outline of edited spans is drawn only while the tool is on.
            c.label.update()

    def finish_text_edit(self) -> None:
        """Confirm the correction open in the editor, if any.

        For the window, before it decides whether there is anything unsaved:
        typed-but-unconfirmed text is the user's work too. A correction the
        save could not write is dropped, with the reason in the status bar.
        """
        self._commit_text_edit(keep_open=False)

    def finish_field_edit(self) -> None:
        """Confirm the form field open in the editor, if any.

        Called for the same reason as :meth:`finish_text_edit`: a value typed
        on the page and not yet confirmed is unsaved work, and a save would
        otherwise materialise the document without it.
        """
        self._commit_field_edit()

    def text_editor(self) -> QLineEdit | None:
        """The editor currently open over a span, if any."""
        return self._editor

    def field_editor(self) -> QLineEdit | None:
        """The editor currently open over a form field, if any."""
        return self._field_editor

    def begin_text_edit(
        self, canvas: _Canvas, x: float, y: float, where: QPointF | None = None
    ) -> None:
        """Open the editor over the span under the page-space point (*x*, *y*).

        A click is also how the user leaves the span being edited, so an open
        editor is confirmed first (a QLabel takes no focus, so the editor
        would never hear about the click otherwise).

        A click that cannot open the editor SAYS why, on the page next to
        the click (*where*, in the label's pixels) and in the status bar. The
        first version stayed silent, and "Modifica testo does nothing" was all
        the user could conclude.
        """
        self._commit_text_edit(keep_open=False)
        self._hide_notice()
        if self._model is None:
            return
        index = canvas.index
        try:
            span = self._model.text_span_at(index, x, y)
            if span is None:
                if self._model.page_has_text(index):
                    reason = self.tr(
                        "Qui non c'è testo: clicca sopra una riga del documento."
                    )
                else:
                    reason = self.tr(
                        "Questa pagina non contiene testo modificabile: "
                        "probabilmente è un'immagine, come una scansione."
                    )
                self._notify(reason, canvas, where)
                return
            # Refuse at once what can never be edited (vertical text, Type3),
            # instead of letting the user type a correction first.
            self._model.check_text_edit(index, span, span.text)
        except ValueError as error:
            self._notify(str(error), canvas, where)
            return
        # The source can be gone or unreadable: say so -- never a traceback
        # out of a mouse click.
        except Exception as error:  # noqa: BLE001
            self._notify(
                self.tr("Impossibile leggere il testo: {0}").format(error), canvas, where
            )
            return
        editor = _SpanEditor(canvas.label)
        editor.setText(canvas.item.text_of(span))
        editor.committed.connect(self._commit_text_edit)
        editor.cancelled.connect(self._close_text_editor)
        editor.focus_left.connect(self._commit_on_focus_left)
        self._editor = editor
        self._editing = (canvas, span)
        self._place_text_editor()
        editor.show()
        editor.setFocus(Qt.FocusReason.MouseFocusReason)
        editor.selectAll()

    def text_notice(self) -> QLabel | None:
        """The note on the page explaining the last click, while it is shown."""
        return self._notice

    def _notify(self, message: str, canvas: _Canvas, where: QPointF | None) -> None:
        """Say why the text tool did nothing: on the page by the click, and in the status bar."""
        self.text_edit_refused.emit(message)
        self._hide_notice()
        label = canvas.label
        notice = QLabel(message, label)
        notice.setWordWrap(True)
        notice.setStyleSheet(NOTICE_STYLE)
        notice.setMaximumWidth(max(160, min(360, label.width() - 16)))
        notice.adjustSize()
        point = where if where is not None else QPointF(8.0, 8.0)
        # Just below and right of the click, kept inside the page.
        x = int(min(max(4.0, point.x() + 12.0), max(4, label.width() - notice.width() - 4)))
        y = int(min(max(4.0, point.y() + 12.0), max(4, label.height() - notice.height() - 4)))
        notice.move(x, y)
        notice.show()
        notice.raise_()
        self._notice = notice
        self._notice_timer.start(NOTICE_MS)

    def _hide_notice(self) -> None:
        notice = self._notice
        if notice is None:
            return
        self._notice = None
        self._notice_timer.stop()
        notice.hide()
        notice.deleteLater()

    def _place_field_editor(self) -> None:
        """Lay the editor exactly over the field it edits."""
        if self._field_editor is None or self._editing_field is None:
            return
        canvas, field = self._editing_field
        area = canvas.label._rect_pixels(field.rect)
        font = self._field_editor.font()
        font.setPixelSize(max(10, min(int(area.height() * 0.7), 18)))
        self._field_editor.setFont(font)
        self._field_editor.setGeometry(
            int(area.left()),
            int(area.top()),
            max(60, int(area.width())),
            max(20, int(area.height())),
        )

    def _commit_field_edit(self) -> None:
        """Record what the field editor holds, if it changed anything."""
        editor, editing = self._field_editor, self._editing_field
        if editor is None or editing is None:
            return
        canvas, field = editing
        value = editor.text()
        self._close_field_editor()
        if value != canvas.item.form_values.get(field.name, field.value):
            self.field_value_committed.emit(canvas.index, field.name, value)

    def _close_field_editor(self) -> None:
        editor = self._field_editor
        self._field_editor = None
        self._editing_field = None
        if editor is not None:
            editor.hide()
            editor.deleteLater()

    def _place_text_editor(self) -> None:
        """Lay the editor over its span: same place, a usable size.

        Always horizontal, whatever the rotation: on a page turned a quarter
        the span runs up the screen, and a line edit cannot. It then sits at
        the span's corner, across it -- for the few seconds of typing that is
        better than refusing the page.
        """
        if self._editor is None or self._editing is None:
            return
        canvas, span = self._editing
        area = canvas.label._rect_pixels(span.bbox)
        scale = canvas.scale
        height = max(20, int((span.bbox[3] - span.bbox[1]) * scale) + 8)
        width = max(120, int((span.width + span.room) * scale) + 16)
        width = min(width, max(120, canvas.label.width()))
        x = int(min(max(0.0, area.left() - 4), max(0, canvas.label.width() - width)))
        y = int(min(max(0.0, area.top() - 4), max(0, canvas.label.height() - height)))
        font = self._editor.font()
        font.setPixelSize(max(10, min(int(span.size * scale * 0.85), 48)))
        self._editor.setFont(font)
        self._editor.setGeometry(x, y, width, height)

    def _commit_on_focus_left(self) -> None:
        self._commit_text_edit(keep_open=False)

    def _commit_text_edit(self, keep_open: bool = True) -> None:
        """Confirm the open edit: check it as the save would, then report it.

        A refusal is said in the window's status bar and on the editor
        itself. With *keep_open* (Enter) the editor stays, with the text the
        user typed, so it can be shortened; when the editor is being left
        anyway (a click elsewhere, the tool switched off) the edit is dropped
        -- a correction that cannot be saved must not look as if it were.
        """
        editor, editing = self._editor, self._editing
        if editor is None or editing is None or self._model is None:
            return
        canvas, span = editing
        text = editor.text()
        if text == canvas.item.text_of(span):
            self._close_text_editor()
            return
        try:
            self._model.check_text_edit(canvas.index, span, text)
        except Exception as error:  # noqa: BLE001 -- a refusal, whatever the cause
            message = str(error) if isinstance(error, ValueError) else (
                self.tr("Impossibile verificare la modifica: {0}").format(error)
            )
            self.text_edit_refused.emit(message)
            if keep_open:
                editor.setStyleSheet(TEXT_EDIT_REFUSED)
                editor.setToolTip(message)
                return
            self._close_text_editor()
            return
        index = canvas.index
        self._close_text_editor()
        self.text_edited.emit(index, span, text)

    def _close_text_editor(self) -> None:
        """Drop the editor without reporting anything."""
        editor = self._editor
        if editor is None:
            return
        # Cleared first: hiding the editor moves the focus, and the focus-out
        # it causes must find nothing left to confirm.
        self._editor = None
        self._editing = None
        editor.hide()
        editor.deleteLater()

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
        self._close_text_editor()
        self._close_field_editor()
        self._hide_notice()
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