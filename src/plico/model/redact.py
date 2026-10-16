"""Redaction geometry — the bridge between what the user draws and the PDF.

Two coordinate systems are in play, and confusing them puts the black box
next to the secret instead of on top of it:

* **page space** — the unrotated page, in PDF points. This is what the model
  stores, and it is exactly the space ``Page.add_redact_annot()`` expects.
  Storing it here rather than on screen is not a detail: a redaction marks a
  region of the *document*, so it must stay on the same words when the page
  is rotated afterwards. Screen coordinates would rotate away from the text
  and the next save would blacken the wrong paragraph.
* **view space** — what is actually on screen: the page with its own /Rotate
  applied (MuPDF does that for us, and ``PageItem.width_pt`` already includes
  it) plus the user's rotation offset on top.

The four matrices below were read off PyMuPDF's ``Page.rotation_matrix`` and
are pinned against PyMuPDF itself by ``tests/test_redact.py``: if a PyMuPDF
upgrade ever changes them, the suite fails instead of quietly misplacing a
redaction.
"""

from dataclasses import dataclass

# An affine map (a, b, c, d, e, f) sending (x, y) to
# (a·x + c·y + e, b·x + d·y + f) — PyMuPDF's own tuple layout.
Matrix = tuple[float, float, float, float, float, float]

IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


@dataclass(frozen=True)
class RedactionRect:
    """A rectangle in page space (unrotated PDF points).

    Frozen so it can be handed to an undo command and compared by value: the
    command needs to find *this* rectangle again in the page's list, and
    identity comparison would break as soon as the list is rebuilt.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    @classmethod
    def from_corners(cls, x0: float, y0: float, x1: float, y1: float) -> "RedactionRect":
        """Build from two arbitrary corners, normalising them.

        A drag can start at any corner, so a rectangle is only ever
        constructed through here — ``x0`` is always the left edge and ``y0``
        the top one, which is what the rest of the code assumes.
        """
        return cls(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def as_tuple(self) -> tuple[float, float, float, float]:
        """The four numbers, in the order ``pymupdf.Rect`` takes them."""
        return (self.x0, self.y0, self.x1, self.y1)

    def clamped_to(self, width: float, height: float) -> "RedactionRect":
        """Trim the rectangle to a page of *width* × *height* points.

        A drag that leaves the page (or a fit-width layout with a stray
        pixel) must not produce a rectangle reaching outside the media box.
        """
        return RedactionRect.from_corners(
            min(max(self.x0, 0.0), width),
            min(max(self.y0, 0.0), height),
            min(max(self.x1, 0.0), width),
            min(max(self.y1, 0.0), height),
        )


def rotation_matrix(
    unrotated_width: float, unrotated_height: float, rotation: int
) -> Matrix:
    """Map page space → view space for a page turned *rotation* degrees.

    *unrotated_width* and *unrotated_height* are the page's own dimensions
    with /Rotate undone — the translations below are all expressed with them.
    """
    quarter = rotation % 360
    if quarter == 90:
        return (0.0, 1.0, -1.0, 0.0, unrotated_height, 0.0)
    if quarter == 180:
        return (-1.0, 0.0, 0.0, -1.0, unrotated_width, unrotated_height)
    if quarter == 270:
        return (0.0, -1.0, 1.0, 0.0, 0.0, unrotated_width)
    if quarter != 0:
        raise ValueError(f"Rotazione non gestita: {rotation}")
    return IDENTITY


def derotation_matrix(
    unrotated_width: float, unrotated_height: float, rotation: int
) -> Matrix:
    """The inverse of :func:`rotation_matrix`: view space → page space."""
    quarter = rotation % 360
    if quarter == 90:
        return (0.0, -1.0, 1.0, 0.0, 0.0, unrotated_height)
    if quarter == 180:
        return (-1.0, 0.0, 0.0, -1.0, unrotated_width, unrotated_height)
    if quarter == 270:
        return (0.0, 1.0, -1.0, 0.0, unrotated_width, 0.0)
    if quarter != 0:
        raise ValueError(f"Rotazione non gestita: {rotation}")
    return IDENTITY


def map_point(x: float, y: float, matrix: Matrix) -> tuple[float, float]:
    """Send one point through *matrix*."""
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


def map_rect(rect: RedactionRect, matrix: Matrix) -> RedactionRect:
    """Send *rect* through *matrix*, normalising the result.

    All four corners have to go through the map: a quarter turn swaps them,
    so the transformed ``(x0, y0)`` is no longer the top-left one, and
    rebuilding the rectangle from the *old* corner pair would give a box
    mirrored around the page.
    """
    corners = (
        (rect.x0, rect.y0),
        (rect.x1, rect.y0),
        (rect.x1, rect.y1),
        (rect.x0, rect.y1),
    )
    mapped = [map_point(x, y, matrix) for x, y in corners]
    xs = [p[0] for p in mapped]
    ys = [p[1] for p in mapped]
    return RedactionRect(min(xs), min(ys), max(xs), max(ys))


def unrotated_size(width_pt: float, height_pt: float, base_rotation: int) -> tuple[float, float]:
    """Unrotated page size from the *oriented* size the model stores.

    ``PageItem.width_pt`` / ``height_pt`` come from ``page.rect``, which MuPDF
    has already rotated by the page's own /Rotate, so for the odd
    quarter-turns the two are swapped and have to be swapped back.
    """
    if base_rotation % 180 == 0:
        return width_pt, height_pt
    return height_pt, width_pt
