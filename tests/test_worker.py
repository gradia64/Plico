"""Tests for RenderWorker rendering."""

import fitz

from plico.rendering import RenderRequest, RenderWorker


def _make_pdf(path, text="Test Page"):
    doc = fitz.open()
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


def test_worker_survives_a_missing_source(tmp_path):
    """A sourced document that vanished must not raise inside the thread."""
    worker = RenderWorker()
    seen = []
    worker.rendered.connect(lambda key, img: seen.append(key))

    key = ("page", 0, 0, 0, 1.0, 1.0)
    worker._render(RenderRequest(key, str(tmp_path / "nope.pdf"), 0, 1.0, 0))

    assert seen == []


def test_worker_rotation():
    """Verify that prerotate produces a different transformation matrix."""
    mat_normal = fitz.Matrix(1.0, 1.0)
    mat_rotated = fitz.Matrix(1.0, 1.0).prerotate(90)
    # A 90° rotation matrix should differ from the identity
    assert mat_rotated != mat_normal
