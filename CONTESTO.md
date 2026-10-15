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
testati: aprire, unire più PDF, ruotare, eliminare, riordinare, dividere
(estrarre un sottoinsieme), comprimere in salvataggio, annulla/ripristina,
rendering asincrono, cache, integrazione desktop KDE, packaging Flatpak.
Versione `0.1.0`, licenza GPL-3.0-or-later.

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
│   │   ├── commands.py       # RotatePage, DeletePage, MovePage (QUndoCommand)
│   │   └── save.py           # save_as, extract_pages, parse_page_ranges
│   ├── rendering/
│   │   └── worker.py         # RenderWorker: unico proprietario degli handle fitz
│   └── widgets/
│       ├── page_view.py      # QScrollArea: rendering su richiesta, zoom, HiDPI
│       └── thumbnail_bar.py  # QListView + modello + cache, caricamento lazy
└── tests/
    ├── test_model.py         # modello, comandi, salvataggio, parse_page_ranges
    ├── test_worker.py        # il worker di rendering in isolamento
    └── test_integration.py   # MainWindow vera, offscreen: ~30 test end-to-end
```

Gate di qualità attuale: **57 passed, 1 skipped**, `ruff` pulito, `mypy` pulito
(12 file sorgente).

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
pagina a `total_rotation` in `PageView._oriented_size`, mentre `page_sizes`
(che viene da `page.rect`) la rotazione base ce l'ha già dentro. Effetto: le
pagine con `/Rotate` diverso da zero — scansioni, PDF esportati da telefono,
qualsiasi cosa un visualizzatore abbia "raddrizzato" scrivendo `/Rotate` —
venivano mostrate **verticali e capovolte**. Il test di regressione è
`test_page_with_base_rotation_is_not_rotated_twice` in
`tests/test_integration.py`: se qualcuno tocca di nuovo la rotazione, quello è
il test che deve fallire. (Era un caso non coperto perché tutti i PDF di test
erano generati con `/Rotate 0`.)

La regola in una riga:

> **Al renderer va `item.rotation`; la vista scambia largo/alto su
> `item.rotation`; solo il salvataggio conosce `total_rotation`.**

---

## 5. Il modello (`src/plico/model/document.py`)

```python
@dataclass
class PageItem:
    source_index: int     # posizione nella propria sorgente
    base_rotation: int    # /Rotate originale (0/90/180/270)
    rotation: int = 0     # offset scelto dall'utente
    source_id: int = 0    # indice in DocumentModel.sources

    @property
    def total_rotation(self) -> int: ...
