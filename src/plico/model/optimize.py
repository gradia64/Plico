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
that throws information away, and it is what decides everything on scans.
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


def _rewrite(src: str, out: str, level: CompressionLevel) -> None:
    """First pass: MuPDF's clean, plus the image step when the level asks for it."""
    with pymupdf.open(src) as doc:
        if level.rewrites_images:
            doc.rewrite_images(
                dpi_threshold=level.image_threshold,
                dpi_target=level.image_target,
                quality=level.image_quality,
            )
        # `clean` is the step that is worth the most: a PDF built by copying
        # pages around carries one content stream per operation, and merging
        # them loses nothing.
        doc.save(out, garbage=4, deflate=True, clean=True)


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
    path: str, level: CompressionLevel, progress: Progress | None = None
) -> CompressionResult:
    """Rewrite *path* smaller, atomically, and report the gain.

    The original file is never left truncated: every pass writes to a
    temporary file in the same directory, and only at the end does the winner
    take *path*'s place. If nothing was gained the file stays exactly as it
    was: an already optimised PDF must not **grow** because the user asked to
    compress it.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    before = os.path.getsize(path)

    def report(value: int) -> None:
        if progress is not None:
            progress(value)

    report(0)

    with _scratch(directory) as cleaned:
        _rewrite(path, cleaned, level)
        report(60)
        with _scratch(directory) as compacted:
            _compact(cleaned, compacted, lambda value: report(60 + value * 4 // 10))
            # qpdf is not bound to beat a file MuPDF has already reorganised,
            # so adopt whichever of the two came out smaller.
            candidates = (cleaned, compacted)
            best = min(candidates, key=os.path.getsize)
            if os.path.getsize(best) < before:
                # Carry the original's permissions across the swap.
                os.chmod(best, os.stat(path).st_mode & 0o7777)
                os.replace(best, path)

    report(100)
    return CompressionResult(before, os.path.getsize(path))
