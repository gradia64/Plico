# Changelog

Le modifiche di Plico che si notano da fuori, versione per versione. Il
formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e le
versioni il [Semantic Versioning](https://semver.org/lang/it/).

## [Non rilasciato]

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

[Non rilasciato]: https://github.com/gradia64/Plico/compare/v0.1.5...HEAD
[0.1.5]: https://github.com/gradia64/Plico/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/gradia64/Plico/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/gradia64/Plico/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/gradia64/Plico/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/gradia64/Plico/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/gradia64/Plico/releases/tag/v0.1.0
