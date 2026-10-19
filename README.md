<p align="center">
  <a href="README.en.md"><img src="https://img.shields.io/badge/Lang-English-blue?style=for-the-badge" alt="English"></a>
  <a href="README.fr.md"><img src="https://img.shields.io/badge/Lang-Français-blue?style=for-the-badge" alt="Français"></a>
  <a href="README.de.md"><img src="https://img.shields.io/badge/Lang-Deutsch-blue?style=for-the-badge" alt="Deutsch"></a>
  <a href="README.es.md"><img src="https://img.shields.io/badge/Lang-Español-orange?style=for-the-badge" alt="Español"></a>
</p>

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
  `1-3,5,8` — l'ordine digitato è conservato, quindi vale anche come riordino.
  Virgole e spazi separano allo stesso modo: `1 3` sono le pagine 1 e 3
- **Trovare** (*Modifica → Trova…*, `Ctrl+F`): una barra sotto la pagina
  evidenzia tutte le occorrenze, `Invio`/`F3` passa alla successiva,
  `Maiusc+F3` alla precedente, `Esc` chiude. Trova anche le parole appena
  riconosciute dall'OCR, prima di salvare
- **Impostazioni** (*Impostazioni → Configura Plico…*, `Ctrl+Maiusc+,`): la
  lingua dell'interfaccia — automatica, cioè quella del sistema, oppure una
  fra italiano, inglese, francese, tedesco e spagnolo; con una lingua di
  sistema che Plico non ha si usa l'inglese — e l'icona nell'area di notifica.
  Con l'icona si può anche far sì che la X riduca Plico nell'area di notifica
  invece di chiuderlo: si esce da *File → Esci* (`Ctrl+Q`) o da «Esci» nel
  menu dell'icona. La lingua cambia al prossimo avvio
- **Guida** (*Aiuto → Guida di Plico*, `F1`) in italiano, inglese, francese,
  tedesco e spagnolo, nella lingua dell'interfaccia: si legge in una finestra
  di Plico, anche senza rete
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
  ricercabile. Se ne vanno anche i campi del modulo e le note sotto la zona,
  mentre cancellare una parola non tocca le righe sopra e sotto
- **Compilare i form AcroForm**: si scrive dentro la pagina, il dock «Modulo»
  in vista — testo, anche multiriga, caselle e tendine — e i valori finiscono
  nel file al salvataggio, con undo/redo
- **Modifica minima del testo**: un clic su una riga la apre in un editor
  sulla pagina; il testo vecchio viene tolto dal file e quello nuovo scritto
  nello stesso punto, con lo stesso corpo, colore e — quando è installato — lo
  stesso font. Le righe vicine restano intatte anche con l'interlinea singola
- **OCR** (*Modifica → Riconosci testo…*, `Ctrl+Shift+O`): una scansione
  diventa **cercabile e selezionabile** senza cambiare aspetto — il testo
  riconosciuto viene scritto sotto l'immagine, invisibile. Si sceglie quali
  pagine e in che lingua, e ogni giro è un solo passo di undo
- **Firmare** (*File → Firma…*, `Ctrl+Shift+D`): una firma **PAdES** con il
  proprio certificato, invisibile o stampata in un riquadro sulla pagina, e
  *File → Verifica le firme…* per rileggere chi ha firmato e se il documento è
  stato toccato dopo. Una seconda firma si aggiunge alla prima senza romperla

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
    │   ├── assemble.py        # pagine da più PDF, campi dei moduli intatti
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
- **salvataggio**: materializza la lista copiando ciascuna sorgente una volta
  sola e mettendo poi le pagine in ordine nel file d'uscita — copiare due volte
  dalla stessa sorgente rinomina o perde i campi dei moduli

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
comandi undo come gli altri (`Ctrl+Z`).

Il risultato **si vede subito**, senza salvare e riaprire. Con lo strumento
acceso le zone sono rettangoli scuri con le maniglie, per correggerle; appena
lo spegni (`Esc`) la pagina e la sua miniatura mostrano l'**anteprima vera**:
le cancellazioni applicate a una copia della pagina in memoria, con lo stesso
codice del salvataggio, quindi anche quello che sparisce insieme alle parole
(un bordo, un pezzo di immagine). Ogni segno è confermato da un avviso sopra la
pagina, e il titolo della finestra conta le cancellazioni ancora da applicare.
Prima di scrivere il file — salvataggio, firma, copia compressa, estrazione di
pagine — Plico chiede conferma con il numero di zone e le pagine, perché da lì
il contenuto non si recupera più.

