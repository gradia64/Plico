# Plico

Un vero editor PDF nativo per Linux, costruito con **Qt6** e **PySide6**, con
**PyMuPDF** per leggere e renderizzare i PDF e **pikepdf** (qpdf) per
comprimerli.

> Il file PDF non si tocca mai finché non salvi.

## Caratteristiche

- **Ruotare, eliminare, riordinare** pagine (drag & drop nella barra miniature)
- **Unire** un altro PDF: le sue pagine si aggiungono a quelle già aperte
  senza copiare nulla, perché ogni pagina virtuale sa a quale documento
  sorgente appartiene. Si può unire anche un'immagine (una ricevuta
  fotografata in coda a un PDF)
- **Creare un PDF da immagini** (*File → Crea da immagini…*, `Ctrl+Shift+N`):
  foto e scansioni — PNG, JPEG, TIFF, BMP, GIF — diventano una pagina
  ciascuna, nell'ordine scelto. Una scansione mantiene il suo formato reale
  (un A4 a 300 dpi resta un A4), una foto da telefono viene ridotta a un A4
  orientato come lei, e i JPEG entrano senza essere ricompressi
- **Estrarre pagine** (dividere) in un nuovo file con una selezione tipo
  `1-3,5,8` — l'ordine digitato è conservato, quindi vale anche come riordino
- **Undo/Redo** completo grazie a `QUndoStack`
- **Rendering asincrono** in un thread separato — l'UI non si blocca mai
- **Rendering lazy**: si renderizzano solo le pagine visibili, non l'intero
  documento
