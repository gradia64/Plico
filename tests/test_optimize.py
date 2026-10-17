"""Unit tests for the compression pipeline.

The numbers asserted here are the ones the feature is built on, and they were
measured on generated documents rather than guessed:

* ``clean=True`` (mutool clean) is what really shrinks a fragmented text PDF.
  A document built page by page carries one tiny content stream per drawing
  call, and merging those is worth an order of magnitude -- losslessly.
* only the lossy levels touch the images, and on a scan they are the only
  thing that matters.

So a regression in the recipe shows up here as a failing test instead of as a
quietly worse file for the user.
"""

import os
import random

import pymupdf
import pytest
from PySide6.QtGui import QGuiApplication, QImage

from plico.model import (
    LEVELS,
    LEVELS_BY_KEY,
    DocumentModel,
    optimize_in_place,
    save_compressed,
)

# The light level must at least halve a fragmented text PDF.
SOGLIA_TESTO = 0.5
# The medium level must take at least a quarter off a scan.
SOGLIA_SCANSIONE = 0.75


@pytest.fixture(scope="module")
def qapp():
    """Only needed for QImage, to build the JPEG of a fake scan."""
    yield QGuiApplication.instance() or QGuiApplication([])


def _fragmented_text(path: str, pages: int = 20) -> None:
    """A PDF in the shape real PDFs arrive in: many pages, many streams.

    ``insert_text`` creates one object per call, so the document carries
    hundreds of tiny content streams. That is exactly the shape in which
    ``clean=True`` makes the difference.
    """
    with pymupdf.open() as doc:
        for i in range(pages):
            page = doc.new_page(width=595, height=842)
            for k in range(40):
                page.insert_text(
                    (60, 60 + k * 18),
                    f"Paragrafo {k} della pagina {i + 1}: contenuto ripetuto per occupare spazio.",
                    fontsize=10,
                )
        doc.save(path, deflate=True)


def _scan(path: str, pages: int = 3, side: int = 1000) -> None:
    """A fake scanned PDF: one large JPEG image per page.

    The pixels are noise, therefore incompressible: the downscaling is
    really measured instead of vanishing inside an already excellent
    compression.

    The image goes through QImage and not ``pymupdf.Pixmap(cs, w, h, bytes)``:
    that signature does not exist in PyMuPDF 1.28 and its exception embeds
    the whole buffer in the error messages.
    """
    jpg = f"{path}.jpg"
    campioni = random.Random(1).randbytes(side * side * 3)
    QImage(campioni, side, side, side * 3, QImage.Format.Format_RGB888).save(jpg, "JPEG", 95)
    try:
        with pymupdf.open() as doc:
            for _ in range(pages):
                page = doc.new_page(width=595, height=842)
                page.insert_image(pymupdf.Rect(0, 0, 595, 842), filename=jpg)
            doc.save(path, deflate=True)
    finally:
        os.unlink(jpg)


# --------------------------------------------------------------------- #
#  The levels
# --------------------------------------------------------------------- #

def test_only_the_lossy_levels_touch_the_images():
    """A level that resamples must also say *where* to take the images.

    An ``image_target`` of zero with ``rewrites_images`` true would do nothing
    and nobody would notice: better a test that says so.
    """
    for level in LEVELS:
        if level.rewrites_images:
            assert 0 < level.image_target < level.image_threshold, level.key
            assert 0 < level.image_quality < 100, level.key
        else:
            assert level.image_target == 0, level.key
            assert level.image_quality == 0, level.key


def test_level_keys_are_unique_and_discoverable():
    assert len({level.key for level in LEVELS}) == len(LEVELS)
    assert all(LEVELS_BY_KEY[level.key] is level for level in LEVELS)


def test_the_levels_get_progressively_stronger():
    """The further down the level, the lower the target and quality."""
    ridimensionano = [level for level in LEVELS if level.rewrites_images]
    bersagli = [level.image_target for level in ridimensionano]
    qualita = [level.image_quality for level in ridimensionano]
    assert bersagli == sorted(bersagli, reverse=True)
    assert qualita == sorted(qualita, reverse=True)


# --------------------------------------------------------------------- #
#  optimize_in_place
# --------------------------------------------------------------------- #

def test_optimize_shrinks_a_fragmented_text_pdf(qapp, tmp_path):
    path = str(tmp_path / "frammentato.pdf")
    _fragmented_text(path)
    before = os.path.getsize(path)

    risultato = optimize_in_place(path, LEVELS_BY_KEY["light"])

    after = os.path.getsize(path)
    assert after < before * SOGLIA_TESTO, f"{before} -> {after} byte"
    assert risultato.source_size == before
    assert risultato.output_size == after
    assert risultato.shrank
    assert risultato.saved_bytes == before - after
    assert risultato.percent_saved > 50
    with pymupdf.open(path) as doc:
        assert doc.page_count == 20


def test_optimize_keeps_the_text_readable(qapp, tmp_path):
    """Compressing must not mean losing the extractable text."""
    path = str(tmp_path / "testo.pdf")
    _fragmented_text(path, pages=3)

    optimize_in_place(path, LEVELS_BY_KEY["light"])

    with pymupdf.open(path) as doc:
        assert "della pagina 2" in doc[1].get_text()


def test_optimize_never_grows_an_already_optimized_file(qapp, tmp_path):
    """Going twice over the same file must not make it worse."""
    path = str(tmp_path / "gia.pdf")
    _fragmented_text(path)
    optimize_in_place(path, LEVELS_BY_KEY["light"])
    before = os.path.getsize(path)

    risultato = optimize_in_place(path, LEVELS_BY_KEY["light"])

    assert os.path.getsize(path) <= before
    if not risultato.shrank:
        assert os.path.getsize(path) == before


