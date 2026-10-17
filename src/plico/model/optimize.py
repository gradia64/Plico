"""Targeted compression: shrinking a materialised PDF without breaking it.

Two independent passes, both of which rewrite the file end to end:

``mutool clean`` (through PyMuPDF's ``clean=True``)
    Merges and grooms the content streams. A PDF born from copying pages
    around carries hundreds of tiny content streams, one per edit: merging
    them **loses nothing**, and that is where nearly all the gain on text
    documents comes from (188 KB -> 12 KB on a 20-page test document, against
    qpdf's 11% on its own).

``qpdf`` (through pikepdf)
    Object streams, deduplication and a second, maximum-effort Flate pass.
    Alone it is worth little, but on top of the pass above it polishes the
    file.

On the two stronger levels a **lossy** pass runs first, resampling the
embedded images to a lower resolution and JPEG quality. It is the only step
that throws information away, and it is what decides everything on scans. It
can be restricted to some pages, and the whole structural side can be turned
off, through :class:`CompressionOptions`; the two lossless passes cannot be
restricted and do not need to be, because they lose nothing.

Restricting the image pass has a price worth knowing. MuPDF resamples a whole
document at a time, so touching some pages means rebuilding the file out of a
copy holding only those pages -- and that splits an image two pages were
sharing, which can *grow* a file. The rule below still applies: a compression
that grows is thrown away rather than kept.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pikepdf
import pymupdf

__all__ = [
    "LEVELS",
    "LEVELS_BY_KEY",
    "CompressionLevel",
    "CompressionOptions",
    "CompressionResult",
    "Progress",
    "optimize_in_place",
]

#: Called with an integer percentage (0-100) while compression runs.
Progress = Callable[[int], None]


@dataclass(frozen=True)
class CompressionLevel:
    """One of the presets offered to the user.

    ``label`` and ``detail`` are user-facing text, so they are written in the
    source language and translated where they are put on screen.
    """

    key: str
    label: str
    detail: str
    #: Resolution (dpi) above which an image is resampled.
    image_threshold: int = 0
    #: Target resolution; 0 means "leave the images alone".
    image_target: int = 0
    #: Quality of the outgoing JPEG.
    image_quality: int = 0

    @property
    def rewrites_images(self) -> bool:
        return self.image_target > 0


LEVELS: tuple[CompressionLevel, ...] = (
    CompressionLevel(
        key="light",
        label="Leggera",
        detail=(
            "Senza alcuna perdita: fonde i content stream e ricompatta il file "
            "con qpdf. Le immagini non vengono toccate, quindi su una scansione "
            "non guadagna quasi nulla."
        ),
    ),
    CompressionLevel(
        key="medium",
        label="Media",
        detail=(
            "Come Leggera, e in piu` ricampiona a 150 dpi le immagini che "
            "superano i 200 dpi, salvandole in JPEG a qualita` 80."
        ),
        image_threshold=200,
        image_target=150,
        image_quality=80,
    ),
    CompressionLevel(
        key="strong",
        label="Forte",
        detail=(
            "Come Media, ma scende a 96 dpi e qualita` 60: file molto piu` "
            "piccoli, immagini visibilmente morbide."
        ),
        image_threshold=150,
        image_target=96,
        image_quality=60,
    ),
)

LEVELS_BY_KEY: dict[str, CompressionLevel] = {level.key: level for level in LEVELS}


@dataclass(frozen=True)
class CompressionOptions:
    """What to compress: a preset, plus the two things a preset cannot say.

    ``groom`` off means "only the images": the file is not rebuilt, so the
    lossless passes are skipped and the image step is the only thing left that
    can change anything. ``image_pages`` limits that step to the pages named --
    0-based, in the order of the materialised document -- while ``None`` means
    every page. The lossless passes always cover the whole file: they are
    per-file rewrites, and nothing is lost in them.
    """

    level: CompressionLevel
    groom: bool = True
    image_pages: tuple[int, ...] | None = None


def _as_options(value: CompressionOptions | CompressionLevel) -> CompressionOptions:
    """A bare preset is the common case, so both shapes are accepted."""
    if isinstance(value, CompressionOptions):
        return value
    return CompressionOptions(level=value)


@dataclass(frozen=True)
class CompressionResult:
    """How much was really gained."""

    source_size: int
    output_size: int

    @property
    def saved_bytes(self) -> int:
        return max(0, self.source_size - self.output_size)

    @property
    def ratio(self) -> float:
        """Final size as a fraction of the initial one (0.52 = 52%)."""
        if self.source_size <= 0:
            return 1.0
        return self.output_size / self.source_size

    @property
    def percent_saved(self) -> int:
        return round(100 * (1.0 - self.ratio))

    @property
    def shrank(self) -> bool:
        return self.output_size < self.source_size


@contextlib.contextmanager
def _scratch(directory: str) -> Iterator[str]:
    """A temporary file in *directory*, removed whatever happens.

    The same directory and not ``/tmp`` because the final step is an
    ``os.replace``, which is atomic only inside one filesystem.
    """
    handle, path = tempfile.mkstemp(dir=directory, suffix=".pdf.tmp")
    os.close(handle)
    try:
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


def _clean(doc: pymupdf.Document, out: str, options: CompressionOptions) -> None:
    """Save *doc* to *out*, grooming the content streams when asked to."""
    # `clean` is the step that is worth the most: a PDF built by copying
    # pages around carries one content stream per operation, and merging
    # them loses nothing.
    doc.save(out, garbage=4, deflate=True, clean=options.groom)


def _resample(doc: pymupdf.Document, level: CompressionLevel) -> None:
    """The lossy step, applied to every image the document carries."""
    doc.rewrite_images(
        dpi_threshold=level.image_threshold,
        dpi_target=level.image_target,
        quality=level.image_quality,
    )


def _rewrite(src: str, out: str, options: CompressionOptions) -> None:
    """First pass: MuPDF's clean, plus the image step when the level asks for it."""
    level = options.level
    with pymupdf.open(src) as doc:
        if not level.rewrites_images or options.image_pages is None:
            if level.rewrites_images:
                _resample(doc, level)
            _clean(doc, out, options)
            return
        _rewrite_some_pages(doc, src, out, options)


