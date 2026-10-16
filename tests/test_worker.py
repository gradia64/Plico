"""Tests for RenderWorker rendering."""

import pymupdf

from plico.rendering import RenderRequest, RenderWorker


def _make_pdf(path, text="Test Page"):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=24)
    doc.save(str(path))
    doc.close()


def test_render_worker_renders_page(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    _make_pdf(pdf_path)

    worker = RenderWorker()
    rendered_images = []

    def on_rendered(key, image):
        rendered_images.append((key, image))

    worker.rendered.connect(on_rendered)

    # ("page", source_id, source_index, rotation, zoom, dpr)
    key = ("page", 0, 0, 0, 1.0, 1.0)
    req = RenderRequest(key, str(pdf_path), 0, 1.0, 0)
    worker._render(req)

    assert len(rendered_images) == 1
    assert rendered_images[0][0] == key
    img = rendered_images[0][1]
    assert img.width() > 0
    assert img.height() > 0
    assert not img.isNull()


def test_worker_reuses_one_handle_per_source(tmp_path):
    """Merging must not open a fresh handle for every single render."""
    pdf_path = tmp_path / "test.pdf"
    _make_pdf(pdf_path)

    worker = RenderWorker()
    seen = []
    worker.rendered.connect(lambda key, img: seen.append(key))

    for index in (0, 0, 0):
        key = ("page", 0, index, 0, 1.0, 1.0)
        worker._render(RenderRequest(key, str(pdf_path), index, 1.0, 0))

    assert len(worker._docs) == 1
    assert len(seen) == 3


def test_worker_reports_a_missing_source(tmp_path):
    """A vanished source must not raise, and must not leave the asker hanging.

    The requester marks a key as "in flight"; it clears that marker on
    render_failed. Without the signal the page would wait forever for a
    render that can never arrive and would never be retried.
    """
    worker = RenderWorker()
    seen = []
    failed = []
    worker.rendered.connect(lambda key, img: seen.append(key))
    worker.render_failed.connect(failed.append)

    key = ("page", 0, 0, 0, 1.0, 1.0)
    worker._render(RenderRequest(key, str(tmp_path / "nope.pdf"), 0, 1.0, 0))

    assert seen == []
    assert failed == [key]


def test_worker_reports_a_page_out_of_range(tmp_path):
    """A bad page index is a per-request failure, not a thread-killer."""
    pdf_path = tmp_path / "one.pdf"
    _make_pdf(pdf_path)

    worker = RenderWorker()
    failed = []
    worker.render_failed.connect(failed.append)

    key = ("page", 0, 99, 0, 1.0, 1.0)
    worker._render(RenderRequest(key, str(pdf_path), 99, 1.0, 0))

    assert failed == [key]


def test_evict_forgets_and_closes_a_handle(tmp_path):
    """After saving over a file, the worker must not keep reading the old inode."""
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path)

    worker = RenderWorker()
    key = ("page", 0, 0, 0, 1.0, 1.0)
    worker._render(RenderRequest(key, str(pdf_path), 0, 1.0, 0))
    assert str(pdf_path) in worker._docs

    worker._evict(str(pdf_path))

    assert str(pdf_path) not in worker._docs
    assert worker._docs == {}


def test_evict_ignores_an_unknown_path(tmp_path):
    """Evicting a path we never opened is a no-op, not an error."""
    worker = RenderWorker()
    worker._evict(str(tmp_path / "never-opened.pdf"))
    assert worker._docs == {}


def test_worker_rotation():
    """Verify that prerotate produces a different transformation matrix."""
    mat_normal = pymupdf.Matrix(1.0, 1.0)
    mat_rotated = pymupdf.Matrix(1.0, 1.0).prerotate(90)
    # A 90° rotation matrix should differ from the identity
    assert mat_rotated != mat_normal


def test_worker_reports_a_mupdf_error_as_a_failure(tmp_path):
    """MuPDF's own exceptions are not RuntimeError: they must still fail cleanly.

    A large-format page (14400 pt, the PDF maximum) at the view's highest
    zoom on a HiDPI screen (8 × 2) asks MuPDF for an image it refuses to
    build, with ``FzErrorLimit``, which derives straight from ``Exception``.
    MuPDF checks the size before allocating, so this costs no memory.
    """
    pdf_path = tmp_path / "poster.pdf"
    doc = pymupdf.open()
    doc.new_page(width=14400, height=14400)
    doc.save(str(pdf_path))
    doc.close()

    worker = RenderWorker()
    seen = []
    failed = []
    worker.rendered.connect(lambda key, img: seen.append(key))
    worker.render_failed.connect(failed.append)

    key = ("page", 0, 0, 0, 8.0, 2.0)
    worker._render(RenderRequest(key, str(pdf_path), 0, 16.0, 0))

    assert seen == []
    assert failed == [key]


def _encrypted_pdf(path, password: str = "segreta") -> str:
    """One page with a word on it, locked with *password*."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "SEGRETO", fontsize=24)
    doc.save(
        str(path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="proprietario",
        user_pw=password,
    )
    doc.close()
    return str(path)


def _has_ink(image) -> bool:
    """Whether anything was drawn: an empty page renders uniformly white."""
    return any(
        image.pixel(x, y) != 0xFFFFFF
        for y in range(0, min(150, image.height()), 3)
        for x in range(0, min(300, image.width()), 3)
    )


def test_a_locked_source_renders_nothing_and_does_not_raise(tmp_path):
    """The worker never asks for a password: it fails that page and moves on."""
    path = _encrypted_pdf(tmp_path / "cifrato.pdf")

    worker = RenderWorker()
    seen = []
    failed = []
    worker.rendered.connect(lambda key, img: seen.append(key))
    worker.render_failed.connect(failed.append)

    key = ("page", 0, 0, 0, 1.0, 1.0)
    worker._render(RenderRequest(key, path, 0, 1.0, 0))

    assert seen == []
    assert failed == [key]


def test_authenticate_unlocks_the_document(tmp_path):
    """After the password arrives, the same page really has its content."""
    path = _encrypted_pdf(tmp_path / "cifrato.pdf")

    worker = RenderWorker()
    images = []
    worker.rendered.connect(lambda key, img: images.append(img))

    worker.authenticate(path, "segreta")
    assert path in worker._docs

    worker._render(RenderRequest(("page", 0, 0, 0, 1.0, 1.0), path, 0, 1.0, 0))

    assert len(images) == 1
    assert _has_ink(images[0]), "la pagina decifrata deve mostrare il suo testo"


def test_a_failed_render_does_not_poison_the_handle(tmp_path):
    """The sequence the window produces: locked render, password, render again.

    MuPDF leaves a handle that touched a page of a locked document unable to
    decrypt anything afterwards -- measured, ``authenticate`` then reports
    success and the text comes back empty, with "aes padding out of range"
    from the library. Nothing here ever touches a page before the unlock, and
    this test watches that order hold: a blank render is still a valid QImage,
    so the assertion is on the ink, not on the image existing.
    """
    path = _encrypted_pdf(tmp_path / "cifrato.pdf")

    worker = RenderWorker()
    failed = []
    images = []
    worker.render_failed.connect(failed.append)
    worker.rendered.connect(lambda key, img: images.append(img))
    key = ("page", 0, 0, 0, 1.0, 1.0)

    worker._render(RenderRequest(key, path, 0, 1.0, 0))  # still locked
    worker.authenticate(path, "segreta")
    worker._render(RenderRequest(key, path, 0, 1.0, 0))

    assert len(failed) == 1
    assert len(images) == 1
    assert _has_ink(images[0]), "la pagina e` tornata vuota dopo lo sblocco"
