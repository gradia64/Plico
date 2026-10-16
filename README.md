# Plico

Un vero editor PDF nativo per Linux, costruito con **Qt6** e **PySide6**, con
**PyMuPDF** per leggere e renderizzare i PDF e **pikepdf** (qpdf) per
comprimerli.

> Il file PDF non si tocca mai finché non salvi.

## Caratteristiche

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
- **Salvataggio** su file temporaneo: il PDF di partenza non si tocca
- **Salva compresso** a tre livelli, con il guadagno mostrato a fine lavoro —
  e il livello "leggera" è senza perdita
- **Redazione vera**: si trascina un rettangolo sui dati da eliminare e al
  salvataggio il testo viene **rimosso**, non coperto — quel che resta non è
  più copiabile né ricercabile
- **Compilare i form AcroForm**: il dock «Modulo» mostra i campi della pagina
  in vista — testo, anche multiriga, caselle e tendine — e i valori finiscono
  nel file al salvataggio, con undo/redo

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
    │   ├── commands.py        # QUndoCommand: RotatePage, DeletePage, AddRedaction, SetFieldValue…
    │   ├── redact.py          # rettangoli di redazione, matrici di rotazione
    │   ├── forms.py           # campi AcroForm: lettura, scrittura, svuotamento
    │   ├── save.py            # save_as(), save_compressed(), extract_pages()
    │   └── optimize.py        # livelli di compressione, optimize_in_place()
    ├── rendering/
    │   └── worker.py          # RenderWorker in QThread
    └── widgets/
        ├── page_view.py       # QScrollArea: rendering, fit-width, HiDPI, redazione, campi
        ├── thumbnail_bar.py   # QListView + modello + cache, caricamento lazy
        ├── form_panel.py      # dock «Modulo»: un editor per ogni campo
        └── compress.py        # dialogo del livello, format_size, task
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

### Compressione: dove si guadagna davvero

"Salva compresso" (`Ctrl+Shift+C`) scrive una copia più piccola del documento
virtuale — quindi rispetta eliminazioni, riordini e rotazioni — e lascia
intatti i PDF di partenza.

| Livello | Cosa fa | Senza perdita? |
| --- | --- | --- |
| **Leggera** | fonde i content stream frammentati, compatta la struttura | sì |
| **Media** | come sopra, più immagini oltre 200 dpi riportate a 150 (qualità 80) | no |
| **Forte** | immagini oltre 150 dpi riportate a 96 (qualità 60) | no |

Il guadagno più grosso non viene dalle immagini ma da `clean` di mutool: un
PDF che ha subito copie e modifiche si porta dietro centinaia di content
stream minuscoli, e fonderli vale, su un documento di testo, 188 KB → 12 KB
(6%). Su una scansione invece la struttura non ha niente da dare, e conta solo
il lavoro sulle immagini (un JPEG da 3,4 MB su 3 pagine resta al 100% con
"leggera", scende al 52% con "media" e al 36% con "forte").

La compressione gira in un thread separato, quindi la finestra resta reattiva
anche sui file grandi.

### Redazione: il testo se ne va davvero

`Ctrl+Shift+X` attiva lo strumento: si trascina un rettangolo sui dati da
eliminare, un clic secco su una zona la annulla, `Esc` esce. Le zone restano
**modificabili finché non salvi** — sono comandi undo come gli altri (`Ctrl+Z`)
e l'anteprima scura sulla pagina mostra esattamente dove finiranno.

Al salvataggio PyMuPDF riscrive i content stream e **toglie** le parole che
ricadono nella zona: nel file non restano né il testo né l'immagine sotto il
rettangolo. Un rettangolo nero disegnato sopra — quello che fanno parecchi
strumenti — lascerebbe il segreto copiabile e ricercabile.

`Ctrl+Shift+F` (*Modifica → Redigi testo…*) cerca invece una parola in **tutte**
le pagine e marca ogni occorrenza in un colpo solo, come un unico passo di
undo.

Due cose da sapere: si redige quello che si disegna o quello che si cerca
(mancano la selezione di testo e la selezione di area), e `apply_redactions()`
elimina anche la grafica vettoriale che tocca il rettangolo, quindi un bordo o
una tabella a cavallo del segno possono sparire. I metadati del PDF, invece,
non sono un rischio: il file di uscita è ricostruito dalle sole pagine, quindi
`/Info`, l'XMP e gli allegati non ci arrivano mai.

### Form: compilare il PDF, non solo leggerlo

