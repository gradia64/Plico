"""Form AcroForm: leggere i campi, scriverli e ritrovarli nel file salvato.

I moduli di prova si costruiscono qui con PyMuPDF invece di pescarne uno dal
sistema: cosi` i test girano anche dove quel file non c'e`, e ogni tipo di
campo ha un caso suo.
"""

import fitz
from PySide6.QtGui import QUndoStack

from plico.model import (
    LEVELS_BY_KEY,
    AddRedaction,
    DocumentModel,
    SetFieldValue,
)
from plico.model.forms import CHECKBOX, CHECKED, CHOICE, TEXT, write_fields
from plico.model.redact import RedactionRect
from plico.model.save import save_as, save_compressed


def _aggiungi(
    pagina: fitz.Page,
    nome: str,
    tipo: int,
    rect: tuple[float, float, float, float],
    valore: str | None = None,
    scelte: list[str] | None = None,
) -> None:
    """Aggiunge un campo alla pagina. La pagina deve essere gia` viva."""
    widget = fitz.Widget()
    widget.field_name = nome
    widget.field_type = tipo
    widget.rect = fitz.Rect(*rect)
    if valore is not None:
        widget.field_value = valore
    if scelte:
        widget.choice_values = list(scelte)
    pagina.add_widget(widget)
    widget.update()


def _modulo(path: str, rotazione: int = 0) -> None:
    """Un testo, una nota, una casella e una tendina."""
    with fitz.open() as doc:
        pagina = doc.new_page(width=595, height=842)
        pagina.insert_text((72, 60), "Modulo di prova", fontsize=16)
        _aggiungi(pagina, "nome", fitz.PDF_WIDGET_TYPE_TEXT, (72, 100, 300, 128), "vecchio")
        _aggiungi(pagina, "nota", fitz.PDF_WIDGET_TYPE_TEXT, (72, 140, 400, 210))
        _aggiungi(pagina, "accetto", fitz.PDF_WIDGET_TYPE_CHECKBOX, (72, 230, 92, 250))
        _aggiungi(
            pagina,
            "colore",
            fitz.PDF_WIDGET_TYPE_COMBOBOX,
            (72, 270, 300, 300),
            "rosso",
            ["rosso", "verde"],
        )
        if rotazione:
            pagina.set_rotation(rotazione)
        doc.save(path, garbage=4, deflate=True)


def _semplice(path: str) -> None:
    """Un PDF senza nessun modulo."""
    with fitz.open() as doc:
        pagina = doc.new_page(width=595, height=842)
        pagina.insert_text((72, 72), "Nessun campo qui", fontsize=20)
        doc.save(path, deflate=True)


def _valori(path: str, indice: int = 0) -> dict[str, str]:
    """I valori come stanno nel file, riletti con PyMuPDF."""
    with fitz.open(path) as doc:
        pagina = doc[indice]  # viva: i widget la referenziano debolmente
        return {w.field_name or "": w.field_value or "" for w in pagina.widgets() or ()}


def _inchiostro(path: str, area: tuple[float, float, float, float]) -> int:
    """Quanti pixel scuri ci sono in *area*: serve a vedere l'aspetto disegnato."""
    with fitz.open(path) as doc:
        pagina = doc[0]
        pix = pagina.get_pixmap(clip=fitz.Rect(*area), colorspace=fitz.csGRAY)
        return sum(1 for b in pix.samples if b < 240)


def _aperto(tmp_path, **kwargs) -> tuple[DocumentModel, str]:
    percorso = str(tmp_path / "modulo.pdf")
    _modulo(percorso, **kwargs)
    modello = DocumentModel()
    modello.open(percorso)
    return modello, percorso


def test_legge_i_campi_della_sorgente(tmp_path):
    modello, _ = _aperto(tmp_path)

    campi = {campo.name: campo for campo in modello.pages[0].form_fields}
    assert set(campi) == {"nome", "nota", "accetto", "colore"}
    assert campi["nome"].kind == TEXT
    assert campi["nome"].value == "vecchio"
    assert campi["nome"].editable
    assert campi["accetto"].kind == CHECKBOX
    assert campi["accetto"].value == "Off"
    assert not campi["accetto"].checked
    assert campi["colore"].kind == CHOICE
    assert campi["colore"].options == ("rosso", "verde")
    assert campi["colore"].value == "rosso"