- **Cache** a budget di byte per le pagine, LRU per le miniature
- **Salvataggio** su file temporaneo: il PDF di partenza non si tocca.
  `Ctrl+S` salva sul file aperto (o sull'ultimo «Salva con nome»),
  `Ctrl+Shift+S` chiede dove; il titolo segna con `*` le modifiche non
  salvate, e chiudere o aprire un altro file chiede prima di perderle.
  `Ctrl+W` (*File → Chiudi*) chiude il documento lasciando aperta la finestra
- **Salva compresso** a tre livelli, più «solo le immagini» e le pagine da
  ricampionare: il guadagno è quello vero, misurato sul file già scritto (e il
  livello "leggera" è senza perdita)
- **Cancellazione vera** (in inglese *redaction*): si disegna una zona sui dati
  da eliminare, oppure si trascina sulle parole, e al salvataggio il testo
  viene **rimosso**, non coperto — quel che resta non è più copiabile né
  ricercabile
- **Compilare i form AcroForm**: il dock «Modulo» mostra i campi della pagina
  in vista — testo, anche multiriga, caselle e tendine — e i valori finiscono
  nel file al salvataggio, con undo/redo
- **Modifica minima del testo**: un clic su una riga la apre in un editor
  sulla pagina; il testo vecchio viene tolto dal file e quello nuovo scritto
  nello stesso punto, con lo stesso corpo, colore e — quando è installato — lo
  stesso font
- **OCR** (*Modifica → Riconosci testo…*, `Ctrl+Shift+O`): una scansione
  diventa **cercabile e selezionabile** senza cambiare aspetto — il testo
  riconosciuto viene scritto sotto l'immagine, invisibile. Si sceglie quali
  pagine e in che lingua, e ogni giro è un solo passo di undo
- **Firmare** (*File → Firma…*, `Ctrl+Shift+D`): una firma **PAdES** con il
  proprio certificato, invisibile o stampata in un riquadro sulla pagina, e
  *File → Verifica le firme…* per rileggere chi ha firmato e se il documento è
  stato toccato dopo

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
    │   ├── textedit.py        # modifica di una riga di testo: span, verifica, riscrittura
    │   ├── ocr.py             # riconoscimento con Tesseract, strato invisibile, lingue
    │   ├── sign.py            # firma PAdES con pyHanko e rilettura delle firme
    │   ├── images.py          # da immagini a PDF: A4, dpi, EXIF, JPEG intatti
    │   ├── save.py            # save_as(), save_compressed(), extract_pages()
    │   └── optimize.py        # livelli di compressione, optimize_in_place()
    ├── rendering/
    │   └── worker.py          # RenderWorker in QThread
    └── widgets/
        ├── page_view.py       # QScrollArea: rendering, fit-width, HiDPI, redazione, campi
        ├── thumbnail_bar.py   # QListView + modello + cache, caricamento lazy
        ├── form_panel.py      # dock «Modulo»: un editor per ogni campo
        ├── ocr.py             # dialogo lingue/pagine e task di riconoscimento
        ├── sign.py            # dialoghi di firma e di verifica delle firme
        └── compress.py        # dialogo delle opzioni, format_size, task
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

Dopo un salvataggio sopra il file aperto, Plico **riapre** il file salvato:
è quello il documento, adesso, con eliminazioni, rotazioni e redazioni già
dentro. Per questo le modifiche fatte fino a lì non si possono più annullare.
Estrarre pagine sopra un file aperto, invece, non è permesso.

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

Il livello dice *quanto*, non *cosa*: sotto la tendina ci sono due scelte in
più. **«Solo le immagini»** salta la ricompattazione del file — serve su una
scansione, dove il guadagno sta nelle immagini, mentre su un documento di solo
testo non guadagna niente e il programma lo dice invece di scrivere una copia
identica. **«Pagine da ricampionare»** lascia intatte le immagini delle altre
pagine, utile quando in mezzo a scansioni pesanti ci sono pagine di testo. C'è
un caso in cui non si guadagna nulla: se due pagine si dividono la stessa
immagine, comprimerne una sola obbliga l'altra ad averne una copia per conto
suo, e il file crescerebbe — allora non viene scritto niente, e il messaggio lo
spiega.

Il guadagno non è una stima: il file compresso viene scritto davvero (accanto
alla destinazione) e solo dopo il programma dice quanto pesa, adottandolo solo
se ha guadagnato.

La compressione gira in un thread separato, quindi la finestra resta reattiva
anche sui file grandi.

### Cancella zona: il testo se ne va davvero

`Ctrl+Shift+X` (*Modifica → Cancella zona*) attiva lo strumento: si trascina un rettangolo sui dati da
eliminare, un clic secco su una zona la annulla, `Esc` esce. Una zona già
disegnata si **corregge senza rifarla**: gli angoli la ridimensionano, il
centro la sposta. Le zone restano **modificabili finché non salvi** — sono
comandi undo come gli altri (`Ctrl+Z`) e l'anteprima scura sulla pagina mostra
esattamente dove finiranno.

Al salvataggio PyMuPDF riscrive i content stream e **toglie** le parole che
ricadono nella zona: nel file non restano né il testo né l'immagine sotto il
rettangolo. Un rettangolo nero disegnato sopra — quello che fanno parecchi
strumenti — lascerebbe il segreto copiabile e ricercabile.

`Ctrl+Shift+F` (*Modifica → Cancella parola…*) cerca invece una parola in **tutte**
le pagine e marca ogni occorrenza in un colpo solo, come un unico passo di
undo.

`Ctrl+Shift+L` (*Modifica → Cancella selezione*) è la terza strada, quella che
si aspetta chi ha usato un editor: si trascina sulle parole da eliminare e
vengono marcate **per intero**, una per una, con un segno stretto quanto la
parola. Il trascinamento è un gesto solo, quindi un `Ctrl+Z` disfa tutta la
selezione; trascinare dove non c'è testo non lascia niente; un clic su un segno
lo toglie, come nella zona, e anche qui un segno si sposta e si ridimensiona.
Funziona anche sulle parole lette dall'OCR.

Tre cose da sapere: le parole si prendono **intere** (un segno a metà parola
non nasconderebbe niente), l'unità minima è la parola e non la lettera, e
`apply_redactions()` elimina anche la grafica vettoriale che tocca il
rettangolo, quindi un bordo o una tabella a cavallo del segno possono sparire.
I metadati del PDF, invece, non sono un rischio: il file di uscita è
ricostruito dalle sole pagine, quindi `/Info`, l'XMP e gli allegati non ci
arrivano mai.

### Modifica del testo: una riga alla volta

`Ctrl+Shift+T` (*Modifica → Modifica testo*) attiva lo strumento: un clic su
una riga **già presente** nel PDF apre un piccolo editor sopra di essa,
**Invio** conferma, **Esc** annulla. Un clic dove non c'è testo, o su una
pagina che è solo un'immagine (una scansione), lo dice accanto al puntatore.
Lo strumento corregge il testo che c'è: non aggiunge testo nuovo in un punto
vuoto. La correzione si vede subito sulla pagina ed è un comando come gli
altri (`Ctrl+Z`); nel file entra solo al salvataggio, dove il testo vecchio
viene **rimosso** dal content stream — non coperto — e quello nuovo scritto
nello stesso punto. Sfondo, bordi delle tabelle e testo accanto restano.

È una modifica *minima*, e lo dice: un testo che non ci sta nello spazio
libero (fino al bordo della cella o alla parola successiva) viene
rimpicciolito fino all'80% e oltre rifiutato, con il motivo nella barra di
stato. Non si modificano il testo verticale e i font Type3. Il font è quello
del documento quando si può riusare, altrimenti lo stesso installato sul
sistema, altrimenti un sosia (serif, sans o monospazio) con lo stesso stile.

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

### OCR: rendere cercabile una scansione

*Modifica → Riconosci testo…* (`Ctrl+Shift+O`) legge le pagine scelte con
Tesseract e scrive sotto l'immagine uno **strato di testo invisibile**
(modalità di render 3). La pagina si vede identica, ma il testo si può
selezionare, copiare, cercare con `Ctrl+F` — e la *Cancella parola*
(`Ctrl+Shift+F`) finalmente lo trova, cosa che su una scansione non marcata è
impossibile.

Il riconoscimento costa (circa mezzo secondo per pagina A4 a 300 dpi), per
questo non è automatico: si dice quali pagine (la corrente, la corrente e le
successive, o tutto il documento) e in che lingua, con italiano e inglese
insieme come proposta. Gira nel thread pool con una barra di avanzamento
annullabile, e ogni giro è **un solo** passo di undo: un `Ctrl+Z` toglie lo
strato di tutte le pagine in una volta.

Il font dello strato è uno dei Base-14 e non viene incorporato, quindi rendere
cercabile una scansione non aggiunge un byte. Le parole che il PDF già contiene
non vengono riscritte: una pagina metà testo e metà scansione non si ritrova il
testo doppio.

I dati di lingua (`*.traineddata`) si mettono in
`~/.local/share/plico/tessdata/`, senza root; il Flatpak porta già `eng` e
`ita`. La libreria Tesseract deve essere presente: nel Flatpak è compilata
dentro (§ Flatpak), su una distribuzione è il pacchetto `tesseract` /
`libtesseract`.

### Firma: un PDF firmato, non un timbro

*File → Firma…* (`Ctrl+Shift+D`) firma il documento con un certificato
PKCS#12 (`.p12` / `.pfx`) e produce una firma **PAdES** — il profilo di firma
PDF che i lettori europei riconoscono. Si sceglie se la firma resta invisibile
o se compare in un riquadro in basso a destra con nome, data e motivo: il
riquadro è contenuto della pagina, quindi non si può togliere senza rompere la
firma.

Tre cose che questa implementazione fa e una che non fa:

- **La firma è l'ultimo byte del file.** Prima si materializza il documento
  (con tutti i campi compilati, il testo riscritto, le redazioni applicate, le
  pagine ruotate), poi si firma. L'ordine inverso produrrebbe una firma che
  copre una versione del documento diversa da quella che l'utente vede.
- **Firmare adotta il file firmato.** Dopo `Firma…` la sessione punta al nuovo
  file, perché continuare a lavorare sulla lista di pagine che l'ha generato
  significherebbe perdere la firma al primo salvataggio successivo.
- **Salvare sopra un file firmato chiede prima.** Un salvataggio normale
  riscrive il PDF da zero: la firma non c'è più. Il programma lo dice e
  aspetta un «sì», invece di farlo e basta.
- **Non decide di chi fidarsi.** Plico non porta con sé nessun archivio di
  autorità: una firma integra e valida di un certificato sconosciuto viene
  mostrata come «integra, ma il certificato non è fra quelli che consideri
  fidati». Si aggiungono i certificati di cui fidarsi uno per uno (file `.pem`)
  e restano in `QSettings`.

*File → Verifica le firme…* rilegge le firme dal file **su disco** e distingue
i quattro casi che contano: firma integra e attendibile; integra ma di un
certificato sconosciuto (ambra, non rosso: è comunque una firma vera); integra
ma su un documento **modificato dopo la firma** — vale solo per la versione
firmata; firma rotta o certificato scaduto.

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
- PyMuPDF (pymupdf) ≥ 1.24.3
- pikepdf ≥ 9 (compressione mirata)
- pyHanko ≥ 0.37 (firma PAdES; porta con sé crittografia e validazione)
- Tesseract (libreria, 4 o 5) e almeno un dato di lingua per l'OCR — il
  Flatpak li porta entrambi

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
| `python3-pyhanko.json` | modulo per pyHanko e le sue dipendenze, sempre da wheel |
| `io.github.gradia64.Plico.desktop` | launcher (registra `application/pdf`) |
| `io.github.gradia64.Plico.metainfo.xml` | metadati AppStream |
| `io.github.gradia64.Plico.svg` | icona |

Cinque scelte non ovvie:

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
- **pyHanko da wheel, in un solo modulo** (`python3-pyhanko.json`): pyHanko
  tira con sé `cryptography`, `asn1crypto`, `aiohttp`, `lxml` e una decina di
  altre dipendenze, tutte pure Python o con wheel `manylinux` per il 3.13 della
  BaseApp, quindi si installano in un colpo solo con `--no-index --no-deps`.
  Sono i venti file elencati nel modulo, ciascuno con il suo `sha256`: la
  firma digitale è la parte del programma in cui "più o meno quella versione"
  non è una risposta accettabile.
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