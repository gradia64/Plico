# CONTESTO — guida per chi riprende il lavoro su Plico

Questo file è scritto per un altro agente (o una persona) che apre il
repository senza aver visto la conversazione che l'ha prodotto. Dice a che
punto è il progetto, perché è fatto così, e soprattutto **quali trappole sono
già costate tempo** — in modo che non le ripaghino una seconda volta.

Le sezioni 3, 4 e 10 sono quelle da leggere per prime: contengono
l'invariante su cui è costruito tutto il resto e gli errori che si fanno più
facilmente.

---

## 1. Cos'è Plico

Un editor PDF **nativo** per Linux, in Qt6/PySide6 con PyMuPDF sotto il cofano.
Nasce da un'osservazione: su Linux non esiste un equivalente di Adobe Acrobat,
l'ecosistema è frammentato (PDF Arranger per unire e ruotare, Xournal++ per
annotare, Okular per leggere, pdftk/qpdf da terminale) e il successo di
Stirling-PDF dimostra che la domanda c'è.

Scopo dichiarato: un progetto longevo, da far crescere a tappe, non un MVP usa
e getta. La roadmap lunga (§12) è parte del progetto, non un extra.

**Stato attuale: l'MVP è chiuso.** Fanno parte dell'MVP e sono implementati e
testati: aprire (anche i file **cifrati**, con la password), unire più PDF
(l'unione si **annulla** con Ctrl+Z come ogni altra modifica), ruotare,
eliminare, riordinare, dividere (estrarre un sottoinsieme), comprimere in
salvataggio, annulla/ripristina, rendering asincrono, cache, integrazione
desktop KDE, packaging Flatpak. Versione `0.1.0`, licenza GPL-3.0-or-later.

Della roadmap lunga (§12) sono già dentro anche le voci che non erano
nell'MVP: compilazione dei form, redazione vera, modifica minima del testo,
**OCR** (uno strato di testo invisibile sotto le scansioni) e la **firma
PAdES**. Restano le rifiniture, elencate in §12.

---

## 2. Com'è fatto il repository

```
plico/
├── pyproject.toml            # packaging, dipendenze, ruff/mypy/pytest, data-files
├── README.md                 # presentazione per l'utente (in italiano)
├── CONTESTO.md               # questo file
├── LICENSE                   # GPL v3
├── flatpak/                  # packaging: manifest, metadati AppStream, .desktop, icona
├── src/plico/
│   ├── app.py                # entry point: QApplication + apertura da riga di comando
│   ├── i18n.py               # cataloghi .qm: dove cercarli, quali chiedere, caricarli
│   ├── translations/         # plico_{en,es,fr,de}.ts: i cataloghi, tutti completi
│   ├── main_window.py        # finestra, menu, toolbar, dock, QSettings, dialogs
│   ├── model/
│   │   ├── document.py       # DocumentModel, PageItem  ← il cuore
│   │   ├── commands.py       # RotatePage, DeletePage, MovePage, AddRedaction, SetFieldValue, EditText…
│   │   ├── redact.py         # rettangoli di redazione e matrici di rotazione
│   │   ├── forms.py          # campi AcroForm: lettura, scrittura, svuotamento
│   │   ├── save.py           # save_as, save_compressed, extract_pages, parse_page_ranges
│   │   ├── assemble.py       # un PDF da pagine di altri: ogni sorgente copiata una volta
│   │   ├── textedit.py       # modifica minima del testo: uno span, il suo aspetto
│   │   ├── images.py         # immagini → un PDF qualsiasi, che diventa una sorgente
│   │   ├── ocr.py            # Tesseract: riconoscere, cercare i dati di lingua, strato invisibile
│   │   ├── sign.py           # firma PAdES con pyHanko e rilettura delle firme
│   │   └── optimize.py       # livelli e opzioni di compressione, optimize_in_place  ← pikepdf
│   ├── rendering/
│   │   └── worker.py         # RenderWorker: unico proprietario degli handle PyMuPDF
│   └── widgets/
│       ├── page_view.py      # QScrollArea: rendering, zoom, HiDPI, redazione, campi, testo
│       ├── thumbnail_bar.py  # QListView + modello + cache, caricamento lazy
│       ├── form_panel.py     # dock «Modulo»: un editor per ogni campo della pagina
│       ├── ocr.py            # dialogo pagine/lingua e task di riconoscimento
│       ├── sign.py           # dialoghi di firma e di verifica delle firme
│       └── compress.py       # dialogo delle opzioni, format_size, task sul thread pool
└── tests/
    ├── test_model.py         # modello, comandi, salvataggio, parse_page_ranges (45)
    ├── test_worker.py        # il worker di rendering in isolamento (11)
    ├── test_optimize.py      # i livelli di compressione e optimize_in_place (16)
    ├── test_redact.py        # redazione vera, zone ritoccabili, righe vicine, OCR (61)
    ├── test_forms.py         # campi AcroForm: letti, scritti, riletti, redatti, riordinati (34)
    ├── test_textedit.py      # uno span sostituito: testo, sfondo, font, spazio (33)
    ├── test_images.py        # immagini → PDF: DPI, foto ridotte, EXIF, JPEG intatti (13)
    ├── test_ocr.py           # OCR: spazio pagina, strato invisibile, undo, lingua (21)
    ├── test_sign.py          # certificati, firma, seconda firma, verdetto, firme vecchie (33)
    ├── test_edit_text.py     # EditText e salvataggio: undo, redazioni, estrai, comprimi (21)
    ├── test_i18n.py          # cataloghi: estrazione, nomi, caricamento, traduzione (8)
    ├── test_translations.py  # le quattro lingue: complete, segnaposto, menu veri (24)
    └── test_integration.py   # MainWindow vera, offscreen: 161 test end-to-end
```

Gate di qualità attuale: **513 passed, 1 skipped** (con `lrelease` dell'SDK nel `PATH`), `ruff` pulito, `mypy` pulito
(26 file sorgente). Uno `skip` è il test delle icone, che vuole un tema che
fornisca `object-rotate-*`. Gli altri skip possibili dipendono da
strumenti che mancano (§9): `pylupdate6` e `lrelease`/`pyside6-lrelease` in
`tests/test_i18n.py`. **Uno skip lì non è innocuo**: è il test che avvisa
quando una stringa nuova manca dal catalogo, e durante la review di ottobre
2026 il catalogo è rimasto indietro proprio perché era saltato.

---

## 3. L'idea centrale — e va rispettata

> **Il file PDF non si tocca mai finché non salvi.**

Il modello non modifica il PDF. È solo una lista di *pagine virtuali*: ognuna
punta a una pagina di un documento sorgente e l'unico stato che aggiunge è la
rotazione scelta dall'utente.

Da qui deriva tutto il resto, e non è un dettaglio implementativo ma la ragione
per cui il codice è semplice:

- **undo/redo banale**: i comandi modificano una lista Python, non un file;
- **rendering senza lock**: il worker apre i sorgenti in sola lettura e
  renderizza quello che gli viene chiesto, senza coordinarsi col modello;
- **nessuna copia di pagine**: unire un secondo PDF significa solo accodare
  `PageItem` che puntano a un altro `source_id` (la sorgente è registrata in
  `DocumentModel.sources`). Nessuna pagina viene mai copiata o riscritta;
- **salvataggio = un solo ciclo** che materializza la lista
  (`model/save.py::_write_pdf`).

Quando arriveranno redaction/OCR servirà mutare il documento, ma la struttura a
"servizio documentale" regge: cambierà il *sorgente* delle pagine, non il
modello.

**Corollario da non dimenticare:** `PageItem.source_index` identifica una
pagina solo *dentro la sua sorgente*. L'identità di una pagina virtuale è la
coppia **`(source_id, source_index)`**. Confondere le due cose è l'errore che
si fa appena si tocca l'unione — vedi §10.

---

## 4. ⚠️ La regola della rotazione (il punto più delicato)

Ci sono **due** rotazioni e non vanno mai scambiate:

| Dove | Cosa contiene | Chi la legge |
| --- | --- | --- |
| `PageItem.base_rotation` | la `/Rotate` originale della pagina | nessuno, direttamente |
| `PageItem.rotation` | **solo** l'offset scelto dall'utente | il renderer e la vista |
| `PageItem.total_rotation` | la somma `(base + user) % 360` | **solo** il salvataggio |

Tre conseguenze, tutte non negoziabili:

1. **PyMuPDF applica già la `/Rotate`.** `page.rect` è *già orientato* e
   `page.get_pixmap()` rende la pagina *già ruotata*. Verificato:
   su una pagina A4 con `/Rotate 90`, `page.rect` è `842×595` e
   `get_pixmap(matrix=Matrix(1,1).prerotate(0))` produce `842×595`.

2. **Il worker riceve solo `item.rotation`.** Passargli `total_rotation`
   applicherebbe la rotazione base una seconda volta.

3. **`save_as` scrive `item.total_rotation`**, perché `page.set_rotation()`
   imposta la `/Rotate` assoluta, non un delta.

**Questo bug è realmente accaduto** (è stato trovato e corretto durante la
stesura di questo documento). Un refactor aveva portato il codice a passare
`total_rotation` al worker *e* a far decidere lo scambio largo/alto della
pagina a `total_rotation` in `PageView._oriented_size`, mentre `width_pt`/
`height_pt` (che vengono da `page.rect`) la rotazione base ce l'hanno già dentro. Effetto: le
pagine con `/Rotate` diverso da zero — scansioni, PDF esportati da telefono,
qualsiasi cosa un visualizzatore abbia "raddrizzato" scrivendo `/Rotate` —
venivano mostrate **verticali e capovolte**. Il test di regressione è
`test_page_with_base_rotation_is_not_rotated_twice` in
`tests/test_integration.py`: se qualcuno tocca di nuovo la rotazione, quello è
il test che deve fallire. (Era un caso non coperto perché tutti i PDF di test
erano generati con `/Rotate 0`.)

4. **I rettangoli disegnati col mouse nascono in spazio vista.** Il puntatore
   arriva in `page.rect` **con la rotazione dell'utente già applicata**, cioè
   nello spazio di una pagina con `/Rotate = total_rotation`; `add_redact_annot()`
   invece vuole lo spazio **non ruotato**. Verificato: `search_for("SEGRETO")`
   restituisce lo stesso `Rect` con `/Rotate` a 0 e a 90, ed è quello che
   `apply_redactions()` consuma. I rettangoli di redazione si conservano quindi
   in **spazio pagina**, e le due conversioni stanno in `model/redact.py`
   (`rotation_matrix` / `derotation_matrix`, solo multipli di 90). Tenerli in
   spazio vista sarebbe un bug silenzioso: ruotando la pagina *dopo* averli
   disegnati, il salvataggio successivo annerirebbe il paragrafo accanto.

La regola in una riga:

> **Al renderer va `item.rotation`; la vista scambia largo/alto su
> `item.rotation`; solo il salvataggio conosce `total_rotation`; i rettangoli
> di redazione si conservano in spazio pagina, non in spazio vista.**

---

## 5. Il modello (`src/plico/model/document.py`)

```python
@dataclass
class PageItem:
    source_index: int     # posizione nella propria sorgente
    base_rotation: int    # /Rotate originale (0/90/180/270)
    rotation: int = 0     # offset scelto dall'utente
    source_id: int = 0    # indice in DocumentModel.sources
    width_pt: float = 0.0    # dimensione orientata, /Rotate già applicata
    height_pt: float = 0.0

    @property
    def total_rotation(self) -> int: ...
```

`DocumentModel(QObject)` espone:

- `pages: list[PageItem]` — le pagine virtuali, nell'ordine mostrato;
- `page_sizes` (property, **derivata**) — le dimensioni **orientate**, lette
  da `item.width_pt`/`item.height_pt` e quindi sempre allineate a `pages`.
  Tenerle in una lista parallela è la cosa che viene naturale, ed è quello che
  c'era: ma `DeletePage` e `MovePage` mutano `pages` da soli, e bastava il
  comando che dimenticava di aggiornare la seconda lista perché impaginazione e
  documento divergessero. Derivandola, l'allineamento diventa una proprietà
  della struttura invece che una disciplina da ricordare a ogni comando nuovo.
  I valori vengono da `page.rect`, quindi includono la `/Rotate` base, e sono
  letti all'apertura perché la vista possa impaginare *prima* che il thread di
  rendering abbia prodotto un pixel: costa una passata di metadati, non un
  render;
- `sources: list[str]` — i percorsi dei PDF aperti;
- `page_count` (property);
- `open(path, password=None)` — sostituisce tutto, aprendo in sola lettura;
- `read_source(source_id, path, password=None) -> list[PageItem]` — descrive
  *path* come pagine virtuali **senza toccare il modello**. È il passo che si
  può fare prima di impegnarsi, e da lì passa tutto il resto: `open()` è
  `set_pages(read_source(...), path)` e `append_document()` è
  `read_source()` + accodamento. Ricorda la password in `passwords[path]`;
- `set_pages(items, path)` — installa *items* come documento intero, senza
  aprire niente. Serve alla finestra, che legge **prima** e resetta le viste
  **dopo**: un documento che non si apre non deve lasciare a schermo una
  pagina 1 vuota;
- `append_document(path, password=None) -> int` — **unire**: accoda tutte le
  pagine di un altro PDF. La sorgente viene registrata *dopo* essere stata
  letta con successo, così un file corrotto lascia il modello esattamente
  com'era;
- `passwords: dict[str, str]` — path → password. Serve perché lo stesso file
  viene riaperto due volte **da altri**: dal worker (per renderizzarlo) e dal
  salvataggio (per copiarne le pagine), e nessuno dei due ha qualcuno a cui
  chiedere. Lo riempie `read_source`, lo svuota `close()`;
- `source_for(item) -> str`;
- segnali `changed` (struttura) e `page_changed(int)` (modifica in loco).

I PDF cifrati passano da due nomi di modulo:

- `PasswordRequired` (`Exception`, in `model/document.py`), con `path` e
  `wrong`: la finestra deve poter dire «password errata» al secondo tentativo
  e distinguerlo dal primo;
- `open_for_reading(path, password=None) -> pymupdf.Document` — **l'unico**
  punto in cui Plico apre in lettura un PDF esistente. Autentica prima di
  leggere qualunque pagina: su un handle bloccato la prima lettura lo lascia
  incapace di decifrare per sempre (misurato, §10), quindi l'ordine è la
  sostanza e non uno stile. Un file senza password utente si apre senza
  chiedere nulla.


**Le viste osservano il modello**, non vengono "puntate" dalla finestra. È una
scelta deliberata: aggiornare le viste a mano dopo ogni comando significa
dimenticarsene su undo/redo, che è esattamente il bug che era stato
introdotto e poi corretto. `PageView` e `ThumbnailBar` si connettono a
`model.changed` / `model.page_changed` da soli. `ThumbnailBar`, in
particolare, tratta `page_changed` **senza** resettare il modello — la riga
resta e va solo ridipinta — e ne scarta la miniatura vecchia: la chiave di
render contiene la rotazione utente, quindi l'immagine resa prima della
rotazione non sarebbe più raggiungibile da `data()` e resterebbe nella LRU a
occupare spazio, una per ogni rotazione (avanti e indietro).

---

## 6. RenderWorker — il pezzo critico (`src/plico/rendering/worker.py`)

Un `QObject` spostato in un `QThread`, che possiede **l'unico** handle PyMuPDF.
La UI comunica solo via signal; le connessioni fra thread diversi sono
`queued`, quindi gli slot girano nel thread giusto senza gestire nulla a mano.

```python
key = ("page" | "thumb", source_id, source_index, rotation, zoom, dpr, redactions)

class RenderRequest:
    key: tuple
    source_path: str     # quale PDF
    source_index: int    # quale pagina in quel PDF
    zoom: float          # pixel REALI (zoom × dpr)
    rotation: int        # solo offset utente
    redactions: tuple    # RedactionRect da applicare prima del render, () per nessuna
```

Con `redactions` non vuoto il worker non disegna la pagina della sorgente ma
`redacted_copy()`: una copia di una pagina sola (`insert_pdf`) con le
cancellazioni bruciate da `burn_redactions()`, la stessa funzione che usa il
salvataggio. L'handle della sorgente resta in sola lettura e la copia si
chiude subito dopo il render.

`RenderWorker` ha quattro signal:

```python
render_requested = Signal(object)        # in
rendered         = Signal(object, QImage)  # out
render_failed    = Signal(object)        # out: key di una richiesta fallita
evict_requested  = Signal(str)           # in: dimentica l'handle di un path
```

e:

- apre i sorgenti **pigramente**, al primo render richiesto, tenendo una LRU di
  al massimo `MAX_OPEN_DOCUMENTS = 16` handle (unire molti PDF non deve
  sprecare un file descriptor per documento);
- riceve il **percorso** nel `RenderRequest` invece di dipendere da un
  messaggio "apri" precedente: non c'è alcun ordinamento fra thread da
  sbagliare, e una pagina non viene mai resa dal documento sbagliato.

**Le password arrivano al worker, non se le fa chiedere.**
`RenderWorker.authenticate(path, password)` è uno slot `@Slot(str, str)` — il
nome è pubblico proprio perché `QMetaObject.invokeMethod()` lo cerca per
stringa, e con la `_` davanti non lo trova: `No such method
RenderWorker::authenticate(QString,QString)`, e la password non arriva a
nessuno. Memorizza la password e **riapre subito** l'handle. La finestra lo
invoca con `BlockingQueuedConnection` mentre la vista tiene indietro le
richieste (`PageView.set_paused(True)`): la connessione è bloccante perché
l'handle dev'essere aperto e decifrato **prima** che il worker serva il primo
render di quelle pagine, e mettere la password in coda dietro le richieste che
abilita sarebbe peggio che inutile. `shutdown()` svuota `_passwords`.

Chi chiede un render segna la `key` come "in volo". Se il worker non riesce a
produrre l'immagine — sorgente sparita, pagina fuori intervallo, documento
chiuso — emette `render_failed` con quella key: il ricevente **deve** azzerare
il segno, altrimenti la pagina aspetta per sempre un render che non arriverà
mai e non viene più ritentata.

Per lo stesso motivo `_render` intercetta **`Exception`**, non un elenco di
tipi: le eccezioni di MuPDF (`FzErrorLimit`, `FzErrorFormat`, …) derivano
direttamente da `Exception`, non da `RuntimeError`. Il caso concreto: una
pagina di grande formato (14400 pt) allo zoom massimo su HiDPI (8 × 2) dà
`FzErrorLimit: Overly large image`. Con l'elenco ristretto l'eccezione
usciva dallo slot, `render_failed` non partiva e la pagina restava «in volo»
per sempre. Test: `test_worker_reports_a_mupdf_error_as_a_failure`.

`evict_requested` esiste per un caso preciso: dopo un salvataggio che
sovrascrive una sorgente, `save_as()` ha fatto `os.replace()` e l'inode è
cambiato, ma il worker terrebbe aperto il documento **vecchio**. Senza
l'evict, riaprire lo stesso file renderebbe il contenuto di prima del salvataggio.

L'evict da solo **non basta**, e non è il punto: dopo una sovrascrittura è
il *modello* a essere sbagliato (vedi §10, «Salvare sopra il file aperto»).
`MainWindow._adopt_saved_file()` emette l'evict e poi **riapre il file
salvato**; l'evict viaggia in coda prima dei render chiesti dalla riapertura,
quindi arriva per primo.

Punti che sembrano dettagli e non lo sono:

- **Si emette `QImage`, mai `QPixmap`.** `QPixmap` esiste solo nel thread GUI;
  la conversione `QPixmap.fromImage()` va fatta nel ricevente.
- `QImage` avvolge il buffer di `pix.samples`: serve `.copy()`, altrimenti il
  buffer liberato da PyMuPDF lascia l'immagine a puntare nel vuoto.
- Un render in ritardo va **scartato**: il ricevente confronta la `key` con
  quella che la vista vuole adesso (`pending_key`).

### Chiusura pulita — da non toccare senza capire

`MainWindow.shutdown_worker()` fa, **in quest'ordine**:

1. `QMetaObject.invokeMethod(worker, "shutdown", BlockingQueuedConnection)` —
   chiude gli handle PyMuPDF **dentro** il thread del worker. Chiamare
   `worker.shutdown()` direttamente dal thread GUI toccherebbe il documento
   dal thread sbagliato, in gara con un render in corso;
2. `thread.quit()`;
3. `thread.wait(5000)`, con `terminate()` come ultima risorsa.

Lo shutdown è agganciato **sia** a `closeEvent` **sia** a
`aboutToQuit` di QApplication. Solo `closeEvent` non basta: qualunque uscita
che non chiuda la finestra (`app.quit()`, fine sessione, eccezione all'avvio)
distruggeva un `QThread` ancora in corsa e faceva **abortire il processo**
(`QThread: Destroyed while thread '' is still running`, exit 134 con core
dump). Se in futuro compare quell'errore, il sospetto è un `QThread` con
parent widget (vedi §10).

---

## 7. Le viste

### `PageView` (`widgets/page_view.py`)

`QScrollArea` con una colonna di `QLabel`. Costanti: `ZOOM_STEPS`,
`PRELOAD = 200` px, `CACHE_BUDGET = 64 MB`, `FALLBACK_VIEWPORT_H = 800`.

- **Rendering su richiesta**: si chiedono solo le pagine visibili, più
  `PRELOAD` di margine. Su un PDF da 300 pagine all'apertura partono 2 render
  di pagina e ~12 miniature — non 300.
- **Visibilità calcolata, non letta da Qt.** `_visible_range()` usa `y_px` /
  `height_px` registrati da `_relayout()`. Il motivo è in §10: la
  `geometry()` di un widget non significa nulla finché Qt non ha eseguito un
  layout, e in una finestra mai mostrata ogni etichetta riporta lo stesso
  rettangolo stantio — così *tutte* le pagine sembrano visibili.
- **Cache in byte, non in pagine** (`_cache_put`): a zoom alto una pagina sono
  decine di MB, contare le pagine non limita nulla.
- **HiDPI**: si renderizza a `zoom × dpr` e si fa
  `img.setDevicePixelRatio(dpr)`. È questo che rende il testo nitido e che
  sopravvive allo spostamento della finestra fra monitor con DPI diversi.
- **Niente sfarfallio**: la pixmap vecchia resta finché la nuova non è pronta.
- **Fit-width stabile**: la scrollbar viene sempre sottratta alla larghezza
  disponibile, altrimenti il contenuto "respira" di qualche pixel.
- **Ancoraggio**: dopo eliminazione/riordino la vista resta sulla pagina che
  si stava leggendo, rintracciata per `(source_id, source_index)`.

Gli slot che contano: `set_zoom`, `set_zoom_fit_width`, `zoom_in`/`zoom_out`,
`ensure_page_visible(index)`, `refresh_geometry()`, `reset()`, `clear()`.

### `ThumbnailBar` (`widgets/thumbnail_bar.py`)

`QListView` + `QAbstractListModel` che avvolge `DocumentModel.pages`.
`THUMB_ZOOM = 0.2`, key `thumb_key(...)`, cache `ThumbnailCache` (LRU,
`maxsize=60`) creata da `MainWindow` e passata al costruttore. **È la barra
l'unica a leggerla e a riempirla**: `MainWindow` non instrada più i render.

La barra è anche il **router** delle miniature: tiene in `_pending` le key che
ha chiesto (key → riga di destinazione) e usa quella mappa per due cose:

- **niente richieste duplicate**: `_request_row` esce se la key è già in cache
  o già in volo. Senza il controllo, ogni tick di scroll riemetteva le
  richieste di tutto il visibile, riempiendo la coda del worker di duplicati e
  ritardando la pagina che l'utente aspetta;
- **scarto degli obsoleti**: `_on_rendered` fa `_pending.pop(key)`. Se la key
  non c'è, il risultato non è suo — è un render di pagina (li gestisce la
  `PageView`) o un render di un documento che non mostriamo più. Le chiavi
  ripartono da `source_id 0` a ogni apertura, quindi senza questo filtro la
  miniatura del file precedente finirebbe sulla riga del nuovo.

Per lo stesso motivo `MainWindow` **non** instrada più le miniature: ognuno
riceve tutti i `rendered` e scarta quelli che non sono suoi, in base al tag in
`key[0]` (`"page"` / `"thumb"`).

- **Caricamento lazy**: `_visible_rows()` chiede solo le miniature in vista
  (più ±2 celle), con fallback al primo schermo pieno finché il layout non è
  avvenuto. La scansione parte dalla riga sotto la cima del viewport e si
  ferma appena esce dalla fascia visibile: è O(visibili), non O(pagine) a ogni
  tick di scroll. La barra si aggiorna anche su
  `verticalScrollBar().valueChanged`.
- **La selezione sopravvive a un reset**: `beginResetModel/endResetModel`
  azzera `currentIndex`, quindi dopo ogni delete/riordino la selezione moriva e
  `Ctrl+R` non faceva più nulla finché non si ricliccava. `_on_doc_changed`
  ripristina `_last_row` (clampato al nuovo conteggio) con `_restoring = True`,
  così la selezione torna **senza** trascinare la vista principale sulla riga.
- **Un in-place edit scarta la miniatura stantia**: la key embedde la
  rotazione utente, quindi la voce resa prima della rotazione è irraggiungibile
  da `data()`. `_on_page_changed` la elimina (e dimentica l'eventuale render in
  volo della rotazione annullata), altrimenti ogni rotazione lasciava
  un'immagine orfana nella cache.
- **Il drag & drop è tradotto in un comando**: `dropEvent` chiama
  `event.ignore()` perché il riordino interno predefinito non avvenga **mai**,
  ed emette `move_requested(from, to)`. Lasciare che la vista si riordini da
  sola disallineerebbe vista e modello. La destinazione passa da
  `drop_target_row()`, che **conta lo scostamento del pop** (vedi §10).
- Segnali: `move_requested(int, int)`, `page_selected(int)`.
- `ThumbnailCache` è una LRU vera: `get()` e `[]` spostano la voce in testa,
  perché le righe intorno al viewport sono rilette a ogni repaint e sono
  esattamente quelle che vale la pena tenere.

---

### `FormPanel` (`widgets/form_panel.py`)

Il dock «Modulo»: un editor per ogni campo **modificabile** della pagina in
vista (`QLineEdit`, `QPlainTextEdit` per i multilinea, `QCheckBox`,
`QComboBox`). È deliberatamente sottile — mostra i campi che il modello già
descrive e riferisce cosa scrive l'utente, senza mai **possedere** la verità: i
valori stanno in `PageItem.form_values`, quindi un cambio di pagina, un undo o
una rotazione si limitano a ridisegnare la stessa funzione del modello. Un
editor che non si può salvare sarebbe una promessa non mantenuta, quindi i
campi in sola lettura non vengono mostrati affatto.

## 8. Comandi e salvataggio

### Modifiche non salvate (`MainWindow`)

- **«Salvato» = l'indice clean del `QUndoStack`**, e basta. L'unione è un
  comando come gli altri (`AppendDocument`, §8), quindi anche le pagine unite
  sono coperte da Ctrl+Z e il flag `_merged_since_save` non esiste più:
  `is_modified()` è `not self._undo_stack.isClean()`. `_update_title()` mette
  nel titolo il nome del file con `[*]` (solo il nome: il display name lo
  aggiunge Qt) ed è collegato a `cleanChanged`, così un undo che riporta al
  salvato toglie l'asterisco.
- **`_save_target`** è il file su cui scrive `Ctrl+S` (`_save_file`): quello
  aperto, oppure l'ultimo «Salva con nome» (`_save_file_as`). Entrambi passano
  da `_save_to()`. Salvare *altrove* non cambia le sorgenti, quindi l'undo
  resta (`_mark_saved` sposta solo l'indice clean); salvare *sopra* una
  sorgente riapre il file (`_adopt_saved_file`, vedi §10) e l'undo riparte.
  «Salva compresso» su un altro file è una copia e non segna il documento
  come salvato.
- **`_confirm_discard()`** chiede Salva / Non salvare / Annulla prima di
  `closeEvent`, di *File → Chiudi* e del dialogo di `_open_file` (non dopo:
  la domanda riguarda il documento in vista). «Salva» passa da `_save_file`;
  un salvataggio fallito o annullato lascia il documento aperto. Prima di
  decidere chiama `PageView.finish_text_edit()`: una correzione scritta
  nell'editor ma non ancora confermata è lavoro dell'utente, e senza questo
  passo sparirebbe con l'editor senza nessuna domanda. Nei test
  `QMessageBox.question` va **monkeypatchato** (§10): il fixture `windows`
  non chiama `close()`, quindi non incontra la domanda.
- **File → Chiudi (`Ctrl+W`)**: `_close_file()` fa la domanda,
  `close_document()` svuota la finestra senza chiedere nulla. L'ordine conta:
  prima `PageView.clear()`, che chiude l'editor **senza** confermarlo (la
  risposta sulle modifiche è già stata data) e svuota la cache dei render;
  poi strumenti spenti, undo stack, `DocumentModel.close()`, cache delle
  miniature, e un `evict` al worker per **ogni** sorgente, perché chi chiude
  un PDF si aspetta di poterlo spostare o cancellare. La voce è attiva solo
  con un documento aperto: la tiene allineata `_update_title()`, da cui
  passano apertura, chiusura e salvataggio.
- **La password si chiede in `MainWindow._ask_password()`**, con
  `QInputDialog.getText(..., QLineEdit.EchoMode.Password)`: `open_path()` e
  `merge_path()` la chiamano in un ciclo, e al secondo tentativo il testo dice
  che la password era errata. Il dialogo va tenuto **qui** e non nel modello,
  che nei test è usato senza GUI. Annullare non deve costare niente: se le
  pagine non si riescono a leggere, `open_path()` restituisce `False` senza
  aver toccato né le pagine, né il titolo, né lo stato «da salvare» — e
  `merge_path()` non deve lasciare un passo di undo vuoto. Il
  `RenderWorker.authenticate()` bloccante e la pausa delle viste stanno
  attorno a questo (§6).

`model/commands.py`: `RotatePage`, `DeletePage` (`pop` al redo, `insert`
all'undo — lo stack è LIFO, quindi gli indici restano coerenti), `MovePage`,
`AppendDocument`. La rotazione di più pagine selezionate va raggruppata con
`stack.beginMacro()`, così è **un solo** passo di undo.

**`AppendDocument` riceve le pagine già lette**, e le legge il chiamante
(`MainWindow._push_merge`, che è anche quello che chiede la password): un file
che non porta pagine non deve lasciare un comando vuoto nello stack, e un
`redo()` che rileggesse il file lo farebbe scrivere pagine diverse da quelle
che l'utente ha visto. `redo()` accoda la sorgente (la prima volta) e allunga
`pages`; `undo()` taglia `pages[-n:]` e **lascia la sorgente registrata**,
senza pagine che la usino.

**Un `source_id` non si riusa mai.** Prima `undo()` toglieva la sorgente, e
l'unione successiva riceveva lo stesso id per un file diverso: le chiavi di
render contengono l'id, quindi le pagine del file nuovo venivano mostrate con i
pixel di quello tolto (misurato: una pagina blu mostrata rossa, mentre il
salvataggio la scriveva blu). Svuotare le cache a ogni `changed` toglieva il
sintomo ma non un render del file vecchio ancora in viaggio dal worker, che
arrivava con la stessa chiave chiesta dalla pagina nuova; con gli id mai
riusati nessuna chiave può più rispondere per un altro file. Il prezzo è che
`sources` può contenere voci che nessuna pagina legge: chi deve sapere quali
file sono **in uso** lo chiede alle pagine, come fa `sources_at()` — scrivere
sopra un file la cui unione è stata annullata è un salvataggio altrove, non un
motivo per riaprire il documento. Il nome è
`QCoreApplication.translate("AppendDocument", "Unisci «{0}»")` con il nome del
file, così Ctrl+Z dice cosa sta per togliere.

`model/save.py`:

- **ogni sorgente si copia una volta sola** (`model/assemble.py`,
  `assemble(out, ordine)`): l'intervallo dalla prima all'ultima pagina che
  contribuisce, in **una** chiamata a `insert_pdf`; le pagine in mezzo che non
  servono si eliminano, e l'ordine si fa dentro il file d'uscita con
  `move_page()` (e `fullcopy_page()` per una pagina chiesta due volte). Prima
  le pagine si copiavano a sequenze contigue, una chiamata per sequenza, e
  copiare **due volte dalla stessa sorgente** rompe i moduli (misurato su
  PyMuPDF 1.28): un campo con un widget per pagina perdeva il widget della
  seconda copia — la pagina usciva senza campo — e un campo incontrato di
  nuovo veniva rinominato (`nome` → `nome [12]`). Non bastano né
  `join_duplicates` né `final=0`, e `Document.select()` toglie l'intero
  AcroForm. Tre dettagli:
  - `delete_page()` lascia in `/Fields` i campi delle pagine tolte, **valore
    compreso**: `_prune_fields()` toglie ogni campo che nessuna pagina mostra
    più, perché una pagina eliminata non deve lasciare nel file quello che
    c'era scritto;
  - due campi della **stessa** sorgente con lo stesso nome sono un campo solo
    (per PDF e per il modello, che scrive i valori per nome): la prima copia
    li unisce (`join_duplicates`), una sorgente successiva che ne ha passa
    prima da una copia sua. Campi omonimi di sorgenti **diverse** (anche lo
    stesso file unito due volte) restano due, e MuPDF rinomina il secondo;
  - il prezzo è copiare anche le pagine fra quelle chieste: estrarre la prima
    e l'ultima di 1000 pagine costa ~1,1 s (misurato), un salvataggio normale
    o rovesciato ~0,3 s;
- `_write_pdf` riapre ogni sorgente con `open_for_reading(path,
  model.passwords.get(path))`: qui la password non si può chiedere — il
  salvataggio ricopia file che l'utente ha già sbloccato, e il worker li
  riapre da solo per renderizzarli — quindi sta nel modello, che l'ha imparata
  all'apertura;
- `save_as(model, out_path)` / `extract_pages(model, out_path, indices)` /
  `save_compressed(...)` condividono `_write_atomically`, che scrive **sempre**
  su un file temporaneo nella **stessa directory** e poi fa `os.replace()`: non
  esiste una scorciatoia che scriva direttamente sulla destinazione. Il prezzo è
  che la *directory* deve essere scrivibile; il guadagno è che un errore a metà
  scrittura non può troncare niente — nemmeno un «Salva con nome» sopra un file
  che l'utente non ha mai aperto — e che i permessi del file sostituito
  sopravvivono (`os.chmod` sul temporaneo: PyMuPDF ricrea il file e altrimenti
  riporterebbe la destinazione a `0o664`);
- `DocumentModel.sources_at(path)` dice quali sorgenti sono lo stesso file di
  *path*, confrontando l'**inode** (un'altra grafia del percorso o un hard link
  contano). Lo usa `MainWindow._save_file`, e con esso `_adopt_saved_file`, per
  sapere se il salvataggio ha sovrascritto una sorgente aperta: in quel caso il
  documento va riadottato e l'handle del worker dimenticato
  (`evict_requested`), perché `os.replace()` cambia l'inode mentre la copia
  cachata continua a leggere il documento vecchio;
- `extract_pages` **rifiuta** di scrivere sopra una sorgente aperta
  (`ValueError`): un sottoinsieme lì lascerebbe le pagine non estratte a
  puntare a pagine che non esistono più;
- `parse_page_ranges(spec, page_count)` converte `"1-3,5,8"` in indici
  **0-based preservando l'ordine digitato** (quindi `"5,1-3"` riordina oltre
  che estrarre) e solleva `ValueError` per input malformati, fuori intervallo
  o vuoti: scartare pagine in silenzio durante una divisione sarebbe peggio
  che rifiutare.

### Compressione mirata (`model/optimize.py`)

Due passate **senza perdita** più una sola con perdita, e le misure dicono
che l'ordine conta:

- `clean=True` di PyMuPDF (mutool clean) è **la vincita grossa**: un PDF si
  porta dietro centinaia di content stream minuscoli (uno per ogni
  `insert_text`, per ogni copia di pagina) e fonderli vale 188 KB → 12 KB su
  20 pagine di testo (6,3%). `garbage=4, deflate=True` da soli si fermano al
  99,4% e `pikepdf` da solo all'89,1%; `subset_fonts()` non aggiunge nulla;
- `pikepdf`/qpdf aggiunge object stream, deduplicazione e un secondo
  passaggio Flate (`compress_streams`, `recompress_flate`,
  `ObjectStreamMode.generate`, `StreamDecodeLevel.generalized`);
- `doc.rewrite_images(dpi_threshold, dpi_target, quality)` è **l'unico passo
  con perdita**, e sulle scansioni decide tutto: un JPEG da 3,4 MB su 3
  pagine resta al 100% con `light`, scende al 52,0% con `medium` e al 35,9%
  con `strong`.

I tre livelli sono `light` (immagini intatte), `medium` (200 → 150 dpi,
qualità 80) e `strong` (150 → 96 dpi, qualità 60) — `LEVELS` in
`optimize.py`, l'unico posto dove cambiare i numeri.

**Il livello dice *quanto*, non *cosa***: accanto sta `CompressionOptions`
(`optimize.py`) con `level`, **`groom`** (ricompattare anche il file) e
**`image_pages`** (le pagine di cui ricampionare le immagini; `None` = tutte).
Le tre scelte le fa il dialogo (`widgets/compress.py`); le funzioni accettano
sia le opzioni sia un livello nudo (`_as_options`), perché i test e i chiamanti
vecchi dicevano solo il livello.

**`groom=False` non è un livello più debole**: il ricampionamento delle
immagini si fa comunque, il file non viene ricompattato. Ha senso su un PDF
fatto di scansioni, dove il guadagno sta nelle immagini; su un documento di
solo testo non guadagna niente, ed è giusto dirlo invece di scrivere una copia
identica (la finestra lo racconta: «il peso sta nelle immagini delle pagine che
non hai scelto»).

**Il ricampionamento per pagina non esiste nell'API di PyMuPDF** —
`rewrite_images()` non ha un elenco di pagine — e si ottiene ricostruendo il
file a blocchi: le pagine scelte in un documento, `rewrite_images()` su quello,
le altre in un secondo documento, e i due riuniti in ordine con `assemble()`
(con `join_duplicates`, perché sono due copie dello stesso documento). Le
pagine non scelte si tolgono dalla copia con `delete_page()`, **non** con
`select()`: `select()` cancella l'AcroForm, e le pagine scelte uscivano dalla
compressione senza i loro campi (misurato). Due conseguenze misurate:

- **un'immagine condivisa da una pagina scelta e una no si sdoppia**: MuPDF la
  tiene una volta sola, e ricampionarla per una pagina sola obbliga l'altra a
  una copia per conto suo. Su due pagine che si dividono la stessa foto il file
  *cresce*, quindi la compressione viene rifiutata — meglio di un file scritto
  e più grande;
- i content stream vengono riscritti, quindi `clean` gira comunque sul
  risultato.

`optimize_in_place(path, options, progress)` adotta il risultato **solo se è
più piccolo** (un PDF già ottimizzato non deve crescere, e nessuno vuole un
file compresso più grande dell'originale).

**Il guadagno si mostra prima di scrivere**, e i numeri sono quelli veri
(`save.py`): `prepare_compressed()` materializza il documento virtuale in un
temporaneo (`_write_temporary`, quindi il file rispetta eliminazioni, riordini
e rotazioni), lo comprime lì e restituisce un **`CompressionPreview`** — il
file esiste, la destinazione non è ancora stata toccata. Chi lo riceve deve
decidere: `preview.keep()` mette il temporaneo al posto della destinazione con
i permessi di quella, `preview.drop()` lo cancella. `save_compressed()` è le
due cose in fila, per chi non ha una finestra da mostrare: comprime, e adotta
solo se ha guadagnato. La finestra invece comprime e poi racconta — le due
passate girano **una volta sola** e il guadagno non è una stima.

La compressione gira su `QThreadPool` con un `QRunnable`, non sul thread dei
render: sono due lavori indipendenti e un PDF grande non deve congelare la
finestra. I segnali sono connessi **solo a metodi legati di QObject** — un
lambda verrebbe eseguito nel thread emittente e toccherebbe widget dalla
thread sbagliata. Anche lo scambio finale (`preview.keep()`) può fallire —
destinazione diventata in sola lettura, cartella sparita — e allora il
temporaneo si cancella e l'errore arriva in un dialogo, invece di uscire dallo
slot lasciando un `.pdf.tmp` accanto alla destinazione.

### Redazione vera (`model/redact.py`)

**Nell'interfaccia si chiama «Cancella zona»** (*Modifica → Cancella zona*,
`Ctrl+Shift+X`, anche nella barra degli strumenti); la ricerca per parola è
*Cancella parola…* (`Ctrl+Shift+F`, «Parola da eliminare in tutte le
pagine») e la selezione col mouse è **«Cancella selezione»** (`Ctrl+Shift+L`,
`QAction` checkable accanto a «Cancella zona», icona `edit-select-all`). Sono
tre strumenti mutuamente esclusivi — `MainWindow._on_selection_toggled()`,
`_on_redaction_toggled()` e `_on_text_mode_toggled()` spengono gli altri due —
perché il trascinamento deve avere un solo significato. Il nome è cambiato due
volte, entrambe su segnalazione dell'utente:

1. «Redazione» / «Redigi testo»: in italiano corrente *redigere un testo*
   vuol dire **scriverlo**, quindi «Redigi testo» si leggeva come «Scrivi
   testo», l'opposto di quello che fa;
2. «Oscuramento» / «Oscura parola»: non è una parola che un utente italiano
   si aspetta in un editor, e non diceva *cosa* sparisce (c'è stato chi l'ha
   confuso con «Elimina pagina»).

La regola che ne viene: **nei testi per l'utente un verbo che dice cosa
succede** (cancella, elimina), non il termine di settore. Nel codice e in
questo documento resta *redaction*/redazione, il termine tecnico.

La differenza fra una redazione e un rettangolo nero: **il testo se ne va**.
`add_redact_annot()` + `apply_redactions()` riscrivono i content stream e
tolgono davvero le parole; un rettangolo disegnato sopra lascerebbe il
contenuto copiabile e ricercabile, che è la trappola da cui questa funzione
esiste.

- `PageItem.redactions` è una lista di `RedactionRect` in **spazio pagina**
  (vedi §4): ruotare la pagina dopo non sposta la redazione;
- `AddRedaction` / `RemoveRedaction` sono `QUndoCommand` come gli altri, quindi
  una redazione disegnata per sbaglio si annulla con Ctrl+Z;
- `save.py` le applica **dopo** `page.set_rotation(item.total_rotation)`, una
  volta per pagina, passando il rettangolo così com'è: lo spazio pagina è
  esattamente quello che `add_redact_annot()` vuole. `apply_redactions()`
  **preserva la `/Rotate`** e consuma le annotazioni, quindi non serve
  riapplicare la rotazione;
- vale per `save_as` **e** per `save_compressed`: comprimere un documento
  redatto non fa riapparire niente;
- `DocumentModel.find_text()` cerca una parola in **tutte** le pagine e
  restituisce i rettangoli già pronti: `search_for()` risponde nello spazio non
  ruotato, cioè esattamente quello delle redazioni, quindi non c'è niente da
  convertire. Le occorrenze già coperte da un segno non tornano una seconda
  volta, e `MainWindow._redact_text()` avvolge l'intera ricerca in una
  `beginMacro`/`endMacro`: un solo `Ctrl+Z` disfa tutto;
- la vista **non tocca il modello**: `PageView` emette `redaction_added` /
  `redaction_removed` / `selection_made` e `MainWindow` spinge il comando
  sullo stack, esattamente come per il drag & drop delle miniature.

**La selezione col mouse segue le parole, non il rettangolo.** Con
`Ctrl+Shift+L` si trascina su una frase e a sparire è ogni parola che il
rettangolo tocca, per intero: un segno a metà parola non nasconde niente (il
resto della parola resterebbe leggibile e copiabile), quindi la parola è
l'unità minima.

- `DocumentModel.words_on(index)` restituisce le parole della pagina in spazio
  pagina come `RedactionRect`: quelle del content stream
  (`page.get_text("words")`, che risponde nello spazio **non ruotato** —
  verificato con `/Rotate 0` e `90`) più quelle dello strato OCR
  (`item.ocr_words`). Il rettangolo del trascinamento è già in quello spazio,
  perché `_to_page()` passa da `page_matrix()`;
- `words_under()` filtra per **intersezione** e scarta quelle già coperte da un
  segno (`DocumentModel.unmarked()` → `_not_already_marked()`): selezionare due
  volte la stessa frase non crea due comandi sovrapposti, e ciò che si vede
  selezionato è esattamente ciò che verrà cancellato;
- ogni parola toccata diventa un `AddRedaction` (quindi ha il suo rettangolo
  stretto, non uno grande quanto il trascinamento), ma tutti dentro
  `beginMacro`/`endMacro`: la selezione è **un gesto solo** e si disfa con un
  solo `Ctrl+Z` (`MainWindow._add_selection()`);
- trascinare dove non c'è testo non crea comandi: `text_edit_refused` porta a
  «Nessuna parola nella selezione.» e lo stack resta com'era;
- un **clic** su un segno lo toglie anche in questa modalità, come nella zona:
  è la via di ritorno per una selezione sbagliata;
- le parole sono in cache per canvas (`_Canvas.words`) e si invalidano in
  `_on_page_changed()` (l'OCR aggiunge parole) e quando le canvas vengono
  riusate dopo un salvataggio (il `PageItem` è un altro).

**Un segno già disegnato si sposta e si ridimensiona.** Con la zona o la
selezione accesa ogni segno mostra i quattro angoli: preso dal centro si sposta
(misura invariata, e se il mouse esce dalla pagina scivola indietro lungo il
bordo invece di uscirne), preso da un angolo si ridimensiona. Sono gli handle a
dire che un segno si può correggere: senza, l'unico modo di aggiustare un
rettangolo sarebbe toglierlo e ridisegnarlo — su una pagina fitta di testo,
sbagliare di nuovo.

- la vista scrive il rettangolo nuovo **nel modello mentre il mouse si muove**
  (altrimenti la pagina non seguirebbe), ma è una scrittura provvisoria: al
  rilascio `mouseReleaseEvent()` rimette quello di prima e chiede a
  `MainWindow` un `AdjustRedaction`, che applica quello nuovo. Così l'intero
  gesto resta **un solo passo** di Annulla, e niente cambia senza che la pila
  lo sappia;
- se il gesto non finisce — si lascia lo strumento, Esc, si apre un altro
  documento — `_PageLabel.forget_drag()` rimette il rettangolo di partenza
  (`set_redaction_mode()` e `set_selection_mode()` la chiamano su ogni canvas):
  una modifica che nessun `Ctrl+Z` potrebbe togliere non deve sopravvivere;
- `RedactionRect.translated(dx, dy)` e `.with_corner(angolo, x, y)` fanno la
  geometria in spazio pagina; `with_corner()` passa da `from_corners()`, quindi
  trascinare un angolo oltre il lato opposto **ribalta** il rettangolo invece di
  produrne uno con larghezza negativa;
- `AdjustRedaction(modello, indice, posizione, prima, dopo, moved)` si chiama
  «Sposta zona su pagina n» o «Ridimensiona zona su pagina n»;
- un segno sotto `MIN_MARK` (2 pt) non viene applicato: nasconderebbe niente;
- l'hit test degli angoli lavora in **pixel** (`MARK_HANDLE`, 8 px): un
  bersaglio per il mouse non deve rimpicciolirsi con la pagina;
- l'ancoraggio tiene la distanza dal punto preso, non dall'angolo: il segno
  segue il mouse com'era stato afferrato;
- un **clic incerto** (meno di `CLICK_SLOP` pixel di movimento) resta un clic
  e toglie il segno, ma il trascinamento l'ha già spostato di quei pixel: il
  rettangolo provvisorio si legge *prima* che `forget_drag()` rimetta quello
  di partenza, altrimenti l'undo rimetteva il segno spostato — uno stato che
  nessun comando aveva prodotto.

**Un segno fatto di parole non tocca le righe vicine.** MuPDF cancella ogni
glifo il cui riquadro *tocca* la redazione, e il riquadro di un glifo va
dall'ascendente al discendente: con l'interlinea singola (1,0 – 1,2, misurato
con Helvetica e Times) entra nelle righe sopra e sotto. Cercare «SEGRETO»
trasformava la riga sotto da «Riga sotto innocente» in «Riga sott».

- `RedactionRect.snug` dice che il rettangolo è quello di parole su una riga:
  lo mettono `find_text()` e `words_on()` (ricerca e selezione), non la zona
  disegnata, che cancella tutto ciò che tocca perché è quello che l'utente ha
  disegnato;
- `_redact()` lavora in **due passate**: la prima toglie immagini e grafica
  sotto il segno intero (`text=PDF_REDACT_TEXT_NONE`), la seconda il testo
  attraverso `text_band()`, che per un segno *snug* è la fascia fra il 40% e
  il 60% dell'altezza — ogni glifo della riga la attraversa, nessuno della
  riga accanto ci arriva. Sopra una scansione i pixel della parola spariscono
  comunque tutti;
- un segno **spostato o ridimensionato** torna una zona disegnata
  (`translated()` e `with_corner()` non portano `snug`): a cavallo di due
  mezze righe la fascia cadrebbe nello spazio fra le due e non cancellerebbe
  niente di ciò che copre. Cancellare troppo è un difetto, cancellare troppo
  poco in una redazione è il difetto.

Limiti da conoscere: `apply_redactions()` con i valori di default
(`images=2`, `graphics=1`) elimina anche la **grafica vettoriale** che tocca il
rettangolo — un bordo o una tabella a cavallo del segno possono sparire.

I metadati **non sono un problema**, al contrario di quanto sembri: il file di
uscita è ricostruito con `insert_pdf()` dalle sole pagine, quindi `/Info`,
l'XMP e i file allegati della sorgente non ci arrivano mai. Verificato con una
sorgente che li portava tutti e tre: dopo `save_as` il titolo è vuoto, l'XMP è
0 byte e gli allegati sono scomparsi. Per lo stesso motivo un salvataggio
normale **non conserva** titolo e autore, che è una perdita da tenere a mente.
Le **annotazioni**, invece, vengono copiate da `insert_pdf()`: è `_redact()` a
eliminare quelle che toccano un rettangolo di redazione, perché
`apply_redactions()` toglie il **contenuto** ma lascia l'annotazione in piedi
(misurato: una nota «SEGRETO» appoggiata sulla parola redatta sopravviveva al
salvataggio, cioè trapelava proprio ciò che la redazione doveva nascondere). Un
commento lontano dal segno resta nel file. Lo stesso vale per i **campi dei
moduli**, con un ciclo a parte: `page.annots()` non elenca i widget e
`apply_redactions()` non li tocca, quindi un campo compilato con «Mario Rossi»
e coperto da una zona usciva dal salvataggio con il suo valore (misurato).
`_redact()` elimina anche ogni widget che tocca un segno (`delete_widget`).

**Anteprima e conferma (ottobre 2026, segnalazione dell'utente).** Un utente
ha segnato due parole, non ha visto cambiare niente, ha salvato e riaperto il
file per scoprire che erano sparite davvero. Le zone si disegnavano **solo
finché lo strumento era acceso**; spento, la pagina tornava intatta fino al
salvataggio, e con *Cancella parola* lo strumento veniva acceso apposta per
mostrare i segni. Ora:

- `PageView.redaction_preview()` è vero quando né «Cancella zona» né
  «Cancella selezione» sono accesi; in quel caso `_request_visible()` mette le
  zone della pagina nella chiave e nella `RenderRequest`, e la pagina si vede
  **come verrà salvata**. Con uno strumento acceso la chiave ha `()` e sopra la
  pagina vera si disegnano i segni con le maniglie. Accendere o spegnere uno
  strumento, e ogni `page_changed` (anche un Annulla a strumento spento),
  richiede di nuovo le pagine visibili;
- con l'anteprima, i campi del modulo e i testi modificati che toccano una zona
  **non** vengono ridisegnati sopra (`_hidden_by_preview()`): al salvataggio se
  ne vanno con la zona, e ridisegnarli smentirebbe l'anteprima;
- le miniature hanno le zone nella chiave **sempre**, qualunque strumento sia
  acceso: `_is_stale_thumb_key()` scarta quella con un insieme di zone diverso;
- *Cancella parola* non accende più lo strumento;
- `MainWindow._saved_marks` è l'insieme `(source_id, source_index, rect)` già
  scritto nel file di destinazione (`_mark_saved()` lo aggiorna; apertura e
  chiusura lo svuotano). «In sospeso» vuol dire modello meno quello: dopo un
  «Salva con nome» il modello tiene le zone, ma il file le ha già. Il titolo
  le conta (« — 2 cancellazioni da applicare»), aggiornato a ogni
  `indexChanged` della pila;
- `_confirm_redactions()` chiede prima di **ogni** scrittura che le applica:
  `_save_to()` e la firma (le zone non ancora nel file di destinazione,
  `_marks_to_write()`), la copia compressa e l'estrazione (tutte quelle delle
  pagine scritte, perché il file è sempre nuovo). Frasi intere per ogni caso,
  perché i traduttori non possono riordinare due mezze frasi. Il dialogo è
  `_ask_to_burn()`, e `tests/conftest.py` lo sostituisce con un «sì» per
  tutta la suite: un `QMessageBox` modale offscreen aspetterebbe per sempre;
- `widgets/toast.py`: un `QLabel` sopra la vista, in basso al centro, con i
  colori dei tooltip del tema, trasparente al mouse, che sparisce dopo 4,5 s.
  `MainWindow._notify()` scrive lo stesso testo nella barra di stato e nel
  toast. Lo usano i segni (zona disegnata, selezione, *Cancella parola*),
  l'uscita da uno strumento con cancellazioni in sospeso e la fine dell'OCR,
  che prima finiva solo nella barra di stato.

### Compilazione dei form (`model/forms.py`)

Un campo AcroForm non è contenuto: è un'**annotazione** con un valore, e il
valore sta nel dizionario del campo. Compilarlo significa scrivere nel widget e
chiamare `update()` mentre la pagina che si sta salvando è ancora viva.

- `PageItem.form_fields` è la **descrizione** dei campi che la sorgente offre
  (`Field`: nome, tipo, valore, `rect` in spazio pagina, scelte, multiline),
  letta una volta in `_items_for()` — e solo se `doc.is_form_pdf`, che è una
  proprietà di documento e risparmia una scansione per ogni pagina;
- `PageItem.form_values` è un dizionario nome → valore con **solo i campi
  toccati**: un nome assente significa «lascia quello che c'era», che non è la
  stessa cosa di un valore vuoto (`""` è una modifica dell'utente e deve
  arrivare al file);
- `SetFieldValue` è un `QUndoCommand` con `id()`/`mergeWith()`: un `QLineEdit`
  emette un segnale **per tasto**, e senza fusione scrivere «Anna» costerebbe
  quattro Ctrl+Z. Fonde solo modifiche consecutive **allo stesso campo** e
  conserva il valore del primo comando, così un undo disfa il campo intero;
- i valori si scrivono **sulla sorgente in memoria** prima della copia
  (`_fill_source_fields(doc, values)`, che passa su tutte le pagine), non sulla
  pagina già copiata: `insert_pdf()` **rinomina** la seconda copia di un campo
  omonimo (`nome` → `nome [12]`), quindi scrivere per nome dopo la copia non
  troverebbe più niente. Era il difetto per cui lo stesso campo su due pagine
  restava vecchio sulla seconda, con un esito che dipendeva dall'ordine delle
  pagine. L'handle modificato **non viene mai salvato**: il file su disco resta
  intatto;
- `save.py` scrive i campi **prima** di `_redact()`: una redazione sopra un
  campo deve portarselo via, e un valore appena scritto non deve sparire per
  una redazione altrove sulla stessa pagina;
- vale per `save_as` **e** per `save_compressed`: `clean=True` conserva il
  modulo e i suoi valori (verificato);
- i tipi modificabili sono **testo**, **casella**, **tendina/lista** e
  **radiobutton**. I radio ci sono anche se PyMuPDF **non sa crearne uno**
  (`page.add_widget()` con `PDF_WIDGET_TYPE_RADIOBUTTON` solleva `ValueError:
  bad xref`, sempre, con o senza valore): sa però **scriverli**, purché la
  pagina resti viva — senza un riferimento alla pagina `update()` muore con
  `ReferenceError: weakly-referenced object no longer exists`. Un gruppo è
  **un campo con un bottone per scelta**, tutti con lo stesso nome: `read_fields`
  ne restituisce uno per bottone, e `value`/`option` si leggono da `button_states()`
  (`{'normal': ['Off', 'primo']}`) e dal `/V` del campo padre, non
  dall'`/AS` del bottone. Scrivere significa mettere `/V` sul padre e `/AS` sul
  bottone scelto e `/Off` sugli altri; MuPDF vuole il nome del campo come
  **nome** `/secondo` e non come stringa, e PyMuPDF gliela scriveva come
  stringa: da qui `_name_the_choice()`. Le **firme** appartengono a *File →
  Firma…*.

La vista disegna i campi sulla pagina (`_paint_fields`, con il valore preso dal
**modello** e non dal file). Un clic su un campo **fa quello che l'utente
intende**: un campo di testo a riga singola apre l'editor sulla pagina, una
casella si spunta dove è stata cliccata, un bottone radio sceglie la sua
risposta. Tendina, testo multiriga e campi in sola lettura si limitano a
selezionare l'editor nel pannello, che è dove può stare un editor che offre le
scelte, cresce o dice di no: `PageView` emette `field_clicked` solo per questi,
e per gli altri agisce da sé (`begin_field_edit`, `toggle_field`,
`choose_field`), così `MainWindow` continua a ricevere un solo segnale.

### Modifica minima del testo (`model/textedit.py`)

**Stato:** completa, dal modello all'interfaccia (*Modifica → Modifica
testo*, `Ctrl+Shift+T`). Nasce da un prototipo
provato su PDF veri (LibreOffice con tabella e cella colorata, un PDF
commerciale con testo bianco su sfondo, un PDF con font Type3).

- **L'unità è lo span** di `get_text("dict")`: una corsa di testo su una riga
  con un solo font, corpo e colore. Un *blocco* è un paragrafo su più righe
  (riscriverlo in `(x0, y1)` lo schiaccia su una riga), una *parola* non ha
  stile proprio. Lo span porta già baseline (`origin`), font, corpo, colore
  e flag. `span_at(page, x, y)` lo cattura in un `TextSpan` frozen e
  autosufficiente: il salvataggio non deve ritrovarlo.
- **Tutto in spazio pagina.** `get_text("dict")`, `add_redact_annot()` e
  `TextWriter` usano lo spazio non ruotato anche con `/Rotate 90`
  (verificato: stesso rettangolo a 0 e a 90), quindi è lo stesso spazio delle
  redazioni (§4) e non serve alcuna conversione.
- **Il testo vecchio si toglie davvero**, con una redazione che tocca **solo**
  il testo: `fill=None` (misurato: lo sfondo di una cella colorata resta),
  `images=PDF_REDACT_IMAGE_NONE`, `graphics=PDF_REDACT_LINE_ART_NONE`. Con i
  default di `apply_redactions()` sparirebbero i bordi della tabella.
  La redazione **non** è il riquadro dello span: quel riquadro, dall'ascendente
  al discendente, con l'interlinea singola tocca le righe sopra e sotto, e
  MuPDF cancellava lettere anche da quelle (misurato a 1,0 / 1,15 / 1,2). Si
  redige la fascia fra metà e un quinto del corpo sopra la baseline
  (`_removal_band`), che attraversa ogni glifo dello span e nessun altro.
- **Il font: tre fonti, in quest'ordine.**
  1. Quello incorporato, se ha una mappa dei caratteri. **Quasi mai:**
     LibreOffice incorpora sottoinsiemi indicizzati per glifo (14-33 glifi,
     `has_glyph()` dice no a tutto). Funziona invece su PDF con font completi.
  2. Lo stesso font **installato sul sistema**, cercato per nome PostScript con
     `fc-match` e verificato (fc-match risponde *sempre*, anche con un altro
     font). È la fonte che salva i PDF da ufficio: Liberation, DejaVu, Noto…
  3. Un sosia Base-14 scelto dai flag (serif/mono, grassetto/corsivo).

  I nomi vanno confrontati con `_font_key()`: `get_fonts()` dice
  «Nimbus Roman Regular», `get_text()` dice «NimbusRoman-Regular».
- **`TextWriter`, non `insert_text()`**: con un font Base-14 `insert_text()`
  scrive «Łódź» come «·ód·»; `TextWriter` incorpora il font come Type0 e
  scrive tutto l'Unicode che il font contiene.
- **Lo spazio a destra (`room`) non è quello della riga.** Una cella di
  tabella è un blocco a sé: la cella accanto e il bordo in mezzo sono
  invisibili alla riga, e il prototipo scriveva «Licenze software» dentro la
  cella dell'importo. `_room()` guarda il testo di **tutti** i blocchi alla
  stessa altezza e le **linee verticali** (anche i rettangoli sottili, che
  molti produttori usano come filetti). Il bordo della pagina si prende in
  spazio pagina (`page.rect * page.derotation_matrix`), non da `page.rect`:
  quello è già ruotato, e su un A4 con `/Rotate 90` lasciava correre il testo
  fino a 806 pt su una pagina larga 595. Oltre lo spazio il testo si
  rimpicciolisce fino a `MIN_SCALE = 0.8`, sotto si rifiuta.
- **Rifiutati, con un messaggio:** testo non orizzontale e font **Type3** (i
  glifi sono disegni: il colore sta nel glifo, quindi lo span dice «nero», e
  la redazione lascia residui visibili).
- **`check_edit()`** fa la stessa scelta di `apply_edit()` senza toccare la
  pagina: va chiamato quando l'utente conferma, perché una modifica
  impossibile si rifiuta lì, non al salvataggio.
- **Peso del file:** un font di sistema viene incorporato intero (36 KB →
  241 KB per una modifica). `doc.subset_fonts()` prima del salvataggio
  riporta a 44 KB: `save.py` dovrà chiamarlo quando ci sono modifiche.

**Da verificare nel Flatpak:** che `fc-match` esista nel runtime e veda i font
dell'host (`/run/host/fonts`). Se manca, si scende al sosia Base-14: brutto ma
corretto.

**Nel documento:**

- `PageItem.text_edits` è una lista di `TextEdit(span, new_text)` frozen,
  **al massimo una per span** (`edit_for(span)`, `text_of(span)`): due testi
  sullo stesso span verrebbero scritti uno sopra l'altro.
- `DocumentModel.text_span_at(index, x, y)` apre la **sorgente** con
  `open_for_reading` (quindi anche un PDF cifrato, con la password tenuta dal
  modello) e restituisce lo span originale, mai quello già modificato: così
  un secondo intervento sullo stesso span lo riconosce e sostituisce il primo.
- `EditText(model, index, span, new_text)` ricorda cosa diceva lo span
  *prima* (niente, o una modifica precedente) e l'undo torna esattamente lì.
  Si fonde con il comando precedente sullo stesso span (`mergeWith`, id
  `0x5445`), e quando il risultato è lo stato di partenza — testo originale
  riscritto, o nessun cambiamento — si segna **obsoleto** e Qt lo toglie
  dallo stack: niente passi di undo che non cambiano nulla, e niente
  modifiche «uguali all'originale» che a ogni salvataggio riscriverebbero lo
  span e reincorporerebbero un font.
- In `save.py` l'ordine per pagina è: campi (già scritti sulla sorgente) →
  **modifiche al testo** (`_edit_text`) → **redazioni**. Una redazione sopra
  uno span modificato si porta via anche il testo nuovo (c'è il test). Se
  almeno una pagina ha modifiche, `out.subset_fonts()` prima di `save()`;
  verificato che un modulo AcroForm sulla stessa pagina sopravvive.
- Vale per `save_as`, `extract_pages` e `save_compressed`, e per il
  salvataggio sopra il file aperto.

**Limiti noti:** `find_text()` (Cancella parola) cerca nelle sorgenti, quindi
trova le parole *vecchie* di uno span modificato e non quelle nuove. Una
modifica che al salvataggio non si può più scrivere (per esempio il font di
sistema è stato disinstallato) fa fallire il salvataggio con il messaggio di
`check_edit`.

**Nell'interfaccia (`widgets/page_view.py`, `main_window.py`):**

- **Una modalità, come la Redazione, e mai insieme a lei**: un clic su una
  pagina apre l'editor *oppure* inizia un segno. `_on_text_mode_toggled` e
  `_on_redaction_toggled` spengono l'altra; Esc (`_leave_tools`) le spegne
  entrambe; aprire un altro documento le spegne.
- **Un clic, non un doppio clic**: dentro una modalità esplicita il doppio
  clic non serve. `_PageLabel.mousePressEvent` converte il punto in spazio
  pagina e chiama `PageView.begin_text_edit()`, che chiede lo span a
  `DocumentModel.text_span_at()` (sorgente, anche cifrata).
- **Un clic che non apre l'editor lo dice**, con un avviso **disegnato nella
  pagina** accanto al clic (una `QLabel` figlia della pagina, `text_notice()`,
  sparisce dopo 4 secondi o al clic successivo) e nella barra di stato
  (`_notify`). **Non un `QToolTip`**: il tooltip è una finestra separata, e
  nella prova reale su Wayland non è stato visto (nel terminale solo «This
  plugin supports grabbing the mouse only for popup windows»), quindi anche la
  seconda versione sembrava muta. Il PDF della prova era una **scansione**:
  il caso esatto che il messaggio doveva spiegare, e che è emerso solo quando
  il messaggio è diventato un widget della pagina. «Qui non c'è testo» se la
  pagina ha testo altrove, «non contiene testo modificabile» se non ne ha
  (`DocumentModel.page_has_text`: una scansione), e il motivo di
  `check_text_edit()` per uno span che non si potrà mai salvare (verticale,
  Type3) — controllato **al clic**, non dopo che l'utente ha scritto. La prima
  versione restava muta, e all'utente lo strumento sembrava rotto
  («se faccio Modifica testo non succede nulla»).
- **Tolleranza di `HIT_TOLERANCE = 3` punti** in `span_at`: il riquadro di
  uno span stringe i glifi, quindi un clic fra due righe o appena prima della
  prima lettera non trovava niente. Vince lo span che contiene il punto,
  altrimenti il più vicino entro la tolleranza.
- **L'editor (`_SpanEditor`) è figlio della `_PageLabel`**: scorre con la
  pagina senza calcoli; un ridimensionamento o uno zoom lo riposizionano
  (`_place_text_editor()` in `_relayout()`); un cambio di struttura del
  documento (elimina, sposta, unisci, undo di questi) lo chiude **senza**
  confermare, perché il suo indice di pagina può non valere più. È sempre
  orizzontale: sulle pagine ruotate di un quarto si appoggia all'angolo dello
  span invece di essere disattivato.
- **Invio conferma, Esc annulla.** Esc va *reclamato*: la finestra lo usa
  come scorciatoia per uscire dallo strumento, e una scorciatoia di finestra
  vince sul widget a fuoco finché il widget non accetta lo
  `ShortcutOverride` (`_SpanEditor.event`). Un clic altrove o l'uscita dallo
  strumento confermano (la `QLabel` non prende il fuoco, quindi il clic va
  gestito a mano in `begin_text_edit`); perdere il fuoco perché si è passati a
  un'altra finestra **no**.
- **La verifica è alla conferma**, con `DocumentModel.check_text_edit()`: lo
  stesso giudizio del salvataggio, sulla pagina sorgente. Con Invio un
  rifiuto lascia l'editor aperto **con il testo digitato**, bordo rosso e il
  motivo nella barra di stato (`text_edit_refused`); quando l'editor si
  chiude comunque (clic altrove, strumento spento) la modifica rifiutata
  viene scartata, perché non deve sembrare accettata.
- **L'anteprima si dipinge sempre** (`_paint_text_edits`), non solo nella
  modalità: la pagina deve leggersi come verrà salvata. Il pittore usa
  `view_matrix()` come trasformazione, quindi baseline, corpo e riquadro si
  disegnano con i loro numeri in spazio pagina e ruotano con il render. Lo
  sfondo è il colore del render a un angolo del riquadro (sopra gli
  ascendenti), messo in cache per span e per render perché `toImage()` costa;
  il font è quello di Qt più vicino (`_preview_font`: la famiglia dal nome
  PostScript, altrimenti lo stile dai flag). È un'anteprima: il font esatto
  lo decide il salvataggio. Nella modalità, gli span modificati hanno un
  contorno tratteggiato.

### Testo riconosciuto — OCR (`model/ocr.py`)

*Modifica → Riconosci testo…* (`Ctrl+Shift+O`) scrive **sotto** la scansione
uno strato di testo **invisibile**: la pagina si vede come prima, ma il testo
si può selezionare, cercare con Ctrl+F, copiare — e la redazione per parola
(`Ctrl+Shift+F`) finalmente lo trova.

- **Una capacità, non una modifica automatica.** Riconoscere costa (mezzo
  secondo per pagina A4 a 300 dpi, misurato) e può sbagliare, quindi si
  sceglie *cosa* e *in che lingua*: `OcrDialog` propone la pagina corrente, la
  corrente e le successive, o tutto il documento, e la lingua fra quelle
  installate — con italiano+inglese insieme quando ci sono entrambe, perché un
  documento italiano è pieno di numeri e indirizzi e le due leggono meglio di
  una sola.
- **Nello spazio pagina, come tutto il resto.** `recognise()` mette a zero il
  `/Rotate` per la durata della chiamata e lo rimette com'era, quindi i
  rettangoli tornano in spazio pagina e si confrontano con `PageItem.redactions`
  e con gli edit di testo senza convertire niente. `write_layer()` scrive in
  spazio pagina anche su una pagina con `/Rotate` acceso (misurato); il font è
  un Base-14, non incorporato, in `render_mode=3`: una scansione che diventa
  cercabile non guadagna un byte.
- **Non riscrive il testo che c'è già.** MuPDF restituisce anche le parole del
  flusso vero, quindi una pagina metà testo e metà scansione si ritroverebbe il
  testo scritto due volte — e poi letto, copiato e trovato due volte. Le parole
  il cui centro cade dentro un rettangolo di `get_text("words")` si scartano.
- **Nel thread pool, non nella coda dei render** (`OcrTask`, con
  `QProgressDialog` annullabile e mostrato **subito**: con il ritardo
  predefinito di mezzo secondo il dialogo non era ancora a schermo, quindi
  non ancora modale, e la finestra accettava Canc o un trascinamento mentre il
  task leggeva la lista delle pagine), e al termine **un solo** `beginMacro`: un
  comando `OcrPage` per pagina, così un Ctrl+Z disfa tutto il giro. Il
  salvataggio scrive lo strato **prima** degli edit di testo e delle redazioni:
  il primo cambia il testo sotto (uno strato vecchio resterebbe lì), il secondo
  deve portarsi via anche lo strato OCR che cade dentro il rettangolo.
- **Le lingue** stanno in `~/.local/share/plico/tessdata`, senza root, oppure
  dove le mette la distribuzione; `$PLICO_TESSDATA` vince su tutto. Il Flatpak
  impacchetta `ita`, `eng`, `spa`, `fra` e `deu` in `/app/share/tessdata`
  (§11). La lingua proposta è quella dell'interfaccia più l'inglese
  (`default_language()`), l'inglese da solo per una lingua che Plico non
  parla; nella tendina le lingue hanno il loro nome («Deutsch»,
  `widgets/ocr.language_name()`), che non va tradotto. Se manca la
  libreria o il dato di lingua `unavailable_reason()` lo dice in chiaro,
  invece di far fallire il lavoro a metà.
- **Dove vivono le parole.** `PageItem.ocr_words` (lista di `OcrWord`: testo e
  rettangolo in spazio pagina) è parte della pagina virtuale, quindi si annulla
  con Ctrl+Z come tutto il resto e non si può perdere per strada;
  **la ricerca le trova prima del salvataggio**: `find_text()` cerca nella
  sorgente *e* in `ocr_words` (`_ocr_hits`, senza distinguere maiuscole e
  anche dentro una parola, come `search_for`; una frase segue parole
  consecutive), perché lo strato arriva nel file solo salvando — prima la
  promessa «Cancella parola lo trova» valeva solo dopo aver salvato e
  riaperto. Ogni parola trovata è un segno *snug* grande quanto la parola;
  `DocumentModel.ocr_page()` legge la sorgente in sola lettura — come
  `find_text()` — e non tocca il modello. Chi le scrive sul PDF è solo
  `save.py` (`_write_ocr`).

### Creare un PDF da immagini (`model/images.py`)

*File → Crea da immagini…* (`Ctrl+Shift+N`) e *Unisci*, che accetta anche
immagini. Si crea da **immagini** e non da pagine bianche per scelta
dell'utente: un documento vuoto non serve a niente senza uno strumento per
scrivere in un punto vuoto, e chi scrive un testo lo esporta in PDF dal suo
editor.

- **Il modello non conosce le immagini, e resta così.** `images_to_pdf()`
  scrive **un** PDF qualsiasi, che diventa una sorgente come le altre: da lì
  ruotare, riordinare, unire e salvare non sanno che la pagina era una foto.
- **Misurato su MuPDF 1.28**, ed è il motivo per cui il modulo è corto:
  `convert_to_pdf()` rispetta la **risoluzione** (un A4 a 300 dpi esce
  595 × 842 pt) e l'**orientamento EXIF** (una foto verticale resta
  verticale); un **JPEG entra intatto**, stesso flusso `DCTDecode`, nessuna
  ricompressione; un TIFF a più pagine dà una pagina per fotogramma. **WEBP
  non è supportato** da questa build («Failed to open file … as type webp»),
  quindi non è offerto. `IMAGE_SUFFIXES` è l'unico elenco dei formati.
- **Le foto da telefono dicono 72 dpi**: 4000 px diventerebbero una pagina
  di 1,4 m. Oltre 1,25 × il lato lungo di A4, `page_size_for()` riduce
  l'immagine — mai ingrandita, mai deformata — dentro un A4 orientato come
  lei, disegnandola con `show_pdf_page`: il flusso dell'immagine resta lo
  stesso, cambia solo il posizionamento.
- **I PDF intermedi sono file veri**, perché il worker apre le sorgenti per
  percorso: stanno in una `TemporaryDirectory(prefix="plico-")` creata al
  primo uso e cancellata da `shutdown_worker()` **dopo** che il worker ha
  chiuso i suoi handle. Non vengono cancellati alla chiusura del documento:
  costano poco e non c'è niente da guadagnare a rincorrerli.
- **Un documento creato da immagini è «Senza titolo»**: `_save_target` è
  `None`, quindi `Ctrl+S` diventa «Salva con nome», con la proposta
  `_save_suggestion` accanto alla prima immagine e con il suo nome. È
  **modificato dalla nascita** (`QUndoStack.resetClean()`): sul disco c'è solo
  un temporaneo, e chiuderlo senza domanda lo perderebbe. Creare non è un
  passo di annulla. Anche *Salva compresso* propone il nome da
  `_save_target`/`_save_suggestion`, mai da `DocumentModel.path`, che qui
  punta al temporaneo.
- **Un'immagine unita** passa da `AppendDocument` con un `label`: nel menu
  Modifica si legge «Unisci «ricevuta.png»», non il nome del temporaneo.

### Firma digitale (`model/sign.py`)

Una firma non è una modifica della lista di pagine: è calcolata sui **byte** di
un file. Questo modulo scrive quindi un file nuovo — come fa la compressione —
e la finestra adotta il risultato. Firma e verifica sono di **pyHanko**, che
costruisce il CMS, il `/ByteRange` e l'aggiornamento incrementale attorno a
esso, ed è l'unica cosa nel processo che sa leggere ciò che ha prodotto.

- **`save_signed(model, out_path, request)`** (`model/save.py`) è una riga:
  `_write_atomically(..., optimize=lambda path: sign_in_place(path, request))`.
  La firma gira **dentro il temporaneo**, prima di `chmod` e `os.replace`,
  quindi una password sbagliata o un certificato illeggibile non toccano il
  file di partenza. L'ordine conta: prima si materializza il documento (campi
  compilati, testo riscritto, redazioni applicate, pagine ruotate), poi si
  firma; il contrario coprirebbe una versione diversa da quella che si vede.