Al salvataggio PyMuPDF riscrive i content stream e **toglie** le parole che
ricadono nella zona: nel file non restano né il testo né l'immagine sotto il
rettangolo. Un rettangolo nero disegnato sopra — quello che fanno parecchi
strumenti — lascerebbe il segreto copiabile e ricercabile. Con il contenuto se
ne vanno anche le **note** e i **campi del modulo** che la zona tocca: un campo
compilato con un nome resterebbe altrimenti nel file, valore compreso.

`Ctrl+Shift+F` (*Modifica → Cancella parola…*) cerca invece una parola in **tutte**
le pagine e marca ogni occorrenza in un colpo solo, come un unico passo di
undo. Cerca anche nel testo riconosciuto dall'OCR, già prima di salvare. Non
accende nessuno strumento: le pagine mostrano subito l'anteprima delle
occorrenze tolte.

`Ctrl+Shift+L` (*Modifica → Cancella selezione*) è la terza strada, quella che
si aspetta chi ha usato un editor: si trascina sulle parole da eliminare e
vengono marcate **per intero**, una per una, con un segno stretto quanto la
parola. Il trascinamento è un gesto solo, quindi un `Ctrl+Z` disfa tutta la
selezione; trascinare dove non c'è testo non lascia niente; un clic su un segno
lo toglie, come nella zona, e anche qui un segno si sposta e si ridimensiona.
Funziona anche sulle parole lette dall'OCR.

Quattro cose da sapere:

- le parole si prendono **intere** (un segno a metà parola non nasconderebbe
  niente), e l'unità minima è la parola, non la lettera;
- un segno fatto di parole — da *Cancella parola* o da *Cancella selezione* —
  toglie il testo della **sua riga soltanto**: con l'interlinea singola le
  lettere delle righe sopra e sotto toccano il suo riquadro, e restano dove
  sono. Una zona **disegnata** invece cancella tutto ciò che tocca, perché è
  quello che si è disegnato, e lo stesso vale per un segno di parole che si è
  spostato o ridimensionato;
- `apply_redactions()` elimina anche la grafica vettoriale che tocca il
  rettangolo, quindi un bordo o una tabella a cavallo del segno possono
  sparire;
- un clic su un segno lo toglie anche se il mouse si è mosso di un pixel: è un
  clic, non uno spostamento, e `Ctrl+Z` lo rimette esattamente dov'era.

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
nello stesso punto. Sfondo, bordi delle tabelle e testo accanto restano, e
così le righe sopra e sotto: il testo vecchio si toglie da una fascia attorno
alla riga, non dal suo riquadro, che con l'interlinea singola toccherebbe
anche le vicine.

È una modifica *minima*, e lo dice: un testo che non ci sta nello spazio
libero (fino al bordo della cella, alla parola successiva o al margine della
pagina, anche su una pagina ruotata) viene
rimpicciolito fino all'80% e oltre rifiutato, con il motivo nella barra di
stato. Non si modificano il testo verticale e i font Type3. Il font è quello
del documento quando si può riusare, altrimenti lo stesso installato sul
sistema, altrimenti un sosia (serif, sans o monospazio) con lo stesso stile.

### Form: compilare il PDF, non solo leggerlo

Si compila **sulla pagina**: un clic su un campo di testo apre l'editor dove
sta il campo, una casella si spunta dove l'hai cliccata, un pulsante radio
sceglie la risposta che rappresenta. Il dock **Modulo** (a destra) elenca i
campi della pagina in vista e resta la strada per quelli che sulla pagina non
si scrivono — tendine, testo multiriga, campi in sola lettura. I valori restano
**modificabili finché non salvi** e passano per gli stessi undo/redo del resto
(`Ctrl+Z`).

Un campo AcroForm non è contenuto del PDF, ma un'annotazione con un valore, e
Plico lo tratta come tale: la **descrizione** dei campi arriva dalla sorgente,
i **valori** che scrivi vivono nel modello, e `save.py` li applica mentre
materializza le pagine — prima delle redazioni, così una redazione sopra un
campo se lo porta via. Il valore disegnato sulla pagina è quello del modello,
cioè quello che *sarà* nel file.

Un campo viene scritto **solo se lo tocchi**: uno mai aperto conserva il valore
che aveva nella sorgente, che non è la stessa cosa di svuotarlo. Un gruppo di
pulsanti radio è **una domanda sola** — il dock lo mostra come una tendina con
le risposte — e si sceglie anche cliccandone uno sulla pagina. Le firme
appartengono a *File → Firma…*.

### OCR: rendere cercabile una scansione

