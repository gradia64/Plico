"""Unit tests for the compression pipeline.

The numbers asserted here are the ones the feature is built on, and they were
measured on generated documents rather than guessed:

* ``clean=True`` (mutool clean) is what really shrinks a fragmented text PDF.
  A document built page by page carries one tiny content stream per drawing
  call, and merging those is worth an order of magnitude -- losslessly.
* only the lossy levels touch the images, and on a scan they are the only
  thing that matters.

So a regression in the recipe shows up here as a failing test instead of as a
quietly worse file for the user.
"""

import os
import random

import fitz
import pytest
from PySide6.QtGui import QGuiApplication, QImage

from plico.model import (
    LEVELS,
    LEVELS_BY_KEY,
    DocumentModel,
    optimize_in_place,
    save_compressed,
)

# Il livello leggero deve dimezzare almeno un PDF di testo frammentato.
SOGLIA_TESTO = 0.5
# Il livello medio deve togliere almeno un quarto a una scansione.
SOGLIA_SCANSIONE = 0.75


@pytest.fixture(scope="module")
def qapp():
    """Serve solo a QImage, per fabbricare il JPEG di una finta scansione."""
    yield QGuiApplication.instance() or QGuiApplication([])


def _testo_frammentato(path: str, pagine: int = 20) -> None:
    """Un PDF nella forma in cui i PDF veri arrivano: tante pagine, tanti stream.

    ``insert_text`` crea un oggetto per ogni chiamata, quindi il documento si
    porta dietro centinaia di content stream minuscoli. E' esattamente la
    forma in cui ``clean=True`` fa la differenza.
    """
    with fitz.open() as doc:
        for i in range(pagine):
            pagina = doc.new_page(width=595, height=842)
            for k in range(40):
                pagina.insert_text(
                    (60, 60 + k * 18),
                    f"Paragrafo {k} della pagina {i + 1}: contenuto ripetuto per occupare spazio.",
                    fontsize=10,
                )
        doc.save(path, deflate=True)


def _scansione(path: str, pagine: int = 3, lato: int = 1000) -> None:
    """Un finto PDF scansionato: una grossa immagine JPEG per pagina.

    I pixel sono rumore, quindi incomprimibili: il ridimensionamento si
    misura davvero invece di sparire dentro una compressione gia' ottima.

    L'immagine passa da QImage e non da ``fitz.Pixmap(cs, w, h, bytes)``:
    quella firma non esiste in PyMuPDF 1.28 e la sua eccezione incorpora
    l'intero buffer nei messaggi di errore.
    """
    jpg = f"{path}.jpg"
    campioni = random.Random(1).randbytes(lato * lato * 3)
    QImage(campioni, lato, lato, lato * 3, QImage.Format.Format_RGB888).save(jpg, "JPEG", 95)
    try:
        with fitz.open() as doc:
            for _ in range(pagine):
                pagina = doc.new_page(width=595, height=842)
                pagina.insert_image(fitz.Rect(0, 0, 595, 842), filename=jpg)
            doc.save(path, deflate=True)
    finally:
        os.unlink(jpg)


# --------------------------------------------------------------------- #
#  I livelli
# --------------------------------------------------------------------- #

def test_only_the_lossy_levels_touch_the_images():
    """Un livello che ricampiona deve anche dire *dove* portare le immagini.

    Un ``image_target`` a zero con ``rewrites_images`` vero non farebbe nulla
    e nessuno se ne accorgerebbe: meglio un test che lo dice.
    """
    for livello in LEVELS:
        if livello.rewrites_images:
            assert 0 < livello.image_target < livello.image_threshold, livello.key
            assert 0 < livello.image_quality < 100, livello.key
        else:
            assert livello.image_target == 0, livello.key
            assert livello.image_quality == 0, livello.key


def test_level_keys_are_unique_and_discoverable():
    assert len({livello.key for livello in LEVELS}) == len(LEVELS)
    assert all(LEVELS_BY_KEY[livello.key] is livello for livello in LEVELS)