- **`SignatureRequest`**: certificato PKCS#12 (`.p12`/`.pfx`), password, motivo,
  luogo, `field_name` (predefinito `"Firma"`), pagina e rettangolo del timbro.
  `Identity` è quello che si legge dal certificato *prima* di firmare
  (`common_name`, `organization`, `country`, scadenza); `Signature` è quello
  che si legge *dopo* (`intact`, `valid`, `trusted`, `covers_whole_file`,
  `changed`, `error`, più la proprietà `ok` che è la sintesi).
- **Il nome del campo si libera da solo**: `_free_field_name()` guarda i campi
  firma già presenti e, se `"Firma"` è occupato, usa `"Firma 2"`, `"Firma 3"`…
  Un campo non può contenere due firme (pyHanko rifiuta di riempirlo due
  volte), e la finestra *promette* che una seconda firma si aggiunge alla prima:
  senza questo, firmare un documento già firmato falliva.
- **La firma è invisibile o stampata.** Il timbro è contenuto della pagina:
  `stamp_text()` produce `Firmato da %(name)s`, la data e — solo se c'è — il
  motivo; `stamp_box(width, height)` dà il rettangolo in basso a destra **in
  coordinate PDF**, e su una pagina troppo piccola rimpicciolisce il riquadro
  invece di farlo uscire dal bordo.