*Modifica → Riconosci testo…* (`Ctrl+Shift+O`) legge le pagine scelte con
Tesseract e scrive sotto l'immagine uno **strato di testo invisibile**
(modalità di render 3). La pagina si vede identica, ma il testo si può
selezionare, copiare, cercare con `Ctrl+F` — e la *Cancella parola*
(`Ctrl+Shift+F`) finalmente lo trova, cosa che su una scansione non marcata è
impossibile. Lo trova subito, non solo dopo aver salvato: lo strato entra nel
file al salvataggio, ma la ricerca guarda anche le parole appena riconosciute.

Il riconoscimento costa (circa mezzo secondo per pagina A4 a 300 dpi), per
questo non è automatico: si scrivono le pagine come in *Estrai pagine* (`3`,
`4-8`, `1-3,5`; all'apertura sono proposte tutte) e si sceglie la lingua, con
quella dell'interfaccia e l'inglese insieme come proposta. Gira nel thread pool con una barra di avanzamento
annullabile — finché gira, la finestra non accetta modifiche alle pagine che
sta leggendo — e ogni giro è **un solo** passo di undo: un `Ctrl+Z` toglie lo
strato di tutte le pagine in una volta. Alla fine un avviso sopra la pagina
dice su quante pagine ha letto il testo (o che non ne ha trovato), oltre alla
barra di stato.

Il font dello strato è uno dei Base-14 e non viene incorporato, quindi rendere
cercabile una scansione non aggiunge un byte. Le parole che il PDF già contiene
non vengono riscritte: una pagina metà testo e metà scansione non si ritrova il
testo doppio.

I dati di lingua (`*.traineddata`) si mettono in
`~/.local/share/plico/tessdata/`, senza root; il Flatpak porta già italiano,
inglese, spagnolo, francese e tedesco, e propone la lingua dell'interfaccia
insieme all'inglese. La libreria Tesseract deve essere presente: nel Flatpak è compilata
dentro (§ Flatpak), su una distribuzione è il pacchetto `tesseract` /
`libtesseract`.

### Firma: un PDF firmato, non un timbro

*File → Firma…* (`Ctrl+Shift+D`) firma il documento con un certificato
PKCS#12 (`.p12` / `.pfx`) e produce una firma **PAdES** — il profilo di firma
PDF che i lettori europei riconoscono. Si sceglie se la firma resta invisibile
o se compare in un riquadro in basso a destra con nome, data e motivo: il
riquadro è contenuto della pagina, quindi non si può togliere senza rompere la
firma.

Quattro cose che questa implementazione fa e una che non fa:

- **La firma è l'ultimo byte del file.** Prima si materializza il documento
  (con tutti i campi compilati, il testo riscritto, le redazioni applicate, le
  pagine ruotate), poi si firma. L'ordine inverso produrrebbe una firma che
  copre una versione del documento diversa da quella che l'utente vede.
- **Firmare adotta il file firmato.** Dopo `Firma…` la sessione punta al nuovo
  file, perché continuare a lavorare sulla lista di pagine che l'ha generato
  significherebbe perdere la firma al primo salvataggio successivo.
- **Una seconda firma si aggiunge alla prima.** Se il documento firmato non ha
  modifiche non salvate, la firma nuova si accoda al file così com'è (un
  aggiornamento incrementale) e la prima resta valida. Con modifiche non
  salvate il file va riscritto e la firma che c'era non coprirebbe più niente,
  quindi viene tolta e resta solo la nuova: il programma lo dice prima e chiede
  se continuare.
- **Salvare sopra un file firmato chiede prima.** Un salvataggio normale
  riscrive il PDF da zero: la firma non c'è più, e il file salvato non ne porta
  una rotta al suo posto. Il programma lo dice e aspetta un «sì», invece di
  farlo e basta.
- **Non decide di chi fidarsi.** Plico non porta con sé nessun archivio di
  autorità: una firma integra e valida di un certificato sconosciuto viene
  mostrata come «integra, ma il certificato non è fra quelli che consideri
  fidati». Si aggiungono i certificati di cui fidarsi uno per uno (file `.pem`)
  e restano in `QSettings`.

*File → Verifica le firme…* rilegge le firme dal file **su disco** e distingue
i casi che contano: firma integra e attendibile; integra ma di un certificato
sconosciuto (ambra, non rosso: è comunque una firma vera); integra ma su un
documento **modificato dopo la firma** — vale solo per la versione firmata;
firma **rotta**, cioè il contenuto che copriva è cambiato (rosso, sempre, anche
se il file ha revisioni successive); firma non valida o certificato scaduto.
Un modulo che non è mai stato firmato non viene scambiato per un documento
firmato.

