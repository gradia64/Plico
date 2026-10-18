"""Save (materialize virtual page list back to a real PDF)."""

import contextlib
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import pymupdf
from PySide6.QtCore import QCoreApplication

from .assemble import acroform_key, assemble
from .document import DocumentModel, PageItem, open_for_reading
from .forms import write_fields
from .ocr import write_layer
from .optimize import (
    CompressionLevel,
    CompressionOptions,
    CompressionResult,
    Progress,
    optimize_in_place,
)
from .redact import burn_redactions
from .sign import SignatureRequest, sign_in_place
from .textedit import apply_edit

_T = TypeVar("_T")


def _redact(page: pymupdf.Page, item: PageItem) -> None:
    """Burn *item*'s redaction rectangles into *page*.

    This is the point of no return: the words are gone from the content
    stream, not merely covered up. The work is :func:`burn_redactions`, which
    the on-screen preview runs too.
    """
    burn_redactions(page, item.redactions)


def _edit_text(page: pymupdf.Page, item: PageItem) -> None:
    """Write *item*'s text replacements into *page*.

    Runs BEFORE the redactions of the same page: a redaction drawn over an
    edited span must take the new words with it, exactly as it would take
    the old ones. Each span was captured from the source and the page here
    is that source's copy, so the span's rectangle and baseline still hold.
    """
    for edit in item.text_edits:
        apply_edit(page, edit.span, edit.new_text)


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


def _write_ocr(page: pymupdf.Page, item: PageItem) -> None:
    """Write *item*'s OCR words onto *page* as an invisible text layer.

    Runs BEFORE the redactions of the same page, and that order is the whole
    point: the layer is real text in the content stream, so a redaction drawn
    over a recognised word takes the word with it. The other way round would
    leave the redacted word perfectly extractable -- invisible on screen, very
    much not invisible to whoever copies it out, which is the worst possible
    way to lose a redaction.
    """
    write_layer(page, item.ocr_words)


def _signed(doc: pymupdf.Document, widget: pymupdf.Widget) -> bool:
    """Whether a signature widget holds a signature (a /V), on itself or its field."""
    kind: str = doc.xref_get_key(widget.xref, "V")[0]
    if kind != "null":
        return True
    parent_kind, reference = doc.xref_get_key(widget.xref, "Parent")
    if parent_kind == "xref" and reference:
        kind = doc.xref_get_key(int(reference.split()[0]), "V")[0]
        return kind != "null"
    return False


