"""Save (materialize virtual page list back to a real PDF)."""

import os
import re
import secrets
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import pikepdf
import pymupdf
from PySide6.QtCore import QCoreApplication

from .assemble import acroform_key, assemble, prune_fields
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
from .sign import SignatureRequest, holds_signature, sign_in_place, signature_widgets
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


def _drop_old_signatures(out: pymupdf.Document) -> bool:
    """Take out the signatures the rebuilt file can no longer honour.

    A signature covers the bytes of the file it was made in, and this file is
    built anew: copied over by ``insert_pdf()``, the old one survives as a
    field whose digest matches nothing, and /SigFlags still says "signed"
    (measured: a plain save of a signed document came out with the field, the
    flags at 3, and pyHanko reading ``intact=False``). Reopened, the file
    looked signed and failed verification -- the look of a forgery, for what
    was an ordinary save. The filled signature fields go; an EMPTY one, a
    place left for a signature to come, is form content and stays.

    Returns whether any signature was taken out; :func:`_settle_sigflags`
    then says what /SigFlags must become.
    """
    found = False
    for index, xref in signature_widgets(out):
        if not holds_signature(out, xref):
            continue
        # Bound to a local: a widget keeps a weak reference to its page.
        # load_widget and not a walk of page.widgets(): see signature_widgets.
        page = out[index]
        page.delete_widget(page.load_widget(xref))
        found = True
    return found


def _settle_sigflags(out: pymupdf.Document, dropped: bool) -> None:
    """Make /SigFlags tell the truth about the signature fields left.

    Bit 1 says a signature field exists, bit 2 that the file may only be
    appended to (because something in it is signed). With no signature field
    left -- every signature dropped, or an empty field taken by a redaction --
    the flags go to 0: a file that kept /SigFlags 3 after losing its only
    signature field still announced one (reported by a review). With empty
    fields left but the signatures gone, only bit 1 is still true.
    """
    target = acroform_key(out, "SigFlags")
    if target is None:
        return
    if not signature_widgets(out):
        out.xref_set_key(*target, "0")
    elif dropped:
        out.xref_set_key(*target, "1")