- **Una seconda firma non riscrive il file.** `save_signed` ricostruisce il
  documento dalle pagine, e un file ricostruito è fatto di byte nuovi: la
  firma che c'era smette di coprire qualcosa (misurato: dopo la seconda, la
  prima leggeva `intact=False`, mentre la finestra prometteva che la seconda
  «si aggiunge alla prima»). Per un file firmato **senza modifiche non
  salvate** `_sign_file()` usa `sign_copy(sorgente, destinazione, richiesta)`:
  copia i byte così come sono e pyHanko accoda la firma in un aggiornamento
  incrementale. Con modifiche non salvate la sola strada è riscrivere, e la
  domanda lo dice («la firma che porta ora verrà tolta»). Il test di
  `sign_in_place` chiamato due volte non se ne accorgeva: la finestra non passa
  di lì.
- **Un file ricostruito non porta firme che non può onorare.** `insert_pdf()`
  copia il campo della firma vecchia insieme alla pagina, e `/SigFlags` resta
  a 3: misurato, un semplice salvataggio di un documento firmato usciva con un
  campo il cui digest non corrisponde a niente, che riaperto dava il titolo
  «— firmato» e alla verifica una firma **rotta** — l'aspetto di una
  falsificazione, per un salvataggio qualsiasi. `_drop_old_signatures()` (in
  `_write_pdf`, quindi per ogni salvataggio, estrazione, compressione e firma
  ricostruita) toglie i campi firma **riempiti** (un `/V` sul widget o sul
  campo padre) e rimette `/SigFlags` a 0; un campo firma **vuoto**, il posto
  lasciato per una firma futura, è contenuto del modulo e resta. Anche il
  riquadro stampato se ne va: è l'aspetto del widget.
