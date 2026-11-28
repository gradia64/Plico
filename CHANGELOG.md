# Changelog

Le modifiche di Plico che si notano da fuori, versione per versione. Il
formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e le
versioni il [Semantic Versioning](https://semver.org/lang/it/).

## [Non rilasciato]

## [0.2.2] — 2026-11-28

### Aggiunto

- **Spostare e ricolorare le annotazioni**: senza strumenti accesi
  un'annotazione si trascina in un altro punto della pagina (resta dentro la
  pagina), e il tasto destro ha *Colore…*. Vale per quelle già nel file e per
  quelle fatte in Plico; evidenziazioni, sottolineature e barrature restano
  sul loro testo, timbri e allegati tengono il loro aspetto. Spostare non
  ridisegna l'annotazione: un timbro o un riquadro col bordo restano come
  erano.
- **Ridimensionare le annotazioni**: le maniglie agli angoli di forme,
  riquadri di testo, disegni, linee e timbri ne cambiano la misura, per quelle
  già nel file e per i disegni fatti in Plico. Il bordo resta dello stesso
  spessore, il testo di un riquadro va a capo di nuovo, un timbro si allarga
  con la sua immagine; le note restano della loro misura. Si annulla con
  `Ctrl+Z`.
- **Testo dei riquadri di testo (FreeText)** già nel file: *Modifica testo…*
  dal tasto destro, e *Colore…* ne cambia il colore del testo.

## [0.2.1] — 2026-11-26

### Aggiunto

- **Annotazioni già nel PDF**: con uno strumento di *Annota* acceso un clic
  toglie anche le annotazioni che il file aveva già (evidenziazioni, note,
  forme, disegni), e il tasto destro su un'annotazione apre *Modifica nota…*
  e *Togli annotazione*, anche senza strumenti accesi. Le note fatte in Plico
  si riscrivono allo stesso modo. Tutto si annulla con `Ctrl+Z` e arriva nel
  file solo al salvataggio; le miniature e la pagina mostrano subito il
  risultato. Link e campi dei moduli non sono annotazioni da toccare qui e
  restano come sono.

### Modificato

- I messaggi di `assert` e dei test saltati sono in inglese, come il resto
  del codice dei test.
- CI: le action del rilascio e del Flatpak girano su Node 24.

## [0.2.0] — 2026-11-21

### Aggiunto

- **Stampa** (*File → Stampa…*, `Ctrl+P`): stampa il documento così come
  verrebbe salvato — pagine eliminate, rotazioni, moduli, testo corretto e
  zone cancellate compresi, anche prima di salvare. Tutte le pagine, un
  intervallo o la pagina corrente; le pagine orizzontali su carta verticale
  vengono girate. Nel Flatpak serve l'accesso a CUPS (`--socket=cups`); il
  `.deb` dipende da libcups. Su Debian e Ubuntu, chi usa il PySide6 del
  sistema deve installare `python3-pyside6.qtprintsupport`. Se un PDF vieta
  la stampa, Plico lo dice e stampa solo dopo una conferma.
- **Duplica pagina** (*Modifica → Duplica pagina*, `Ctrl+D`) e **Inserisci
  pagina vuota** (della misura della pagina scelta, dopo di lei): si
  annullano come ogni altra modifica, e la copia si modifica per conto suo.
- **Ritaglia margini** (*Modifica → Ritaglia margini…*): margini in millimetri,
  come si vedono sullo schermo, per la pagina scelta o per tutte, oppure
  rilevati dal contenuto. Si annulla come ogni modifica; al salvataggio
  diventa la `/CropBox`. Nasconde, non cancella: il dialogo lo dice e rimanda
  a Cancella zona.
- **Annotazioni** (menu *Annota*): Evidenzia (`Ctrl+Shift+H`), Sottolinea
  (`Ctrl+Shift+U`) e Barra (`Ctrl+Shift+K`) sulle parole trascinate, Nota con
  un clic e Disegno a mano libera. Restano modificabili fino al salvataggio
  (un clic con lo strumento acceso le toglie, `Ctrl+Z` le annulla) e poi
  diventano annotazioni PDF vere; quelle che toccano una zona cancellata
  vengono eliminate con lei.
- **Pannello Segnalibri** (*Visualizza → Segnalibri*, una scheda accanto alle
  miniature): mostra l'indice del PDF, porta alla pagina con un clic e
  permette di aggiungere, rinominare, spostare, cambiare livello ed eliminare
  le voci. Ogni modifica si annulla; il salvataggio scrive l'indice del
  pannello. Unendo un PDF, i suoi segnalibri si aggiungono in coda.
