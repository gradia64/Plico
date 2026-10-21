"""Images → PDF (model/images.py): sizes, order, orientation, and refusals.

The images are made with QImage: Pillow is not a dependency, and QImage can
set the two things that matter here -- the resolution and, for JPEG, the
EXIF orientation.
"""

import base64
import os

import pymupdf
import pytest
from PySide6.QtGui import QColor, QImage, QImageIOHandler, QImageWriter
from PySide6.QtWidgets import QApplication

from plico.model.images import images_to_pdf, is_image, page_size_for

A4 = (595.0, 842.0)


@pytest.fixture(scope="module")
def qapp():
    # A QApplication, never a QCoreApplication: the instance outlives this
    # module, and test_integration.py needs widgets.
    return QApplication.instance() or QApplication([])


def _image(path, width: int, height: int, dpi: int = 0, fmt: str = "PNG") -> str:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 220, 255))
    if dpi:
        image.setDotsPerMeterX(round(dpi / 0.0254))
        image.setDotsPerMeterY(round(dpi / 0.0254))
    assert image.save(str(path), fmt)
    return str(path)


def _sizes(path: str) -> list[tuple[float, float]]:
    with pymupdf.open(path) as doc:
        return [(round(p.rect.width, 1), round(p.rect.height, 1)) for p in doc]


# --- page size ------------------------------------------------------------------


def test_a_plausible_size_is_kept():
    assert page_size_for(595.0, 842.0) == (595.0, 842.0)
    assert page_size_for(300.0, 200.0) == (300.0, 200.0)


def test_an_oversized_landscape_image_fits_a_landscape_a4():
    width, height = page_size_for(4000.0, 3000.0)
    # A 4:3 photo meets the short side of a landscape A4 first.
    assert (width, height) == pytest.approx((793.33, 595.0), abs=0.01)


def test_an_oversized_portrait_image_fits_a_portrait_a4():
    width, height = page_size_for(3000.0, 4000.0)
    assert height <= 842.0 + 1e-6 and width <= 595.0 + 1e-6
    assert width / height == pytest.approx(0.75)


def test_is_image_ignores_case_and_rejects_pdf():
    assert is_image("/x/Foto.JPG") and is_image("scan.tiff")
    assert not is_image("documento.pdf") and not is_image("foto.webp")


# --- conversion -----------------------------------------------------------------


def test_a_scan_at_300_dpi_becomes_an_a4_page(qapp, tmp_path):
    scan = _image(tmp_path / "scan.png", 2480, 3508, dpi=300)
    out = str(tmp_path / "out.pdf")

    assert images_to_pdf([scan], out) == 1

    (size,) = _sizes(out)
    assert size == pytest.approx(A4, abs=1)


def test_a_phone_photo_at_72_dpi_is_brought_down_to_a4(qapp, tmp_path):
    """4000 px at 72 dpi would be a page 1.4 metres wide."""
    photo = _image(tmp_path / "foto.jpg", 4000, 3000, dpi=72, fmt="JPEG")
    out = str(tmp_path / "out.pdf")

    images_to_pdf([photo], out)

    (size,) = _sizes(out)
    assert size == pytest.approx((793.3, 595.0), abs=0.5)


def test_pages_follow_the_order_given(qapp, tmp_path):
    first = _image(tmp_path / "a.png", 300, 200, dpi=72)
    second = _image(tmp_path / "b.png", 200, 300, dpi=72)
    third = _image(tmp_path / "c.png", 100, 100, dpi=72)
    out = str(tmp_path / "out.pdf")

    assert images_to_pdf([second, third, first], out) == 3

    assert _sizes(out) == [(200.0, 300.0), (100.0, 100.0), (300.0, 200.0)]


def test_a_jpeg_goes_in_untouched(qapp, tmp_path):
    """No decode and re-encode: same stream, same size, not one pixel worse."""
    photo = _image(tmp_path / "foto.jpg", 1200, 900, dpi=150, fmt="JPEG")
    out = str(tmp_path / "out.pdf")

    images_to_pdf([photo], out)

    with pymupdf.open(out) as doc:
        (xref, *_rest) = doc[0].get_images()[0]
        assert doc.xref_get_key(xref, "Filter")[1] == "/DCTDecode"
        assert len(doc.xref_stream_raw(xref)) == os.path.getsize(photo)


def test_the_exif_orientation_is_honoured(qapp, tmp_path):
    """Landscape pixels flagged "rotate 90°" come out as a portrait page."""
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    path = str(tmp_path / "girata.jpg")
    writer = QImageWriter(path, b"jpeg")
    writer.setTransformation(QImageIOHandler.Transformation.TransformationRotate90)
    assert writer.write(image)
    out = str(tmp_path / "out.pdf")

    images_to_pdf([path], out)

    (size,) = _sizes(out)
    assert size[1] > size[0], "the photo must stay upright"


def test_gif_tiff_and_bmp_are_read(qapp, tmp_path):
    gif = tmp_path / "uno.gif"
    gif.write_bytes(
        base64.b64decode("R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==")
    )
    tiff = _image(tmp_path / "scan.tif", 600, 400, dpi=150, fmt="TIFF")
    bmp = _image(tmp_path / "pic.bmp", 300, 200, dpi=96, fmt="BMP")
    out = str(tmp_path / "out.pdf")

    assert images_to_pdf([str(gif), tiff, bmp], out) == 3


def test_a_file_that_is_not_an_image_is_refused_and_nothing_is_written(qapp, tmp_path):
    fake = tmp_path / "finta.png"
    fake.write_text("non sono un'immagine")
    good = _image(tmp_path / "vera.png", 100, 100)
    out = str(tmp_path / "out.pdf")

    with pytest.raises(ValueError, match="finta.png"):
        images_to_pdf([good, str(fake)], out)

    assert not os.path.exists(out)


def test_a_pdf_is_not_an_image(qapp, tmp_path):
    pdf = str(tmp_path / "doc.pdf")
    doc = pymupdf.open()
    doc.new_page()
    doc.save(pdf)
    doc.close()

    with pytest.raises(ValueError, match="già un PDF"):
        images_to_pdf([pdf], str(tmp_path / "out.pdf"))


def test_no_images_is_refused(tmp_path):
    with pytest.raises(ValueError):
        images_to_pdf([], str(tmp_path / "out.pdf"))