- **La finestra adotta il file firmato** (`MainWindow._sign_file()`): dopo la
  firma il documento è il file appena scritto. Continuare a lavorare sulla lista
  di pagine che l'ha prodotto significherebbe perdere la firma al primo
  salvataggio. Il titolo prende «— firmato», e `_signed_on_disk` (rinfrescato
  all'apertura, alla chiusura e a ogni salvataggio) è quello che fa chiedere
  conferma prima di un salvataggio che riscriverebbe il file senza firma.
  `is_signed()` guarda il **bit 1** di `/SigFlags` (*SignaturesExist*), non il
  numero: `get_sigflags()` dà `-1` senza modulo e `0` per un modulo mai
  firmato, e con `>= 0` ogni modulo con `/SigFlags 0` risultava firmato.
  Attenzione al `-1`: in Python `-1 & 1` vale 1, quindi va escluso prima.
- **Non decide di chi fidarsi**: `read_signatures(path, roots=[...])` accetta i
  certificati che l'utente ha scelto (PEM), e senza di essi una firma integra
  resta «valida ma non attendibile». I percorsi scelti si ricordano in
  `QSettings` sotto `firma/radici`.
- **Verifica**: *File → Verifica le firme…* legge il file **su disco** (le
  modifiche non salvate non sono nei byte) e distingue quattro casi: integra e
  attendibile, integra ma di un certificato sconosciuto (ambra, non rosso),
  integra ma su un documento modificato dopo la firma, e firma rotta o
  certificato scaduto. `_verdict()` guarda **prima** `intact`: una firma
  rotta su un file che ha anche revisioni successive ha `changed` vero, e con
  l'ordine vecchio veniva presentata in ambra come «La firma è integra, ma…». `MainWindow._verify_signatures()` avvisa se ci sono
  modifiche non salvate prima di dare un verdetto.
- **`pyhanko` e `pyhanko_certvalidator` sono messi a tacere**:
  `logging.getLogger("pyhanko").setLevel(logging.CRITICAL)` in testa al modulo.
  Un certificato non attendibile — cioè il caso **normale** — e una modifica
  dopo la firma sono eventi che la finestra racconta in una frase, non
  traceback da stampare su stderr.

---

## 9. Ambiente di sviluppo

Il progetto vive in `plico/` con un virtualenv in `plico/.venv`.

```bash
cd plico
python3 -m venv .venv --system-site-packages   # solo se manca
.venv/bin/pip install -e ".[dev]"

# test: NON serve un display
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest

# lint e tipi
.venv/bin/ruff check src/ tests/
.venv/bin/mypy src/plico

# avvio
.venv/bin/plico                      # oppure: .venv/bin/python -m plico.app
```

Note sull'ambiente in cui il progetto è stato sviluppato (Debian unstable):

- il Python di sistema è 3.14.8; PySide6 6.11.2 arriva dai pacchetti di
  sistema (`/usr/lib/python3/dist-packages`), PyMuPDF è installato nel venv;
- `pip install --user` **non funziona**: la site-packages utente è in sola
  lettura (`OSError: [Errno 30]`). Da qui il venv con `--system-site-packages`;
- **`import fitz` è un alias deprecato**: dalla 1.24.3 (maggio 2024) il modulo
  si chiama `pymupdf`. Il progetto ha migrato tutto insieme (11 file) e il
  pavimento di versione in `pyproject.toml` è `pymupdf>=1.24.3`. Non mescolare
  i due import. Attenzione: con `pymupdf` mypy vede un pacchetto con `py.typed`
  e stub generati che **non elencano** le costanti dei tipi di widget
  (`PDF_WIDGET_TYPE_*`, definite a runtime in `pymupdf/mupdf.py`), quindi
  `model/forms.py` porta sei `# type: ignore[attr-defined]` con il perché
  scritto sopra;
- gli script di validazione che servono un pacchetto (per esempio
  `jsonschema`) vanno creati e usati **nella stessa invocazione**: `/tmp` non
  sopravvive fra un comando e l'altro.

Su una macchina **senza desktop** (un container, la CI) servono altre cose,
tutte scoperte perché qualcosa saltava o falliva in silenzio:

- **le librerie di sistema di Qt**: senza `libEGL.so.1` pytest non parte
  nemmeno (`INTERNALERROR … ImportError: libEGL.so.1`, da `pytest-qt`). Su
  Debian/Ubuntu: `libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3`;
- **Tesseract e almeno una lingua** (`tesseract-ocr tesseract-ocr-ita`), o i
  test dell'OCR vengono saltati;
- **`pylupdate6`**, che non viene con PySide6 ma con PyQt6: `pip install
  PyQt6` nel venv basta, serve solo lo strumento. `pyside6-lrelease` arriva
  invece con PySide6 da pip. Entrambi vanno trovati nel `PATH`, quindi la
  `bin/` del venv va messa lì (`PATH=.venv/bin:$PATH`), non basta lanciare
  `.venv/bin/python -m pytest`;
- `fc-match` (fontconfig) per i font di sistema della modifica del testo:
  senza, si scende ai sosia Base-14.

---

## 10. Insidie già pagate (leggere prima di scrivere codice)

### PySide6 / Qt6

- `QUndoStack`, `QUndoCommand` e **`QAction` stanno in `QtGui`**, non in
  `QtWidgets` (`QUndoView` invece è in `QtWidgets`). L'import sbagliato dà un
  `ImportError` netto, ma si perde tempo a cercarlo.
- In Qt6 gli enum vanno **scoped**: `Qt.ItemDataRole.UserRole`,
  `QListView.Movement.Static`, `Qt.DockWidgetArea.LeftDockWidgetArea`,
  `QSizePolicy.Policy.Preferred`, `QImage.Format.Format_RGB888`. La forma non
  scoped è deprecata ed è ciò che rompe gli stub di PySide6.
- `QListView.current_index()` **non esiste**: è `currentIndex()`. Un
  `QListView.Movement.Vertical` non esiste: gli unici valori sono
  `Static`, `Snap`, `Free`.
- `QVariant` non è importabile da `PySide6.QtCore`: un modello che non ha un
  valore deve restituire `None`.
- `ensureWidgetVisible` è un metodo di **`QScrollArea`**, non di `QLabel`.
- `QWidget.setBackgroundRole()` vuole un `ColorRole`, non un intero.
- `QLabel.pixmap()` in Qt6 restituisce una `QPixmap` per valore: `is not None`
  è sempre vero, e non significa nulla. Usare `isNull()`.
- `QKeySequence("Canc")` — il nome italiano del tasto Delete — si analizza in
  una sequenza **vuota**: `isEmpty()` è `False` ma `toString()` è `""`, quindi
  il tasto non fa niente. Usare `"Del"`. C'è un test che verifica che ogni
  azione abbia una scorciatoia non vuota: è la regressione per questa classe
  di bug.
- `beginResetModel()` / `endResetModel()` **azzerano `currentIndex`**: dopo
  ogni delete o riordino la selezione della barra moriva, e `Ctrl+R` non faceva
  più niente finché non si ricliccava. Se il modello si resetta, la vista deve
  ripristinare la selezione da sé (`ThumbnailBar._on_doc_changed`).
- Una `OrderedDict` usata come LRU non è una LRU finché **anche `get()`** non
  sposta la voce in testa: le righe intorno al viewport sono rilette a ogni
  repaint, quindi con il solo `__getitem__` venivano sfrattate proprio le voci
  più usate. `ThumbnailCache` sposta la voce in testa in lettura e in scrittura.
- Il **nome di un `QUndoCommand`** va dato *prima* di `super().__init__()`, cioè
  quando la metà `QObject` del comando non esiste ancora: `self.tr()` non è
  disponibile. Si usa `QCoreApplication.translate("<NomeClasse>", "…")` — anche
  la forma che `lupdate` si aspetta — e si passa la stringa già formattata al
  costruttore.

### Thread e distruzione degli oggetti

- **Mai dare un parent widget a un `QThread`.** `~QWidget` lo distruggerebbe
  mentre gira, e Qt aborta il processo con
  `QThread: Destroyed while thread '' is still running`. Il thread va creato
  senza parent, e il worker senza parent perché `moveToThread` sia valido.
- Un `QObject` con affinity su un thread morto, distrutto dal thread GUI, è
  un'altra via allo stesso abort. Da qui `thread.finished.connect(worker.deleteLater)`.
- `QMessageBox` è **modale**: in un test offscreen blocca la suite per sempre.
  Monkeypatchare il metodo (per esempio `QMessageBox.warning`) invece di
  sperare.
- Non usare `pkill -f "pytest"` per sbloccare un test appeso: il pattern
  corrisponde alla command line della shell che lo esegue e la uccide.
- **PyMuPDF non promette di funzionare da più thread**, e Plico lo usa da tre:
  il worker di rendering, il pool (compressione, OCR) e il thread
  dell'interfaccia (`text_span_at`, `find_text`, `words_on`, i salvataggi).
  Le chiamate si sovrappongono davvero: **misurato**, durante un
  `get_pixmap` di 0,8 s in un altro thread il thread principale ha continuato
  a girare (pausa massima 0,02 s), quindi il binding rilascia il GIL e non è
  il GIL a serializzare MuPDF. Regge perché ogni thread apre **handle suoi**
  (`open_for_reading` a ogni lettura, il worker con i suoi) e nessun
  `Document` o `Page` passa da un thread all'altro: è la regola da non
  rompere. Un crash raro e non riproducibile durante un render va cercato
  prima qui.
- Un **callable Python** (`lambda`, `list.append`) connesso a un segnale di un
  `QObject` che vive in un **altro thread** viene consegnato *accodato*, non
  diretto: uno spy messo nel test sul thread GUI non viene chiamato in modo
  sincrono e sembra che il segnale non sia mai stato emesso. È esattamente ciò
  che è successo spiando `worker.render_requested` mentre `_pending` cresceva
  correttamente. In quel caso asserire sullo **stato** (`_pending`), non sul
  segnale.
- **`PySide6.QtTest` non è disponibile** in questa installazione: un test che
  simula il mouse deve costruire `QMouseEvent` a mano. La forma da usare è
  quella a **6 argomenti con la posizione globale** — quella a 5 è segnalata
  come deprecata da Qt 6 e sporca l'output di pytest:
  `QMouseEvent(tipo, punto, punto, Qt.MouseButton.LeftButton, …)`; gli eventi si
  consegnano poi a `label.mousePressEvent/mouseMoveEvent/mouseReleaseEvent`.

### Geometria e visibilità

- La `geometry()` di un widget è affidabile **solo dopo** un giro di layout di
  Qt. In una finestra mai mostrata tutte le etichette riportano lo stesso
  rettangolo, e un test di visibilità basato su `intersects()` conclude che
  ogni pagina è visibile. Per questo `PageView` registra da sé `y_px` e
  `height_px` in `_relayout()` e calcola la visibilità in modo deterministico.
  (Con una finestra *mostrata* il codice vecchio funzionava: è il motivo per
  cui il bug è rimasto nascosto.)
- La **cache delle pagine conta i byte**: `PageView._cache_put` deve togliere i
  byte della pixmap che sta sostituendo (`self._cache.pop(key, None)`) *prima*
  di aggiungere i nuovi, altrimenti il budget di 64 MB sfratta più del dovuto.
  Il caso è raro — la stessa key si ricalcola solo quando cambiano zoom o dpr —
  ma il conto deve tornare, non «quasi tornare».

### Drag & drop

- La posizione dell'indicatore va letta da
  `event.dropIndicatorPosition()` (`QtWidgets.QAbstractItemView.DropIndicatorPosition`,
  `AboveItem = 1`, `BelowItem = 2`): `indexAt(center)` da solo non dice se il
  rilascio è sopra o sotto l'elemento.
- L'indice di destinazione è nella lista **già accorciata**: `MovePage` fa
  `pop(from)` e poi `insert(to)`, quindi per un elemento raccolto sopra e
  rilasciato sotto la riga *k* la destinazione è `k - 1`, non `k`. La logica
  sta in `ThumbnailBar.drop_target_row(from_row, target_row, below)` ed è
  testata in entrambe le direzioni contro `MovePage` stesso.

### Modello

- **Niente liste parallele a `pages`.** `page_sizes` era una seconda lista che
  `DeletePage`/`MovePage` non aggiornavano: dopo un delete restava a 3 mentre
  `pages` era a 2. La correzione non è stata «ricordarsi di aggiornare anche
  l'altra lista», ma togliere la seconda lista: la dimensione orientata vive
  su `PageItem` (`width_pt`/`height_pt`) e `DocumentModel.page_sizes` è una
  **property derivata**. Così l'allineamento è una proprietà della struttura
  invece che una disciplina da mantenere. Vale per qualsiasi dato per-pagina
  che si voglia aggiungere in futuro.
- **Salvare sopra il file aperto invalida il modello.** Dopo `os.replace()` il
  file è il documento *materializzato*: pagine eliminate sparite, indici
  rinumerati, rotazione utente scritta nella `/Rotate`, redazioni bruciate. I
  `PageItem` però descrivevano ancora il file vecchio, quindi continuare a
  lavorare rendeva le pagine sbagliate, ruotava due volte e **il salvataggio
  successivo perdeva pagine in silenzio** (3 pagine, elimina la prima, ruota,
  salva sopra, salva altrove: usciva solo «PAGINA 3», senza rotazione).
  La correzione: dopo `save_as` o `save_compressed` sopra una sorgente,
  `MainWindow._adopt_saved_file()` **riapre il file salvato** (che *è* il
  documento), svuota cache e undo stack (niente può annullare ciò che è su
  disco) e lo dice nella barra di stato. Le funzioni di `save.py` non lo
  fanno da sole: `save_compressed` gira sul thread pool e non può toccare il
  modello. Chi usa l'API direttamente deve riaprire da sé. Test:
  `test_saving_over_the_open_file_then_saving_again_keeps_every_page`
  (anche con `/Rotate` di partenza) e
  `test_compressing_over_the_open_file_reopens_the_document`.
- Un `QUndoCommand` che al `redo` non ricalcola lo stato è un comando rotto:
  `DeletePage.redo` faceva `insert` + `pop` sullo stesso indice (un no-op), per
  cui *redo dopo undo non cancellava nulla*. Il `redo` deve funzionare anche
  quando l'oggetto è già stato costruito e annullato una volta.

### PyMuPDF

- **Un radiobutton non si crea, ma si scrive.** `page.add_widget()` con
  `PDF_WIDGET_TYPE_RADIOBUTTON` solleva `ValueError: bad xref` **sempre** —
  con il valore impostato, senza valore e con `field_value = True`: il difetto
  e` nella creazione del widget, non nel valore. Nei test il gruppo si scrive
  a mano con pikepdf (`tests/radio_forms.py`), che è anche la forma con cui lo
  scrivono gli altri programmi. Scriverne uno, invece, PyMuPDF lo sa fare,
  **purché la pagina resti viva**: legando `page = doc[0]` a una variabile
  locale, `widget.field_value = "secondo"` + `update()` scrive `/V` sul campo
  padre e `/AS /secondo` sul bottone. Con la pagina temporanea muore con
  `ReferenceError: weakly-referenced object no longer exists` (dentro
  `Widget._checker`, che fa `doc = self.parent.parent`), e questa è la ragione
  per cui `forms.write_fields()` prende una `Page`, non un documento;
- **MuPDF vuole i nomi dei campi come nomi**: PyMuPDF scriveva il valore del
  gruppo radio come **stringa** (`/V (secondo)`), che è fuori specifica e che
  i lettori seri non leggono. Per questo `forms._name_the_choice()` riscrive a
  basso livello `xref_set_key(parent, "V", "/secondo")` — e la rilettura con
  `field_value` tornava `'Off'` proprio perché l'`/AS` non era stato aggiornato;
- **Su un handle bloccato la prima lettura è definitiva.** Se una pagina viene
  toccata *prima* di autenticare (`doc[0]`, `get_text()`), l'handle resta
  incapace di decifrare: un `authenticate()` successivo riporta
  `is_encrypted == False` e `permissions == -4`, ma `get_text()` torna `''` e
  MuPDF stampa su stderr `syntax error in content stream` e
  `format error: aes padding out of range: 233`. Per questo c'è **un solo**
  punto di apertura in lettura, `open_for_reading()`, che autentica prima di
  qualunque lettura. Verificato insieme a questo: dopo un `authenticate()`
  riuscito `needs_pass` **resta `1`** (dice «il file è cifrato», non «è ancora
  chiuso» — fidarsi di quel numero per capire se si è entrati è sbagliato), un
  file con password utente vuota si apre senza chiedere niente
  (`needs_pass == 0`), una password proprietario vale come utente, e RC4-128 e
  AES-256 si comportano allo stesso modo;
- Salvare **sopra il file aperto** richiede il salvataggio incrementale:
  `ValueError: save to original must be incremental`. Il progetto evita del
  tutto il problema scrivendo su un temporaneo e facendo `os.replace()` — e da
  lì **ogni** scrittura passa dal temporaneo, «Salva con nome» sopra un file
  esistente compreso: la scorciatoia diretta era un buco (un errore a metà
  troncava la destinazione) e perdeva anche i permessi, perché PyMuPDF ricrea
  il file con l'umask (`0o640` tornava `0o664`).
- **Una redazione cancella ogni glifo il cui riquadro la tocca**, e il
  riquadro di un glifo va dall'ascendente al discendente: con l'interlinea
  singola (1,0 – 1,2) entra nelle righe sopra e sotto. Il riquadro di uno span
  o di una parola non è quindi un rettangolo da redigere così com'è: la
  modifica del testo usa una fascia attorno alla baseline, i segni fatti di
  parole una fascia a metà riga (§8). E `page.annots()` **non elenca i
  widget**: un campo del modulo sotto una redazione va tolto a parte.
- `pymupdf.Matrix` non ha attributi `x0` / `xy`: per le rotazioni si usa
  `prerotate()`.
- `pymupdf.Pixmap(csRGB, w, h, bytes)` **non è una firma valida** in 1.28.
  Peggio: l'eccezione che solleva incorpora nel messaggio L'INTERO buffer di
  pixel, quindi un `traceback` stampato diventa qualche megabyte di «log»
  binario. Per costruire un'immagine di prova si usa
  `QImage(campioni, w, h, w * 3, QImage.Format.Format_RGB888).save(path, "JPEG", 95)`.
- `clean=True` riscrive i content stream: è la vincita della compressione. Sui
  form è **verificato**: i campi e i loro valori sopravvivono a `clean=True`.
- **Un widget tiene un riferimento debole alla sua pagina.** `page.widgets()`
  su una pagina temporanea (`doc[0].widgets()`) funziona in lettura, ma il
  primo `update()` dopo fallisce con `RuntimeError: Annot is not bound to a
  page` (e `widget.parent` arriva a `ReferenceError`). La pagina va tenuta in
  una variabile locale: in `document.py` il ciclo è esplicito proprio per
  questo, e `save.py` usa l'oggetto vivo di `out[...]`.
- **Svuotare un campo non è `field_value = ""`.** Misurato: così `/V` resta al
  valore vecchio; forzare `/V` a `()` da solo svuota il valore ma lascia
  l'**aspetto** vecchio *disegnato* sulla pagina (inchiostro 793 su 793). La
  sola sequenza che svuota e ridipinge è `field_value = ""` → `/V` a `()` →
  `update()` (inchiostro 0). Per questo `write_fields()` chiama
  `_clear_value()`, che risale anche a `/Parent`.
- **`insert_pdf()` rinomina i campi omonimi**, e copiare due volte dalla
  stessa sorgente perde i widget figli. Se due pagine portano un widget con lo
  stesso nome, dopo la copia il secondo si chiama `nome [12]` (misurato:
  stesso xref nella sorgente, nomi diversi nel file costruito), e
  `write_fields(page, {"nome": …})` sulla pagina già copiata restituisce `0`.
  Per questo `save.py` scrive i valori **sulla sorgente in memoria**
  (`_fill_source_fields`) prima di copiare, e `assemble()` copia ogni sorgente
  in una chiamata sola (§8). Collegate: `Document.select()` toglie l'AcroForm,
  `delete_page()` lascia i campi della pagina tolta in `/Fields`, e
  `xref_set_key(catalogo, "AcroForm/Fields", …)` attraverso un AcroForm
  **indiretto** scrive la stringa `fitz: replace me!` invece dell'array:
  l'AcroForm va risolto prima (`assemble.acroform_key()`).
- **`get_textpage_ocr()` vuole il `tessdata` esplicito.** Senza, non cerca da
  solo: fallisce con `RuntimeError: No tessdata specified and Tesseract is not
  installed`, anche quando la libreria c'è. E `tessdata=` non basta alla
  libreria: PyMuPDF la carica con `ctypes`, quindi in una sandbox la `.so` deve
  stare nel `LD_LIBRARY_PATH` (nel Flatpak: `/app/lib`, vedi §11).
- **L'OCR legge lo spazio della pagina com'è adesso.** `get_textpage_ocr()`
  lavora sulla pagina con il `/Rotate` in vigore, quindi i rettangoli escono
  ruotati rispetto allo spazio pagina: `recognise()` azzera la rotazione per la
  chiamata e la rimette nel `finally` (la pagina è quella del documento del
  worker, non una copia — lasciarla ruotata cambierebbe il documento sotto i
  piedi di chi la usa). `insert_text()`, invece, scrive **sempre** in spazio
  pagina, anche con `/Rotate` acceso (misurato: `render_mode=3` finisce dove
  deve), quindi lo strato invisibile non richiede conversioni.
- **MuPDF restituisce anche le parole già presenti nel flusso.** Su una pagina
  metà testo e metà scansione, `get_textpage_ocr()` include le parole del testo
  vero: scriverle tutte significa averle due volte (lette due volte, copiate
  due volte, trovate due volte). `recognise()` scarta quelle il cui centro cade
  dentro un rettangolo di `get_text("words")`.

### Test

- `QT_QPA_PLATFORM=offscreen` è obbligatorio: senza display i test non
  partono.
- **L'applicazione Qt è una sola per tutta la sessione di pytest**, e la crea
  il primo modulo che ne chiede una. Un fixture che crea una
  `QCoreApplication` in un file che gira *prima* di `test_integration.py`
  (l'ordine è alfabetico) fa abortire l'intera suite con un core dump:
  `QMainWindow` trova un'applicazione senza widget («Must construct a
  QApplication before a QWidget»). È successo con `test_edit_text.py`. Nei
  file nuovi usare `QApplication.instance() or QApplication([])`.
- Il fixture `windows` di `tests/test_integration.py` chiude **sempre** ogni
  `MainWindow` (`shutdown_worker()` + `deleteLater()` + `processEvents()`),
  così un'asserzione fallita non può lasciare un thread in corsa e far
  abortire pytest senza mostrare il fallimento vero. Se si aggiungono test
  con finestre, usare quel fixture.
- Il rendering è asincrono: serve `_pump(seconds)`, che cicla
  `processEvents()` + `sleep`, altrimenti si asserisce su una pixmap che non
  è ancora arrivata.
- I test non devono toccare la configurazione reale dell'utente: quello su
  `QSettings` monkeypatcha `MainWindow._settings` su un file INI in `tmp_path`.
- `restoreGeometry` viene **clampato** allo schermo della piattaforma
  offscreen (800 px): asserire la dimensione in pixel è sbagliato, va
  confrontato il round-trip.

### pyHanko / firma

- **Il riquadro del timbro è in coordinate PDF (`/Rect`, origine in basso a
  sinistra), ma `widget.rect` di MuPDF è in coordinate con l'origine in alto**:
  lo stesso oggetto si legge `(359, 36, 559, 106)` in `stamp_box()` e
  `Rect(359.0, 736.0, 559.0, 806.0)` rileggendolo (842 − 106 = 736). Sbagliarlo
  mette il timbro in cima alla pagina, e l'errore si vede solo aprendo il file
  in un altro lettore.
- **Un campo firma non si riempie due volte.** Firmare un documento già firmato
  è legittimo — e la finestra lo promette — ma riusare il nome `"Firma"` fa
  fallire tutto con `SigningError: Signature field with name Firma appears to be
  filled already`. Da qui `_free_field_name()`: il secondo campo diventa
  `"Firma 2"` (trovato dalla sonda dentro il Flatpak, non dai test: serviva un
  documento *già firmato* come sorgente).
- **`SimpleSigner.load_pkcs12()` vuole un percorso**, non un `BytesIO`
  (`TypeError: expected str, bytes or os.PathLike object, not BytesIO`), e con
  la password sbagliata solleva `ValueError` **stampando anche un traceback su
  stderr**. Perciò il firmatario si costruisce a mano da
  `cryptography` → `asn1crypto` (`SimpleSigner(signing_cert=...,
  signing_key=..., cert_registry=SimpleCertificateStore())`): gli argomenti
  `cert_registry=None` e `other_certs=` non esistono, e la catena va registrata
  nello store.
- **Le radici fidate per `ValidationContext` devono essere certificati
  `asn1crypto`** (`asn1crypto.x509.Certificate.load(der)`), non `cryptography`:
  altrimenti `AttributeError: 'Name' object has no attribute 'hashable'` in
  `_register_root`.
- **`SigSeedSubFilter.PADES`** (non `ETSI_CADES_DETACHED`), il `SigFieldSpec`
  va nel **costruttore** di `PdfSigner` (`new_field_spec=`), e `sign_pdf()`
  restituisce il flusso di output. `TextBoxStyle` sta in
  `pyhanko.pdf_utils.text`, `TextStampStyle` in `pyhanko.stamp`.
- **La lettura di una firma modifica le classi di errore**: `intact`/`valid`/
  `trusted` restano veri anche su un documento modificato dopo la firma, quello
  che cambia è `covers_whole_file` (da `ENTIRE_FILE` a `ENTIRE_REVISION`),
  `changed` e `ok`. Un documento toccato **non** rende falsa la firma: la rende
  vecchia, e va detto così.

### Attenzione

- `build/`, `build-dir/` e `.flatpak-builder/` (residui di `pip install` e
  della build Flatpak) sono stati **rimossi**: contenevano copie dei sorgenti e
  una ricerca globale poteva far modificare la copia invece dell'originale. La
  build Flatpak ora tiene la cache **fuori dal progetto**, con
  `--state-dir=$HOME/.cache/plico-flatpak/state` e la build directory in
  `$HOME/.cache/plico-flatpak/build`.

---

## 11. Flatpak

I file stanno in `flatpak/`: `io.github.gradia64.plico.json` (manifest),
`python3-pymupdf.json` e `python3-pikepdf.json` (i moduli delle due
dipendenze, con wheel e `sha256` fissati), `.desktop`, `.metainfo.xml`,
`.svg`. Gli stessi file sono installati anche da `pip install .` tramite
`[tool.setuptools.data-files]` in `pyproject.toml`, così c'è una sola fonte
di verità.

Scelte non ovvie (documentate anche nel README):

- **L'id è `io.github.gradia64.plico`, tutto minuscolo**: AppStream lo chiede
  (`cid-contains-uppercase-letter`) e dopo la prima pubblicazione su Flathub un
  id non si cambia più, quindi è stato adeguato prima. È il nome del `.desktop`,
  dell'icona, del manifest e del componente AppStream, e `app.APP_ID` lo passa a
  `QApplication.setDesktopFileName()`: su Wayland è così che la finestra viene
  collegata al suo lanciatore (senza, il compositore vedeva «plico» e il dock
  mostrava un'icona generica). `test_the_app_id_names_every_desktop_file`
  controlla che i cinque posti dicano la stessa cosa. Gli URL del repository
  restano `github.com/gradia64/Plico`: la verifica di Flathub per gli id
  `io.github` confronta il nome del repository senza badare alle maiuscole. Chi
  aveva installato una build con l'id vecchio (`…Plico`) ha ora **due app
  diverse**: quella vecchia va disinstallata a mano
  (`flatpak uninstall io.github.gradia64.Plico`).

- **`Exec=plico %F`, non `%U`**: `%U` chiede URL, e GIO li passa davvero
  (`file:///…/a%20b.pdf`), che `pymupdf.open` non apre. Per chi li passa lo
  stesso (script, altri launcher) `app.local_path()` converte gli URL
  `file:` in percorsi prima di aprirli. Un primo argomento che è
  un'**immagine** passa da *Crea da immagini* (`app.open_arguments()`): aperta
  così com'è, MuPDF la legge come documento immagine e il salvataggio fallisce
  con `source or target not a PDF`.

- **`base: io.qt.PySide.BaseApp`** e `pip3 install --no-deps`: PySide6 arriva
  già compilato dal runtime, allineato al Qt di `org.kde.Platform`. Il bundle
  non duplica Qt e pip non prova nemmeno a scaricare PySide6 da PyPI.
- **PyMuPDF da wheel `manylinux` `cp310-abi3`** e non da sorgente: compilare
  MuPDF dentro il manifest vorrebbe dire `swig` e minuti di build.
- **pikepdf da wheel `cp313` con `--no-deps`**: pikepdf dichiara `Pillow`,
  `lxml` e `packaging`, ma `open()` e `save()` non li importano — verificato
  bloccando `PIL` e `lxml` con `sys.meta_path` — e la BaseApp ha già
  `packaging`. La wheel va scelta per l'interprete della BaseApp (3.13), non
  per quello del venv. Se un giorno servissero le API sulle immagini
  (`pikepdf.PdfImage`) o il supporto PDF/A, andrebbero aggiunte anche le
  loro wheel.
- **`build-options.env` è un OGGETTO, non una lista**:
  `{"BASEAPP_REMOVE_WEBENGINE": "1", ...}`. Il README della BaseApp mostra la
  forma a lista, ma il parser e lo schema ufficiale vogliono l'oggetto. È
  l'unico errore vero che il controllo di conformità ha trovato.
- **Tesseract si compila qui** (`leptonica 1.84.1`, `tesseract 5.4.1`, poi un
  modulo `simple` che copia `ita`, `eng`, `spa`, `fra` e `deu` (`.traineddata`)
  di `tessdata_fast`, tutti dallo stesso commit, in `/app/share/tessdata`): su Flathub non esiste
  un'estensione Tesseract e la runtime non lo porta, e senza la libreria
  `get_textpage_ocr()` fallisce anche avendo i dati di lingua. Tre trappole
  pagate: con CMake 4 un `cmake_minimum_required` vecchio **ferma** la
  configurazione (`» Compatibility with CMake < 3.5 has been removed`,
  risolto con `-DCMAKE_POLICY_VERSION_MINIMUM=3.5`), leptonica **rifiuta** di
  essere configurata dentro l'albero dei sorgenti (quindi i due moduli hanno
  `"builddir": true`, altrimenti `CMake generation is not possible within the
  source directory`), e `-DCMAKE_INSTALL_LIBDIR=lib` serve perché PyMuPDF
  carica `libtesseract.so` con `ctypes` e deve trovarla in `/app/lib`.
