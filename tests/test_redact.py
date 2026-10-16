"""Redazione: la geometria, i comandi e la rimozione vera del testo.

Le quattro matrici di ``model/redact.py`` sono state lette da
``Page.rotation_matrix`` di PyMuPDF, e qui vengono confrontate di nuovo con
fitz: se un aggiornamento di PyMuPDF le cambiasse, la suite fallisce invece di
spostare in silenzio un rettangolo.

L'ultima parte e` quella che conta davvero: dopo il salvataggio il testo
marcato non deve piu` *esistere* nel file, non solo essere coperto da un
rettangolo nero.
"""

import fitz
import pytest

from plico.model import LEVELS_BY_KEY, DocumentModel, RedactionRect, save_as, save_compressed
from plico.model.commands import AddRedaction, RemoveRedaction
from plico.model.redact import (
    derotation_matrix,
    map_point,
    map_rect,
    rotation_matrix,
    unrotated_size,
)

SEGRETO = "SEGRETO"
PUBBLICO = "PUBBLICO"


def _pdf_con_testo(path: str, rotation: int = 0, pagine: int = 1) -> None:
    """Due parole ben distanti su una A4: una da redigere, una da conservare."""
    with fitz.open() as doc:
        for _ in range(pagine):
            page = doc.new_page(width=595, height=842)
            page.insert_text((100, 100), SEGRETO, fontsize=20)
            page.insert_text((100, 700), PUBBLICO, fontsize=20)
        if rotation:
            doc[0].set_rotation(rotation)
        doc.save(path)


def _rettangolo_del_segreto(path: str) -> RedactionRect:
    """Il rettangolo da redigere, letto dalla pagina sorgente.

    ``search_for`` restituisce coordinate nello spazio NON ruotato: e` lo
    stesso spazio in cui il modello conserva le redazioni, quindi qui non
    serve nessuna conversione.
    """
    with fitz.open(path) as doc:
        area = doc[0].search_for(SEGRETO)[0]
    return RedactionRect.from_corners(area.x0, area.y0, area.x1, area.y1)


# --------------------------------------------------------------------- #
#  Geometria
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("gradi", [0, 90, 180, 270])
def test_le_matrici_sono_quelle_di_pymupdf(tmp_path, gradi: int) -> None:
    """Non «simili»: identiche a quelle che usa MuPDF per la stessa pagina."""
    src = str(tmp_path / "g.pdf")
    with fitz.open() as doc:
        doc.new_page(width=595, height=842).set_rotation(gradi)
        doc.save(src)

    with fitz.open(src) as doc:
        page = doc[0]
        avanti = page.rotation_matrix
        indietro = page.derotation_matrix

    nostra = rotation_matrix(595, 842, gradi)
    assert (avanti.a, avanti.b, avanti.c, avanti.d, avanti.e, avanti.f) == pytest.approx(nostra)
    nostra_inversa = derotation_matrix(595, 842, gradi)
    assert (indietro.a, indietro.b, indietro.c, indietro.d, indietro.e, indietro.f) == pytest.approx(
        nostra_inversa
    )


@pytest.mark.parametrize("gradi", [0, 90, 180, 270])
def test_andata_e_ritorno_nello_spazio_vista(gradi: int) -> None:
    """Quello che l'utente disegna deve tornare dov'era, senza derive."""
    rect = RedactionRect.from_corners(100.0, 78.5, 197.8, 106.0)

    in_vista = map_rect(rect, rotation_matrix(595, 842, gradi))
    indietro = map_rect(in_vista, derotation_matrix(595, 842, gradi))

    assert indietro.x0 == pytest.approx(rect.x0, abs=1e-9)
    assert indietro.y0 == pytest.approx(rect.y0, abs=1e-9)
    assert indietro.x1 == pytest.approx(rect.x1, abs=1e-9)
    assert indietro.y1 == pytest.approx(rect.y1, abs=1e-9)