def _write_pdf(
    model: DocumentModel, out_path: str, pages: list[int] | None = None
) -> None:
    """Build the output PDF at *out_path* from the virtual page list.

    *pages* selects a subset by 0-based index, preserving the given order;
    ``None`` means "every page, in model order".

    The output is rebuilt from pages, so document-level data has to be
    carried over on purpose: :func:`_carry_document_data` brings the outline,
    the page labels and the metadata of the sources along, remapped to the
    pages written. Not when a redaction is written: a title, a bookmark or
    the XMP packet can hold the very words being removed, and then nothing
    but the pages follows (the window says so before writing). Embedded
    files are never carried.
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
            dropped = _drop_old_signatures(out)
            # After the redactions and the dropped signatures: both delete
            # widgets, and a field left without one must leave the AcroForm
            # with its value (see prune_fields).
            prune_fields(out)
            _settle_sigflags(out, dropped)
            _carry_document_data(out, sources, items)
            if any(item.text_edits for item in items):
                # A replacement embeds its font whole: one edit in a system
                # font took a 36 KB file to 241 KB. Subsetting brings it back
                # to 44 KB (measured), and only runs when something was written.
                out.subset_fonts()
            out.save(out_path, garbage=4, deflate=True)
    finally:
        for src in sources.values():
            src.close()


# Bookmarks carried at most: the outline comes from the file, and a crafted
# one with millions of entries would hold the save for minutes.
_MAX_OUTLINE = 20_000
# modDate is not among them: the file written now is a modified one.
_METADATA_KEYS = ("title", "author", "subject", "keywords", "creator", "producer", "creationDate")


def _carry_document_data(
    out: pymupdf.Document,
    sources: dict[int, pymupdf.Document],
    items: list[PageItem],
) -> None:
    """Give *out* the outline, page labels and metadata of its sources.

    Every save used to drop them -- rotating one page of a manual and
    pressing Ctrl+S took its bookmarks, its title and its "i, ii, iii"
    numbering away (reported by a review). Page labels are only numbers and
    always follow; the outline and the metadata do not when a redaction is
    written (see :func:`_write_pdf`).
    """
    # Where each source page ended up: its first copy, for a duplicated one.
    placed: dict[tuple[int, int], int] = {}
    for index, item in enumerate(items):
        placed.setdefault((item.source_id, item.source_index), index)
    _carry_page_labels(out, sources, items)
    if any(item.redactions for item in items):
        return
    # The sources in the order their pages first appear: a merge reads like
    # the files it is made of, one after the other.
    order = list(dict.fromkeys(item.source_id for item in items))
    outline: list[list] = []
    for source_id in order:
        # The entries above the current one, as (level, kept): an entry
        # whose page is gone goes, and its children move up to its place.
        ancestors: list[tuple[int, bool]] = []
        for level, title, page, *_ in sources[source_id].get_toc(simple=True):
            while ancestors and ancestors[-1][0] >= level:
                ancestors.pop()
            target = placed.get((source_id, page - 1))
            kept = target is not None
            if target is not None and len(outline) < _MAX_OUTLINE:
                depth = sum(1 for _, alive in ancestors if alive) + 1
                outline.append([depth, title, target + 1])
            ancestors.append((level, kept))
    if outline:
        out.set_toc(outline)
    # The metadata of the document the first page comes from: the one the
    # user opened, unless pages from a merged file were moved before it.
    main = sources[items[0].source_id]
    metadata = {key: main.metadata.get(key) or "" for key in _METADATA_KEYS}
    if any(metadata.values()):
        metadata["modDate"] = pymupdf.get_pdf_now()
        out.set_metadata(metadata)
    xmp = main.get_xml_metadata()
    if xmp:
        out.set_xml_metadata(xmp)


def _carry_page_labels(
    out: pymupdf.Document, sources: dict[int, pymupdf.Document], items: list[PageItem]
) -> None:
    """Page labels ("i, ii, iii, 1, 2...") renumbered for the pages written.

    A rule says "from this page on, this style, starting at this number"; a
    page keeps the label it had, and a new rule starts wherever the pages
    stop following each other in their source.
    """
    rules_of = {
        source_id: sorted(doc.get_page_labels(), key=lambda rule: rule["startpage"])
        for source_id, doc in sources.items()
    }
    if not any(rules_of.values()):
        return
    rules: list[dict] = []
    previous: tuple[int, int, int] | None = None  # source, page, rule index
    for index, item in enumerate(items):
        own = rules_of[item.source_id]
        position = max(
            (i for i, rule in enumerate(own) if rule["startpage"] <= item.source_index),
            default=-1,
        )
        key = (item.source_id, item.source_index, position)
        if previous is not None and key == (previous[0], previous[1] + 1, previous[2]):
            previous = key
            continue
        previous = key
        if position < 0:
            # No rule covers it: the plain number it showed, its position.
            rules.append({"startpage": index, "prefix": "", "style": "D", "firstpagenum": item.source_index + 1})
            continue
        rule = own[position]
        rules.append({
            "startpage": index,
            "prefix": rule.get("prefix", ""),
            "style": rule.get("style", ""),
            "firstpagenum": rule.get("firstpagenum", 1) + item.source_index - rule["startpage"],
        })
    out.set_page_labels(rules)


@dataclass(frozen=True)
class _Protection:
    """How the file being replaced was encrypted, to encrypt its successor.

    *password* is the user password, the one that opens the file; *owner* is
    the owner password the new file gets.
    """

    password: str
    owner: str
    permissions: int


# The permission bits of /P (ISO 32000, table 22), as Document.permissions
# reports them, and the pikepdf flag that carries each one.
_PERMISSION_FLAGS = {
    1 << 2: "print_lowres",
    1 << 3: "modify_other",
    1 << 4: "extract",
    1 << 5: "modify_annotation",
    1 << 8: "modify_form",
    1 << 9: "accessibility",
    1 << 10: "modify_assembly",
    1 << 11: "print_highres",
}


def _protection(model: DocumentModel, target: str) -> _Protection | None:
    """The encryption to give *target*, when it is an encrypted open source.

    The output is rebuilt from pages, and a rebuilt document carries no
    ``/Encrypt``: saving over a password-protected file wrote it back in the
    clear, with no word to the user (reported by a pentest). The password the
    user typed to open it is the one the session knows; the owner password is
    never known, so it becomes the owner password too -- the only way to keep
    the content protected, and the permissions are carried over as they were
    read. A *new* file written with "save as" stays a new, plain file: what is
    protected is the file the user is replacing.

    A file with only an owner password (an empty user password) opens without
    asking, so no password is known for it, but it is encrypted all the same
    and its permissions are the point of it: it used to be written back in the
    clear (reported by a review). It gets an empty user password again, and
    as owner password the one the user gave when asked (see
    :func:`owner_only_sources`), or a random one -- an empty owner password
    would open it with every permission.
    """
    for source in model.sources_at(target):
        password = model.passwords.get(source)
        with open_for_reading(source, password) as doc:
            if password:
                return _Protection(password, password, doc.permissions)
            if is_encrypted(doc):
                owner = model.owner_passwords.get(source) or secrets.token_urlsafe(32)
                return _Protection("", owner, doc.permissions)
    return None


def owner_only_sources(model: DocumentModel, target: str) -> list[str]:
    """The sources at *target* protected by an owner password only.

    The ones whose owner password the window has not asked for yet: writing
    over them keeps their restrictions, and the owner password the user
    knows can stay valid only if they type it.
    """
    found = []
    for source in model.sources_at(target):
        if model.passwords.get(source) or source in model.owner_passwords:
            continue
        if file_is_encrypted(source):
            found.append(source)
    return found


def owner_password_matches(path: str, password: str) -> bool:
    """Whether *password* is the owner password of the file at *path*."""
    try:
        with pikepdf.open(path, password=password) as pdf:
            return bool(pdf.owner_password_matched)
    except (pikepdf.PasswordError, OSError, pikepdf.PdfError):
        return False


def is_encrypted(doc: pymupdf.Document) -> bool:
    """Whether *doc* carries ``/Encrypt``, even with an empty user password.

    ``needs_pass`` and ``is_encrypted`` both say no for an owner-password-only
    file; the metadata still names its encryption.
    """
    return bool(doc.needs_pass or doc.metadata.get("encryption"))


def file_is_encrypted(path: str) -> bool:
    """Whether the file at *path* is an encrypted PDF (False if unreadable)."""
    try:
        with pymupdf.open(path) as doc:
            return is_encrypted(doc)
    except Exception:  # noqa: BLE001 -- not a PDF we can read is not a protected one
        return False


def _protection_password(model: DocumentModel, target: str) -> str | None:
    """The password :func:`_protection` gives *target*, if any."""
    protection = _protection(model, target)
    return protection.password if protection else None


def _protect(tmp_path: str, protection: _Protection | None) -> None:
    """Encrypt the temporary *tmp_path* in place (AES-256), if asked to.

    pikepdf and not PyMuPDF's own ``save(encryption=...)``: MuPDF writes
    ``/Encrypt`` as a direct object, and pyHanko refuses to sign such a file
    ("Encryption settings must be an indirect reference"); qpdf writes it
    indirect, and a protected document can then be signed too.
    """
    if protection is None:
        return
    allow = pikepdf.Permissions(
        **{flag: bool(protection.permissions & bit) for bit, flag in _PERMISSION_FLAGS.items()}
    )
    encrypted = tmp_path + ".enc"
    try:
        with pikepdf.open(tmp_path) as pdf:
            pdf.save(
                encrypted,
                encryption=pikepdf.Encryption(
                    user=protection.password, owner=protection.owner, R=6, allow=allow
                ),
            )
        os.replace(encrypted, tmp_path)
    except BaseException:
        if os.path.exists(encrypted):
            os.unlink(encrypted)
        raise


def _private_temporary(target: str) -> str:
    """An empty file for *target*'s content, in a directory only we can enter.

    Next to *target*, so the final rename stays on one filesystem and atomic.
    Not directly in *target*'s directory: ``mkstemp`` makes the file 0600, but
    PyMuPDF and pikepdf do not write into it -- they remove it and create a
    new one with the umask, 0644 on most systems. In a directory other users
    can read (a shared folder, ``/tmp``) the whole document was readable by
    them for as long as the write ran (reported by a pentest). ``mkdtemp``
    makes the directory 0700, and whatever is created inside it is out of
    their reach however it is created; the compression and signing passes
    put their own scratch files next to the path they are given, so they end
    up in here too.
    """
    directory = tempfile.mkdtemp(dir=os.path.dirname(target), prefix=".plico-")
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".pdf.tmp")
    os.close(fd)
    return tmp_path


def _discard(tmp_path: str) -> None:
    """Remove a temporary from :func:`_private_temporary` and its directory."""
    directory = os.path.dirname(tmp_path)
    shutil.rmtree(directory, ignore_errors=True)


def _write_temporary(model: DocumentModel, target: str, pages: list[int] | None) -> str:
    """Materialise the document into a temporary next to *target*.

    The caller owns the file that comes back: it either adopts it (see
    :func:`_adopt`) or discards it (:func:`_discard`). Nothing is written to
    *target* here.
    """
    tmp_path = _private_temporary(target)
    try:
        _write_pdf(model, tmp_path, pages)
    except BaseException:
        # Never leave a half-written temp file behind.
        _discard(tmp_path)
        raise
    return tmp_path


def _adopt(tmp_path: str, target: str) -> None:
    """Put the temporary in *target*'s place, keeping *target*'s permissions."""
    # Keep the original file's permissions across the swap.
    if os.path.exists(target):
        os.chmod(tmp_path, os.stat(target).st_mode & 0o7777)
    os.replace(tmp_path, target)
    _discard(tmp_path)


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
    is passed back to the caller. It gets the file already encrypted when
    *target* is a protected source (see :func:`_protection`): signing is the
    one caller, and a signature has to be the last thing written.
    """
    protection = _protection(model, target)
    tmp_path = _write_temporary(model, target, pages)
    try:
        _protect(tmp_path, protection)
        result = optimize(tmp_path) if optimize is not None else None
        _adopt(tmp_path, target)
        return result
    except BaseException:
        # Never leave a half-written temp file behind.
        _discard(tmp_path)
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
        _discard(self.path)


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
    protection = _protection(model, target)
    tmp_path = _write_temporary(model, target, None)
    try:
        result = optimize_in_place(tmp_path, options, progress)
        if protection is not None:
            _protect(tmp_path, protection)
            # Measured again once encrypted: the encryption has a cost of its
            # own, and a small file could come out larger while the window
            # announced a gain (reported by a review). A protection means
            # *target* is the open source, so the file it would replace is
            # the honest term of comparison.
            result = CompressionResult(os.path.getsize(target), os.path.getsize(tmp_path))
    except BaseException:
        _discard(tmp_path)
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
        optimize=lambda path: sign_in_place(
            path, request, _protection_password(model, os.path.abspath(out_path))
        ),
    )


def sign_copy(
    source: str, out_path: str, request: SignatureRequest, document_password: str | None = None
) -> None:
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
    tmp_path = _private_temporary(target)
    try:
        shutil.copyfile(source, tmp_path)
        sign_in_place(tmp_path, request, document_password)
        _adopt(tmp_path, target)
    except BaseException:
        _discard(tmp_path)
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
    as extracts. Range bounds are inclusive. Commas and blanks both separate
    (``"1 3"`` is pages 1 and 3), blanks around a dash do not (``"1 - 3"`` is
    a range), and repeated separators are tolerated. Anything malformed, out
    of range, or empty raises :class:`ValueError` with a message meant to be
    shown to the user: silently dropping pages from a split would be worse
    than refusing to run it.

    Blanks used to be deleted before splitting, so ``"1 3"`` became page 13
    -- the wrong page, extracted without a word (reported by a review).
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

    # The dash first takes its blanks with it, then commas and blanks split.
    for token in re.split(r"[\s,]+", re.sub(r"\s*-\s*", "-", spec.strip())):
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