- **Proteggi con password** (*File → Proteggi con password…*): salva con una
  password scelta (AES-256) e, se si vuole, senza permesso di stampa, copia o
  modifica, con una password del proprietario facoltativa (se manca e c'è un
  limite, ne viene creata una casuale). Su un file già protetto si può
  scegliere «Nessuna password» per toglierla. Il file salvato viene riaperto,
  così i salvataggi successivi restano protetti.

### Sicurezza

Correzioni da due revisioni della 0.1.8.

- **PDF con sola password del proprietario** (si aprono senza chiedere nulla,
  ma limitano stampa, copia o modifica): il salvataggio li riscriveva in
  chiaro, senza permessi. Ora restano cifrati con gli stessi permessi. Al
  primo salvataggio Plico chiede la password del proprietario: chi la conosce
  la scrive e resta valida anche sul file salvato; lasciando vuoto ne viene
  creata una nuova, casuale, e i limiti restano. Firmarli così come sono su
  disco falliva: ora funziona.
- **«Salva con nome» sopra un PDF protetto non aperto** lo sostituiva con un
  file senza password, senza avvisare. Ora Plico chiede prima (anche per
  «Salva compresso», «Firma» ed «Estrai pagine»).
- **Firme fuori dalle pagine**: un campo firma presente nel modulo ma non in
  una pagina non veniva visto, e il salvataggio toglieva la firma senza
  chiedere. Ora conta anche quello.
- **Firmare un documento con migliaia di campi** bloccava la finestra: la
  scelta del nome del campo firma ora è lineare, come l'apertura.
- Gli errori del dialogo delle firme e i riepiloghi di compressione e OCR
  mostrano sempre testo semplice, mai markup.

### Corretto

- **Ogni salvataggio toglieva segnalibri, titolo, autore e numerazione delle
  pagine** (per esempio «i, ii, iii» in una prefazione): bastava ruotare una
  pagina e salvare. Ora restano, anche unendo ed estraendo pagine: i
  segnalibri seguono le loro pagine e spariscono solo con quelle eliminate.
  Quando si cancella una zona, titolo, autore e segnalibri non vengono
  copiati, perché potrebbero contenere il testo tolto; la conferma lo dice.
- Dopo aver salvato, compresso o firmato sopra un PDF protetto, la riapertura
  automatica chiedeva di nuovo la password; annullando, il documento si
  chiudeva. Ora usa quella già data.
- La compressione di un PDF protetto misurava il guadagno prima della
  cifratura: poteva annunciare un risparmio per un file che cresceva. Ora il
  confronto è col file da sostituire, già cifrato.
- Un errore di scrittura nel salvare un certificato fidato non veniva
  mostrato come errore.
- La finestra «Informazioni su Plico» ha sempre il pulsante OK e non resta in
  memoria dopo la chiusura.

## [0.1.8] — 2026-11-10

### Aggiunto

- **AppImage per ARM64** (`Plico-X.Y.Z-aarch64.AppImage`), per Raspberry Pi
  4 e 5, portatili Snapdragon e Asahi Linux. Richiede glibc 2.39 o successiva
  (Debian 13, Ubuntu 24.04, Fedora 40 o più recenti), perché la chiedono le
  librerie Qt per ARM. Le stesse versioni di Qt, PyMuPDF, pikepdf e pyHanko
  dell'AppImage x86_64.

### Sicurezza

Correzioni da un penetration test della 0.1.7.

- **PDF protetti da password**: salvare (anche compresso o firmato) sopra un
  file protetto lo riscriveva in chiaro, senza dirlo. Ora il file resta
  cifrato (AES-256) con la password usata per aprirlo e gli stessi permessi.
  «Salva con nome» su un file nuovo scrive, come prima, un file non protetto.
- **Cancellazione del testo verticale o inclinato**: «Cancella parola…» e la
  selezione delle parole toglievano solo poche lettere di una parola scritta
  in verticale o in diagonale (intestazioni di tabella, timbri, assi dei
  grafici); il resto restava nel file, estraibile. Ora sparisce tutta.
- **Documenti firmati**: un file firmato senza il flag `/SigFlags` veniva
  preso per non firmato, e il salvataggio toglieva la firma senza chiedere.
  Ora la firma si riconosce dai campi.
