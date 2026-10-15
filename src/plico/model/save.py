"""Save (materialize virtual page list back to a real PDF)."""

import contextlib
import os
import tempfile
from collections.abc import Iterator

import fitz

from .document import DocumentModel, PageItem


def _contiguous_runs(items: list[PageItem]) -> Iterator[list[PageItem]]:
    """Group page items that are consecutive pages of the SAME source.

    ``insert_pdf`` copies a *range* of pages, so a document that was merely
    reordered can be copied in a handful of calls instead of one call per
    page. On very large PDFs this is the difference between seconds and
    minutes. The run must break whenever the source document changes, or a
    merged document would copy the wrong pages.
    """
    run: list[PageItem] = []
    for item in items:
        if run and not (
            item.source_id == run[-1].source_id
            and item.source_index == run[-1].source_index + 1
        ):
            yield run
            run = []
        run.append(item)
    if run:
        yield run


def _write_pdf(
    model: DocumentModel, out_path: str, pages: list[int] | None = None
) -> None:
    """Build the output PDF at *out_path* from the virtual page list.

    *pages* selects a subset by 0-based index, preserving the given order;
    ``None`` means "every page, in model order".
    """
    assert model.sources, "No document open"
    items = model.pages if pages is None else [model.pages[i] for i in pages]
    # One handle per source document, opened on demand: a merged document
    # can interleave pages from several files, so the run list must be
    # served from whichever source each run belongs to.
    sources: dict[int, fitz.Document] = {}
    try:
        with fitz.open() as out:
            for run in _contiguous_runs(items):
                source_id = run[0].source_id
                src = sources.get(source_id)
                if src is None:
                    src = fitz.open(model.sources[source_id])
                    sources[source_id] = src
                out.insert_pdf(
                    src,
                    from_page=run[0].source_index,
                    to_page=run[-1].source_index,
                )
                # Rotation is per page, so it is applied after the bulk copy.
                base = len(out) - len(run)
                for offset, item in enumerate(run):
                    out[base + offset].set_rotation(item.total_rotation)
            if len(out) == 0:
                # A PDF with zero pages is not a useful artefact; fail loudly
                # rather than writing a file the user cannot open.
                raise ValueError("Il documento non contiene pagine da salvare.")
            out.save(out_path, garbage=4, deflate=True)
    finally:
        for src in sources.values():
            src.close()


def _write_atomically(
    model: DocumentModel, target: str, pages: list[int] | None
) -> None:
    """Write *target*, never destroying the file currently being read.

    PyMuPDF cannot write to a document it is reading, so when the target is
    the open source the output goes to a temporary file in the same
    directory and replaces the original only once written successfully.
    """
    # Merging means several sources; overwriting ANY of them would have
    # PyMuPDF writing to a file it is still reading.
    overwriting = os.path.exists(target) and any(
        os.path.exists(src) and os.path.samefile(target, src)
        for src in model.sources
    )

    if not overwriting:
        _write_pdf(model, target, pages)
        return

    directory = os.path.dirname(target)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".pdf.tmp")
    os.close(fd)
    try:
        _write_pdf(model, tmp_path, pages)
        # Keep the original file's permissions across the swap.
        os.chmod(tmp_path, os.stat(target).st_mode & 0o7777)
        os.replace(tmp_path, target)
    except BaseException:
        # Never leave a half-written temp file behind.
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def save_as(model: DocumentModel, out_path: str) -> None:
    """Render the virtual page list to *out_path*.

    The source PDF is opened read-only; pages are copied by ``source_index``
    and their rotation is set to ``base_rotation + rotation``.

    Saving onto the file that is currently open is allowed; see
    :func:`_write_atomically`.
    """
    assert model.sources, "No document open"
    _write_atomically(model, os.path.abspath(out_path), None)


def extract_pages(model: DocumentModel, out_path: str, indices: list[int]) -> None:
    """Split: write only *indices* (0-based, in the order given).

    This never mutates the open document -- the selection is materialised
    into a separate file, exactly like :func:`save_as`.
    """
    assert model.sources, "No document open"
    if not indices:
        raise ValueError("Nessuna pagina da estrarre.")
    _write_atomically(model, os.path.abspath(out_path), indices)


def parse_page_ranges(spec: str, page_count: int) -> list[int]:
    """Parse a 1-based page spec such as ``"1-3,5,8"`` into 0-based indices.

    The order the user typed is preserved, so ``"5,1-3"`` reorders as well
    as extracts. Range bounds are inclusive. Anything malformed, out of
    range, or empty raises :class:`ValueError` with a message meant to be
    shown to the user: silently dropping pages from a split would be worse
    than refusing to run it.
    """
    indices: list[int] = []

    for token in spec.replace(" ", "").split(","):
        if not token:
            continue
        if "-" in token:
            low, _, high = token.partition("-")
            if not (low.isdigit() and high.isdigit()):
                raise ValueError(f"Intervallo non valido: «{token}»")
            if int(low) > int(high):
                raise ValueError(f"Intervallo al contrario: «{token}»")
            indices.extend(range(int(low), int(high) + 1))
        elif token.isdigit():
            indices.append(int(token))
        else:
            raise ValueError(f"Indicazione di pagina non valida: «{token}»")

    if not indices:
        raise ValueError("Nessuna pagina indicata.")

    for number in indices:
        if not 1 <= number <= page_count:
            raise ValueError(
                f"La pagina {number} non esiste: il documento ne ha {page_count}."
            )

    return [number - 1 for number in indices]