def _drop_old_signatures(out: pymupdf.Document) -> None:
    """Take out the signatures the rebuilt file can no longer honour.

    A signature covers the bytes of the file it was made in, and this file is
    built anew: copied over by ``insert_pdf()``, the old one survives as a
    field whose digest matches nothing, and /SigFlags still says "signed"
    (measured: a plain save of a signed document came out with the field, the
    flags at 3, and pyHanko reading ``intact=False``). Reopened, the file
    looked signed and failed verification -- the look of a forgery, for what
    was an ordinary save. The filled signature fields go; an EMPTY one, a
    place left for a signature to come, is form content and stays.
    """
    found = False
    for index in range(len(out)):
        # Bound to a local: a widget keeps a weak reference to its page.
        page = out[index]
        for widget in list(page.widgets() or ()):
            if widget.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE and _signed(  # type: ignore[attr-defined]
                out, widget
            ):
                page.delete_widget(widget)
                found = True
    target = acroform_key(out, "SigFlags")
    if found and target is not None:
        out.xref_set_key(*target, "0")


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
    if not items:
        # A PDF with zero pages is not a useful artefact; fail loudly rather
        # than writing a file the user cannot open.
        raise ValueError(QCoreApplication.translate("Save", "Il documento non contiene pagine da salvare."))
    # One handle per source document: a merged document can interleave pages
    # from several files, and each is copied from its own.
    sources: dict[int, pymupdf.Document] = {}
    try:
        for item in items:
            if item.source_id in sources:
                continue
            path = model.sources[item.source_id]
            # An encrypted source is unlocked again here: the model kept the
            # password precisely because this function has nobody to ask (and
            # neither has the worker).
            src = open_for_reading(path, model.passwords.get(path))
            sources[item.source_id] = src
            # Fields are written before the pages are copied, and before any
            # redaction: see _fill_source_fields.
            values = values_by_source.get(item.source_id)
            if values:
                _fill_source_fields(src, values)
        with pymupdf.open() as out:
            # Each source copied once, then put in order inside the output:
            # copying a source twice loses or renames its form fields (see
            # assemble.py).
            assemble(out, [(sources[item.source_id], item.source_index) for item in items])
            # Rotation is per page, so it is applied after the copy.
            for index, item in enumerate(items):
                page = out[index]
                page.set_rotation(item.total_rotation)
            # Text edits and redactions run on the built pages: out[] and items
            # are parallel, so each lands on the page built for its item. The
            # order is the dependency order: the OCR layer is text a redaction
            # must be able to delete, and an edit goes before the redaction
            # that has to remove the NEW words, not the old ones.
            for index, item in enumerate(items):
                if item.ocr_words or item.text_edits or item.redactions:
                    page = out[index]
                    if item.ocr_words:
                        _write_ocr(page, item)
                    if item.text_edits:
                        _edit_text(page, item)
                    if item.redactions:
                        _redact(page, item)
            _drop_old_signatures(out)
            if any(item.text_edits for item in items):
                # A replacement embeds its font whole: one edit in a system
                # font took a 36 KB file to 241 KB. Subsetting brings it back
                # to 44 KB (measured), and only runs when something was written.
                out.subset_fonts()
            out.save(out_path, garbage=4, deflate=True)
    finally:
        for src in sources.values():
            src.close()


def _write_temporary(model: DocumentModel, target: str, pages: list[int] | None) -> str:
    """Materialise the document into a temporary next to *target*.

    The caller owns the file that comes back: it either adopts it (see
    :func:`_adopt`) or deletes it. Nothing is written to *target* here.
    """
    directory = os.path.dirname(target)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".pdf.tmp")
    os.close(fd)
    try:
        _write_pdf(model, tmp_path, pages)
    except BaseException:
        # Never leave a half-written temp file behind.
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    return tmp_path


def _adopt(tmp_path: str, target: str) -> None:
    """Put the temporary in *target*'s place, keeping *target*'s permissions."""
    # Keep the original file's permissions across the swap.
    if os.path.exists(target):
        os.chmod(tmp_path, os.stat(target).st_mode & 0o7777)
    os.replace(tmp_path, target)


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
    tmp_path = _write_temporary(model, target, pages)
    try:
        result = optimize(tmp_path) if optimize is not None else None
        _adopt(tmp_path, target)
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


@dataclass
class CompressionPreview:
    """A compressed file written, and waiting for a yes.

    The work is already done -- the temporary next to the destination holds the
    real result -- so the size the user is shown before deciding is the size
    they would get, not an estimate of it. Whoever creates one must either
    :meth:`keep` it or :meth:`drop` it: the file is real, and has to be cleaned
    up one way or the other.
    """

    path: str
    target: str
    result: CompressionResult

    def keep(self) -> None:
        """Give the temporary *target*'s name, and with it its permissions."""
        _adopt(self.path, self.target)

    def drop(self) -> None:
        """Throw the compressed file away, leaving *target* as it was."""
        with contextlib.suppress(OSError):
            os.unlink(self.path)


def prepare_compressed(
    model: DocumentModel,
    out_path: str,
    options: CompressionOptions | CompressionLevel,
    progress: Progress | None = None,
) -> CompressionPreview:
    """Compress into a temporary, without touching *out_path*.

    Splitting the work from the swap is what lets the window show the gain
    before writing anything: the numbers come from the real result, and the
    passes run once instead of twice.
    """
    assert model.sources, "No document open"
    target = os.path.abspath(out_path)
    tmp_path = _write_temporary(model, target, None)
    try:
        result = optimize_in_place(tmp_path, options, progress)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    return CompressionPreview(tmp_path, target, result)