def test_the_levels_get_progressively_stronger():
    """Piu` si scende di livello, piu` bassi bersaglio e qualita`."""
    ridimensionano = [livello for livello in LEVELS if livello.rewrites_images]
    bersagli = [livello.image_target for livello in ridimensionano]
    qualita = [livello.image_quality for livello in ridimensionano]
    assert bersagli == sorted(bersagli, reverse=True)
    assert qualita == sorted(qualita, reverse=True)


# --------------------------------------------------------------------- #
#  optimize_in_place
# --------------------------------------------------------------------- #

def test_optimize_shrinks_a_fragmented_text_pdf(qapp, tmp_path):
    path = str(tmp_path / "frammentato.pdf")
    _testo_frammentato(path)
    prima = os.path.getsize(path)

    risultato = optimize_in_place(path, LEVELS_BY_KEY["light"])

    dopo = os.path.getsize(path)
    assert dopo < prima * SOGLIA_TESTO, f"{prima} -> {dopo} byte"
    assert risultato.source_size == prima
    assert risultato.output_size == dopo
    assert risultato.shrank
    assert risultato.saved_bytes == prima - dopo
    assert risultato.percent_saved > 50
    with fitz.open(path) as doc:
        assert doc.page_count == 20


def test_optimize_keeps_the_text_readable(qapp, tmp_path):
    """Comprimere non deve voler dire perdere il testo estraibile."""
    path = str(tmp_path / "testo.pdf")
    _testo_frammentato(path, pagine=3)

    optimize_in_place(path, LEVELS_BY_KEY["light"])

    with fitz.open(path) as doc:
        assert "della pagina 2" in doc[1].get_text()


def test_optimize_never_grows_an_already_optimized_file(qapp, tmp_path):
    """Passare due volte sullo stesso file non deve peggiorarlo."""
    path = str(tmp_path / "gia.pdf")
    _testo_frammentato(path)
    optimize_in_place(path, LEVELS_BY_KEY["light"])
    prima = os.path.getsize(path)

    risultato = optimize_in_place(path, LEVELS_BY_KEY["light"])

    assert os.path.getsize(path) <= prima
    if not risultato.shrank:
        assert os.path.getsize(path) == prima


def test_optimize_keeps_page_rotation(qapp, tmp_path):
    """La rotazione e` per pagina, e deve sopravvivere alla riscrittura."""
    path = str(tmp_path / "ruotato.pdf")
    _testo_frammentato(path, pagine=2)
    with fitz.open(path) as doc:
        doc[1].set_rotation(90)
        doc.saveIncr()

    optimize_in_place(path, LEVELS_BY_KEY["light"])

    with fitz.open(path) as doc:
        assert doc[0].rotation == 0
        assert doc[1].rotation == 90


def test_optimize_reports_progress(qapp, tmp_path):
    path = str(tmp_path / "progresso.pdf")
    _testo_frammentato(path, pagine=5)
    visti: list[int] = []

    optimize_in_place(path, LEVELS_BY_KEY["light"], progress=visti.append)

    assert visti, "pikepdf deve riportare l'avanzamento"
    assert visti[-1] == 100
    assert all(0 <= valore <= 100 for valore in visti)


def test_optimize_without_progress_does_not_complain(qapp, tmp_path):
    """Il callback e` opzionale: senza, non deve succedere niente."""
    path = str(tmp_path / "muto.pdf")
    _testo_frammentato(path, pagine=3)

    optimize_in_place(path, LEVELS_BY_KEY["light"])

    assert os.path.getsize(path) > 0


# --------------------------------------------------------------------- #
#  Le immagini: e` qui che si perde qualcosa, ed e` voluto
# --------------------------------------------------------------------- #

def test_medium_level_shrinks_a_scan(qapp, tmp_path):
    path = str(tmp_path / "scansione.pdf")
    _scansione(path)
    prima = os.path.getsize(path)

    risultato = optimize_in_place(path, LEVELS_BY_KEY["medium"])

    dopo = os.path.getsize(path)
    assert dopo < prima * SOGLIA_SCANSIONE, f"{prima} -> {dopo} byte"
    assert risultato.shrank
    with fitz.open(path) as doc:
        assert doc.page_count == 3
        assert doc[0].get_images(), "l'immagine non deve sparire"