@pytest.mark.parametrize(
    "gradi,larghezza,altezza",
    [(0, 595, 842), (90, 842, 595), (180, 595, 842), (270, 842, 595)],
)
def test_in_vista_il_rettangolo_resta_dentro_la_pagina(
    gradi: int, larghezza: int, altezza: int
) -> None:
    rect = RedactionRect.from_corners(100.0, 100.0, 200.0, 130.0)
    in_vista = map_rect(rect, rotation_matrix(595, 842, gradi))

    assert in_vista.x0 >= -1e-9
    assert in_vista.y0 >= -1e-9
    assert in_vista.x1 <= larghezza + 1e-9
    assert in_vista.y1 <= altezza + 1e-9


def test_un_punto_segue_la_matrice() -> None:
    """Il caso piu` semplice, per fissare la convenzione (a·x + c·y + e, …)."""
    x, y = map_point(10.0, 20.0, (2.0, 0.0, 0.0, 3.0, 5.0, 7.0))
    assert (x, y) == pytest.approx((25.0, 67.0))


def test_la_dimensione_non_ruotata_raddrizza_i_quarti_dispari() -> None:
    """``width_pt`` viene da ``page.rect``, che ha gia` applicato il /Rotate."""
    assert unrotated_size(595, 842, 0) == (595, 842)
    assert unrotated_size(595, 842, 180) == (595, 842)
    assert unrotated_size(842, 595, 90) == (595, 842)
    assert unrotated_size(842, 595, 270) == (595, 842)


@pytest.mark.parametrize("gradi", [1, 45, 359])
def test_una_rotazione_non_gestita_e_un_errore(gradi: int) -> None:
    """Meglio un errore rumoroso che una redazione nel posto sbagliato."""
    with pytest.raises(ValueError):
        rotation_matrix(595, 842, gradi)
    with pytest.raises(ValueError):
        derotation_matrix(595, 842, gradi)


def test_un_rettangolo_si_costruisce_da_angoli_qualsiasi() -> None:
    """Un trascinamento puo` partire da qualunque angolo."""
    rect = RedactionRect.from_corners(200.0, 300.0, 100.0, 150.0)
    assert rect.as_tuple() == (100.0, 150.0, 200.0, 300.0)
    assert rect.width == 100.0
    assert rect.height == 150.0


def test_il_rettangolo_viene_ritagliato_sulla_pagina() -> None:
    rect = RedactionRect.from_corners(-10.0, -20.0, 700.0, 900.0).clamped_to(595, 842)
    assert rect.as_tuple() == (0.0, 0.0, 595.0, 842.0)


# --------------------------------------------------------------------- #
#  Comandi
# --------------------------------------------------------------------- #

def test_aggiungere_una_redazione_e_annullabile(tmp_path) -> None:
    src = str(tmp_path / "doc.pdf")
    _pdf_con_testo(src)

    model = DocumentModel()
    model.open(src)
    visti: list[int] = []
    model.page_changed.connect(visti.append)

    rect = _rettangolo_del_segreto(src)
    comando = AddRedaction(model, 0, rect)

    comando.redo()
    assert model.pages[0].redactions == [rect]
    assert visti == [0], "la pagina deve ridisegnarsi subito"

    comando.undo()
    assert model.pages[0].redactions == []
    assert visti == [0, 0], "anche l'annullamento deve ridisegnare"

    comando.redo()
    assert model.pages[0].redactions == [rect], "un redo dopo l'undo deve rimetterla"


def test_togliere_una_redazione_e_annullabile(tmp_path) -> None:
    src = str(tmp_path / "doc.pdf")
    _pdf_con_testo(src)

    model = DocumentModel()
    model.open(src)
    rect = _rettangolo_del_segreto(src)
    model.pages[0].redactions.append(rect)

    comando = RemoveRedaction(model, 0, rect)
    comando.redo()
    assert model.pages[0].redactions == []

    comando.undo()
    assert model.pages[0].redactions == [rect], "l'undo deve rimetterla dov'era"

    comando.redo()
    assert model.pages[0].redactions == []