```

`DocumentModel(QObject)` espone:

- `pages: list[PageItem]` — le pagine virtuali, nell'ordine mostrato;
- `page_sizes: list[tuple[float, float]]` — dimensioni **orientate**,
  parallele a `pages`. Vengono da `page.rect`, quindi includono la `/Rotate`
  base. Sono lette al momento dell'apertura perché la vista possa impaginare
  *prima* che il thread di rendering abbia prodotto un pixel: costa una
  passata di metadati, non un render;
- `sources: list[str]` — i percorsi dei PDF aperti;
- `page_count` (property);
- `open(path)` — sostituisce tutto, aprendo in sola lettura;
- `append_document(path) -> int` — **unire**: accoda tutte le pagine di un
  altro PDF. La sorgente viene registrata *dopo* essere stata letta con
  successo, così un file corrotto lascia il modello esattamente com'era;
- `source_for(item) -> str`;
- segnali `changed` (struttura) e `page_changed(int)` (modifica in loco).

**Le viste osservano il modello**, non vengono "puntate" dalla finestra. È una
scelta deliberata: aggiornare le viste a mano dopo ogni comando significa
dimenticarsene su undo/redo, che è esattamente il bug che era stato
introdotto e poi corretto. `PageView` e `ThumbnailBar` si connettono a
`model.changed` / `model.page_changed` da soli.

---

## 6. RenderWorker — il pezzo critico (`src/plico/rendering/worker.py`)

Un `QObject` spostato in un `QThread`, che possiede **l'unico** handle fitz.
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

`RenderWorker` ha `render_requested = Signal(object)` e
`rendered = Signal(object, QImage)` e:

- apre i sorgenti **pigramente**, al primo render richiesto, tenendo una LRU di
  al massimo `MAX_OPEN_DOCUMENTS = 16` handle (unire molti PDF non deve
  sprecare un file descriptor per documento);
- riceve il **percorso** nel `RenderRequest` invece di dipendere da un
  messaggio "apri" precedente: non c'è alcun ordinamento fra thread da
  sbagliare, e una pagina non viene mai resa dal documento sbagliato.

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
   chiude i fitz handle **dentro** il thread del worker. Chiamare
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
`maxsize=60`), condivisa con `MainWindow` tramite i signal del worker.

- **Caricamento lazy**: `_visible_rows()` chiede solo le miniature in vista
  (più ±2 celle), con fallback al primo schermo pieno finché il layout non è
  avvenuto. La barra si aggiorna anche su `verticalScrollBar().valueChanged`.
- **Il drag & drop è tradotto in un comando**: `dropEvent` calcola
  `from_row`/`to_row`, chiama `event.ignore()` perché il riordino interno
  predefinito non avvenga **mai**, ed emette `move_requested(from, to)`.
  Lasciare che la vista si riordini da sola disallineerebbe vista e modello.
- Segnali: `move_requested(int, int)`, `page_selected(int)`.

---

## 8. Comandi e salvataggio

`model/commands.py`: `RotatePage`, `DeletePage` (`pop` al redo, `insert`
all'undo — lo stack è LIFO, quindi gli indici restano coerenti), `MovePage`.
La rotazione di più pagine selezionate va raggruppata con
`stack.beginMacro()`, così è **un solo** passo di undo.

`model/save.py`:

- `_contiguous_runs(items)` raggruppa le pagine consecutive **della stessa
  sorgente**, così un documento solo riordinato si copia con pochi
  `insert_pdf` invece di uno per pagina (il raggruppamento si interrompe
  quando cambia `source_id`);
- `save_as(model, out_path)` / `extract_pages(model, out_path, indices)`
  condividono `_write_atomically`, che scrive su un file temporaneo nella
  **stessa directory** e poi fa `os.replace()`. Salvare sopra il file aperto
  è sicuro: un errore a metà scrittura non può distruggere l'originale;
- `parse_page_ranges(spec, page_count)` converte `"1-3,5,8"` in indici
  **0-based preservando l'ordine digitato** (quindi `"5,1-3"` riordina oltre
  che estrarre) e solleva `ValueError` per input malformati, fuori intervallo
  o vuoti: scartare pagine in silenzio durante una divisione sarebbe peggio
  che rifiutare.

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
- `import fitz` stampa un avviso di deprecazione (`use import pymupdf`). Il
  codice usa `fitz` ovunque: o si migra tutto insieme, o si lascia stare. Non
  mescolare i due import;
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

### Geometria e visibilità

- La `geometry()` di un widget è affidabile **solo dopo** un giro di layout di
  Qt. In una finestra mai mostrata tutte le etichette riportano lo stesso
  rettangolo, e un test di visibilità basato su `intersects()` conclude che
  ogni pagina è visibile. Per questo `PageView` registra da sé `y_px` e
  `height_px` in `_relayout()` e calcola la visibilità in modo deterministico.
  (Con una finestra *mostrata* il codice vecchio funzionava: è il motivo per
  cui il bug è rimasto nascosto.)

### PyMuPDF

- Salvare **sopra il file aperto** richiede il salvataggio incrementale:
  `ValueError: save to original must be incremental`. Il progetto evita del
  tutto il problema scrivendo su un temporaneo e facendo `os.replace()`.
- `fitz.Matrix` non ha attributi `x0` / `xy`: per le rotazioni si usa
  `prerotate()`.

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

- Esiste una directory `build/` **stantia** alla radice, residuo di un
  `pip install`: contiene copie dei sorgenti. Una ricerca globale la trova e
  si rischia di modificare la copia invece dell'originale. `build-dir/` e
  `.flatpak-builder/` sono gli artefatti della build Flatpak, anche loro
  ignorati da git.

---

## 11. Flatpak

I file stanno in `flatpak/`: `io.github.gradia.Plico.json` (manifest),
`python3-pymupdf.json` (modulo PyMuPDF con wheel e `sha256` fissati),
`.desktop`, `.metainfo.xml`, `.svg`. Gli stessi file sono installati anche da
`pip install .` tramite `[tool.setuptools.data-files]` in `pyproject.toml`,
così c'è una sola fonte di verità.

Scelte non ovvie (documentate anche nel README):

- **`base: io.qt.PySide.BaseApp`** e `pip3 install --no-deps`: PySide6 arriva
  già compilato dal runtime, allineato al Qt di `org.kde.Platform`. Il bundle
  non duplica Qt e pip non prova nemmeno a scaricare PySide6 da PyPI.
- **PyMuPDF da wheel `manylinux` `cp310-abi3`** e non da sorgente: compilare
  MuPDF dentro il manifest vorrebbe dire `swig` e minuti di build.
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
    json.load(open('flatpak/io.github.gradia.Plico.json')))" && echo "manifest OK"

# 2. metadati AppStream e launcher
appstreamcli validate --no-net flatpak/io.github.gradia.Plico.metainfo.xml
desktop-file-validate flatpak/io.github.gradia.Plico.desktop

# 3. build e installazione
flatpak remote-add --user --if-not-exists flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.flatpak.Builder//stable \
    org.kde.Sdk//6.11 io.qt.PySide.BaseApp//6.11

flatpak run org.flatpak.Builder --force-clean --user --install \
    --install-deps-from=flathub \
    build-dir flatpak/io.github.gradia.Plico.json

flatpak run io.github.gradia.Plico
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

1. compilare **form** e **firmare**;
2. **redaction vera**: rimozione effettiva del testo, non un rettangolo nero
   sopra. Qui il documento va mutato e la struttura a "servizio documentale"
   va estesa, non aggirata;
3. **OCR** integrato (Tesseract);
4. **modifica minima del testo** — la parte difficile, ma è il vero
   differenziale rispetto a PDF Arranger e simili.

**Debito tecnico noto:**

- `pikepdf` era previsto per la compressione mirata: oggi si usa
  `garbage=4, deflate=True` di PyMuPDF, che è già qualcosa ma non tutto;
- `PageView._on_screen_changed` esiste ma **non è connesso** (fu rimosso
  perché `self.window()` è `None` durante la costruzione): il rendering HiDPI
  oggi non reagisce al cambio di monitor a finestra aperta;
- il resto dei "Tocchi KDE" è fatto (icone dal tema senza asset impacchettati,
  `self.tr()` su tutto il testo visibile, `QSettings` per geometria/dock/zoom);
  manca solo l'infrastruttura di traduzione vera (`.ts` + `lrelease`).

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
