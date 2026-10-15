"""Save (materialize virtual page list back to a real PDF)."""

import contextlib
import os
import tempfile
from collections.abc import Iterator

import fitz

from .document import DocumentModel, PageItem


def _contiguous_runs(items: list[PageItem]) -> Iterator[list[PageItem]]:
    """Group page items whose ``source_index`` values are consecutive.

    ``insert_pdf`` copies a *range* of pages, so a document that was merely
    reordered can be copied in a handful of calls instead of one call per
    page. On very large PDFs this is the difference between seconds and
    minutes.
    """
    run: list[PageItem] = []
    for item in items:
        if run and item.source_index != run[-1].source_index + 1:
            yield run
            run = []
        run.append(item)
    if run:
        yield run


def _write_pdf(model: DocumentModel, out_path: str) -> None:
    """Build the output PDF at *out_path* from the virtual page list."""
    assert model.path is not None, "No document open"
    with fitz.open(model.path) as src, fitz.open() as out:
        for run in _contiguous_runs(model.pages):
            first = run[0].source_index
            last = run[-1].source_index
            out.insert_pdf(src, from_page=first, to_page=last)
            # Rotation is per page, so it is applied after the bulk copy.
            base = len(out) - len(run)
            for offset, item in enumerate(run):
                out[base + offset].set_rotation(item.total_rotation)
        if len(out) == 0:
            # A PDF with zero pages is not a useful artefact; fail loudly
            # rather than writing a file the user cannot open.
            raise ValueError("Il documento non contiene pagine da salvare.")
        out.save(out_path, garbage=4, deflate=True)


def save_as(model: DocumentModel, out_path: str) -> None:
    """Render the virtual page list to *out_path*.

    The source PDF is opened read-only; pages are copied by ``source_index``
    and their rotation is set to ``base_rotation + rotation``.

    Saving onto the file that is currently open is allowed: PyMuPDF cannot
    write to a file it is reading, so the new document goes to a temporary
    file in the same directory and only replaces the original once it has
    been written successfully. A failure therefore never destroys the
    user's original.
    """
    assert model.path is not None, "No document open"

    target = os.path.abspath(out_path)
    source = os.path.abspath(model.path)
    overwriting = os.path.exists(target) and os.path.samefile(target, source)

    if not overwriting:
        _write_pdf(model, target)
        return

    directory = os.path.dirname(target)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".pdf.tmp")
    os.close(fd)
    try:
        _write_pdf(model, tmp_path)
        # Keep the original file's permissions across the swap.
        os.chmod(tmp_path, os.stat(source).st_mode & 0o7777)
        os.replace(tmp_path, target)
    except BaseException:
        # Never leave a half-written temp file behind.
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