def test_aprire_non_registra_nessun_valore(tmp_path):
    modello, _ = _aperto(tmp_path)
    assert modello.pages[0].form_values == {}


def test_una_pagina_senza_modulo_non_ha_campi(tmp_path):
    percorso = str(tmp_path / "semplice.pdf")
    _semplice(percorso)

    modello = DocumentModel()
    modello.open(percorso)

    assert modello.pages[0].form_fields == []
    assert modello.pages[0].form_values == {}


def test_il_valore_finisce_nel_file(tmp_path):
    modello, _ = _aperto(tmp_path)
    uscita = str(tmp_path / "out.pdf")

    modello.pages[0].form_values["nome"] = "Anna"
    modello.pages[0].form_values["nota"] = "due righe\nscritte a mano"
    save_as(modello, uscita)

    valori = _valori(uscita)
    assert valori["nome"] == "Anna"
    assert valori["nota"] == "due righe\nscritte a mano"


def test_la_casella_si_spunta(tmp_path):
    modello, _ = _aperto(tmp_path)
    uscita = str(tmp_path / "out.pdf")

    modello.pages[0].form_values["accetto"] = CHECKED
    save_as(modello, uscita)

    assert _valori(uscita)["accetto"] == "Yes"


def test_la_tendina_cambia_scelta(tmp_path):
    modello, _ = _aperto(tmp_path)
    uscita = str(tmp_path / "out.pdf")

    modello.pages[0].form_values["colore"] = "verde"
    save_as(modello, uscita)

    assert _valori(uscita)["colore"] == "verde"


def test_svuotare_un_campo_e_una_modifica(tmp_path):
    """Cancellare e` un cambiamento: deve arrivare al file."""
    modello, _ = _aperto(tmp_path)
    uscita = str(tmp_path / "out.pdf")

    modello.pages[0].form_values["nome"] = ""
    save_as(modello, uscita)

    assert _valori(uscita)["nome"] == ""


def test_la_sorgente_non_viene_toccata(tmp_path):
    modello, percorso = _aperto(tmp_path)
    uscita = str(tmp_path / "out.pdf")

    modello.pages[0].form_values["nome"] = "Anna"
    save_as(modello, uscita)

    assert _valori(percorso)["nome"] == "vecchio"
    assert _valori(uscita)["nome"] == "Anna"


def test_undo_riporta_al_valore_del_file(tmp_path):
    modello, _ = _aperto(tmp_path)
    uscita = str(tmp_path / "out.pdf")
    stack = QUndoStack()

    stack.push(SetFieldValue(modello, 0, "nome", "Anna"))
    assert modello.pages[0].form_values["nome"] == "Anna"

    stack.undo()
    assert "nome" not in modello.pages[0].form_values

    save_as(modello, uscita)
    assert _valori(uscita)["nome"] == "vecchio"


def test_le_modifiche_allo_stesso_campo_si_fondono(tmp_path):
    """Un QLineEdit emette un segnale per tasto: non devono essere dieci undo."""
    modello, _ = _aperto(tmp_path)
    stack = QUndoStack()

    for valore in ("A", "An", "Ann", "Anna"):
        stack.push(SetFieldValue(modello, 0, "nome", valore))

    assert stack.count() == 1, "i tasti dello stesso campo sono un solo comando"
    assert modello.pages[0].form_values["nome"] == "Anna"

    stack.undo()
    assert "nome" not in modello.pages[0].form_values


def test_campi_diversi_non_si_fondono(tmp_path):
    modello, _ = _aperto(tmp_path)
    stack = QUndoStack()

    stack.push(SetFieldValue(modello, 0, "nome", "A"))
    stack.push(SetFieldValue(modello, 0, "nota", "B"))

    assert stack.count() == 2


def test_i_campi_sopravvivono_alla_compressione(tmp_path):
    """Il passo clean=True della compressione non deve mangiarsi il modulo."""
    modello, _ = _aperto(tmp_path)
    uscita = str(tmp_path / "compresso.pdf")

    modello.pages[0].form_values["nome"] = "Anna"
    modello.pages[0].form_values["accetto"] = CHECKED
    save_compressed(modello, uscita, LEVELS_BY_KEY["light"])

    valori = _valori(uscita)
    assert valori["nome"] == "Anna"
    assert valori["accetto"] == "Yes"


