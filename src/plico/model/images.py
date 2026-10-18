"""Images → PDF: photos and scans become pages Plico can work on.

The model only knows PDF sources, and that is kept: the images are turned
into ONE ordinary PDF, which then becomes a source like any other. From
there on nothing knows that a page started as a photo -- reordering,
rotating, deleting, merging and saving all work unchanged.

Measured on MuPDF 1.28, and the reason the code below is this short:

* ``convert_to_pdf()`` honours the image's resolution: an A4 scan at 300 dpi
  comes out as exactly 595 × 842 pt;
* it honours the EXIF orientation too, so a photo taken upright stays
  upright;
* a JPEG goes in as it is, without being decoded and re-encoded: the PDF is
  the size of the photo, and not one pixel worse;
* multi-frame TIFFs come out as one page per frame;
* WEBP is NOT supported by this MuPDF build ("Failed to open file ... as
  type webp"), so it is not offered.
"""

import os

import pymupdf
from PySide6.QtCore import QCoreApplication

# The formats offered in the file dialogs, all checked against MuPDF.
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif")

_A4 = (595.0, 842.0)

# Beyond this, a page size says "no real resolution" rather than "large
# format". A phone photo carries 72 dpi, and 4000 pixels at 72 dpi make a
# page 1.4 metres wide; anything longer than a quarter more than A4 is
# brought down to fit inside an A4 of the same orientation.
_MAX_SIDE = _A4[1] * 1.25


def is_image(path: str) -> bool:
    """Whether *path* names one of the image formats Plico converts."""
    return os.path.splitext(path)[1].lower() in IMAGE_SUFFIXES


def page_size_for(width: float, height: float) -> tuple[float, float]:
    """The page an image of *width* × *height* points should get.

    The image's own size when it is plausible (a scan at its real
    resolution), otherwise scaled down -- never up, never stretched -- to fit
    an A4 turned the same way as the image.
    """
    if max(width, height) <= _MAX_SIDE:
        return width, height
    box_w, box_h = _A4 if height >= width else (_A4[1], _A4[0])
    scale = min(box_w / width, box_h / height)
    return width * scale, height * scale


def images_to_pdf(paths: list[str], out_path: str) -> int:
    """Write the images in *paths*, in that order, as one PDF at *out_path*.

    Returns the number of pages written (a multi-frame TIFF brings several).
    Raises :class:`ValueError`, with a message for the user, when a file is
    not an image MuPDF can read or when there is nothing to write; nothing
    is written in that case.
    """
    with pymupdf.open() as out:
        for path in paths:
            name = os.path.basename(path)
            try:
                with pymupdf.open(path) as image:
                    if image.is_pdf:
                        raise ValueError(
                            QCoreApplication.translate(
                                "Images",
                                "«{0}» è già un PDF: aprilo, oppure aggiungilo con Unisci.",
                            ).format(name)
                        )
                    converted = pymupdf.open("pdf", image.convert_to_pdf())
            except ValueError:
                raise
            # MuPDF's own errors do not derive from RuntimeError (§6): a file
            # it cannot decode is reported to the user, whatever it raises.
            except Exception as error:
                raise ValueError(
                    QCoreApplication.translate("Images", "«{0}» non è un'immagine che si possa leggere.").format(name)
                ) from error
            with converted:
                for index in range(converted.page_count):
                    rect = converted[index].rect
                    width, height = page_size_for(rect.width, rect.height)
                    if (width, height) == (rect.width, rect.height):
                        out.insert_pdf(converted, from_page=index, to_page=index)
                    else:
                        # Drawn into a smaller page as a form: the image stream
                        # itself is copied untouched, only its placement changes.
                        page = out.new_page(width=width, height=height)
                        page.show_pdf_page(page.rect, converted, index)
        if out.page_count == 0:
            raise ValueError(QCoreApplication.translate("Images", "Nessuna immagine da convertire."))
        out.save(out_path, garbage=4, deflate=True)
        return int(out.page_count)