Il dock **Modulo** (a destra) elenca i campi della pagina in vista: testo
(anche multiriga), caselle e tendine. Un clic su un campo sulla pagina lo
seleziona nel pannello — si scrive lì, non dentro la pagina. I valori restano
**modificabili finché non salvi** e passano per gli stessi undo/redo del resto
(`Ctrl+Z`).

Un campo AcroForm non è contenuto del PDF, ma un'annotazione con un valore, e
Plico lo tratta come tale: la **descrizione** dei campi arriva dalla sorgente,
i **valori** che scrivi vivono nel modello, e `save.py` li applica mentre
materializza le pagine — prima delle redazioni, così una redazione sopra un
campo se lo porta via. Il valore disegnato sulla pagina è quello del modello,
cioè quello che *sarà* nel file.

Un campo viene scritto **solo se lo tocchi**: uno mai aperto conserva il valore
che aveva nella sorgente, che non è la stessa cosa di svuotarlo. I pulsanti
radio non sono modificabili — PyMuPDF non li sa costruire e li rilegge male — e
le firme appartengono alla tappa successiva.

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
- pikepdf ≥ 9 (compressione mirata)

## Installazione

```bash
pip install -e ".[dev]"
```

L'entry point accetta i file da aprire, come si aspetta un'app desktop:

```bash
plico relazione.pdf              # apre
plico a.pdf b.pdf                # apre a.pdf e vi unisce b.pdf
```

## Flatpak

Il packaging è in `flatpak/` ed è pensato per essere pubblicabile su Flathub.

| File | Ruolo |
| --- | --- |
| `io.github.gradia64.Plico.json` | manifest dell'applicazione |
| `python3-pymupdf.json` | modulo per PyMuPDF, con wheel e `sha256` fissati |
| `python3-pikepdf.json` | modulo per pikepdf, con wheel e `sha256` fissati |
| `io.github.gradia64.Plico.desktop` | launcher (registra `application/pdf`) |
| `io.github.gradia64.Plico.metainfo.xml` | metadati AppStream |
| `io.github.gradia64.Plico.svg` | icona |

Quattro scelte non ovvie:

- **`base: io.qt.PySide.BaseApp`** invece di installare PySide6 con pip. La
  BaseApp di Flathub contiene già PySide6 compilato e allineato al Qt di
  `org.kde.Platform`, quindi il bundle non duplica Qt né rischia di
  sovrascrivere la versione del runtime. Per questo l'installazione
  dell'applicazione usa `--no-deps`: PySide6 arriva dal runtime, PyMuPDF dal
  suo modulo, e pip non deve nemmeno provare a scaricare PySide6 da PyPI.
- **PyMuPDF da wheel `manylinux`** (`cp310-abi3`, valida per ogni Python ≥ 3.10,
  quindi anche per il 3.13 del runtime) e non da sorgente: compilare MuPDF
  dentro il manifest vorrebbe dire `swig` e parecchi minuti di build.
- **pikepdf da wheel `cp313`** (l'interprete della BaseApp, che non è quello
  del venv) **installata con `--no-deps`**: pikepdf dichiara `Pillow`, `lxml` e
  `packaging`, ma `open()` e `save()` non li importano, e `packaging` è già
  nella BaseApp. Se servissero le API sulle immagini o il supporto PDF/A
  andrebbero aggiunte anche le loro wheel.
- **`cleanup-commands: /app/cleanup-BaseApp.sh`**, richiesto dalla BaseApp.

Costruire e installare nella propria utenza:

```bash
# una volta sola: builder, SDK e BaseApp
flatpak remote-add --user --if-not-exists flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.flatpak.Builder//stable \
    org.kde.Sdk//6.11 io.qt.PySide.BaseApp//6.11

# build + install. La cache sta FUORI dal progetto: build-dir/ e
# .flatpak-builder/ dentro l'albero vengono trovati dalle ricerche globali e
# contengono copie dei sorgenti.
flatpak run org.flatpak.Builder --force-clean --user --install \
    --install-deps-from=flathub \
    --state-dir="$HOME/.cache/plico-flatpak/state" \
    "$HOME/.cache/plico-flatpak/build" \
    flatpak/io.github.gradia64.Plico.json

flatpak run io.github.gradia64.Plico
```

Per pubblicare su Flathub la sorgente `type: dir` del modulo `plico` va
sostituita con la sorgente `git` del tag di rilascio.

## Sviluppo

```bash
# test (senza display, grazie a QT_QPA_PLATFORM=offscreen).
# NB: pytest non è in .venv/bin, quindi si passa da python -m
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q

# lint + tipi
ruff check src/ tests/
mypy src/plico

# avvio
plico            # oppure: python -m plico.app
```

## Licenza

GPL v3 — vedi [LICENSE](LICENSE).