"""Printing: the document as it would be saved, page by page, as images.

What goes to the printer is not the page list on screen but the file a save
would write -- deletions, rotations, redactions, form values, text edits and
OCR included -- materialised into a private temporary first. Printing the
sources instead would put on paper the very content a redaction mark hides.

Each page is rendered by MuPDF and painted as an image. Handing the printer
vector content would need a second PDF renderer (Qt's own does not draw
PDF), and MuPDF is the one that shows the page on screen: what is printed is
what was seen. The resolution is capped (see :data:`MAX_DPI`), so a 1200 dpi
printer does not make every page a 400 MB image.

The device is a :class:`QPagedPaintDevice`, so the same code paints on a
``QPrinter`` and on a ``QPdfWriter`` -- which is how the tests check it
without QtPrintSupport, a module some distributions package apart.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pymupdf
from PySide6.QtCore import QPointF, QRectF, QSizeF
from PySide6.QtGui import QImage, QPagedPaintDevice, QPainter

# Enough for text to look like text on paper, and 26 MB for an A4 page.
MAX_DPI = 300


def page_fit(
    page: tuple[float, float], area: tuple[float, float], auto_rotate: bool = True
) -> tuple[bool, float]:
    """How a page of *page* points goes on *area*: (turned 90°, scale).

    A landscape page on portrait paper is turned, as every viewer does when it
    prints: otherwise it would come out at half its size. The scale keeps the
    proportions and fits the whole page, centred.
    """
    width, height = page
    turned = auto_rotate and (width > height) != (area[0] > area[1]) and width != height
    if turned:
        width, height = height, width
    return turned, min(area[0] / width, area[1] / height)


def print_pdf(
    path: str,
    device: QPagedPaintDevice,
    pages: Sequence[int] | None = None,
    progress: Callable[[int], bool] | None = None,
    auto_rotate: bool = True,
) -> int:
    """Paint the pages *pages* (0-based, all for None) of *path* on *device*.

    *progress* is called after every page with the number printed so far,
    and returning False stops there. Returns how many pages were painted;
    the caller decides what a stop means for its device (``QPrinter.abort``).
    """
    painter = QPainter()
    if not painter.begin(device):
        raise RuntimeError("the printer did not accept the job")
    printed = 0
    try:
        with pymupdf.open(path) as doc:
            chosen = range(len(doc)) if pages is None else pages
            # The paintable area, in device pixels: the paper minus the margins
            # the device asked for.
            area = (float(device.width()), float(device.height()))
            device_dpi = device.logicalDpiX()
            render_dpi = min(device_dpi, MAX_DPI)
            for index in chosen:
                if printed:
                    device.newPage()
                page = doc[index]
                size = (page.rect.width, page.rect.height)
                turned, scale = page_fit(size, area, auto_rotate)
                # Pixels of the image: the size on paper, at render_dpi.
                zoom = scale * render_dpi / device_dpi
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                image = QImage(
                    pixmap.samples, pixmap.width, pixmap.height, pixmap.stride,
                    QImage.Format.Format_RGB888,
                ).copy()  # the samples belong to the pixmap, which goes away
                target = QSizeF(size[0] * scale, size[1] * scale)
                painter.save()
                painter.translate(QPointF(area[0] / 2, area[1] / 2))
                if turned:
                    painter.rotate(90)
                painter.drawImage(
                    QRectF(QPointF(-target.width() / 2, -target.height() / 2), target), image
                )
                painter.restore()
                printed += 1
                if progress is not None and not progress(printed):
                    break
    finally:
        painter.end()
    return printed
