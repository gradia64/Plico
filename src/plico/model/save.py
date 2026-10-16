"""Save (materialize virtual page list back to a real PDF)."""

import contextlib
import os
import tempfile
from collections.abc import Callable, Iterator
from typing import TypeVar

import pymupdf

from .document import DocumentModel, PageItem, open_for_reading
from .forms import write_fields
from .optimize import CompressionLevel, CompressionResult, Progress, optimize_in_place

_T = TypeVar("_T")


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


def _redact(page: pymupdf.Page, item: PageItem) -> None:
    """Burn *item*'s redaction rectangles into *page*.

    ``add_redact_annot`` expects coordinates in the page's UNROTATED space,
    which is exactly the space the model stores its rectangles in, so there
    is nothing to convert here. ``apply_redactions`` then removes the text
    under the box, blanks the overlapping image pixels and drops the line art
    that crosses it -- and it leaves the page's /Rotate alone, so it can run
    after ``set_rotation`` without changing the orientation we just wrote.

    This is the point of no return: the words are gone from the content
    stream, not merely covered up.
    """
    for rect in item.redactions:
        page.add_redact_annot(pymupdf.Rect(*rect.as_tuple()))
    page.apply_redactions()
    # The content under the rectangles is gone, but the annotations are not:
    # a sticky note repeating a redacted word survives apply_redactions() and
    # would leak exactly what the redaction was meant to hide (measured). So
    # anything that touches a rectangle goes with it -- the same rule the eye
    # applies to a redaction.
    for annot in list(page.annots() or []):
        if any(annot.rect.intersects(pymupdf.Rect(*r.as_tuple())) for r in item.redactions):
            page.delete_annot(annot)


def _fill_source_fields(doc: pymupdf.Document, values: dict[str, str]) -> None:
    """Write *values* into the form fields of *doc*, in memory only.

    The values are written where the field *lives* -- into the source
    document, before its pages are copied -- and not into the output
    afterwards, for two reasons.

    A field name belongs to the document, not to a page. Two widgets called
    ``nome`` are one field with one /V, and a field whose kids sit on several
    pages keeps its /V in the parent. ``update()`` regenerates the appearance
    of the widget it is called on, so writing only on the page the user
    happened to edit would leave every other page painting the old value -- and
    on a merged document the result would depend on the merge order. Walking
    every page of the source reaches all of them, whichever way the field is
    spelled.

    And MuPDF *renames* a field as it copies it, to keep the names unique:
    the second ``nome`` becomes ``nome [12]``. After the copy the name the user
    typed does not identify the field any more, so the write would silently do
    nothing at all -- which is what used to happen as soon as a page was
    reordered.

    Nothing is written to disk here: the handle is modified in memory and
    never saved, and the file on disk is only read.
    """
    for index in range(len(doc)):
        # Bound to a local on purpose: a widget keeps a weak reference to its
        # page, so a temporary would be collected before the first update().
        page = doc[index]
        write_fields(page, values)


def _write_pdf(
    model: DocumentModel, out_path: str, pages: list[int] | None = None
) -> None:
    """Build the output PDF at *out_path* from the virtual page list.

    *pages* selects a subset by 0-based index, preserving the given order;
    ``None`` means "every page, in model order".

    The output is rebuilt from pages and nothing else, so no document-level
    data follows its source: ``/Info``, the XMP packet and the embedded files
    are all left behind. That is why a redaction needs no separate metadata
    cleanup -- and it is also why a plain "save as" does not keep the title.
    """
    assert model.sources, "No document open"
    items = model.pages if pages is None else [model.pages[i] for i in pages]
    # One value per field name per source: the user may have typed on the page
    # that shows the field first and on the one that shows it again, and PDF
    # has a single slot for both. The last page in document order wins, which
    # is the value the file already reports, being the last update() written.
    values_by_source: dict[int, dict[str, str]] = {}
    for item in items:
        if item.form_values:
            values_by_source.setdefault(item.source_id, {}).update(item.form_values)
    # One handle per source document, opened on demand: a merged document
    # can interleave pages from several files, so the run list must be
    # served from whichever source each run belongs to.
    sources: dict[int, pymupdf.Document] = {}
    try:
        with pymupdf.open() as out:
            for run in _contiguous_runs(items):
                source_id = run[0].source_id
                src = sources.get(source_id)
                if src is None:
                    path = model.sources[source_id]
                    # An encrypted source is unlocked again here: the model
                    # kept the password precisely because this function has
                    # nobody to ask (and neither has the worker).
                    src = open_for_reading(path, model.passwords.get(path))
                    sources[source_id] = src
                    # Fields are written before the pages are copied, and
                    # before any redaction: see _fill_source_fields.
                    values = values_by_source.get(source_id)
                    if values:
                        _fill_source_fields(src, values)
                out.insert_pdf(
                    src,
                    from_page=run[0].source_index,
                    to_page=run[-1].source_index,
                )
                # Rotation is per page, so it is applied after the bulk copy.
                base = len(out) - len(run)
                for offset, item in enumerate(run):
                    page = out[base + offset]
                    page.set_rotation(item.total_rotation)
            if len(out) == 0:
                # A PDF with zero pages is not a useful artefact; fail loudly
                # rather than writing a file the user cannot open.
                raise ValueError("Il documento non contiene pagine da salvare.")
            # The redactions run on the built pages: out[] and items are
            # parallel, so a redaction lands on the page built for the item
            # it belongs to.
            for index, item in enumerate(items):
                if item.redactions:
                    page = out[index]
                    _redact(page, item)
            out.save(out_path, garbage=4, deflate=True)
    finally:
        for src in sources.values():
            src.close()