- **File temporanei**: durante il salvataggio e la compressione il documento
  passava per un file leggibile dagli altri utenti, se la cartella lo era.
  Ora i temporanei stanno in una cartella che solo l'utente può aprire.
- **Documenti costruiti per bloccare Plico**: un PDF di pochi KB con
  centinaia di migliaia di pagine, o con migliaia di campi su una pagina,
  bloccava la finestra per minuti o la chiudeva. Ora Plico apre al massimo
  20 000 pagine (anche unendo documenti) e non legge i campi di una pagina
  che ne ha più di 1000.
- **Testo dei documenti mostrato come testo**: nomi di file e di campi,
  messaggi d'errore e il nome nel certificato di una firma venivano
  interpretati come HTML, quindi un PDF poteva scrivere nella finestra delle
  firme un finto «Firma valida» in verde, o mettere un link cliccabile in una
  domanda di conferma. Ora si vedono così come sono.
- **Certificati fidati**: Plico ricordava il percorso del file `.pem` e lo
  rileggeva a ogni verifica, quindi chi poteva sostituire quel file decideva
  chi era un firmatario fidato. Ora ne tiene una copia in una cartella sua
  (quelli già scelti vengono copiati alla prima verifica).
- **Controllo degli aggiornamenti**: alcune risposte malformate facevano
  comparire un errore interno di Python invece di «Risposta di GitHub non
  valida».

## [0.1.7] — 2026-11-08

### Corretto

- **AppImage su X11**: su distribuzioni recenti (Arch, Fedora 45) Plico si
  chiudeva all'avvio con un errore di segmentazione nelle sessioni X11. Il
  `.AppImage` portava con sé una libxkbcommon-x11 di Ubuntu 22.04, che non va
  d'accordo con la libxkbcommon più recente del sistema; ora la usa dal
  sistema, insieme alle estensioni di libxcb. Su Wayland il problema non
  c'era. Il `.deb` le chiede come dipendenze.