### Integrazione desktop (KDE)

- **Icone dal tema** (`QIcon.fromTheme`: `document-open`, `document-save-as`,
  `edit-undo`, `object-rotate-right`, `zoom-in`, …): nessun asset grafico nel
  pacchetto. Se il tema non fornisce l'icona, l'azione resta senza icona invece
  di mostrare un quadrato vuoto.
- **Cinque lingue**: italiano, inglese, spagnolo, francese e tedesco, anche
  nei pulsanti dei dialoghi standard di Qt e nei metadati dello store (vedi
  «Tradurre Plico»).
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
plico ricevuta.jpg a.pdf         # crea un documento dalla foto e vi unisce a.pdf
```

Accetta anche gli URL `file:///…` che passano alcuni launcher. Il file
`.desktop` chiede comunque percorsi (`Exec=plico %F`).

## Flatpak

Il packaging è in `flatpak/` ed è pensato per essere pubblicabile su Flathub.

| File | Ruolo |
| --- | --- |
| `io.github.gradia64.plico.json` | manifest dell'applicazione |
| `python3-pymupdf.json` | modulo per PyMuPDF, con wheel e `sha256` fissati |
| `python3-pikepdf.json` | modulo per pikepdf, con wheel e `sha256` fissati |
| `python3-pyhanko.json` | modulo per pyHanko e le sue dipendenze, sempre da wheel |
| `io.github.gradia64.plico.desktop` | launcher (registra `application/pdf`, riceve percorsi con `%F`) |
| `io.github.gradia64.plico.metainfo.xml` | metadati AppStream |
| `io.github.gradia64.plico.svg` | icona |

Otto scelte non ovvie:

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
- **Le traduzioni si compilano durante la build**: `lrelease` esiste solo
  nell'SDK di Qt, non nella runtime, e i `.qm` sono gli unici file che
  servono a runtime. Il modulo `plico` installa i `.ts` con il pacchetto e poi
  li compila in `/app/share/plico/translations`, così nel bundle non finisce
  anche il compilatore.
- **`cleanup-commands: /app/cleanup-BaseApp.sh`**, richiesto dalla BaseApp.
- **Nessun accesso alla home** (niente `--filesystem`): ogni file passa dal
  selettore di file del portal (`org.freedesktop.portal.FileChooser`), che
  Qt usa da solo dentro Flatpak. Plico vede il documento come
  `/run/user/<uid>/doc/<id>/nome.pdf` e lo legge e lo scrive lì, salvataggio
  atomico compreso (il temporaneo nella stessa cartella e `os.replace`
  funzionano anche nel document portal); per proporre un percorso nei
  dialoghi usa invece quello vero, che il portal espone nell'attributo
  esteso `user.document-portal.host-path`. Il launcher usa `%F`, così un
  doppio clic arriva già come percorso esportato nel portal.
- **`--talk-name=org.kde.StatusNotifierWatcher`**, l'unico permesso D-Bus:
  senza, dentro la sandbox l'area di notifica non esiste e l'icona delle
  Impostazioni non compare (provato su Plasma). Qt registra l'icona col suo
  nome unico sul bus, quindi non serve possedere altri nomi. L'icona è
  facoltativa e spenta di default.

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
    flatpak/io.github.gradia64.plico.json

flatpak run io.github.gradia64.plico
```

Gli **screenshot** dello store stanno in `flatpak/screenshots/` e li produce
`tools/screenshots.py` dall'app vera; nel metainfo puntano al tag
dell'ultimo rilascio, e a ogni rilascio vanno spostati sul tag nuovo.

### Rilasciare

Flathub non costruisce dal checkout ma da un tag git, fissato anche al suo
commit. Il manifest di `flatpak/` resta quello di sviluppo (`type: dir`), e
quello da inviare lo genera `tools/flathub_manifest.py` **dal tag**. Prima di
scrivere controlla che:

- il tag sia `v` + la versione di `pyproject.toml` + l'ultima `<release>` della
  metainfo;
- gli screenshot della metainfo puntino al tag e non a `main`;
- il tag sia annotato, firmato da una chiave di `.github/allowed_signers` e
  presente su `origin` con lo stesso oggetto.

I tag si firmano con la chiave **SSH** (niente PGP da custodire). Da fare una
volta sola per checkout:

```bash
git config gpg.format ssh
git config user.signingkey ~/.ssh/id_ed25519.pub
git config tag.gpgSign true
git config gpg.ssh.allowedSignersFile "$PWD/.github/allowed_signers"
```

Perché GitHub mostri il tag come «Verified», la stessa chiave va registrata
anche come *signing key* dell'account (Settings → SSH and GPG keys → New SSH
key → Signing key).

A ogni rilascio:

```bash
# 1. versione in pyproject.toml, nuova <release> e URL degli screenshot
#    (…/Plico/vX.Y.Z/flatpak/screenshots/…) nella metainfo; commit e push
# 2. tag firmato, verificato, pubblicato
git tag -s v0.1.0 -m "Plico 0.1.0"
git tag -v v0.1.0
git push origin v0.1.0
# 3. il manifest per Flathub, con i moduli che include
python tools/flathub_manifest.py v0.1.0 ~/flathub/io.github.gradia64.plico
```

`--allow-unsigned --offline` fa una prova a secco su un tag locale non firmato.

## Sviluppo

```bash
# test (senza display, grazie a QT_QPA_PLATFORM=offscreen).
# NB: pytest non è in .venv/bin, quindi si passa da python -m
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q

