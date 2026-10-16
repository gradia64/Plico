"""Compressione mirata: rimpicciolire un PDF materializzato senza romperlo.

Due passaggi indipendenti, entrambi dei quali riscrivono il file per intero:

``mutool clean`` (tramite ``clean=True`` di PyMuPDF)
    Fonde e ripulisce i content stream. Un PDF nato copiando pagine in giro
    si porta dietro centinaia di content stream minuscoli, uno per ogni
    operazione di editing: fonderli **non perde nulla** ed e` li` che sta
    quasi tutto il guadagno sui documenti di testo (188 KB -> 12 KB su un
    documento di prova di 20 pagine, contro l'11% di qpdf da solo).

``qpdf`` (tramite pikepdf)
    Object stream, deduplicazione e un secondo passaggio Flate al massimo
    sforzo. Da solo vale poco, ma sommato al precedente rifinisce il file.

Sui due livelli piu` forti gira prima un passaggio **con perdita**, che
ricampiona le immagini incorporate a una risoluzione e a una qualita` JPEG
piu` basse. E` l'unico passo che butta via informazione, ed e` quello che
decide tutto sulle scansioni.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import fitz
import pikepdf

__all__ = [
    "LEVELS",
    "LEVELS_BY_KEY",
    "CompressionLevel",
    "CompressionResult",
    "Progress",
    "optimize_in_place",
]

#: Chiamata con una percentuale intera (0-100) mentre la compressione procede.
Progress = Callable[[int], None]


@dataclass(frozen=True)
class CompressionLevel:
    """Uno dei preset offerti all'utente."""

    key: str
    label: str
    detail: str
    #: Risoluzione (dpi) oltre la quale un'immagine viene ricampionata.
    image_threshold: int = 0
    #: Risoluzione di destinazione; 0 significa "non toccare le immagini".
    image_target: int = 0
    #: Qualita` del JPEG in uscita.
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
    """Quanto si e` guadagnato davvero."""

    source_size: int
    output_size: int

    @property
    def saved_bytes(self) -> int:
        return max(0, self.source_size - self.output_size)

    @property
    def ratio(self) -> float:
        """Dimensione finale in frazione di quella iniziale (0.52 = 52%)."""
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
    """Un file temporaneo nella stessa directory, rimosso in ogni caso.

    Stessa directory e non ``/tmp`` perche' il passo finale e` un
    ``os.replace``, che e` atomico solo dentro lo stesso filesystem.
    """
    handle, path = tempfile.mkstemp(dir=directory, suffix=".pdf.tmp")
    os.close(handle)
    try:
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


def _rewrite(src: str, out: str, level: CompressionLevel) -> None:
    """Primo passaggio: clean di MuPDF, con l'eventuale passo sulle immagini."""
    with fitz.open(src) as doc:
        if level.rewrites_images:
            doc.rewrite_images(
                dpi_threshold=level.image_threshold,
                dpi_target=level.image_target,
                quality=level.image_quality,
            )
        # `clean` e` il passo che vale di piu`: un PDF costruito copiando
        # pagine in giro porta un content stream per ogni operazione, e
        # fonderli non perde nulla.
        doc.save(out, garbage=4, deflate=True, clean=True)


def _compact(src: str, out: str, progress: Progress | None) -> None:
    """Secondo passaggio: object stream, deduplicazione, un altro giro di Flate."""
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
    """Riscrive *path* piu` piccolo, in modo atomico, e riferisce il guadagno.

    Il file originale non viene mai lasciato troncato: ogni passaggio scrive
    su un file temporaneo nella stessa directory e solo alla fine il vincitore
    prende il posto di *path*. Se non si e` guadagnato niente il file resta
    esattamente com'era: un PDF gia` ottimizzato non deve **crescere** perche'
    l'utente ha chiesto di comprimerlo.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    before = os.path.getsize(path)

    def report(value: int) -> None:
        if progress is not None:
            progress(value)

    report(0)

    with _scratch(directory) as ripulito:
        _rewrite(path, ripulito, level)
        report(60)
        with _scratch(directory) as compatto:
            _compact(ripulito, compatto, lambda valore: report(60 + valore * 4 // 10))
            # qpdf non e` detto che vinca su un file che MuPDF ha gia`
            # riorganizzato, quindi si adotta il migliore dei due.
            candidati = (ripulito, compatto)
            migliore = min(candidati, key=os.path.getsize)
            if os.path.getsize(migliore) < before:
                # Conserva i permessi dell'originale attraverso lo scambio.
                os.chmod(migliore, os.stat(path).st_mode & 0o7777)
                os.replace(migliore, path)

    report(100)
    return CompressionResult(before, os.path.getsize(path))