- **pyHanko entra da wheel, in un modulo solo** (`python3-pyhanko.json`):
  venti file fra `pyhanko`, `cryptography`, `asn1crypto`, `aiohttp`, `lxml` e
  il resto delle dipendenze, tutti pure Python o con wheel `manylinux` per il
  Python 3.13 della BaseApp, quindi una sola riga
  `pip3 install --no-index --prefix=/app --no-deps *.whl`. Le wheel si
  scaricano con `pip download --only-binary=:all: --python-version 3.13
  --implementation cp --abi cp313 --abi abi3 --abi none --platform
  manylinux_2_28_x86_64 --platform manylinux2014_x86_64` (`cffi` non ha un tag
  `manylinux_2_28`: senza il secondo `--platform` la risoluzione fallisce con
  `ResolutionImpossible`), e gli URL e gli `sha256` si prendono dall'API JSON di
  PyPI. La firma è la parte del programma in cui «più o meno quella versione»
  non è una risposta accettabile.

- **I font web dell'host sono esclusi** (`flatpak/fontconfig-local.conf`,
  installato come `/app/etc/fonts/local.conf`, che il `fonts.conf` del runtime
  include). Nella sandbox fontconfig vede anche `/run/host/fonts`, compresi i
  `.woff2` che Debian mette in `/usr/share/fonts/woff` (`fonts-roboto-slab`,
  `fonts-font-awesome`). Quando Qt cerca un glifo di riserva, fontconfig può
  sceglierne uno, e con il runtime KDE 6.11 quella scelta va in **SIGSEGV
  dentro libfontconfig**. Il primo a pagarlo è stato il dialogo della firma: il
  pallino della password (U+25CF) chiudeva l'app appena si scriveva. Sull'host
  lo stesso glifo va a DejaVu e non succede niente, e con
  `QT_QPA_PLATFORM=offscreen` non si riproduce: serve Wayland, dentro il
  Flatpak. Un `QLineEdit` in modalità password basta a riprodurlo, senza
  Plico.