def test_optimize_keeps_page_rotation(qapp, tmp_path):
    """Rotation is per page, and must survive the rewrite."""
    path = str(tmp_path / "ruotato.pdf")
    _fragmented_text(path, pages=2)
    with pymupdf.open(path) as doc:
        doc[1].set_rotation(90)
        doc.saveIncr()

    optimize_in_place(path, LEVELS_BY_KEY["light"])

    with pymupdf.open(path) as doc:
        assert doc[0].rotation == 0
        assert doc[1].rotation == 90


def test_optimize_reports_progress(qapp, tmp_path):
    path = str(tmp_path / "progresso.pdf")
    _fragmented_text(path, pages=5)
    seen: list[int] = []

    optimize_in_place(path, LEVELS_BY_KEY["light"], progress=seen.append)

    assert seen, "pikepdf deve riportare l'avanzamento"
    assert seen[-1] == 100
    assert all(0 <= value <= 100 for value in seen)


def test_optimize_without_progress_does_not_complain(qapp, tmp_path):
    """The callback is optional: without it, nothing must happen."""
    path = str(tmp_path / "muto.pdf")
    _fragmented_text(path, pages=3)

    optimize_in_place(path, LEVELS_BY_KEY["light"])

    assert os.path.getsize(path) > 0


# --------------------------------------------------------------------- #
#  The images: this is where something is lost, and on purpose
# --------------------------------------------------------------------- #

def test_medium_level_shrinks_a_scan(qapp, tmp_path):
    path = str(tmp_path / "scansione.pdf")
    _scan(path)
    before = os.path.getsize(path)

    risultato = optimize_in_place(path, LEVELS_BY_KEY["medium"])

    after = os.path.getsize(path)
    assert after < before * SOGLIA_SCANSIONE, f"{before} -> {after} byte"
    assert risultato.shrank
    with pymupdf.open(path) as doc:
        assert doc.page_count == 3
        assert doc[0].get_images(), "l'immagine non deve sparire"


def test_light_level_leaves_a_scan_alone(qapp, tmp_path):
    """The light level does not touch the images: on a scan it gains nothing.

    It is not a missed optimization, it is the promise of the level: on a
    document that is already image-only there is nothing to take away without
    losing something, so nothing is taken away.
    """
    path = str(tmp_path / "scansione.pdf")
    _scan(path)
    before = os.path.getsize(path)

    optimize_in_place(path, LEVELS_BY_KEY["light"])

    assert os.path.getsize(path) > before * 0.95


def test_strong_level_goes_further_than_medium(qapp, tmp_path):
    medio = str(tmp_path / "medio.pdf")
    forte = str(tmp_path / "forte.pdf")
    _scan(medio)
    _scan(forte)

    optimize_in_place(medio, LEVELS_BY_KEY["medium"])
    optimize_in_place(forte, LEVELS_BY_KEY["strong"])

    assert os.path.getsize(forte) < os.path.getsize(medio)


# --------------------------------------------------------------------- #
#  save_compressed
# --------------------------------------------------------------------- #

def test_save_compressed_writes_the_virtual_document(qapp, tmp_path):
    """The compressed file contains the *virtual* document, not the source."""
    source = str(tmp_path / "sorgente.pdf")
    _fragmented_text(source, pages=10)
    destination = str(tmp_path / "compresso.pdf")

    model = DocumentModel()
    model.open(source)
    model.pages.pop(0)
    model.pages.pop(0)
    model.pages[0].rotation = 90

    risultato = save_compressed(model, destination, LEVELS_BY_KEY["light"])

    assert risultato.shrank
    with pymupdf.open(destination) as doc:
        assert doc.page_count == 8
        assert doc[0].rotation == 90
        assert "della pagina 3" in doc[0].get_text()
    with pymupdf.open(source) as doc:
        assert doc.page_count == 10, "la sorgente non si tocca"


def test_save_compressed_can_overwrite_the_open_source(qapp, tmp_path):
    """Compressing over the open file: right content, new inode."""
    source = str(tmp_path / "doc.pdf")
    _fragmented_text(source, pages=6)
    before = os.path.getsize(source)

    model = DocumentModel()
    model.open(source)
    model.pages.pop(0)

    save_compressed(model, source, LEVELS_BY_KEY["light"])

    assert os.path.getsize(source) < before
    with pymupdf.open(source) as doc:
        assert doc.page_count == 5


def test_save_compressed_leaves_no_temporary_behind(qapp, tmp_path):
    """Temporaries are born next to the file: they must not stay there."""
    source = str(tmp_path / "doc.pdf")
    _fragmented_text(source, pages=5)
    destination = str(tmp_path / "compresso.pdf")

    model = DocumentModel()
    model.open(source)
    save_compressed(model, destination, LEVELS_BY_KEY["light"])

    residui = [name for name in os.listdir(tmp_path) if name.endswith(".tmp")]
    assert residui == []


def test_save_compressed_without_pages_is_refused(qapp, tmp_path):
    """An emptied document must not produce a PDF with no pages."""
    source = str(tmp_path / "doc.pdf")
    _fragmented_text(source, pages=2)
    destination = str(tmp_path / "compresso.pdf")

    model = DocumentModel()
    model.open(source)
    model.pages.clear()

    with pytest.raises(ValueError):
        save_compressed(model, destination, LEVELS_BY_KEY["light"])
    assert not os.path.exists(destination)
