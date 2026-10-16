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
│   ├── main_window.py        # finestra, menu, toolbar, dock, QSettings, dialogs
│   ├── model/
│   │   ├── document.py       # DocumentModel, PageItem  ← il cuore
│   │   ├── commands.py       # RotatePage, DeletePage, MovePage, AddRedaction, SetFieldValue…
│   │   ├── redact.py         # rettangoli di redazione e matrici di rotazione
│   │   ├── forms.py          # campi AcroForm: lettura, scrittura, svuotamento
│   │   ├── save.py           # save_as, save_compressed, extract_pages, parse_page_ranges
│   │   └── optimize.py       # livelli di compressione, optimize_in_place  ← pikepdf
│   ├── rendering/
│   │   └── worker.py         # RenderWorker: unico proprietario degli handle PyMuPDF
│   └── widgets/
│       ├── page_view.py      # QScrollArea: rendering, zoom, HiDPI, redazione, campi
│       ├── thumbnail_bar.py  # QListView + modello + cache, caricamento lazy
│       ├── form_panel.py     # dock «Modulo»: un editor per ogni campo della pagina
│       └── compress.py       # scelta del livello, format_size, task sul thread pool
└── tests/
    ├── test_model.py         # modello, comandi, salvataggio, parse_page_ranges
    ├── test_worker.py        # il worker di rendering in isolamento
    ├── test_optimize.py      # i livelli di compressione e optimize_in_place
    ├── test_redact.py        # rotazione e rimozione *vera* del testo
    ├── test_forms.py         # campi AcroForm: letti, scritti, riletti dal file
    └── test_integration.py   # MainWindow vera, offscreen: 94 test end-to-end
```

Gate di qualità attuale: **226 passed, 1 skipped**, `ruff` pulito, `mypy` pulito
(17 file sorgente).

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
key = ("page" | "thumb", source_id, source_index, rotation, zoom, dpr)

class RenderRequest:
    key: tuple
    source_path: str     # quale PDF
    source_index: int    # quale pagina in quel PDF
    zoom: float          # pixel REALI (zoom × dpr)
    rotation: int        # solo offset utente
```

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
  `closeEvent` e prima del dialogo di `_open_file` (non dopo: la domanda
  riguarda il documento in vista). «Salva» passa da `_save_file`; un
  salvataggio fallito o annullato lascia la finestra aperta. Nei test
  `QMessageBox.question` va **monkeypatchato** (§10): il fixture `windows`
  non chiama `close()`, quindi non incontra la domanda.
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
che l'utente ha visto. `redo()` accoda la sorgente e allunga `pages`; `undo()`
taglia `pages[-n:]` e toglie la sorgente: è tutto quello che serve, perché le
pagine appese puntano a una sorgente che nessun'altra pagina usa. Il nome è
`QCoreApplication.translate("AppendDocument", "Unisci «{0}»")` con il nome del
file, così Ctrl+Z dice cosa sta per togliere.

`model/save.py`:

- `_contiguous_runs(items)` raggruppa le pagine consecutive **della stessa
  sorgente**, così un documento solo riordinato si copia con pochi
  `insert_pdf` invece di uno per pagina (il raggruppamento si interrompe
  quando cambia `source_id`);
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

`optimize_in_place(path, level, progress)` adotta il risultato **solo se è
più piccolo** (un PDF già ottimizzato non deve crescere) e sostituisce il
file con `os.replace` conservandone i permessi. `save_compressed(model,
out_path, level)` passa da `_write_atomically` come `save_as`: prima
materializza il documento virtuale (quindi il file compresso rispetta
eliminazioni, riordini e rotazioni), poi lo comprime, sempre su un
temporaneo nella stessa directory. La sorgente non viene mai toccata.

La compressione gira su `QThreadPool` con un `QRunnable`, non sul thread dei
render: sono due lavori indipendenti e un PDF grande non deve congelare la
finestra. I segnali sono connessi **solo a metodi legati di QObject** — un
lambda verrebbe eseguito nel thread emittente e toccherebbe widget dalla
thread sbagliata.