def test_light_level_leaves_a_scan_alone(qapp, tmp_path):
    """Il livello leggero non tocca le immagini: su una scansione non guadagna.

    Non e` un'ottimizzazione mancata, e` la promessa del livello: su un
    documento gia' solo-immagini non c'e` niente da togliere senza perdere
    qualcosa, e allora non si toglie niente.
    """
    path = str(tmp_path / "scansione.pdf")
    _scansione(path)
    prima = os.path.getsize(path)

    optimize_in_place(path, LEVELS_BY_KEY["light"])

    assert os.path.getsize(path) > prima * 0.95


def test_strong_level_goes_further_than_medium(qapp, tmp_path):
    medio = str(tmp_path / "medio.pdf")
    forte = str(tmp_path / "forte.pdf")
    _scansione(medio)
    _scansione(forte)

    optimize_in_place(medio, LEVELS_BY_KEY["medium"])
    optimize_in_place(forte, LEVELS_BY_KEY["strong"])

    assert os.path.getsize(forte) < os.path.getsize(medio)


# --------------------------------------------------------------------- #
#  save_compressed
# --------------------------------------------------------------------- #

def test_save_compressed_writes_the_virtual_document(qapp, tmp_path):
    """Il file compresso contiene il documento *virtuale*, non la sorgente."""
    sorgente = str(tmp_path / "sorgente.pdf")
    _testo_frammentato(sorgente, pagine=10)
    destinazione = str(tmp_path / "compresso.pdf")

    model = DocumentModel()
    model.open(sorgente)
    model.pages.pop(0)
    model.pages.pop(0)
    model.pages[0].rotation = 90

    risultato = save_compressed(model, destinazione, LEVELS_BY_KEY["light"])

    assert risultato.shrank
    with fitz.open(destinazione) as doc:
        assert doc.page_count == 8
        assert doc[0].rotation == 90
        assert "della pagina 3" in doc[0].get_text()
    with fitz.open(sorgente) as doc:
        assert doc.page_count == 10, "la sorgente non si tocca"


def test_save_compressed_can_overwrite_the_open_source(qapp, tmp_path):
    """Comprimere sopra il file aperto: contenuto giusto, inode nuovo."""
    sorgente = str(tmp_path / "doc.pdf")
    _testo_frammentato(sorgente, pagine=6)
    prima = os.path.getsize(sorgente)

    model = DocumentModel()
    model.open(sorgente)
    model.pages.pop(0)

    save_compressed(model, sorgente, LEVELS_BY_KEY["light"])

    assert os.path.getsize(sorgente) < prima
    with fitz.open(sorgente) as doc:
        assert doc.page_count == 5


def test_save_compressed_leaves_no_temporary_behind(qapp, tmp_path):
    """I temporanei nascono accanto al file: non devono restare li`."""
    sorgente = str(tmp_path / "doc.pdf")
    _testo_frammentato(sorgente, pagine=5)
    destinazione = str(tmp_path / "compresso.pdf")

    model = DocumentModel()
    model.open(sorgente)
    save_compressed(model, destinazione, LEVELS_BY_KEY["light"])

    residui = [nome for nome in os.listdir(tmp_path) if nome.endswith(".tmp")]
    assert residui == []


def test_save_compressed_without_pages_is_refused(qapp, tmp_path):
    """Un documento svuotato non deve produrre un PDF senza pagine."""
    sorgente = str(tmp_path / "doc.pdf")
    _testo_frammentato(sorgente, pagine=2)
    destinazione = str(tmp_path / "compresso.pdf")

    model = DocumentModel()
    model.open(sorgente)
    model.pages.clear()

    with pytest.raises(ValueError):
        save_compressed(model, destinazione, LEVELS_BY_KEY["light"])
    assert not os.path.exists(destinazione)