- **Niente `--filesystem=home`**: l'unico accesso ai file è il portal. Qt
  dentro Flatpak apre da solo i dialoghi di `org.freedesktop.portal.FileChooser`
  e Plico riceve percorsi `/run/user/<uid>/doc/<id>/nome.pdf`. Verificato con
  `flatpak document-export`: `mkstemp` nella cartella del documento, `chmod`
  e `os.replace` funzionano lì, quindi il salvataggio atomico (`save.py`,
  `optimize.py`, `sign.py`) non è cambiato. Cambiano due cose: i percorsi
  *proposti* nei dialoghi passano da `_host_path()` (`main_window.py`, legge
  l'xattr `user.document-portal.host-path`, altrimenti restituisce il percorso
  così com'è), perché il dialogo gira fuori dalla sandbox e una cartella
  `/run/user/.../doc/<id>` non dice niente all'utente. Il `.desktop` con
  `Exec=plico %F` fa sì che `--file-forwarding` esporti nel portal il file del
  doppio clic. I dati utente di Tesseract stanno in `$XDG_DATA_HOME`, che nel
  Flatpak è `~/.var/app/io.github.gradia64.plico/data`.

- **Le traduzioni si compilano nella build** (`lrelease`): il modulo `plico`
  installa i `.ts` con il pacchetto e poi, con
  `for ts in src/plico/translations/*.ts; do lrelease "$ts" -qm
  /app/share/plico/translations/$(basename "$ts" .ts).qm; done`, produce i
  `.qm` in `/app/share/plico/translations`. `lrelease` esiste **solo nell'SDK**
  (in `org.kde.Sdk` c'è `/usr/bin/lrelease`, nella runtime no) e i `.qm` sono
  gli unici file di cui l'applicazione ha bisogno a runtime: compilare qui
  vuol dire anche non spedire il compilatore. Il `.ts` è invece la sorgente del
  traduttore e sta nel repository (`src/plico/translations/plico_*.ts`), con
  `[tool.setuptools.package-data]` che lo fa viaggiare anche con
  `pip install .`.

Costruire, provare, e verificare il manifest:

```bash
# 1. il manifest è conforme allo schema ufficiale flatpak-builder
python3 -m venv /tmp/lintenv && /tmp/lintenv/bin/pip install -q jsonschema
curl -s -o /tmp/schema.json \
    https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json
/tmp/lintenv/bin/python -c "
import json, jsonschema
jsonschema.Draft7Validator(json.load(open('/tmp/schema.json'))).validate(
    json.load(open('flatpak/io.github.gradia64.plico.json')))" && echo "manifest OK"

# 2. metadati AppStream e launcher
appstreamcli validate --no-net flatpak/io.github.gradia64.plico.metainfo.xml
desktop-file-validate flatpak/io.github.gradia64.plico.desktop

# 3. build e installazione
flatpak remote-add --user --if-not-exists flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.flatpak.Builder//stable \
    org.kde.Sdk//6.11 io.qt.PySide.BaseApp//6.11

flatpak run org.flatpak.Builder --force-clean --user --install \
    --install-deps-from=flathub \
    build-dir flatpak/io.github.gradia64.plico.json

flatpak run io.github.gradia64.plico
```

Verifiche già eseguite con esito positivo: schema `flatpak-builder`
conforme, `appstreamcli validate` valido, `desktop-file-validate` pulito,
build riuscita e app avviata dentro il sandbox (finestra "Plico", documento
aperto, thread chiuso).

**Nota d'ambiente:** questo sandbox rende `~/.var/app` in sola lettura, quindi
build e `flatpak run` richiedono accesso completo; `flatpak-builder-lint` (quello
che gira sulla CI di Flathub) non è installabile da PyPI e senza un container
runtime non si può eseguire.

**Screenshot.** `tools/screenshots.py` costruisce due documenti d'esempio,
apre la `MainWindow` vera senza schermo nella lingua chiesta (inglese di
default, la lingua dello store) e salva quattro scene in `flatpak/screenshots/`
(1280×800), che il metainfo elenca con didascalie nelle cinque lingue. Due cose
servono all'ambiente: il tema di icone Breeze e, con il PySide6 di pip,
`/usr/share/icons` fra i percorsi dei temi (lo script lo aggiunge: offscreen
nessuno lo fa, e la barra degli strumenti usciva di sole scritte). Generarli è
stato anche un collaudo: hanno mostrato che *adatta alla larghezza* rendeva la
pagina allo zoom vecchio (segni e campi fuori posto) e che un campo cambiato
mostrava il valore vecchio sotto il nuovo — tutti e due corretti, con il loro
test. Gli URL nel metainfo puntano a `main`: al rilascio vanno fissati al tag.

**CI** (`.github/workflows/`). `ci.yml`, a ogni push e pull request: test su
Python 3.11 e 3.13 (le librerie di sistema di §9 più Tesseract, e PyQt6 per
`pylupdate6`), `ruff`, `mypy`, e un job che valida metainfo (`--pedantic`),
`.desktop` e lo schema del manifest. `flatpak.yml`, su `main` e a mano: la build
vera con `org.flatpak.Builder`, `flatpak-builder-lint` sul manifest e sul repo
(per ora **non bloccante**, finché il modulo `plico` resta `type: dir`), e il
bundle `plico.flatpak` come artefatto. Esito delle prime build riuscite (ottobre
2026): sul manifest il linter segnalava solo `finish-args-home-filesystem-access`,
cioè il `--filesystem=home` che allora c'era. Ora non c'è più: i file passano
solo dai portali (§11). Sul pacchetto costruito segnala in più `appstream-external-screenshot-url` e
`appstream-remote-icon-not-mirrored`: riguardano la copia di screenshot e
icone sui server di Flathub, che fa la loro infrastruttura di build.
`--mirror-screenshots-url` copia gli screenshot nel pacchetto (il log dice
«Committed screenshot ref») ma **non** fa sparire quei due errori: che siano
solo un effetto della build locale è probabile ma **non verificato**, e va
controllato sulla prima build di prova su Flathub. Dettagli
del runner: dentro `org.flatpak.Builder` `--install-deps-from` vuole una
sessione D-Bus (runtime, SDK e BaseApp si installano prima, e il builder gira
in `dbus-run-session`), e `--sandbox` rifiuta il sorgente `".."` del modulo
`plico` — con la sorgente `git` del rilascio il problema non si pone. Altri due
dettagli: su Ubuntu 24.04 serve
`sysctl kernel.apparmor_restrict_unprivileged_userns=0`, altrimenti bubblewrap
non può creare la sandbox della build, e state, build e repo stanno **fuori**
dal checkout, perché il modulo `plico` si costruisce dal checkout stesso.

**Rilascio.** Il manifest in `flatpak/` resta di sviluppo (`type: dir`);
quello per Flathub lo scrive `tools/flathub_manifest.py vX.Y.Z <dir>`, che
legge **tutto dal tag** (manifest, moduli inclusi, `pyproject.toml`, metainfo)
e sostituisce solo la sorgente del modulo `plico` con
`{"type": "git", "url": …, "tag": …, "commit": <hash completo>}`. Prima
rifiuta: un tag non `vX.Y.Z` o in disaccordo con `pyproject.toml` e con la
prima `<release>` della metainfo; screenshot della metainfo che non contengono
`/vX.Y.Z/` (Flathub li copia al momento della build, `main` si muove); un tag
leggero; una firma che non verifica (`git tag -v` con
`gpg.ssh.allowedSignersFile` = `.github/allowed_signers` **del working tree**:
quello del tag permetterebbe a un tag di garantire per sé stesso); un tag
assente da `origin` o diverso lì. `--allow-unsigned` e `--offline` servono
solo per le prove. La firma è **SSH** (`~/.ssh/id_ed25519`,
`gradia@disroot.org`), non PGP: Flathub ricompila dal commit fissato e firma il
proprio repository, quindi una chiave PGP non aggiungerebbe niente; il tag
firmato serve a dire chi l'ha creato. Il checkout ha già la configurazione
locale (`gpg.format ssh`, `user.signingkey`, `tag.gpgSign true`,
`gpg.ssh.allowedSignersFile`). I test (`tests/test_flathub_manifest.py`)
creano un repository temporaneo con una chiave SSH usa e getta e verificano
sia il tag firmato sia i rifiuti.

---

## 12. Cosa manca

**Roadmap lunga, dall'idea originale** (in ordine di difficoltà percepita):

1. compilare **form** — ✅ **fatto**, vedi §8 — e **firmare** — ✅ **fatto**,
   vedi §8: *File → Firma…* (`Ctrl+Shift+D`) produce una firma **PAdES** con un
   certificato PKCS#12, invisibile o stampata in un riquadro, e *File → Verifica
   le firme…* la rilegge dicendo chi ha firmato e se il documento è stato
   toccato dopo. La ragione per cui andava per ultima resta vera ed è scritta
   nel codice: una firma copre dei **byte**, quindi si firma il file appena
   materializzato e la sessione adotta quello;
2. **redaction vera** — ✅ **fatta**, vedi §8;
3. **OCR** integrato (Tesseract) — ✅ **fatto**, vedi §8:
   *Modifica → Riconosci testo…* (`Ctrl+Shift+O`) scrive uno strato
   invisibile, e il Flatpak compila Tesseract e impacchetta cinque lingue
   (§11). Il rinvio precedente non era pigrizia: senza il programma `tesseract`
   né i dati di lingua sulla macchina di sviluppo, l'unico modo di provarlo era
   costruirlo dentro il manifest — cosa che ora il manifest fa, e la prova gira
   nella sandbox;
4. **modifica minima del testo** — la parte difficile, ma è il vero
   differenziale rispetto a PDF Arranger e simili. ✅ **fatta**, vedi §8:
   *Modifica → Modifica testo* (`Ctrl+Shift+T`), una riga alla volta.

**Debito tecnico: le voci e come sono state chiuse** (l'ordine in cui sono
state affrontate è quello di questo elenco):

- la redazione ha tutte e tre le strade e sono tutte fatte: si **disegna** la
  zona che copre il segreto (*Modifica → Cancella zona*, `Ctrl+Shift+X`, un
  rettangolo per volta, `AddRedaction`, annullabile), si **seleziona col mouse**
  (*Cancella selezione*, `Ctrl+Shift+L`: ogni parola toccata diventa un segno
  stretto, tutti in un solo Annulla) oppure si **cerca** la parola
  (`Ctrl+Shift+F` → `DocumentModel.find_text()`, tutte le occorrenze in tutte
  le pagine, un solo Annulla), e una zona già disegnata si **ritocca** col
  mouse (`AdjustRedaction`: gli angoli la ridimensionano, il centro la sposta).
  I metadati non sono più un debito — `/Info`, XMP e allegati non sopravvivono
  alla ricostruzione (vedi §8) — mentre le **annotazioni** vengono copiate;
- la compressione si sceglie in tre modi — livello, «solo le immagini» e le
  pagine di cui ricampionare le immagini (§8) — ma il **guadagno** si vede solo
  a lavoro finito: una stima prima di partire richiederebbe di fare il lavoro,
  che è esattamente quello che si vuole evitare. Il file compresso nasce su un
  temporaneo e viene adottato solo se ha guadagnato, quindi il numero che si
  legge è quello vero;
- i form si compilano **sulla pagina**: un clic su un campo di testo apre
  l'editor dove sta il campo, una casella si spunta, un bottone radio sceglie
  la sua risposta; il dock «Modulo» resta per ciò che sulla pagina non si
  scrive — tendine, testo multiriga, campi in sola lettura. I radiobutton sono
  modificabili anche se PyMuPDF non sa crearli (§8). Le firme si fanno da
  *File → Firma…* (non dal pannello, perché non si compilano: si calcolano);
- il cambio di monitor è gestito da `MainWindow`, non da `PageView`:
  `_watch_screen()` si connette una volta sola a `windowHandle().screenChanged`
  (dal `showEvent`, perché durante la costruzione `self.window()` è `None`) e
  `_on_screen_changed()` richiama `refresh_geometry()` e `_thumb_bar.refresh()`.
  La densità è già letta a ogni richiesta di render — `devicePixelRatioF()` entra
  anche nella chiave della miniatura — mancava solo il segnale;
- il resto dei "Tocchi KDE" è fatto (icone dal tema senza asset impacchettati,
  `self.tr()` su tutto il testo visibile, `QSettings` per geometria/dock/zoom):
  compresa l'**infrastruttura di traduzione** — `src/plico/translations/*.ts`
  estratti con `pylupdate6`, compilati da `lrelease` nella build Flatpak,
  caricati da `i18n.install_translators()` in `app.py` e verificati da
  `tests/test_i18n.py` (l'estrazione, il catalogo aggiornato, i nomi chiesti
  per la lingua di sistema, il giro completo `.ts` → `.qm` → stringa
  tradotta). I cataloghi sono **completi** in inglese, spagnolo, francese e
  tedesco (vedi «Le lingue» qui sotto);
- nei test restano una quarantina di **messaggi di `assert` in italiano**
  (identificatori, docstring e nomi dei test sono in inglese): sono per chi
  sviluppa, non per l'utente, e vanno tradotti quando si ripassa quel file.
  Vanno invece **lasciati in italiano** quelli che confrontano testo
  dell'interfaccia («Cancella zona», «Salva con &nome…») e i dati di prova.

**Punti aperti: nessuno.** Le ultime due, che non erano difetti ma
**capacità** mai esistite, sono chiuse:

- **PDF cifrati** — si aprono chiedendo la password (§5, §6): `PasswordRequired`
  e `open_for_reading()` nel modello, lo slot `RenderWorker.authenticate()` con
  la vista in pausa, `MainWindow._ask_password()`. Misurato: un handle toccato
  prima di autenticare non si recupera più (§10);
- **l'unione si annulla** — è il comando `AppendDocument` (§8), quindi Ctrl+Z
  la toglie come ogni altra modifica, e `MainWindow._merged_since_save` non
  esiste più.

**Con la firma, la roadmap lunga è finita**: le quattro voci dell'idea
originale ci sono tutte e nessuna è un abbozzo — ognuna ha la sua sezione in
§8 e i suoi test.

**Anche il debito tecnico qui sopra è chiuso**, un punto per commit: la zona di
redazione si ritocca col mouse (`AdjustRedaction`, `26c679a`), la compressione
si sceglie anche in *cosa* (`CompressionOptions`, `dc17c4c`), i form si
compilano **sulla pagina** compresi i radiobutton (`33dd6ab`) e l'infrastruttura
di traduzione esiste (`4a60786`). Due voci restano scritte come **scelte**, non
come mancanze: il guadagno della compressione si legge a lavoro finito (un
preventivo richiederebbe di fare il lavoro che si vuole evitare) e le firme non
si compilano dal pannello (si calcolano su un file). Quello che resta è una
rifinitura: la quarantina di messaggi di `assert` in italiano nei test.

Delle dieci voci della review dell'ottobre 2026 non resta niente, e le
decisioni sono scritte dove servono: in §5 e §6 (le API e il giro della
password fino al worker), in §8 (salvataggio sempre atomico e con i permessi
conservati, campi omonimi scritti sulla sorgente prima della copia, cache delle
pagine che restituisce i byte sostituiti, annotazioni che toccano una redazione
eliminate insieme al contenuto, nomi dei comandi via
`QCoreApplication.translate()`, password chieste solo dalla finestra), in §9
(`fitz` → `pymupdf`) e in §10 (le insidie corrispondenti, l'handle bloccato
compreso). Il codice — docstring, commenti, nomi di variabile e nomi dei test
compresi — è tutto in inglese.

### La seconda review (ottobre 2026)

«Punti aperti: nessuno» era vero per le voci note, non per il programma: una
seconda review, fatta **verificando ogni sospetto con uno script su PDF veri**
invece che leggendo, ha trovato otto difetti che i test non coprivano, quattro
dei quali gravi. Sono tutti corretti, un commit e un test di regressione per
ciascuno, e ogni test è stato visto fallire senza la correzione:

1. *Modifica testo* cancellava lettere dalle righe sopra e sotto con
   l'interlinea singola, e *Cancella parola* / *Cancella selezione* facevano lo
   stesso (`a94b1dc`, §8);
2. una redazione lasciava nel file i **campi del modulo** che copriva, valore
   compreso (`8ab9d91`, §8) — §8 diceva il contrario;
3. una **seconda firma** dalla finestra rompeva la prima, e il verdetto
   chiamava «integra» una firma rotta (`b44033e`, §8);
4. dopo un'unione annullata, l'unione successiva veniva **mostrata** con le
   pagine del file tolto, mentre il salvataggio scriveva quelle giuste
   (`a85cc1d`, §8);
5. *Cancella parola* non trovava le parole dell'OCR prima del salvataggio
   (`45671d6`) — §8 diceva di sì;
6. sulle pagine con `/Rotate` 90 o 270 il testo modificato poteva uscire dal
   foglio (`7ee1126`);
7. `Exec=plico %U` faceva arrivare URL che `pymupdf.open` non apre
   (`0ae2082`, §11);

e sei minori (`23a36e8` … `b3f0de9`): un modulo mai firmato letto come
firmato, un clic incerto che spostava un segno fuori dall'undo, il dialogo
dell'OCR modale solo dopo mezzo secondo, lo scambio del file compresso che
falliva senza messaggio, le immagini da riga di comando, e la nota sui thread
di PyMuPDF in §10.

La lezione, per la prossima review: **un'affermazione di questo documento non
è una prova**. Due delle otto voci contraddicevano frasi scritte qui, e una
terza (le chiamate a PyMuPDF serializzate dal GIL) è stata smentita misurando
prima di scriverla. Prima di fidarsi di una frase che dice «verificato»,
cercare il test che la verifica.

**I tre limiti rimasti dopo la review sono chiusi anch'essi**, ma uno era
peggio di come era scritto:

- un `source_id` **non si riusa mai** (`904d08c`, §8): un'unione annullata
  lascia la sorgente registrata e inutilizzata, quindi nemmeno un render del
  file tolto ancora in viaggio dal worker può rispondere per un altro file;
- un file ricostruito **non porta firme rotte** (`87fabb3`, §8): ogni
  salvataggio, non solo la firma di modifiche, usciva con la firma vecchia
  rotta e `/SigFlags` a 3, cioè con l'aspetto di una falsificazione;
- i campi dei moduli: il limite scritto era «i nomi possono cambiare», ma
  misurando è venuto fuori che **un campo con un widget per pagina perdeva il
  widget** appena le pagine venivano riordinate, e che *Salva compresso* con le
  pagine da ricampionare toglieva i campi delle pagine scelte. Ora ogni
  sorgente si copia una volta sola (`assemble.py`, §8), e i campi di una
  pagina eliminata non restano nel file.

---

### Le lingue

Plico parla **italiano** (la lingua del codice), **inglese**, **spagnolo**,
**francese** e **tedesco**. Quello che conta per mantenerlo così:

- **ogni testo che l'utente legge passa da un catalogo**, anche quelli del
  modello: un `ValueError` che finisce in un dialogo si scrive con
  `QCoreApplication.translate("Contesto", "…").format(…)`, mai con una
  f-string. `lupdate` legge **solo testo letterale**: `self.tr(variabile)` non
  viene estratto (era così per i livelli di compressione e i nomi delle lingue
  OCR), e per una tabella costruita all'import si marca il testo con
  `QT_TRANSLATE_NOOP` (in `optimize.py` c'è una versione tipizzata: quella di
  PySide6 restituisce `object`) e lo si traduce dove va a schermo;
- **i cataloghi si rigenerano tutti e quattro** dopo aver toccato una stringa:
  `for l in en es fr de; do pylupdate6 -no-obsolete src/plico -ts
  src/plico/translations/plico_$l.ts; done`, poi si traducono le voci
  `unfinished`. `tests/test_translations.py` fallisce finché un catalogo ha voci
  non tradotte, ha messaggi diversi dagli altri, perde un segnaposto (`{0}`,
  `%(name)s`) o un `&`, o dà due voci dello stesso menu la stessa scorciatoia —
  e lo controlla caricando ogni lingua nella **finestra vera**;
- **le scorciatoie `&` si scelgono per menu**: in tedesco *Datei* ha
  Ö&ffnen, &Speichern, B&eenden…; una lettera doppia nello stesso menu fa
  scegliere ad Alt la voce sbagliata;
- **il francese vuole lo spazio indivisibile** (U+00A0) prima di `: ; ? ! %`
  e dentro `« »`, altrimenti la punteggiatura va a capo da sola;
- **una lingua senza catalogo riceve l'inglese** (`i18n.FALLBACK`), non
  l'italiano: è più probabile che un utente portoghese legga l'inglese;
- **anche Qt va tradotto**: i pulsanti dei dialoghi standard («Save»,
  «Cancel», il selettore di file) vengono dal catalogo di Qt, che
  `i18n.install_qt_translator()` carica da `QLibraryInfo`. Prima non lo
  caricava nessuno, e anche l'utente italiano leggeva «Discard» sotto una
  domanda in italiano;
- il **metainfo** e il **.desktop** hanno l'inglese come lingua base (è quello
  che AppStream e Flathub si aspettano) e le altre quattro come traduzioni;
  nel metainfo le parole chiave tradotte portano `xml:lang` sulla singola
  `<keyword>`, non su `<keywords>` (`appstreamcli` lo dà come errore).

Una lingua nuova è un file `plico_xx.ts` in più: lo si crea con `pylupdate6`, si
traduce, e lo si aggiunge a `LANGUAGES` in `tests/test_translations.py`, alle
`<languages>` del metainfo e alle voci `[xx]` del `.desktop`.

---

## 13. Convenzioni

- Codice e commenti **in inglese**, documenti utente e messaggi all'utente
  **in italiano**.
- `ruff` con `line-length = 100`, `target-version = "py311"`. `mypy` con
  `ignore_missing_imports = true` (PySide6 ha stub parziali, PyMuPDF nessuno).
- Il testo visibile passa da `self.tr("...")`; le stringhe interpolate usano
  `self.tr("...{0}").format(x)` così l'intera frase resta traducibile.
- Niente asset grafici impacchettati: le icone vengono dal tema
  (`QIcon.fromTheme`), con il controllo `isNull()` per i desktop che non ne
  hanno uno. C'è un test che verifica che il pacchetto non contenga immagini.
- Un commento spiega **perché**, mai cosa fa la riga. Le decisioni non ovvie di
  questo progetto (perché i byte e non le pagine, perché il worker non ha
  parent, perché si calcola la visibilità a mano) valgono più del codice che
  le implementa: se se ne cambia una, va aggiornato il commento che la
  giustifica.