- **Aggiornamenti**: quando GitHub rifiuta il controllo perché è stato
  raggiunto il suo limite di richieste (60 all'ora per indirizzo IP, contate
  su tutto ciò che esce da quell'indirizzo), Plico lo dice e indica a che ora
  riprovare, invece di un generico «GitHub ha risposto 403».
- **Salva compresso**: un file che non aveva niente da guadagnare poteva,
  una volta ogni tanto, essere scritto lo stesso con «Risparmiato: 10 B (0%)».
  Il confronto delle dimensioni risentiva dell'identificatore casuale che
  ogni salvataggio dava al PDF; ora la compressione conserva quello del
  documento, e a parità di contenuto la dimensione non cambia.

## [0.1.6] — 2026-10-28

### Aggiunto

- **Aggiornamenti**: *Aiuto → Cerca aggiornamenti…* chiede a GitHub se è
  uscita una versione più recente e apre la sua pagina. In *Impostazioni* si
  può accendere un controllo automatico, al massimo una volta al giorno, che
  annuncia una versione nuova con un avviso sopra la pagina e la voce *Aiuto →
  Scarica Plico*. È spento finché non lo si accende: senza, Plico non si
  collega a niente. Lo si offre dove nessuno aggiorna Plico (AppImage, `.deb`,
  pip); il pacchetto dell'AUR lo aggiorna il gestore dei pacchetti, e il
  Flatpak, che non ha accesso alla rete, apre la pagina delle versioni.

### Corretto

- **AppImage**: l'icona di Plico compare nell'area di notifica e sulla
  finestra; prima c'era quella generica dei PDF.
- **Firma**: un certificato valido solo da una data futura viene rifiutato
  subito nel dialogo, invece di far fallire il salvataggio.
- **AUR**: `qt6-translations` tra le dipendenze facoltative, per avere OK,
  Annulla, Sì e No nella lingua dell'interfaccia.

## [0.1.5] — 2026-10-21

### Aggiunto

- Pacchetto **Debian e Ubuntu** (`plico_0.1.5_amd64.deb`): lo stesso
  contenuto dell'AppImage, installato in `/opt/plico` con il menu e l'icona.
- Pacchetto **Arch Linux** `plico` nell'AUR, costruito dal tag firmato; il
  pacchetto già costruito è anche tra gli allegati della release.
- Galleria di screenshot in cima ai README.

### Modificato

- Icona nuova: due fogli e una matita su una piastra blu notte.

### Sicurezza

- AppImage, `.deb` e Flatpak includono `certifi` 2026.10.19: la versione
  precedente si fidava delle radici emSign, le cui chiavi intermedie sono
  state compromesse
  ([GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2)).

## [0.1.4] — 2026-10-20

La prima release con i pacchetti pronti da scaricare. L'applicazione è la
stessa della 0.1.3: cambiano il modo di distribuirla e la firma dei tag.

### Aggiunto

- **AppImage** (`Plico-0.1.4-x86_64.AppImage`) con Python, Qt, PyMuPDF e i
  dati di lingua dell'OCR in cinque lingue; richiede glibc 2.34 o successiva.
- **Bundle Flatpak** (`Plico-0.1.4-x86_64.flatpak`), senza accesso alla
  cartella home.
- `SHA256SUMS` e un'attestazione di provenienza di GitHub per ogni file.
- Release automatiche: `release.yml` verifica la firma del tag, costruisce i
  pacchetti, fa girare l'intera suite di test e pubblica dopo l'approvazione
  del maintainer.

### Modificato

- I tag si firmano con la chiave di rilascio di Plico (OpenPGP,
  `packaging/plico-release-key.asc`). I tag fino a `v0.1.3` erano firmati con
  una chiave SSH.

## [0.1.3] — 2026-10-19

### Aggiunto

- **Impostazioni**: lingua dell'interfaccia a scelta, oppure quella del
  sistema; le lingue senza traduzione ricevono l'inglese.
- Icona facoltativa nell'area di notifica, e una X della finestra che può
  ridurre Plico lì invece di uscire.
- **Guida** in italiano, inglese, francese, tedesco e spagnolo, che si apre
  con `F1`, e il menu Aiuto.

### Corretto

- All'uscita dalla sessione, le modifiche non salvate vengono chieste invece
  di andare perse.
- «Esci» dal menu dell'icona di notifica, durante un OCR o una compressione,
  non blocca più l'interfaccia.
- L'OCR propone la lingua dell'interfaccia scelta, non quella del sistema.
- Niente più scorciatoie doppie nei menu italiani.

## [0.1.2] — 2026-10-19

### Aggiunto

- **Ricerca** nel documento con `Ctrl+F`: ogni occorrenza evidenziata, `F3` e
  `Maiusc+F3` per spostarsi.

### Corretto

- Cancellare un campo di un modulo ora toglie il suo valore dal file con ogni
  struttura di modulo.
- Un campo firma vuoto non fa più risultare firmato il documento, e si
  possono verificare le firme dei file protetti da password.
- Estrai pagine: «1 3» ora significa le pagine 1 e 3.

## [0.1.1] — 2026-10-18

### Modificato

- Le cancellazioni si vedono prima di salvare: la pagina e la miniatura le
  mostrano applicate appena si spegne lo strumento, e vengono confermate prima
  di scriverle.
- Un avviso sopra la pagina conferma i segni e la fine del riconoscimento del
  testo.
- Il Flatpak non ha più accesso alla cartella home: i file passano dal
  portale di selezione.

### Corretto

- La chiusura improvvisa del dialogo di firma sui sistemi con font web
  installati.

## [0.1.0] — 2026-10-18

La prima versione.

- **Pagine**: ruotare, eliminare, riordinare con il trascinamento, unire PDF e
  immagini (anche l'unione si annulla con `Ctrl+Z`), estrarre pagine, creare
  un PDF da foto e scansioni.
- **PDF cifrati**: si aprono con la password.
- **Cancellazione vera**: il contenuto sotto una zona o una parola esce dal
  file, non viene coperto; le zone si spostano e si ridimensionano col mouse.
- **Moduli**: compilazione dei campi AcroForm sulla pagina e nel pannello
  Modulo.
- **Testo**: correggere una riga di testo dove si trova.
- **OCR**: rendere cercabile una scansione.
- **Firma** PAdES e verifica delle firme presenti.
- **Compressione** in salvataggio, scegliendo cosa comprimere e quanto.
- Annulla/ripristina per ogni modifica, rendering asincrono, integrazione
  desktop KDE, interfaccia in cinque lingue, pacchetto Flatpak.

[Non rilasciato]: https://github.com/gradia64/Plico/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/gradia64/Plico/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/gradia64/Plico/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/gradia64/Plico/compare/v0.1.8...v0.2.0
[0.1.8]: https://github.com/gradia64/Plico/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/gradia64/Plico/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/gradia64/Plico/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/gradia64/Plico/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/gradia64/Plico/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/gradia64/Plico/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/gradia64/Plico/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/gradia64/Plico/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/gradia64/Plico/releases/tag/v0.1.0
