"""Model, commands e save layer: logica pura, testabile senza UI.

I test marcati BUG documentano i difetti trovati in review: falliscono con
il codice attuale e diventano verdi applicando il fix corrispondente.
"""

import fitz
import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QUndoStack

from plico.model.commands import DeletePage, MovePage, RotatePage
from plico.model.document import DocumentModel, PageItem
from plico.model.save import _contiguous_runs, extract_pages, parse_page_ranges, save_as

# --- fixtures -------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture
def mixed_pdf(tmp_path):
    """PDF di 3 pagine con formati diversi: bug come #1 non si vedono su A4 uniformi."""
    path = tmp_path / "mixed.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)   # A4 ritratto
    doc.new_page(width=842, height=595)   # A4 paesaggio
    doc.new_page(width=420, height=595)   # ~A5
    doc.save(str(path))
    return str(path)


@pytest.fixture
def mixed_model(mixed_pdf, qapp):
    m = DocumentModel()
    m.open(mixed_pdf)
    return m


# --- parse_page_ranges ----------------------------------------------------

def test_parse_ranges_basic():
    assert parse_page_ranges("1-3,5", 10) == [0, 1, 2, 4]

def test_parse_ranges_preserves_order():
    assert parse_page_ranges("5,1-3", 10) == [4, 0, 1, 2]

def test_parse_ranges_reversed_raises():
    with pytest.raises(ValueError):
        parse_page_ranges("5-2", 10)

def test_parse_ranges_out_of_bounds_raises():
    # BUG 4: oggi il range viene materializzato PRIMA della validazione,
    # quindi "1-5000000" costruisce mezzo milione di indici prima di
    # rifiutare. Il contratto è già corretto (ValueError); il fix lo rende O(1).
    with pytest.raises(ValueError):
        parse_page_ranges("1-5000000", 3)


# --- _contiguous_runs -------------------------------------------------------

def test_contiguous_runs_break_on_source_and_gap():
    items = [
        PageItem(source_index=0, base_rotation=0, source_id=0),
        PageItem(source_index=1, base_rotation=0, source_id=0),
        PageItem(source_index=5, base_rotation=0, source_id=1),  # cambio sorgente
        PageItem(source_index=6, base_rotation=0, source_id=1),
        PageItem(source_index=2, base_rotation=0, source_id=0),  # ritorno → run nuovo
        PageItem(source_index=9, base_rotation=0, source_id=0),  # gap → run nuovo
    ]
    runs = [[(i.source_id, i.source_index) for i in r] for r in _contiguous_runs(items)]
    assert runs == [
        [(0, 0), (0, 1)],
        [(1, 5), (1, 6)],
        [(0, 2)],
        [(0, 9)],
    ]


# --- comandi e coerenza del modello -----------------------------------------

def test_delete_keeps_page_sizes_aligned(mixed_model):
    """BUG 1: page_sizes non segue pages nei comandi strutturali.

    Fallisce col codice attuale (page_sizes resta a 3 dopo il delete).
    Con il fix 1 diventa verde e poi obsoleto: la dimensione migrerà
    sull'item e page_sizes sparirà del tutto.
    """
    DeletePage(mixed_model, 0).redo()
    assert len(mixed_model.page_sizes) == len(mixed_model.pages)

def test_delete_preserves_sizes_on_items(mixed_model):
    """Contratto post-fix 1: la dimensione vive sull'item, non in lista parallela."""
    DeletePage(mixed_model, 0).redo()
    assert (round(mixed_model.pages[0].width_pt),
            round(mixed_model.pages[0].height_pt)) == (842, 595)

def test_undo_stack_interleaved_roundtrip(mixed_model):
    """Move → Delete → undo → undo: la lista torna identica.

    Verifica l'assunzione su cui poggia tutto (stack LIFO = indici coerenti)
    senza toccare page_sizes: il confronto è per identità di pagina.
    """
    stack = QUndoStack()
    stack.push(MovePage(mixed_model, 0, 2))
    stack.push(DeletePage(mixed_model, 0))
    stack.undo()
    stack.undo()
    assert [(p.source_id, p.source_index) for p in mixed_model.pages] == [(0, 0), (0, 1), (0, 2)]

def test_rotate_undo_emits_page_changed(mixed_model):
    """Prerequisito del fix 2: la miniatura si aggiorna su Ctrl+Z solo se
    il comando emette page_changed ANCHE in undo(). Oggi è già vero per il
    comando — è la ThumbnailBar che non ascolta."""
    rows = []
    mixed_model.page_changed.connect(rows.append)
    cmd = RotatePage(mixed_model, 0, 90)
    cmd.redo()
    cmd.undo()
    assert rows == [0, 0]


# --- salvataggio ------------------------------------------------------------

def test_save_writes_total_rotation(mixed_model, tmp_path):
    """Round-trip della rotazione: rotate 90 su una paesaggio → il file
    salvato ha /Rotate 90 e rect già orientato (MuPDF incorpora /Rotate
    in rect — la stessa proprietà di cui il viewer dipende)."""
    RotatePage(mixed_model, 1, 90).redo()
    out = tmp_path / "out.pdf"
    save_as(mixed_model, str(out))
    with fitz.open(str(out)) as doc:
        assert doc.page_count == 3
        assert doc[1].rotation == 90
        assert (round(doc[1].rect.width), round(doc[1].rect.height)) == (595, 842)

def test_extract_preserves_user_order(mixed_model, tmp_path):
    out = tmp_path / "sel.pdf"
    extract_pages(mixed_model, str(out), [2, 0])   # A5 prima, poi A4 ritratto
    with fitz.open(str(out)) as doc:
        assert doc.page_count == 2
        assert round(doc[0].rect.width) == 420
        assert round(doc[1].rect.width) == 595