# lint + tipi
ruff check src/ tests/ tools/
mypy src/plico

# avvio
plico            # oppure: python -m plico.app

# screenshot per lo store (flatpak/screenshots), in inglese o in un'altra lingua
QT_QPA_PLATFORM=offscreen python tools/screenshots.py [it|es|fr|de]
```

La **CI** (GitHub Actions, `.github/workflows/`) fa le stesse cose a ogni push
e pull request: `ci.yml` esegue test, `ruff` e `mypy` su Python 3.11 e 3.13 e
valida metainfo, `.desktop` e manifest; `flatpak.yml`, su `main` e a richiesta
dalla scheda Actions, costruisce il Flatpak vero, lo passa al linter di
Flathub (`flatpak-builder-lint`) e lascia il pacchetto `plico.flatpak` fra gli
artefatti della run, da installare con `flatpak install --user plico.flatpak`.

### Tradurre Plico

Plico parla **italiano**, **inglese**, **spagnolo**, **francese** e
**tedesco**: segue la lingua del sistema, e una lingua che non conosce riceve
l'inglese. Le stringhe sono in italiano nel codice; i cataloghi delle altre
lingue stanno in `src/plico/translations/plico_{en,es,fr,de}.ts` e si
modificano con Qt Linguist o con un editor di testo. Una lingua nuova è un file
`plico_xx.ts` in più (CONTESTO.md, «Le lingue», dice cosa aggiornare insieme).

`pylupdate6` arriva con PyQt6 (`pip install PyQt6` nel venv basta, serve solo
lo strumento): senza, `tests/test_i18n.py` salta proprio il controllo che
avvisa quando una stringa nuova manca dal catalogo.

```bash
# 1. riestrarre le stringhe dopo aver toccato il codice,
#    in tutti e quattro i cataloghi
for l in en es fr de; do
    pylupdate6 -no-obsolete src/plico -ts src/plico/translations/plico_$l.ts
done

# 2. compilare: pyside6-lrelease arriva con PySide6 (o lrelease dall'SDK)
pyside6-lrelease src/plico/translations/plico_de.ts -qm /tmp/plico_de.qm

# 3. provarla senza installare niente
LANG=de_DE.UTF-8 PLICO_TRANSLATIONS=/tmp plico
```

`tests/test_i18n.py` verifica che i cataloghi siano quelli che le sorgenti
producono, così nessuna stringa nuova resta fuori; `tests/test_translations.py`
che ogni lingua sia completa, conservi i segnaposto (`{0}`) e non dia la stessa
scorciatoia a due voci di un menu.

## Licenza

GPL v3 — vedi [LICENSE](LICENSE).

## About

Un vero editor PDF nativo per Linux: unisci, dividi, ruota, riordina, salva. Qt6 + PySide6 + PyMuPDF.

### Topics

[desktop-application](https://github.com/topics/desktop-application) [flatpak](https://github.com/topics/flatpak) [kde](https://github.com/topics/kde) [linux](https://github.com/topics/linux) [pdf](https://github.com/topics/pdf) [pdf-editor](https://github.com/topics/pdf-editor) [pymupdf](https://github.com/topics/pymupdf) [pyside6](https://github.com/topics/pyside6) [python](https://github.com/topics/python) [qt6](https://github.com/topics/qt6)

### Resources

[Readme](https://github.com/gradia64/Plico#readme-ov-file)

[GPL-3.0 license](https://github.com/gradia64/Plico#GPL-3.0-1-ov-file)

[Activity](https://github.com/gradia64/Plico/activity)
