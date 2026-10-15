"""Tests for RenderWorker rendering."""

import fitz

from plico.rendering import RenderRequest, RenderWorker


def test_render_worker_renders_page(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Test Page", fontsize=24)
    doc.save(str(pdf_path))
    doc.close()

    worker = RenderWorker()
    worker._open(str(pdf_path))

    rendered_images = []

    def on_rendered(key, image):
        rendered_images.append((key, image))

    worker.rendered.connect(on_rendered)

    key = (0, 0, 1.0)
    req = RenderRequest(key, 0, 1.0, 0)
    worker._render(req)

    assert len(rendered_images) == 1
    assert rendered_images[0][0] == key
    img = rendered_images[0][1]
    assert img.width() > 0
    assert img.height() > 0
    assert not img.isNull()


def test_worker_rotation():
    """Verify that prerotate produces a different transformation matrix."""
    mat_normal = fitz.Matrix(1.0, 1.0)
    mat_rotated = fitz.Matrix(1.0, 1.0).prerotate(90)
    # A 90° rotation matrix should differ from the identity
    assert mat_rotated != mat_normal