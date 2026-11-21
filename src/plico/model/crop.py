"""Pagine → Ritaglia margini: the visible part of a page, and where it ends.

A crop is a rectangle in PAGE space (unrotated PDF points, measured from the
corner of the page's current /CropBox, which is where PyMuPDF puts the origin).
Keeping it there, rather than as four margins, means a page turned after it
was cropped still shows the same part of the document.

The user, however, thinks in margins as seen on screen: "two centimetres off
the top" of a landscape page is a side of the PDF page. :func:`margins_of`
and :func:`crop_from_margins` translate between the two through the same
rotation matrices the view uses.

A crop hides, it does not delete: on save it becomes the /CropBox, and what
lies outside is still in the file for any program that looks.
"""

from __future__ import annotations

import pymupdf

from .redact import RedactionRect, derotation_matrix, map_rect, rotation_matrix

# What a crop must leave of a page, in points per side (about 1 cm): a page
# cropped to nothing cannot be shown, clicked or printed.
MIN_VISIBLE = 28.0
# Space kept around the content found by :func:`content_box`, in points.
CONTENT_PADDING = 6.0
# Resolution of the picture the content is looked for in: enough to see a
# line of small print, small enough to scan in a blink.
_DETECT_ZOOM = 0.75
# A pixel at least this light on every channel counts as paper.
_WHITE = 245


def _full(width: float, height: float) -> RedactionRect:
    return RedactionRect(0.0, 0.0, width, height)


def margins_of(
    crop: RedactionRect | None, width: float, height: float, rotation: int
) -> tuple[float, float, float, float]:
    """The crop as (top, right, bottom, left) margins in points, as on screen.

    *width* and *height* are the page's unrotated size, *rotation* its total
    rotation: the margins are those of the page the user sees.
    """
    if crop is None:
        return (0.0, 0.0, 0.0, 0.0)
    view = map_rect(crop, rotation_matrix(width, height, rotation))
    whole = map_rect(_full(width, height), rotation_matrix(width, height, rotation))
    return (
        max(0.0, view.y0 - whole.y0),
        max(0.0, whole.x1 - view.x1),
        max(0.0, whole.y1 - view.y1),
        max(0.0, view.x0 - whole.x0),
    )


def crop_from_margins(
    margins: tuple[float, float, float, float], width: float, height: float, rotation: int
) -> RedactionRect | None:
    """The crop that leaves (top, right, bottom, left) margins off the page on screen.

    No margins at all is no crop (``None``). Margins that would leave less
    than :data:`MIN_VISIBLE` are reduced, so the page never disappears.
    """
    top, right, bottom, left = (max(0.0, value) for value in margins)
    if not any((top, right, bottom, left)):
        return None
    whole = map_rect(_full(width, height), rotation_matrix(width, height, rotation))
    view_w, view_h = whole.x1 - whole.x0, whole.y1 - whole.y0
    left, right = _fit(left, right, view_w)
    top, bottom = _fit(top, bottom, view_h)
    view = RedactionRect(left, top, view_w - right, view_h - bottom)
    return map_rect(view, derotation_matrix(width, height, rotation)).clamped_to(width, height)


def _fit(first: float, second: float, span: float) -> tuple[float, float]:
    """Shrink two opposite margins, in proportion, to leave MIN_VISIBLE between."""
    room = max(0.0, span - MIN_VISIBLE)
    taken = first + second
    if taken <= room:
        return first, second
    if taken == 0:
        return 0.0, 0.0
    return first * room / taken, second * room / taken


def content_box(page: pymupdf.Page) -> RedactionRect | None:
    """Where *page* has something on it, in page space, with a little air.

    Looked for in a picture of the page rather than in its objects: a white
    rectangle filling the page, an invisible OCR layer or a clipped image
    all have boxes that say nothing about what the reader sees. ``None``
    for a page with nothing on it.
    """
    pix = page.get_pixmap(matrix=pymupdf.Matrix(_DETECT_ZOOM, _DETECT_ZOOM), alpha=False)
    # Each byte becomes 0 (paper) or 1 (ink), so a row is found blank by a
    # single count and its ink by find/rfind instead of a loop over pixels.
    table = bytes(0 if value >= _WHITE else 1 for value in range(256))
    samples = pix.samples
    stride, n = pix.stride, pix.n
    top = bottom = None
    left, right = pix.width, -1
    for y in range(pix.height):
        row = samples[y * stride : y * stride + pix.width * n].translate(table)
        first = row.find(1)
        if first < 0:
            continue
        last = row.rfind(1)
        top = y if top is None else top
        bottom = y
        left = min(left, first // n)
        right = max(right, last // n)
    if top is None or bottom is None or right < 0:
        return None
    scale = 1 / _DETECT_ZOOM
    seen = pymupdf.Rect(left * scale, top * scale, (right + 1) * scale, (bottom + 1) * scale)
    # The picture is of the page as shown, its own /Rotate applied: back to
    # page space, where a crop lives.
    unrotated = seen * page.derotation_matrix
    width, height = page.cropbox.width, page.cropbox.height
    return RedactionRect.from_corners(
        unrotated.x0 - CONTENT_PADDING,
        unrotated.y0 - CONTENT_PADDING,
        unrotated.x1 + CONTENT_PADDING,
        unrotated.y1 + CONTENT_PADDING,
    ).clamped_to(width, height)


def apply_crop(page: pymupdf.Page, crop: RedactionRect) -> None:
    """Make *crop* the /CropBox of *page*.

    The page's coordinates start at the corner of its CURRENT crop box, while
    ``set_cropbox`` wants them in the media box: the offset goes back on.
    Runs after everything else written on the page, all of which used the
    coordinates of the box being replaced.
    """
    offset = page.cropbox_position
    page.set_cropbox(
        pymupdf.Rect(crop.x0, crop.y0, crop.x1, crop.y1) + (offset.x, offset.y, offset.x, offset.y)
    )