### Redazione vera (`model/redact.py`)

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
  `redaction_removed` e `MainWindow` spinge il comando sullo stack, esattamente
  come per il drag & drop delle miniature.

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
commento lontano dal segno resta nel file.

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
- i tipi modificabili sono **testo**, **casella** e **tendina/lista**. I
  **radiobutton** restano fuori: PyMuPDF non li sa costruire (`ValueError: bad
  xref`) e li rilegge con un `rect` assurdo (`±INT32_MAX`), quindi
  `read_fields()` li scarta e non si offre un editor per ciò che non si
  riuscirebbe a salvare. Le **firme** appartengono alla tappa della firma.

La vista disegna i campi sulla pagina (`_paint_fields`, con il valore preso dal
**modello** e non dal file) e un clic su un campo seleziona l'editor
corrispondente nel pannello: `PageView` emette `field_clicked` e `MainWindow`
decide, esattamente come per la redazione.

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
- **`insert_pdf()` rinomina i campi omonimi.** Se due pagine portano un widget
  con lo stesso nome, dopo la copia il secondo si chiama `nome [12]` (misurato:
  stesso xref nella sorgente, nomi diversi nel file costruito). Conseguenza:
  `write_fields(page, {"nome": …})` sulla pagina già copiata restituisce `0` e
  non scrive niente. Per questo `save.py` scrive i valori **sulla sorgente in
  memoria** (`_fill_source_fields`) prima di copiare le pagine.

### Test

- `QT_QPA_PLATFORM=offscreen` è obbligatorio: senza display i test non
  partono.
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

### Attenzione

- `build/`, `build-dir/` e `.flatpak-builder/` (residui di `pip install` e
  della build Flatpak) sono stati **rimossi**: contenevano copie dei sorgenti e
  una ricerca globale poteva far modificare la copia invece dell'originale. La
  build Flatpak ora tiene la cache **fuori dal progetto**, con
  `--state-dir=$HOME/.cache/plico-flatpak/state` e la build directory in
  `$HOME/.cache/plico-flatpak/build`.

---

## 11. Flatpak

I file stanno in `flatpak/`: `io.github.gradia64.Plico.json` (manifest),
`python3-pymupdf.json` e `python3-pikepdf.json` (i moduli delle due
dipendenze, con wheel e `sha256` fissati), `.desktop`, `.metainfo.xml`,
`.svg`. Gli stessi file sono installati anche da `pip install .` tramite
`[tool.setuptools.data-files]` in `pyproject.toml`, così c'è una sola fonte
di verità.

Scelte non ovvie (documentate anche nel README):

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

Costruire, provare, e verificare il manifest:

```bash
# 1. il manifest è conforme allo schema ufficiale flatpak-builder
python3 -m venv /tmp/lintenv && /tmp/lintenv/bin/pip install -q jsonschema
curl -s -o /tmp/schema.json \
    https://raw.githubusercontent.com/flatpak/flatpak-builder/main/data/flatpak-manifest.schema.json
/tmp/lintenv/bin/python -c "
import json, jsonschema
jsonschema.Draft7Validator(json.load(open('/tmp/schema.json'))).validate(
    json.load(open('flatpak/io.github.gradia64.Plico.json')))" && echo "manifest OK"

# 2. metadati AppStream e launcher
appstreamcli validate --no-net flatpak/io.github.gradia64.Plico.metainfo.xml
desktop-file-validate flatpak/io.github.gradia64.Plico.desktop

# 3. build e installazione
flatpak remote-add --user --if-not-exists flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.flatpak.Builder//stable \
    org.kde.Sdk//6.11 io.qt.PySide.BaseApp//6.11

flatpak run org.flatpak.Builder --force-clean --user --install \
    --install-deps-from=flathub \
    build-dir flatpak/io.github.gradia64.Plico.json

flatpak run io.github.gradia64.Plico
```

Verifiche già eseguite con esito positivo: schema `flatpak-builder`
conforme, `appstreamcli validate` valido, `desktop-file-validate` pulito,
build riuscita e app avviata dentro il sandbox (finestra "Plico", documento
aperto, thread chiuso).

