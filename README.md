# Plico

Un vero editor PDF nativo per Linux, costruito con **Qt6** e **PySide6** + **PyMuPDF**.

> Il file PDF non si tocca mai finché non salvi.

## Caratteristiche MVP

- **Ruotare, eliminare, riordinare** pagine (drag & drop nella barra miniature)
- **Unire** un altro PDF: le sue pagine si aggiungono a quelle già aperte
  senza copiare nulla, perché ogni pagina virtuale sa a quale documento
  sorgente appartiene
- **Estrarre pagine** (dividere) in un nuovo file con una selezione tipo
  `1-3,5,8` — l'ordine digitato è conservato, quindi vale anche come riordino
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
    │   └── save.py            # save_as(), extract_pages(), parse_page_ranges()
    ├── rendering/
    │   └── worker.py          # RenderWorker in QThread
    └── widgets/
        ├── page_view.py       # QScrollArea: rendering on demand, fit-width, HiDPI
        └── thumbnail_bar.py   # QListView + modello + cache, caricamento lazy
```

### Concetto chiave

Il modello non modifica il PDF: è solo una lista di **pagine virtuali**.
Ogni pagina virtuale è una coppia `(source_id, source_index)` più la
rotazione scelta dall'utente. Tutto deriva da questa lista:

- **undo/redo**: manipola una lista Python, non il file
- **unione**: aggiungere un PDF significa solo accodare pagine che
  puntano a un secondo `source_id`; nessuna pagina viene copiata
- **rendering**: il worker apre in sola lettura i documenti sorgente,
  su richiesta, e renderizza senza coordinarsi col modello
- **salvataggio**: un solo loop che materializza la lista, aprendo
  ciascuna sorgente una volta sola e copiando le sequenze contigue

L'identità di una pagina è sempre la coppia `(source_id, source_index)`, mai
il solo `source_index`: dopo un'unione due pagine hanno regolarmente lo
stesso indice in documenti diversi, e usarne solo uno le farebbe collassare
in una sola (miniatura sbagliata, pixmap in cache riutilizzata a sproposito).

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

Dopo un'unione le sorgenti sono più d'una, quindi il controllo copre **tutte**
le sorgenti: salvare sopra uno qualsiasi dei PDF aperti passa per il file
temporaneo, perché PyMuPDF non può scrivere in un documento che sta leggendo.

### Integrazione desktop (KDE)

- **Icone dal tema** (`QIcon.fromTheme`: `document-open`, `document-save-as`,
  `edit-undo`, `object-rotate-right`, `zoom-in`, …): nessun asset grafico nel
  pacchetto. Se il tema non fornisce l'icona, l'azione resta senza icona invece
  di mostrare un quadrato vuoto.
- **Stringhe traducibili da subito** (`self.tr()` su tutto il testo
  visibile): pronte per Qt Linguist (`lupdate` / `lrelease`) senza doverle
  rintracciare a posteriori.
- **Stato della sessione in `QSettings`** (`~/.config/Plico/plico.conf`):
  geometria della finestra, layout di dock e barra strumenti, e fattore di
  zoom.

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