def save_compressed(
    model: DocumentModel,
    out_path: str,
    options: CompressionOptions | CompressionLevel,
    progress: Progress | None = None,
) -> CompressionResult:
    """Like :func:`save_as`, but compress the result before writing it.

    The compression works on the **materialised** document (deletions,
    reorderings and rotations included), so the file that comes out is exactly
    the one :func:`save_as` would have written, only smaller. The source PDFs
    are not touched even when *out_path* is one of them: the pass always goes
    through a temporary file.

    A compression that gains nothing is not written at all: an already
    optimised PDF is left exactly as it was, which is the promise this function
    has always made.
    """
    preview = prepare_compressed(model, out_path, options, progress)
    if preview.result.shrank:
        preview.keep()
    else:
        preview.drop()
    return preview.result


def save_signed(
    model: DocumentModel, out_path: str, request: SignatureRequest
) -> None:
    """Like :func:`save_as`, then sign the file that came out.

    Signing is not something that happens to the page list: it is a signature
    *over the bytes* of a file, so it can only be applied after the file
    exists. It runs inside the temporary, before the swap, so a certificate
    that turns out to be unusable leaves the previous file intact -- the same
    guarantee every other write here has.

    A signature is computed over everything that was written, which is why the
    window drops the open document afterwards and adopts the signed file: the
    page list it held described the unsigned version, and editing it further
    would quietly break the signature.
    """
    assert model.sources, "No document open"
    _write_atomically(
        model,
        os.path.abspath(out_path),
        None,
        optimize=lambda path: sign_in_place(path, request),
    )


def sign_copy(source: str, out_path: str, request: SignatureRequest) -> None:
    """Sign the file *source* exactly as it is on disk, writing *out_path*.

    The way to add a signature to a file that already carries one. Going
    through :func:`save_signed` would rebuild the file from its pages, and a
    rebuilt file is new bytes: the signatures it had stop covering anything
    (measured: the first one reads ``intact=False`` after the second). Here
    the bytes are copied untouched and pyHanko appends the new signature as
    an incremental update, which is what leaves the earlier ones valid.

    Same guarantees as every other write: a temporary next to *out_path*,
    signed there, and swapped in only once it is complete -- *source* and
    *out_path* may be the same file.
    """
    target = os.path.abspath(out_path)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(target), suffix=".pdf.tmp")
    os.close(fd)
    try:
        shutil.copyfile(source, tmp_path)
        sign_in_place(tmp_path, request)
        _adopt(tmp_path, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


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
        raise ValueError(QCoreApplication.translate("Save", "Nessuna pagina da estrarre."))
    target = os.path.abspath(out_path)
    if model.sources_at(target):
        raise ValueError(
            QCoreApplication.translate(
                "Save",
                "Non si possono estrarre pagine sopra un documento aperto: "
                "scegli un altro file.",
            )
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
                QCoreApplication.translate(
                    "PageRanges", "La pagina {0} non esiste: il documento ne ha {1}."
                ).format(number, page_count)
            )
        return number

    indices: list[int] = []

    for token in spec.replace(" ", "").split(","):
        if not token:
            continue
        if "-" in token:
            low, _, high = token.partition("-")
            if not (low.isdigit() and high.isdigit()):
                raise ValueError(QCoreApplication.translate("PageRanges", "Intervallo non valido: «{0}»").format(token))
            start, end = int(low), int(high)
            if start > end:
                raise ValueError(QCoreApplication.translate("PageRanges", "Intervallo al contrario: «{0}»").format(token))
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
            raise ValueError(
                QCoreApplication.translate("PageRanges", "Indicazione di pagina non valida: «{0}»").format(token)
            )

    if not indices:
        raise ValueError(QCoreApplication.translate("PageRanges", "Nessuna pagina indicata."))

    return [number - 1 for number in indices]