**Nota d'ambiente:** questo sandbox rende `~/.var/app` in sola lettura, quindi
build e `flatpak run` richiedono accesso completo; `flatpak-builder-lint` (quello
che gira sulla CI di Flathub) non è installabile da PyPI e senza un container
runtime non si può eseguire.

Per una submission reale: la sorgente `type: dir` del modulo `plico` va
sostituita con la sorgente `git` del tag di rilascio.

---

## 12. Cosa manca

**Roadmap lunga, dall'idea originale** (in ordine di difficoltà percepita):

1. compilare **form** — ✅ **fatto**, vedi §8 — e **firmare**, che resta da
   fare e va per ultimo: una firma non sopravvive a nessuna modifica
   successiva;
2. **redaction vera** — ✅ **fatta**, vedi §8;
3. **OCR** integrato (Tesseract) — **rinviato, con le prove**: sulla macchina di
   sviluppo c'è la libreria (`libtesseract5`) ma **non** il programma
   `tesseract`, e `/usr/share/tesseract-ocr/5/tessdata` contiene solo
   `configs`, `pdf.ttf` e `tessconfigs` — nessun dato di lingua (servirebbe
   `sudo`, quindi una password); dentro la sandbox Flatpak mancano entrambi, e
   su Flathub non esiste un'extension Tesseract. Servirebbe compilare
   leptonica e tesseract dai sorgenti nel manifest **senza poterli provare in
   locale**: si fa quando c'è una ragione per farlo, non prima;
4. **modifica minima del testo** — la parte difficile, ma è il vero
   differenziale rispetto a PDF Arranger e simili.

**Debito tecnico noto:**

- la redazione si disegna a mano o si chiede per parola (`Ctrl+Shift+F` →
  `DocumentModel.find_text()`, tutte le occorrenze in tutte le pagine, un solo
  Annulla): mancano la selezione di testo e la selezione di area. I metadati
  non sono più un debito — `/Info`, XMP e allegati non sopravvivono alla
  ricostruzione (vedi §8) — mentre le **annotazioni** vengono copiate;
- la compressione ha tre livelli fissi, applicati a tutto il documento: non si
  può ancora scegliere "solo le immagini" o escludere delle pagine, e il
  guadagno si vede solo a lavoro finito (niente stima prima di partire);
- i form si compilano **dal pannello**, non scrivendo sulla pagina: il clic su
  un campo lo seleziona nel dock «Modulo», ma non si digita in-place. I
  radiobutton non sono modificabili e le firme non sono ancora gestite (vedi
  §8);
- il cambio di monitor è gestito da `MainWindow`, non da `PageView`:
  `_watch_screen()` si connette una volta sola a `windowHandle().screenChanged`
  (dal `showEvent`, perché durante la costruzione `self.window()` è `None`) e
  `_on_screen_changed()` richiama `refresh_geometry()` e `_thumb_bar.refresh()`.
  La densità è già letta a ogni richiesta di render — `devicePixelRatioF()` entra
  anche nella chiave della miniatura — mancava solo il segnale;
- il resto dei "Tocchi KDE" è fatto (icone dal tema senza asset impacchettati,
  `self.tr()` su tutto il testo visibile, `QSettings` per geometria/dock/zoom);
  manca solo l'infrastruttura di traduzione vera (`.ts` + `lrelease`).

**Punti aperti: nessuno.** Le ultime due, che non erano difetti ma
**capacità** mai esistite, sono chiuse:

- **PDF cifrati** — si aprono chiedendo la password (§5, §6): `PasswordRequired`
  e `open_for_reading()` nel modello, lo slot `RenderWorker.authenticate()` con
  la vista in pausa, `MainWindow._ask_password()`. Misurato: un handle toccato
  prima di autenticare non si recupera più (§10);
- **l'unione si annulla** — è il comando `AppendDocument` (§8), quindi Ctrl+Z
  la toglie come ogni altra modifica, e `MainWindow._merged_since_save` non
  esiste più.

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