def _write_atomically(
    model: DocumentModel,
    target: str,
    pages: list[int] | None,
    optimize: Callable[[str], _T] | None = None,
) -> _T | None:
    """Write *target*, never destroying the file currently being read.

    PyMuPDF cannot write to a document it is reading, so when the target is
    the open source the output has to go to a temporary file in the same
    directory and replace the original only once written successfully. Every
    write goes that way, not just that one: "save as" over an existing file
    the user never opened would otherwise be written straight over, and a
    failure halfway through (a full disk, a page MuPDF refuses) would leave
    that file truncated. The direct route saved nothing but one rename, and
    costed the property that matters most here.

    The price is that the *directory* must be writable, because the temporary
    is created there. Writing straight to the file would have worked on a
    read-only directory with a writable file; that is the trade being made,
    and it is the usual one for an atomic save.

    *optimize*, when given, is handed the freshly written file -- still a
    temporary, so a failure leaves *target* untouched -- and its return value
    is passed back to the caller.
    """
    directory = os.path.dirname(target)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".pdf.tmp")
    os.close(fd)
    try:
        _write_pdf(model, tmp_path, pages)
        result = optimize(tmp_path) if optimize is not None else None
        # Keep the original file's permissions across the swap.
        if os.path.exists(target):
            os.chmod(tmp_path, os.stat(target).st_mode & 0o7777)
        os.replace(tmp_path, target)
        return result
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


def save_compressed(
    model: DocumentModel,
    out_path: str,
    level: CompressionLevel,
    progress: Progress | None = None,
) -> CompressionResult:
    """Like :func:`save_as`, but compress the result before writing it.

    The compression works on the **materialised** document (deletions,
    reorderings and rotations included), so the file that comes out is exactly
    the one :func:`save_as` would have written, only smaller. The source PDFs
    are not touched even when *out_path* is one of them: the pass always goes
    through a temporary file.
    """
    assert model.sources, "No document open"
    result = _write_atomically(
        model,
        os.path.abspath(out_path),
        None,
        optimize=lambda path: optimize_in_place(path, level, progress),
    )
    # `optimize` e` sempre fornito qui, quindi il risultato c'e` sempre.
    assert result is not None
    return result


def extract_pages(model: DocumentModel, out_path: str, indices: list[int]) -> None:
    """Split: write only *indices* (0-based, in the order given).

    This never mutates the open document -- the selection is materialised
    into a separate file, exactly like :func:`save_as`.

    Extracting onto one of the open sources is refused. A full save over a
    source can be followed by re-opening the file, because the file then IS
    the document; a subset written there would leave the pages that were
    not extracted pointing at pages that no longer exist, and the next save
    would quietly drop them.
    """
    assert model.sources, "No document open"
    if not indices:
        raise ValueError("Nessuna pagina da estrarre.")
    target = os.path.abspath(out_path)
    if model.sources_at(target):
        raise ValueError(
            "Non si possono estrarre pagine sopra un documento aperto: "
            "scegli un altro file."
        )
    _write_atomically(model, target, indices)


def parse_page_ranges(spec: str, page_count: int) -> list[int]:
    """Parse a 1-based page spec such as ``"1-3,5,8"`` into 0-based indices.

    The order the user typed is preserved, so ``"5,1-3"`` reorders as well
    as extracts. Range bounds are inclusive. Anything malformed, out of
    range, or empty raises :class:`ValueError` with a message meant to be
    shown to the user: silently dropping pages from a split would be worse
    than refusing to run it.
    """

    def checked(number: int) -> int:
        if not 1 <= number <= page_count:
            raise ValueError(
                f"La pagina {number} non esiste: il documento ne ha {page_count}."
            )
        return number

    indices: list[int] = []

    for token in spec.replace(" ", "").split(","):
        if not token:
            continue
        if "-" in token:
            low, _, high = token.partition("-")
            if not (low.isdigit() and high.isdigit()):
                raise ValueError(f"Intervallo non valido: «{token}»")
            start, end = int(low), int(high)
            if start > end:
                raise ValueError(f"Intervallo al contrario: «{token}»")
            # Check the bounds BEFORE building the range. A spec such as
            # "1-5000000" used to materialise five million integers and only
            # then discover that the document has three pages -- an
            # out-of-memory waiting to happen on a typo. The range is
            # contiguous and ascending, so checking its ends is enough.
            checked(start)
            checked(end)
            indices.extend(range(start, end + 1))
        elif token.isdigit():
            indices.append(checked(int(token)))
        else:
            raise ValueError(f"Indicazione di pagina non valida: «{token}»")

    if not indices:
        raise ValueError("Nessuna pagina indicata.")

    return [number - 1 for number in indices]