def test_i_campi_sopravvivono_a_una_redazione_altrove(tmp_path):
    """Una redazione lontana dai campi non deve portarseli via."""
    modello, _ = _aperto(tmp_path)
    uscita = str(tmp_path / "out.pdf")
    stack = QUndoStack()

    modello.pages[0].form_values["nome"] = "Anna"
    stack.push(AddRedaction(modello, 0, RedactionRect.from_corners(72, 400, 300, 430)))
    save_as(modello, uscita)

    assert _valori(uscita)["nome"] == "Anna"


def test_la_geometria_non_cambia_con_la_pagina_ruotata(tmp_path):
    """Il rettangolo di un campo sta in spazio pagina, come quello di redazione."""
    dritto = str(tmp_path / "dritto.pdf")
    ruotato = str(tmp_path / "ruotato.pdf")
    _modulo(dritto)
    _modulo(ruotato, rotazione=90)

    primo, secondo = DocumentModel(), DocumentModel()
    primo.open(dritto)
    secondo.open(ruotato)

    uno = {campo.name: campo.rect for campo in primo.pages[0].form_fields}
    due = {campo.name: campo.rect for campo in secondo.pages[0].form_fields}
    assert uno == due, "ruotare la pagina non deve spostare i campi"

    assert secondo.pages[0].unrotated_size == (595, 842)
    assert secondo.pages[0].width_pt == 842, "la dimensione orientata si scambia"


def test_la_pagina_ruotata_salva_il_valore(tmp_path):
    modello, _ = _aperto(tmp_path, rotazione=90)
    uscita = str(tmp_path / "out.pdf")

    modello.pages[0].form_values["nome"] = "Anna"
    save_as(modello, uscita)

    assert _valori(uscita)["nome"] == "Anna"
    with fitz.open(uscita) as doc:
        assert doc[0].rotation == 90


def test_write_fields_ignora_i_nomi_sconosciuti(tmp_path):
    _, percorso = _aperto(tmp_path)

    with fitz.open(percorso) as doc:
        pagina = doc[0]
        assert write_fields(pagina, {"inesistente": "x"}) == 0
        assert write_fields(pagina, {"nome": "Anna"}) == 1
        assert write_fields(pagina, {}) == 0


def test_su_un_documento_unito_i_campi_restano_del_loro_pagina(tmp_path):
    """Unire due PDF non deve mescolare i campi del primo con quelli del secondo."""
    primo, _ = _aperto(tmp_path)
    secondo = str(tmp_path / "secondo.pdf")
    _semplice(secondo)

    primo.append_document(secondo)
    assert len(primo.pages) == 2
    assert len(primo.pages[0].form_fields) == 4
    assert primo.pages[1].form_fields == []


def test_svuotare_un_campo_lo_ridipinge_vuoto(tmp_path):
    """Cancellare deve togliere anche il testo *disegnato*.

    Un /V vuoto con l'aspetto vecchio lascerebbe la parola stampata sulla
    pagina, ed e` esattamente quello che fa ``field_value = ""`` da solo. La
    prima verifica sull'inchiostro c'e` perche' l'area non risulti vuota per
    caso: senza di essa il test passerebbe anche su un modulo mai disegnato.
    """
    modello, percorso = _aperto(tmp_path)
    uscita = str(tmp_path / "out.pdf")

    modello.pages[0].form_values["nome"] = ""
    save_as(modello, uscita)

    assert _valori(uscita)["nome"] == ""
    assert _inchiostro(percorso, (72, 100, 300, 128)) > 0, "il file aveva del testo"
    assert _inchiostro(uscita, (72, 100, 300, 128)) == 0


def test_la_casella_spuntata_si_puo_togliere(tmp_path):
    modello, _ = _aperto(tmp_path)
    spuntato = str(tmp_path / "spuntato.pdf")
    vuoto = str(tmp_path / "vuoto.pdf")

    modello.pages[0].form_values["accetto"] = CHECKED
    save_as(modello, spuntato)
    assert _valori(spuntato)["accetto"] == "Yes"

    secondo = DocumentModel()
    secondo.open(spuntato)
    assert secondo.pages[0].form_fields[2].checked, "la casella risulta spuntata"
    secondo.pages[0].form_values["accetto"] = "Off"
    save_as(secondo, vuoto)

    assert _valori(vuoto)["accetto"] == "Off"
