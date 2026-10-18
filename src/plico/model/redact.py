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

from collections.abc import Sequence
from dataclasses import dataclass

import pymupdf

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
    # Fitted to the words of ONE line (a search hit, a selected word), as
    # opposed to a zone the user drew. MuPDF deletes every glyph whose box
    # touches a redaction, and a glyph box runs from ascender to descender:
    # at ordinary single spacing it reaches into the lines above and below,
    # so a word-sized rectangle took letters off its neighbours (measured:
    # redacting «SEGRETO» turned the next line's «innocente» into «sott»).
    # A snug rectangle removes its text through :meth:`text_band` instead.
    snug: bool = False

    @classmethod
    def from_corners(
        cls, x0: float, y0: float, x1: float, y1: float, snug: bool = False
    ) -> "RedactionRect":
        """Build from two arbitrary corners, normalising them.

        A drag can start at any corner, so a rectangle is only ever
        constructed through here — ``x0`` is always the left edge and ``y0``
        the top one, which is what the rest of the code assumes.
        """
        return cls(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), snug)

    def text_band(self) -> "RedactionRect":
        """The part of the rectangle that deletes text.

        A drawn zone deletes everything it touches: that is what the user
        drew. A snug one deletes through a thin band across the middle of the
        line, which every glyph of that line crosses and no glyph of the next
        line reaches -- a neighbouring box starts at least one leading below,
        and at single spacing that is ~0.73 of this box's height (measured
        with Helvetica and Times at 1.0, 1.15 and 1.2 leading).
        """
        if not self.snug:
            return self
        height = self.y1 - self.y0
        return RedactionRect(self.x0, self.y0 + 0.4 * height, self.x1, self.y0 + 0.6 * height)

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
            self.snug,
        )

    def translated(self, dx: float, dy: float) -> "RedactionRect":
        """The same rectangle moved by *dx*, *dy* points, size untouched.

        A moved mark is a zone the user placed, no longer the box of a word:
        a word-sized box parked across two half lines would put its text band
        in the gap between them and delete nothing it covers.
        """
        return RedactionRect(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)

    def with_corner(self, corner: str, x: float, y: float) -> "RedactionRect":
        """The rectangle with the corner *corner* dragged to *x*, *y*.

        The dragged corner moves and the opposite one stays where it was, so
        resizing a zone does not also shift it. The result is normalised, so
        dragging a corner past the opposite one turns the rectangle over
        instead of inverting it. Like a move, a resize makes the mark a drawn
        zone: stretched over two lines, a word's text band would miss both.
        """
        if corner == "tl":
            return RedactionRect.from_corners(x, y, self.x1, self.y1)
        if corner == "tr":
            return RedactionRect.from_corners(self.x0, y, x, self.y1)
        if corner == "bl":
            return RedactionRect.from_corners(x, self.y0, self.x1, y)
        return RedactionRect.from_corners(self.x0, self.y0, x, y)


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


def burn_redactions(page: pymupdf.Page, redactions: Sequence[RedactionRect]) -> None:
    """Burn *redactions* into *page*: the content under them is gone.

    ``add_redact_annot`` expects coordinates in the page's UNROTATED space,
    which is exactly the space the model stores its rectangles in, so there
    is nothing to convert here. ``apply_redactions`` then removes the text
    under the box, blanks the overlapping image pixels and drops the line art
    that crosses it -- and it leaves the page's /Rotate alone, so it can run
    after ``set_rotation`` without changing the orientation just written.

    Two passes, because the text and the rest do not always need the same
    rectangle. The first takes the image pixels and the line art under every
    mark, whole; the second takes the text, through each mark's
    :meth:`RedactionRect.text_band` -- the whole zone for one the user drew,
    a band across the line for one fitted to words, so that redacting a word
    does not also delete letters of the lines above and below it.

    The save and the on-screen preview both go through here: what the user
    sees before saving is what this function does, not a drawing of it.
    """
    for rect in redactions:
        page.add_redact_annot(pymupdf.Rect(*rect.as_tuple()))
    page.apply_redactions(text=pymupdf.PDF_REDACT_TEXT_NONE)  # type: ignore[attr-defined]
    for rect in redactions:
        page.add_redact_annot(pymupdf.Rect(*rect.text_band().as_tuple()))
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,  # type: ignore[attr-defined]
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,  # type: ignore[attr-defined]
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,  # type: ignore[attr-defined]
    )
    # The content under the rectangles is gone, but the annotations are not:
    # a sticky note repeating a redacted word survives apply_redactions() and
    # would leak exactly what the redaction was meant to hide (measured). So
    # anything that touches a rectangle goes with it -- the same rule the eye
    # applies to a redaction.
    marks = [pymupdf.Rect(*r.as_tuple()) for r in redactions]
    for annot in list(page.annots() or []):
        if any(annot.rect.intersects(mark) for mark in marks):
            page.delete_annot(annot)
    # Form fields too, and they need their own loop: ``annots()`` leaves the
    # widgets out, and apply_redactions() does not touch them either. A field
    # filled in with «Mario Rossi» and covered by a mark came out of the save
    # with its value intact (measured).
    for widget in list(page.widgets() or []):
        if any(widget.rect.intersects(mark) for mark in marks):
            page.delete_widget(widget)


def redacted_copy(
    doc: pymupdf.Document, index: int, redactions: Sequence[RedactionRect]
) -> pymupdf.Document:
    """A one-page document: page *index* of *doc* with *redactions* burnt in.

    For the preview. *doc* is only read -- the renderer shares its handle,
    and a source must stay untouched until a save -- so the page is copied
    into a document of its own and the redactions are applied there. The
    caller closes what comes back.
    """
    copy = pymupdf.open()
    copy.insert_pdf(doc, from_page=index, to_page=index)
    burn_redactions(copy[0], redactions)
    return copy