def _rewrite_some_pages(
    doc: pymupdf.Document, src: str, out: str, options: CompressionOptions
) -> None:
    """Resample the images of the chosen pages only.

    MuPDF works on a whole document at a time, so the pages to leave alone are
    rebuilt from the original: the copy that gets resampled holds only the
    chosen pages, and the body is composed page by page from one or the other.
    Pages come out copied one at a time in any case, so nothing else is lost
    here -- except that an image two pages were sharing does become two.
    """
    assert options.image_pages is not None, "called only for a page selection"
    pages = sorted({index for index in options.image_pages if 0 <= index < doc.page_count})
    if not pages:
        # A selection that names no page is a request to leave the images
        # alone, not a reason to refuse the compression.
        _clean(doc, out, options)
        return
    with pymupdf.open(src) as part:
        part.select(pages)
        _resample(part, options.level)
        with pymupdf.open() as body:
            position = {index: slot for slot, index in enumerate(pages)}
            for index in range(doc.page_count):
                source = part if index in position else doc
                slot = position.get(index, index)
                body.insert_pdf(source, from_page=slot, to_page=slot)
            _clean(body, out, options)


def _compact(src: str, out: str, progress: Progress | None) -> None:
    """Second pass: object streams, deduplication, one more Flate round."""
    with pikepdf.open(src) as pdf:
        pdf.save(
            out,
            compress_streams=True,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            stream_decode_level=pikepdf.StreamDecodeLevel.generalized,
            progress=progress,
        )


def optimize_in_place(
    path: str,
    options: CompressionOptions | CompressionLevel,
    progress: Progress | None = None,
) -> CompressionResult:
    """Rewrite *path* smaller, atomically, and report the gain.

    *options* is either a preset or the adjusted options the dialog builds.

    The original file is never left truncated: every pass writes to a
    temporary file in the same directory, and only at the end does the winner
    take *path*'s place. If nothing was gained the file stays exactly as it
    was: an already optimised PDF must not **grow** because the user asked to
    compress it.
    """
    settings = _as_options(options)
    directory = os.path.dirname(os.path.abspath(path)) or "."
    before = os.path.getsize(path)

    def report(value: int) -> None:
        if progress is not None:
            progress(value)

    report(0)

    with _scratch(directory) as cleaned:
        _rewrite(path, cleaned, settings)
        report(60)
        with contextlib.ExitStack() as stack:
            candidates = [cleaned]
            if settings.groom:
                compacted = stack.enter_context(_scratch(directory))
                _compact(cleaned, compacted, lambda value: report(60 + value * 4 // 10))
                candidates.append(compacted)
            # qpdf is not bound to beat a file MuPDF has already reorganised,
            # so adopt whichever of the two came out smaller.
            best = min(candidates, key=os.path.getsize)
            if os.path.getsize(best) < before:
                # Carry the original's permissions across the swap.
                os.chmod(best, os.stat(path).st_mode & 0o7777)
                os.replace(best, path)

    report(100)
    return CompressionResult(before, os.path.getsize(path))