# --------------------------------------------------------------------- #
#  Il salvataggio: qui si vede se la redazione e` vera
# --------------------------------------------------------------------- #

def test_il_testo_marcato_non_e_piu_nel_file(tmp_path) -> None:
    """La prova che conta: rimosso, non coperto."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_con_testo(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].redactions.append(_rettangolo_del_segreto(src))
    save_as(model, out)

    with fitz.open(out) as doc:
        testo = doc[0].get_text()
    assert SEGRETO not in testo, "il testo marcato e` ancora nel documento"
    assert PUBBLICO in testo, "la redazione ha portato via anche il resto"


def test_la_sorgente_non_viene_toccata(tmp_path) -> None:
    """L'invariante del progetto: finche` non salvi, il PDF non si tocca."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_con_testo(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].redactions.append(_rettangolo_del_segreto(src))
    save_as(model, out)

    with fitz.open(src) as doc:
        assert SEGRETO in doc[0].get_text(), "la redazione e` finita sulla sorgente"


@pytest.mark.parametrize("rotazione", [90, 180, 270])
def test_la_redazione_regge_anche_ruotando_la_pagina(tmp_path, rotazione: int) -> None:
    """La pagina ruota, il rettangolo resta sulle stesse parole."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_con_testo(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].rotation = rotazione
    assert model.pages[0].total_rotation == rotazione
    model.pages[0].redactions.append(_rettangolo_del_segreto(src))
    save_as(model, out)

    with fitz.open(out) as doc:
        page = doc[0]
        assert page.rotation == rotazione, "il salvataggio ha perso la rotazione"
        testo = page.get_text()
    assert SEGRETO not in testo, "ruotando, il rettangolo e` finito altrove"
    assert PUBBLICO in testo


def test_una_pagina_ruotata_nella_sorgente(tmp_path) -> None:
    """Se il /Rotate e` nel file di partenza, il modello lo porta con se`."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_con_testo(src, rotation=90)

    model = DocumentModel()
    model.open(src)
    assert model.pages[0].base_rotation == 90
    assert model.pages[0].unrotated_size == (595, 842)
    model.pages[0].redactions.append(_rettangolo_del_segreto(src))
    save_as(model, out)

    with fitz.open(out) as doc:
        assert doc[0].rotation == 90
        assert SEGRETO not in doc[0].get_text()
        assert PUBBLICO in doc[0].get_text()


def test_una_redazione_finisce_sulla_sua_pagina(tmp_path) -> None:
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_con_testo(src, pagine=3)

    model = DocumentModel()
    model.open(src)
    model.pages[1].redactions.append(_rettangolo_del_segreto(src))
    save_as(model, out)

    with fitz.open(out) as doc:
        assert SEGRETO in doc[0].get_text(), "la prima pagina non era marcata"
        assert SEGRETO not in doc[1].get_text(), "la seconda pagina non e` stata redatta"
        assert SEGRETO in doc[2].get_text(), "la terza pagina non era marcata"


def test_anche_salvando_compresso_il_testo_sparisce(tmp_path) -> None:
    """I due percorsi di salvataggio devono applicare le stesse redazioni."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_con_testo(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].redactions.append(_rettangolo_del_segreto(src))
    save_compressed(model, out, LEVELS_BY_KEY["light"])

    with fitz.open(out) as doc:
        assert SEGRETO not in doc[0].get_text()
        assert PUBBLICO in doc[0].get_text()


def test_senza_redazioni_il_testo_resta(tmp_path) -> None:
    """Controprova: il percorso di redazione non si attiva per sbaglio."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_con_testo(src)

    model = DocumentModel()
    model.open(src)
    save_as(model, out)

    with fitz.open(out) as doc:
        assert SEGRETO in doc[0].get_text()
        assert PUBBLICO in doc[0].get_text()
