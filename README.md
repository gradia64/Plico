# Plico

Un vero editor PDF nativo per Linux, costruito con **Qt6** e **PySide6** + **PyMuPDF**.

> Il file PDF non si tocca mai finché non salvi.

## Caratteristiche MVP

- **Ruotare, eliminare, riordinare** pagine (drag & drop nella barra miniature)
- **Undo/Redo** completo grazie a `QUndoStack`
- **Rendering asincrono** in un thread separato — l'UI non si blocca mai
- **Rendering lazy**: si renderizzano solo le pagine visibili, non l'intero
  documento
- **Cache** a budget di byte per le pagine, LRU per le miniature
- **Salvataggio** con compressione `garbage=4` + `deflate=True`

### Requisito di accettazione

Un PDF da **300 pagine** si apre in meno di 2 secondi e resta reattivo:
all'apertura vengono renderizzate 2 pagine e ~12 miniature, non 300. La cache
delle pagine contiene al più una manciata di voci, indipendentemente dalla
dimensione del documento. Coperto da
[`test_large_document_stays_responsive`](tests/test_integration.py).

## Architettura

```
plico/
├── pyproject.toml
└── src/plico/
    ├── app.py                 # entry point
    ├── main_window.py         # MainWindow + wiring worker/model/view
    ├── model/
    │   ├── document.py        # DocumentModel, PageItem
    │   ├── commands.py        # QUndoCommand: RotatePage, DeletePage, MovePage
    │   └── save.py            # save_as()
    ├── rendering/
    │   └── worker.py          # RenderWorker in QThread
    └── widgets/
        ├── page_view.py       # QScrollArea: rendering on demand, fit-width, HiDPI
        └── thumbnail_bar.py   # QListView + modello + cache, caricamento lazy
```

### Concetto chiave

Il modello non modifica il PDF: è solo una lista di **pagine virtuali**
(`source_index` + `rotation`). Tutto deriva da questa lista:

- **undo/redo**: manipola una lista Python, non il file
- **rendering**: il worker apre il file in sola lettura e renderizza
  senza coordinarsi col modello
- **salvataggio**: un solo loop che materializza la lista

Le viste **osservano il modello**: `PageView` e `ThumbnailBar` si collegano ai
segnali `changed` / `page_changed`, così un undo si riflette automaticamente su
entrambe senza che la finestra debba ricordarsi di aggiornarle.

### Rotazione: due valori, non uno

`base_rotation` è la `/Rotate` originale del PDF, `rotation` è l'offset scelto
dall'utente. Il rendering compone le due, il salvataggio scrive la somma
(`total_rotation`). Le chiavi di cache includono la rotazione, altrimenti una
pagina ruotata riuserebbe la miniatura precedente.

### Salvataggio sopra il file aperto

Salvare sullo stesso file che si sta leggendo è permesso: il nuovo documento
viene scritto in un file temporaneo nella stessa directory e sostituisce
l'originale solo al termine. Un errore di scrittura non distrugge quindi il
file dell'utente.

## Requisiti

- Python ≥ 3.11
- PySide6 ≥ 6.7
- PyMuPDF (pymupdf) ≥ 1.23

## Installazione

```bash
pip install -e ".[dev]"
```

## Sviluppo

```bash
# test (senza display, grazie a QT_QPA_PLATFORM=offscreen)
QT_QPA_PLATFORM=offscreen pytest

# lint + tipi
ruff check src/ tests/
mypy src/plico

# avvio
plico            # oppure: python -m plico.app
```

## Licenza

GPL v3 — vedi [LICENSE](LICENSE).