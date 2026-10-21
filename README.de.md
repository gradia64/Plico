<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/Lang-Italiano-green?style=for-the-badge" alt="Italiano"></a>
  <a href="README.en.md"><img src="https://img.shields.io/badge/Lang-English-blue?style=for-the-badge" alt="English"></a>
  <a href="README.fr.md"><img src="https://img.shields.io/badge/Lang-Français-blue?style=for-the-badge" alt="Français"></a>
  <a href="README.es.md"><img src="https://img.shields.io/badge/Lang-Español-orange?style=for-the-badge" alt="Español"></a>
</p>

# Plico

Ein echter nativer PDF-Editor für Linux, gebaut mit **Qt6** und **PySide6**,
der **PyMuPDF** zum Lesen und Rendern von PDFs und **pikepdf** (qpdf) zum
Komprimieren nutzt.

> Die PDF-Datei wird erst beim Speichern angefasst.

<p align="center">
  <img src="flatpak/screenshots/main.png" alt="Plico — Hauptfenster" width="32%" />
  <img src="flatpak/screenshots/edit.png" alt="Textbearbeitung" width="32%" />
  <img src="flatpak/screenshots/redact.png" alt="Redaktion" width="32%" />
</p>
<p align="center">
  <img src="flatpak/screenshots/form.png" alt="Formular ausfüllen" width="32%" />
  <img src="flatpak/screenshots/search.png" alt="Suche im Dokument" width="32%" />
</p>

## Funktionen

- **Seiten drehen, löschen, neu anordnen** (Drag & Drop in der
  Miniaturleiste)
- **Ein anderes PDF zusammenführen**: dessen Seiten werden zu den bereits
  geöffneten hinzugefügt, ohne etwas zu kopieren, weil jede virtuelle Seite
  weiß, zu welchem Quelldokument sie gehört. Man kann auch ein Bild
  zusammenführen (eine fotografierte Quittung ans Ende eines PDFs)
- **Ein PDF aus Bildern erstellen** (_Datei → Aus Bildern erstellen…_,
  `Ctrl+Shift+N`): Fotos und Scans — PNG, JPEG, TIFF, BMP, GIF — werden
  jeweils eine Seite, in der gewählten Reihenfolge. Ein Scan behält seine
  echte Größe (ein A4 mit 300 dpi bleibt ein A4), ein Handyfoto wird auf ein
  Hochformat-A4 verkleinert, und JPEGs werden ohne Neukomprimierung
  eingebettet
- **Seiten extrahieren** (teilen) in eine neue Datei mit einem Bereich wie
  `1-3,5,8` — die getippte Reihenfolge wird beibehalten, es dient also auch
  zum Neuordnen
- **Einstellungen** (*Einstellungen → Plico konfigurieren…*, `Ctrl+Umschalt+,`):
  die Sprache der Oberfläche — automatisch, also die des Systems, oder eine von
  Italienisch, Englisch, Französisch, Deutsch und Spanisch; bei einer
  Systemsprache, die Plico nicht hat, wird Englisch verwendet — und das Icon im
  Benachrichtigungsbereich. Mit dem Icon kann das X Plico auch in den
  Benachrichtigungsbereich minimieren statt zu schließen: beendet wird über
  *Datei → Beenden* (`Ctrl+Q`) oder «Beenden» im Menü des Icons. Die Sprache
  ändert sich beim nächsten Start
- **Rückgängig/Wiederholen** komplett, gestützt auf `QUndoStack`
- **Asynchrones Rendering** in einem separaten Thread — die Oberfläche
  blockiert nie
- **Lazy Rendering**: es werden nur die sichtbaren Seiten gerendert, nicht
  das ganze Dokument
- **Seitencache mit Byte-Budget**, LRU für Miniaturen
- **Speichern in eine temporäre Datei**: das ursprüngliche PDF wird nie
  angefasst. `Ctrl+S` speichert in die geöffnete Datei (oder in das letzte
  «Speichern unter»), `Ctrl+Shift+S` fragt wo; der Titel markiert
  ungespeicherte Änderungen mit `*`, und Schließen oder Öffnen einer anderen
  Datei fragt vor dem Verlust. `Ctrl+W` (_Datei → Schließen_) schließt das
  Dokument und lässt das Fenster offen
- **Komprimiert speichern** in drei Stufen, plus «nur Bilder» und «zu
  resamplende Seiten»: der Gewinn ist der echte, gemessen an der tatsächlich
  geschriebenen Datei (und die «leichte» Stufe ist verlustfrei)
- **Echte Redaktion**: man zeichnet eine Zone über die zu löschenden Daten, oder
  zieht über die Wörter, und beim Speichern wird der Text **entfernt**, nicht
  nur überdeckt — was übrig bleibt, lässt sich nicht mehr kopieren oder
  suchen. Auch Formularfelder und Notizen unter der Zone verschwinden, während
  das Redigieren eines Wortes die Zeilen darüber und darunter nicht anrührt
- **AcroForm-Formulare ausfüllen**: man schreibt auf die Seite, mit dem
  «Formular»-Dock in Sicht — Text, auch mehrzeilig, Kästchen und
  Dropdowns — und die Werte landen beim Speichern in der Datei, mit
  Rückgängig/Wiederholen
- **Minimale Textbearbeitung**: ein Klick auf eine Zeile öffnet einen Editor
  auf der Seite; der alte Text wird aus der Datei entfernt und der neue an
  derselben Stelle geschrieben, mit derselben Größe, Farbe und — wenn
  installiert — derselben Schrift. Benachbarte Zeilen bleiben intact, auch bei
  einfachem Zeilenabstand
- **OCR** (_Bearbeiten → Text erkennen…_, `Ctrl+Shift+O`): ein Scan wird
  **durchsuchbar und auswählbar**, ohne sein Aussehen zu ändern — der
  erkannte Text wird unter das Bild geschrieben, unsichtbar. Man wählt, welche
  Seiten und in welcher Sprache, und jeder Durchlauf ist ein einziger
  Rückgängig-Schritt
- **Signieren** (_Datei → Signieren…_, `Ctrl+Shift+D`): eine **PAdES**-
  Signatur mit dem eigenen Zertifikat, unsichtbar oder in einem Rahmen auf der
  Seite gedruckt, und _Datei → Signaturen prüfen…_ um nachzulesen, wer
  signiert hat und ob das Dokument danach angefasst wurde. Eine zweite
  Signatur wird zur ersten hinzugefügt, ohne sie zu brechen

### Abnahmevoraussetzung

Ein PDF mit **300 Seiten** öffnet in unter 2 Sekunden und bleibt reaktionsfähig:
beim Öffnen werden 2 Seiten und ~12 Miniaturen gerendert, nicht 300. Der
Seitencache enthält höchstens eine Handvoll Einträge, unabhängig von der
Dokumentgröße. Abgedeckt von
[`test_large_document_stays_responsive`](https://github.com/gradia64/Plico/blob/main/tests/test_integration.py).

## Architektur

```
plico/
├── pyproject.toml
└── src/plico/
    ├── app.py                 # Einstiegspunkt
    ├── main_window.py         # MainWindow + Verdrahtung worker/model/view
    ├── model/
    │   ├── document.py        # DocumentModel, PageItem
    │   ├── commands.py        # QUndoCommand: RotatePage, DeletePage, AddRedaction, SetFieldValue…
    │   ├── redact.py          # Redaktionsrechtecke, Rotationsmatrizen
    │   ├── forms.py           # AcroForm-Felder: lesen, schreiben, leeren
    │   ├── textedit.py        # Bearbeitung einer Textzeile: Span, Prüfung, Neuschreiben
    │   ├── ocr.py             # Erkennung mit Tesseract, unsichtbare Schicht, Sprachen
    │   ├── sign.py            # PAdES-Signatur mit pyHanko und Signatur-Neulesen
    │   ├── images.py          # von Bildern zu PDF: A4, dpi, EXIF, intakte JPEGs
    │   ├── save.py            # save_as(), save_compressed(), extract_pages()
    │   ├── assemble.py        # Seiten aus mehreren PDFs, Formularfelder intact
    │   └── optimize.py        # Komprimierungsstufen, optimize_in_place()
    ├── rendering/
    │   └── worker.py          # RenderWorker in QThread
    └── widgets/
        ├── page_view.py       # QScrollArea: Rendering, Breite anpassen, HiDPI, Redaktion, Felder
        ├── thumbnail_bar.py   # QListView + Modell + Cache, Lazy Loading
        ├── form_panel.py      # «Formular»-Dock: ein Editor pro Feld
        ├── ocr.py             # Dialog Sprachen/Seiten und Erkennungsaufgabe
        ├── sign.py            # Dialoge für Signatur und Signaturprüfung
        └── compress.py        # Optionendialog, format_size, Aufgabe
```

### Schlüsselkonzept

Das Modell verändert das PDF nie: es ist nur eine Liste von **virtuellen
Seiten**. Jede virtuelle Seite ist ein Paar `(source_id, source_index)` plus
die vom Benutzer gewählte Rotation. Alles leitet sich aus dieser Liste ab:

- **Rückgängig/Wiederholen**: manipuliert eine Python-Liste, nicht die Datei
- **Zusammenführen**: ein PDF hinzuzufügen bedeutet nur, Seiten anzuhängen,
  die auf eine zweite `source_id` zeigen; keine Seite wird kopiert
- **Rendering**: der Worker öffnet die Quelldokumente schreibgeschützt, auf
  Anforderung, und rendert ohne sich mit dem Modell abzustimmen
- **Speichern**: materialisiert die Liste, indem jede Quelle einmal kopiert
  und dann die Seiten in Reihenfolge in die Ausgabedatei gesetzt werden —
  zweimal aus derselben Quelle zu kopieren würde Formularfelder umbenennen
  oder verlieren

Die Identität einer Seite ist immer das Paar `(source_id, source_index)`,
nie nur `source_index`: nach einem Zusammenführen haben zwei Seiten
regelmäßig denselben Index in verschiedenen Dokumenten, und nur einen zu
verwenden würde sie zu einer einzigen kollabieren lassen (falsche
Miniatur, Pixmap aus dem Cache fälschlich wiederverwendet).

Die Ansichten **beobachten das Modell**: `PageView` und `ThumbnailBar`
verbinden sich mit den Signalen `changed` / `page_changed`, sodass ein
Rückgängig automatisch auf beiden reflektiert wird, ohne dass das Fenster
sich merken muss, sie zu aktualisieren.

### Rotation: zwei Werte, nicht einer

`base_rotation` ist das ursprüngliche `/Rotate` des PDF, `rotation` ist der
vom Benutzer gewählte Versatz. Das Rendering setzt beide zusammen, das
Speichern schreibt die Summe (`total_rotation`). Die Cache-Schlüssel
enthalten die Rotation, sonst würde eine gedrehte Seite die vorherige
Miniatur wiederverwenden.

### Speichern über die geöffnete Datei

Über dieselbe Datei zu speichern, die man liest, ist erlaubt: das neue
Dokument wird in eine temporäre Datei im selben Ordner geschrieben und
ersetzt das Original erst am Ende. Ein Schreibfehler zerstört also nie die
Datei des Benutzers.

Nach einem Zusammenführen gibt es mehr als eine Quelle, daher deckt die
Prüfung **alle** Quellen ab: über irgendeines der geöffneten PDFs zu
speichern läuft über die temporäre Datei, weil PyMuPDF nicht in ein
Dokument schreiben kann, das es gerade liest.

Nach dem Speichern über die geöffnete Datei **öffnet Plico** die
gespeicherte Datei neu: das ist jetzt das Dokument, mit Löschungen,
Rotationen und Redaktionen bereits drin. Deshalb können die bis dahin
gemachten Änderungen nicht mehr rückgängig gemacht werden. Seiten über eine
geöffnete Datei zu extrahieren ist dagegen nicht erlaubt.

### Kompression: wo der Gewinn wirklich herkommt

«Komprimiert speichern» (`Ctrl+Shift+C`) schreibt eine kleinere Kopie des
virtuellen Dokuments — respektiert also Löschungen, Neuordnungen und
Rotationen — und lässt die ursprünglichen PDFs unangetastet.

| Stufe | Was sie tut | Verlustfrei? |
| --- | --- | --- |
| **Leicht** | fusioniert fragmentierte Content Streams, verdichtet die Struktur | ja |
| **Mittel** | wie oben, plus Bilder über 200 dpi auf 150 herunter (Qualität 80) | nein |
| **Stark** | Bilder über 150 dpi auf 96 herunter (Qualität 60) | nein |

Der größte Gewinn kommt nicht von den Bildern, sondern von mutools `clean`:
ein PDF, das Kopien und Bearbeitungen durchlaufen hat, schleppt Hunderte
winzige Content Streams mit, und sie zu fusionieren ist auf einem
Textdokument 188 KB → 12 KB (6 %) wert. Bei einem Scan hat die Struktur
nichts zu geben, und nur die Arbeit an den Bildern zählt (ein JPEG von
3,4 MB über 3 Seiten bleibt bei «leicht» bei 100 %, fällt bei «mittel» auf
52 % und bei «stark» auf 36 %).

Die Stufe sagt _wie viel_, nicht _was_: unter dem Dropdown gibt es zwei
weitere Wahlen. **«Nur Bilder»** überspringt die Repackung der Datei —
nützlich bei einem Scan, wo der Gewinn in den Bildern liegt, während bei
einem reinen Textdokument nichts gewonnen wird und das Programm das sagt,
statt eine identische Kopie zu schreiben. **«Zu resamplende Seiten»** lässt
die Bilder der anderen Seiten intact, nützlich wenn schwere Scans zwischen
Textseiten liegen. Es gibt einen Fall, in dem nichts gewonnen wird: wenn
sich zwei Seiten dasselbe Bild teilen, würde das Komprimieren nur einer die
andere zwingen, eine eigene Kopie zu bekommen, und die Datei würde wachsen
— dann wird nichts geschrieben und die Meldung erklärt warum.

Der Gewinn ist keine Schätzung: die komprimierte Datei wird wirklich
geschrieben (neben dem Ziel) und erst danach sagt das Programm, wie viel sie
wiegt, und übernimmt sie nur, wenn sie gewonnen hat.

Die Kompression läuft in einem separaten Thread, so dass das Fenster auch bei
großen Dateien reaktionsfähig bleibt.

### Redaktion: der Text verschwindet wirklich

`Ctrl+Shift+X` (_Bearbeiten → Zone redigieren_) aktiviert das Werkzeug: man
zieht ein Rechteck über die zu löschenden Daten, ein einfacher Klick auf eine
Zone hebt sie auf, `Esc` verlässt. Eine bereits gezeichnete Zone wird
**korrigiert, ohne sie neu zu zeichnen**: die Ecken skalieren sie, die Mitte
verschiebt sie. Die Zonen bleiben **bis zum Speichern bearbeitbar** — sie
sind Rückgängig-Befehle wie die anderen (`Ctrl+Z`), und die dunkle Vorschau
auf der Seite zeigt genau, wo sie landen.

Beim Speichern schreibt PyMuPDF die Content Streams neu und **entfernt** die
Wörter, die in die Zone fallen: in der Datei bleiben weder der Text noch das
Bild unter dem Rechteck. Ein schwarzes Rechteck darüber zu zeichnen — was
viele Werkzeuge tun — würde das Geheimnis kopierbar und suchbar lassen. Mit
dem Inhalt verschwinden auch die **Notizen** und die **Formularfelder**, die
die Zone berührt: ein mit einem Namen ausgefülltes Feld würde sonst in der
Datei bleiben, Wert eingeschlossen.

`Ctrl+Shift+F` (_Bearbeiten → Wort redigieren…_) sucht dagegen ein Wort auf
**allen** Seiten und markiert jede Fundstelle auf einmal, als einen einzigen
Rückgängig-Schritt. Es sucht auch im von OCR erkannten Text, schon vor dem
Speichern.

`Ctrl+Shift+L` (_Bearbeiten → Auswahl redigieren_) ist der dritte Weg, der,
den man von einem Editor erwartet: man zieht über die zu löschenden Wörter und
sie werden **ganz** markiert, eines nach dem anderen, mit einer Markierung so
eng wie das Wort. Das Ziehen ist eine einzige Geste, so dass ein `Ctrl+Z`
die ganze Auswahl rückgängig macht; Ziehen, wo kein Text ist, lässt nichts
zurück; ein Klick auf eine Markierung entfernt sie, wie bei einer Zone, und
auch eine Markierung lässt sich verschieben und skalieren. Funktioniert auch
auf von OCR gelesenen Wörtern.

Vier Dinge zu wissen:

- Wörter werden **ganz** genommen (eine Markierung in der Mitte eines
  Wortes würde nichts verbergen), und die kleinste Einheit ist das Wort, nicht
  der Buchstabe;
- eine Wortmarkierung — aus _Wort redigieren_ oder _Auswahl redigieren_ —
  entfernt den Text **nur seiner Zeile**: bei einfachem Zeilenabstand
  berühren die Buchstaben der Zeilen darüber und darunter ihren Rahmen und
  bleiben, wo sie sind. Eine **gezeichnete** Zone dagegen löscht alles, was
  sie berührt, weil das gezeichnet wurde, und dasselbe gilt für eine
  Wortmarkierung, die verschoben oder skaliert wurde;
- `apply_redactions()` entfernt auch Vektorgrafik, die das Rechteck berührt,
  so dass ein Rahmen oder eine Tabelle, die über die Markierung verlaufen,
  verschwinden können;
- ein Klick auf eine Markierung entfernt sie, auch wenn die Maus sich um ein
  Pixel bewegt hat: es ist ein Klick, kein Ziehen, und `Ctrl+Z` setzt sie
  genau dorthin zurück, wo sie war.

PDF-Metadaten sind dagegen kein Risiko: die Ausgabedatei wird nur aus den
Seiten neu aufgebaut, so dass `/Info`, XMP und Anhänge nie durchkommen.

### Textbearbeitung: eine Zeile nach der anderen

`Ctrl+Shift+T` (_Bearbeiten → Text bearbeiten_) aktiviert das Werkzeug: ein
Klick auf eine **bereits vorhandene** Zeile im PDF öffnet einen kleinen Editor
darüber, **Enter** bestätigt, **Esc** bricht ab. Ein Klick, wo kein Text ist,
oder auf einer Seite, die nur ein Bild ist (ein Scan), sagt das neben dem
Zeiger. Das Werkzeug korrigiert den Text, der da ist: es fügt keinen neuen
Text an einer leeren Stelle hinzu. Die Korrektur ist sofort auf der Seite
sichtbar und ist ein Befehl wie die anderen (`Ctrl+Z`); sie gelangt erst
beim Speichern in die Datei, wo der alte Text aus dem Content Stream
**entfernt** wird — nicht überdeckt — und der neue an derselben Stelle
geschrieben. Hintergrund, Tabellenränder und Text daneben bleiben, ebenso
die Zeilen darüber und darunter: der alte Text wird aus einem Band um die
Zeile entfernt, nicht aus ihrem Rahmen, der bei einfachem Zeilenabstand auch
die Nachbarn berühren würde.

Es ist eine _minimale_ Bearbeitung, und sie sagt das: ein Text, der nicht in
den freien Raum passt (bis zum Zellenrand, zum nächsten Wort oder zum
Seitenrand, auch auf einer gedrehten Seite), wird bis auf 80 % verkleinert
und darüber hinaus abgelehnt, mit dem Grund in der Statusleiste. Vertikaler
Text und Type3-Schriften werden nicht bearbeitet. Die Schrift ist die des
Dokuments, wenn sie wiederverwendet werden kann, sonst dieselbe auf dem
System installierte, sonst ein Doppelgänger (Serif, Sans oder
Monospace) mit demselben Stil.

### Formulare: das PDF ausfüllen, nicht nur lesen

Man füllt **auf der Seite** aus: ein Klick auf ein Textfeld öffnet den Editor
dort, wo das Feld ist, ein Kästchen wird dort angekreuzt, wo man geklickt
hat, ein Radiobutton wählt die Antwort, die er darstellt. Das **Formular**-Dock
(rechts) listet die Felder der angezeigten Seite und bleibt der Weg für
die, die sich auf der Seite nicht tippen lassen — Dropdowns, mehrzeiliger
Text, schreibgeschützte Felder. Die Werte bleiben **bis zum Speichern
bearbeitbar** und durchlaufen dieselbe Rückgängig/Wiederholen wie der Rest
(`Ctrl+Z`).

Ein AcroForm-Feld ist kein PDF-Inhalt, sondern eine Annotation mit einem
Wert, und Plico behandelt es als solche: die **Beschreibungen** der Felder
kommen aus der Quelle, die **Werte**, die man schreibt, leben im Modell, und
`save.py` wendet sie beim Materialisieren der Seiten an — vor den
Redaktionen, so dass eine Redaktion über einem Feld es mitnimmt. Der auf der
Seite gezeichnete Wert ist der des Modells, also der, der _im_ Datei sein
wird.

Ein Feld wird **nur geschrieben, wenn man es anfasst**: ein nie geöffnetes
behält den Wert, den es in der Quelle hatte, was nicht dasselbe ist wie es zu
leeren. Eine Gruppe von Radiobuttons ist **eine Frage** — das Dock zeigt sie
als Dropdown mit den Antworten — und man kann auch wählen, indem man in der
Seite auf einen klickt. Signaturen gehören zu _Datei → Signieren…_.

### OCR: einen Scan durchsuchbar machen

_Bearbeiten → Text erkennen…_ (`Ctrl+Shift+O`) liest die gewählten Seiten mit
Tesseract und schreibt unter das Bild eine **unsichtbare Textschicht**
(Rendermodus 3). Die Seite sieht identisch aus, aber der Text lässt sich
auswählen, kopieren, mit `Ctrl+F` suchen — und _Wort redigieren_
(`Ctrl+Shift+F`) findet ihn endlich, was auf einem unmarkierten Scan
unmöglich ist. Er findet ihn sofort, nicht erst nach dem Speichern: die
Schicht gelangt beim Speichern in die Datei, aber die Suche schaut auch auf
die gerade erkannten Wörter.

Die Erkennung kostet (etwa eine halbe Sekunde pro A4-Seite bei 300 dpi), daher
ist sie nicht automatisch: man gibt die Seiten wie bei *Seiten extrahieren*
an (`3`, `4-8`, `1-3,5`; beim Öffnen sind alle vorgeschlagen) und wählt die
Sprache, mit der Sprache der Oberfläche und Englisch zusammen als Vorschlag. Sie läuft im Thread-Pool mit
einem abbrechbaren Fortschrittsbalken — während sie läuft, nimmt das Fenster
keine Seitenbearbeitungen an den Seiten an, die sie liest — und jeder
Durchlauf ist **ein einziger** Rückgängig-Schritt: ein `Ctrl+Z` entfernt die
Schicht von allen Seiten auf einmal.

Die Schrift der Schicht ist eine der Base-14 und wird nicht eingebettet, also
fügt das Durchsuchbarmachen eines Scans kein Byte hinzu. Wörter, die das PDF
bereits enthielt, werden nicht neu geschrieben: eine Seite, halb Text und
halb Scan, endet nicht mit doppeltem Text.

Sprachdaten (`*.traineddata`) kommen in
`~/.local/share/plico/tessdata/`, ohne root; das Flatpak bringt bereits
Italienisch, Englisch, Spanisch, Französisch und Deutsch mit und schlägt die
Oberflächensprache zusammen mit Englisch vor. Die Tesseract-Bibliothek muss
vorhanden sein: im Flatpak ist sie eingebaut (siehe Flatpak), auf einer
Distribution ist es das Paket `tesseract` / `libtesseract`.

### Signieren: ein signiertes PDF, kein Stempel

_Datei → Signieren…_ (`Ctrl+Shift+D`) signiert das Dokument mit einem
PKCS#12-Zertifikat (`.p12` / `.pfx`) und erzeugt eine **PAdES**-Signatur —
das PDF-Signaturprofil, das europäische Leser erkennen. Man wählt, ob die
Signatur unsichtbar bleibt oder in einem Rahmen unten rechts mit Name, Datum
und Grund erscheint: der Rahmen ist Seiteninhalt, also kann man ihn nicht
entfernen, ohne die Signatur zu brechen.

Vier Dinge, die diese Implementierung tut, und eines, das sie nicht tut:

- **Die Signatur ist das letzte Byte der Datei.** Zuerst wird das Dokument
  materialisiert (mit allen ausgefüllten Feldern, neu geschriebenem Text,
  angewandten Redaktionen, gedrehten Seiten), dann signiert. Die umgekehrte
  Reihenfolge würde eine Signatur erzeugen, die eine andere Version des
  Dokuments abdeckt als die, die der Benutzer sieht.
- **Signieren übernimmt die signierte Datei.** Nach _Signieren…_ zeigt die
  Sitzung auf die neue Datei, weil weiter auf der Seitenliste zu arbeiten,
  die sie erzeugt hat, die Signatur beim nächsten Speichern verlieren würde.
- **Eine zweite Signatur wird zur ersten hinzugefügt.** Wenn das signierte
  Dokument keine ungespeicherten Änderungen hat, wird die neue Signatur an
  die Datei angehängt, wie sie ist (ein inkrementelles Update), und die
  erste bleibt gültig. Mit ungespeicherten Änderungen muss die Datei neu
  geschrieben werden und die vorherige Signatur würde nichts mehr abdecken,
  daher wird sie entfernt und nur die neue bleibt: das Programm sagt das
  vorher und fragt, ob fortgefahren werden soll.
- **Über eine signierte Datei zu speichern fragt vorher.** Ein normales
  Speichern schreibt das PDF von Grund auf neu: die Signatur ist weg, und die
  gespeicherte Datei trägt keine kaputte an ihrer Stelle. Das Programm sagt
  das und wartet auf ein «Ja», statt es einfach zu tun.
- **Es entscheidet nicht, wem man vertraut.** Plico bringt keinen
  Autoritätsspeicher mit: eine intakte, gültige Signatur eines unbekannten
  Zertifikats wird als «intakt, aber das Zertifikat ist nicht unter denen,
  die du als vertrauenswürdig betrachtest» angezeigt. Man fügt die
  Zertifikate, denen man vertraut, einzeln hinzu (`.pem`-Dateien) und sie
  bleiben in `QSettings`.

_Datei → Signaturen prüfen…_ liest die Signaturen aus der **Datei auf der
Festplatte** neu und unterscheidet die Fälle, die zählen: Signatur intakt und
vertrauenswürdig; intakt aber von einem unbekannten Zertifikat (amber, nicht
rot: es ist trotzdem eine echte Signatur); intakt aber auf einem Dokument,
das **nach der Signatur geändert** wurde — gültig nur für die signierte
Version; **gebrochene** Signatur, das heißt der Inhalt, den sie abdeckte, hat
sich geändert (rot, immer, auch wenn die Datei spätere Revisionen hat);
ungültige Signatur oder abgelaufenes Zertifikat. Ein Modul, das nie signiert
wurde, wird nicht mit einem signierten Dokument verwechselt.

### Desktop-Integration (KDE)

- **Icons aus dem Theme** (`QIcon.fromTheme`: `document-open`,
  `document-save-as`, `edit-undo`, `object-rotate-right`, `zoom-in`, …): keine
  Grafik-Assets im Paket. Wenn das Theme das Icon nicht liefert, bleibt die
  Aktion ohne Icon, statt ein leeres Quadrat zu zeigen.
- **Fünf Sprachen**: Italienisch, Englisch, Spanisch, Französisch und
  Deutsch, auch in den Schaltflächen der Standarddialoge von Qt und in den
  Store-Metadaten (siehe «Plico übersetzen»).
- **Sitzungszustand in `QSettings`** (`~/.config/Plico/plico.conf`):
  Fenstergeometrie, Layout von Docks und Werkzeugleiste und Zoomfaktor.

## Voraussetzungen

- Python ≥ 3.11
- PySide6 ≥ 6.7
- PyMuPDF (pymupdf) ≥ 1.24.3
- pikepdf ≥ 9 (gezielte Kompression)
- pyHanko ≥ 0.37 (PAdES-Signatur; bringt Kryptographie und Validierung mit)
- Tesseract (Bibliothek, 4 oder 5) und mindestens eine Sprachdatei für OCR —
  das Flatpak bringt beides mit

## Installation

Jede [Release](https://github.com/gradia64/Plico/releases) bietet diese
Pakete für Linux x86_64, gebaut vom signierten Tag:

- **AppImage** (`Plico-X.Y.Z-x86_64.AppImage`): eine einzige Datei, mit
  Python, Qt, PyMuPDF und den Sprachdaten des OCR darin. Ausführbar machen
  (`chmod +x Plico-X.Y.Z-x86_64.AppImage`) und starten. Benötigt glibc 2.34
  oder neuer: Debian 12, Ubuntu 22.04, Fedora 35 oder neuer.
- **Debian und Ubuntu** (`plico_X.Y.Z_amd64.deb`): derselbe Inhalt wie das
  AppImage, installiert in `/opt/plico` mit Menüeintrag und Icon;
  `sudo apt install ./plico_X.Y.Z_amd64.deb`. Dieselben Voraussetzungen wie
  das AppImage; aktualisiert sich nicht selbst.
- **Flatpak** (`Plico-X.Y.Z-x86_64.flatpak`): `flatpak install --user
  Plico-X.Y.Z-x86_64.flatpak` lädt die KDE-Runtime von Flathub, die es
  braucht. Aktualisiert sich nicht selbst: die neue Version wird genauso
  installiert.
- **Arch Linux**: das Paket `plico` aus dem AUR (`paru -S plico` oder ein
  anderer Helper) wird vom signierten Tag gebaut, den `makepkg` mit dem
  Release-Schlüssel prüft; das bereits gebaute Paket ist auch bei den
  Release-Anhängen (`pacman -U plico-X.Y.Z-1-any.pkg.tar.zst`).

Daneben gibt es `SHA256SUMS` und für jede Datei eine Herkunftsbescheinigung
von GitHub: `gh attestation verify Plico-X.Y.Z-x86_64.AppImage -R
gradia64/Plico` prüft, dass die Datei von der CI dieses Repositories von
diesem Tag erzeugt wurde.

Aus dem Quellcode, für die Entwicklung:

```
pip install -e ".[dev]"
```

Der Einstiegspunkt akzeptiert die zu öffnenden Dateien, wie man es von einer
Desktop-App erwartet:

```
plico relazione.pdf              # öffnet
plico a.pdf b.pdf                # öffnet a.pdf und führt b.pdf zusammen
plico ricevuta.jpg a.pdf         # erstellt ein Dokument aus dem Foto und führt a.pdf zusammen
```

Er akzeptiert auch `file:///…`-URLs, die manche Launcher übergeben. Die
`.desktop`-Datei erwartet trotzdem Pfade (`Exec=plico %F`).

## Flatpak

Das Packaging liegt in `flatpak/` und ist dafür gedacht, auf Flathub
veröffentlicht zu werden.

| Datei | Rolle |
| --- | --- |
| `io.github.gradia64.plico.json` | Anwendungsmanifest |
| `python3-pymupdf.json` | Modul für PyMuPDF, mit Wheel und fixiertem `sha256` |
| `python3-pikepdf.json` | Modul für pikepdf, mit Wheel und fixiertem `sha256` |
| `python3-pyhanko.json` | Modul für pyHanko und seine Abhängigkeiten, immer aus Wheels |
| `io.github.gradia64.plico.desktop` | Launcher (registriert `application/pdf`, empfängt Pfade mit `%F`) |
| `io.github.gradia64.plico.metainfo.xml` | AppStream-Metadaten |
| `io.github.gradia64.plico.svg` | Icon |

Acht nicht offensichtliche Entscheidungen:

- **`base: io.qt.PySide.BaseApp`** statt PySide6 mit pip zu installieren. Die
  BaseApp von Flathub enthält PySide6 bereits kompiliert und auf das Qt von
  `org.kde.Platform` abgestimmt, so dass das Bundle Qt nicht dupliziert und
  nicht die Version des Runtimes überschreibt riskiert. Deshalb verwendet die
  Installation der Anwendung `--no-deps`: PySide6 kommt aus dem Runtime,
  PyMuPDF aus seinem Modul, und pip soll nicht einmal versuchen, PySide6
  von PyPI herunterzuladen.
- **PyMuPDF aus einem `manylinux`-Wheel** (`cp310-abi3`, gültig für jedes
  Python ≥ 3.10, also auch für das 3.13 des Runtimes) und nicht aus den
  Quellen: MuPDF im Manifest zu kompilieren würde `swig` und mehrere Minuten
  Build erfordern.
- **pikepdf aus einem `cp313`-Wheel** (dem Interpreter der BaseApp, der nicht
  der des Venvs ist) **mit `--no-deps` installiert**: pikepdf deklariert
  `Pillow`, `lxml` und `packaging`, aber `open()` und `save()` importieren
  sie nicht, und `packaging` ist schon in der BaseApp. Wenn die Bild-APIs
  oder PDF/A-Unterstützung gebraucht würden, müssten auch deren Wheels
  hinzugefügt werden.
- **pyHanko aus Wheels, in einem einzigen Modul**
  (`python3-pyhanko.json`): pyHanko zieht `cryptography`, `asn1crypto`,
  `aiohttp`, `lxml` und ein Dutzend weitere Abhängigkeiten nach sich, alle
  reines Python oder mit `manylinux`-Wheel für das 3.13 der BaseApp, so dass
  sie mit `--no-index --no-deps` in einem Rutsch installiert werden. Es sind
  die zwanzig im Modul aufgelisteten Dateien, jede mit ihrem `sha256`: die
  digitale Signatur ist der Teil des Programms, in dem «ungefähr diese
  Version» keine akzeptable Antwort ist.
- **Die Übersetzungen werden während des Builds kompiliert**: `lrelease`
  existiert nur im SDK von Qt, nicht im Runtime, und die `.qm`-Dateien sind
  die einzigen, die zur Laufzeit nötig sind. Das Modul `plico` installiert
  die `.ts` mit dem Paket und kompiliert sie dann nach
  `/app/share/plico/translations`, so dass der Compiler nicht im Bundle landet.
- **`cleanup-commands: /app/cleanup-BaseApp.sh`**, von der BaseApp
  verlangt.
- **Kein Zugriff auf die Home** (kein `--filesystem`): jede Datei läuft über
  den Dateiauswahldialog des Portals (`org.freedesktop.portal.FileChooser`),
  den Qt innerhalb von Flatpak selbst nutzt. Plico sieht das Dokument als
  `/run/user/<uid>/doc/<id>/name.pdf` und liest und schreibt dort, inklusive
  atomarem Speichern (das Temporäre im selben Ordner und `os.replace`
  funktionieren auch im Document-Portal); um in den Dialogen einen Pfad
  vorzuschlagen, nutzt es stattdessen den echten, den das Portal im
  erweiterten Attribut `user.document-portal.host-path` bereitstellt. Der
  Launcher nutzt `%F`, so dass ein Doppelklick bereits als im Portal
  exportierter Pfad ankommt.
- **`--talk-name=org.kde.StatusNotifierWatcher`**, die einzige D-Bus-Berechtigung:
  ohne sie existiert der Benachrichtigungsbereich in der Sandbox nicht und das
  Icon der Einstellungen erscheint nie (getestet unter Plasma). Qt registriert
  das Icon unter seinem eindeutigen Bus-Namen, daher müssen keine weiteren
  Namen besessen werden. Das Icon ist optional und standardmäßig aus.

Bauen und für den eigenen Benutzer installieren:

```
# einmal: Builder, SDK und BaseApp
flatpak remote-add --user --if-not-exists flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.flatpak.Builder//stable \
    org.kde.Sdk//6.11 io.qt.PySide.BaseApp//6.11

# build + install. Der Cache liegt AUSSERHALB des Projekts: build-dir/ und
# .flatpak-builder/ im Baum werden von globalen Suchen gefunden und enthalten
# Kopien der Quellen.
flatpak run org.flatpak.Builder --force-clean --user --install \
    --install-deps-from=flathub \
    --state-dir="$HOME/.cache/plico-flatpak/state" \
    "$HOME/.cache/plico-flatpak/build" \
    flatpak/io.github.gradia64.plico.json

flatpak run io.github.gradia64.plico
```

Die **Screenshots** des Stores liegen in `flatpak/screenshots/` und werden von
`tools/screenshots.py` aus der echten App erzeugt; im Metainfo zeigen sie auf
das Tag des letzten Releases, und jedes Release setzt sie auf sein neues Tag.

### Veröffentlichen

Flathub baut nicht aus dem Checkout, sondern aus einem Git-Tag, der auch auf
seinen Commit festgezurrt ist. Das Manifest in `flatpak/` bleibt das der
Entwicklung (`type: dir`), und das einzureichende erzeugt
`tools/flathub_manifest.py` **aus dem Tag**. Vor dem Schreiben prüft es, dass:

- das Tag `v` + die Version aus `pyproject.toml` + das letzte `<release>` der
  Metainfo ist;
- die Screenshots der Metainfo auf das Tag und nicht auf `main` zeigen;
- das Tag annotiert ist, von einem Schlüssel aus `.github/allowed_signers`
  signiert und auf `origin` mit demselben Objekt vorhanden.

Tags werden mit dem **SSH**-Schlüssel signiert (kein PGP aufzubewahren).
Einmal pro Checkout:

```
git config gpg.format ssh
git config user.signingkey ~/.ssh/id_ed25519.pub
git config tag.gpgSign true
git config gpg.ssh.allowedSignersFile "$PWD/.github/allowed_signers"
```

Damit GitHub das Tag als «Verified» anzeigt, muss derselbe Schlüssel auch als
_signing key_ des Kontos registriert werden (Settings → SSH and GPG keys →
New SSH key → Signing key).

Bei jedem Release:

```
# 1. Version in pyproject.toml, neues <release> und Screenshot-URLs
#    (…/Plico/vX.Y.Z/flatpak/screenshots/…) in der Metainfo; Commit und Push
# 2. signiertes, verifiziertes, veröffentlichtes Tag
git tag -s v0.1.0 -m "Plico 0.1.0"
git tag -v v0.1.0
git push origin v0.1.0
# 3. das Manifest für Flathub, mit den Modulen, die es einschließt
python tools/flathub_manifest.py v0.1.0 ~/flathub/io.github.gradia64.plico
```

`--allow-unsigned --offline` macht einen Probelauf auf einem lokalen
unsignierten Tag.

## Entwicklung

```
# Tests (ohne Display, dank QT_QPA_PLATFORM=offscreen).
# NB: pytest ist nicht in .venv/bin, daher über python -m
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q

# Lint + Typen
ruff check src/ tests/ tools/
mypy src/plico

# Start
plico            # oder: python -m plico.app

# Screenshots für den Store (flatpak/screenshots), auf Englisch oder in einer anderen Sprache
QT_QPA_PLATFORM=offscreen python tools/screenshots.py [it|es|fr|de]
```

Die **CI** (GitHub Actions, `.github/workflows/`) macht dasselbe bei jedem
Push und Pull Request: `ci.yml` führt Tests, `ruff` und `mypy` auf Python
3.11 und 3.13 aus und validiert Metainfo, `.desktop` und Manifest;
`flatpak.yml`, auf `main` und auf Anforderung vom Actions-Tab, baut das echte
Flatpak, übergibt es dem Linter von Flathub (`flatpak-builder-lint`) und
lässt das Paket `plico.flatpak` unter den Artefakten der Run, installierbar
mit `flatpak install --user plico.flatpak`.

### Plico übersetzen

Plico spricht **Italienisch**, **Englisch**, **Spanisch**, **Französisch**
und **Deutsch**: es folgt der Systemsprache, und eine Sprache, die es nicht
kennt, bekommt Englisch. Die Strings sind im Code auf Italienisch; die
Kataloge der anderen Sprachen liegen in
`src/plico/translations/plico_{en,es,fr,de}.ts` und werden mit Qt Linguist
oder einem Texteditor bearbeitet. Eine neue Sprache ist eine weitere Datei
`plico_xx.ts`: Man erzeugt sie mit `pylupdate6`, übersetzt sie und trägt sie
in `LANGUAGES` in `tests/test_translations.py`, in die `<languages>` des
Metainfo und in die `[xx]`-Einträge der `.desktop`-Datei ein.

`pylupdate6` kommt mit PyQt6 (`pip install PyQt6` im Venv reicht, nur das
Werkzeug wird gebraucht): ohne es überspringt `tests/test_i18n.py` genau die
Prüfung, die warnt, wenn eine neue Zeichenkette im Katalog fehlt.

```
# 1. Strings nach Codeänderungen neu extrahieren,
#    in alle vier Kataloge
for l in en es fr de; do
    pylupdate6 -no-obsolete src/plico -ts src/plico/translations/plico_$l.ts
done

# 2. kompilieren: pyside6-lrelease kommt mit PySide6 (oder lrelease aus dem SDK)
pyside6-lrelease src/plico/translations/plico_de.ts -qm /tmp/plico_de.qm

# 3. ohne Installation ausprobieren
LANG=de_DE.UTF-8 PLICO_TRANSLATIONS=/tmp plico
```

`tests/test_i18n.py` prüft, dass die Kataloge die sind, die die Quellen
erzeugen, so dass keine neue Zeichenkette draußen bleibt;
`tests/test_translations.py`, dass jede Sprache vollständig ist, die
Platzhalter (`{0}`) behält und nicht denselben Shortcut an zwei
Menüeinträge gibt.

## Lizenz

GPL v3 — siehe [LICENSE](https://github.com/gradia64/Plico/blob/main/LICENSE).

## About

Ein echter nativer PDF-Editor für Linux: zusammenführen, teilen, drehen, neu anordnen, speichern. Qt6 + PySide6 + PyMuPDF.

### Topics

[desktop-application](https://github.com/topics/desktop-application) [flatpak](https://github.com/topics/flatpak) [kde](https://github.com/topics/kde) [linux](https://github.com/topics/linux) [pdf](https://github.com/topics/pdf) [pdf-editor](https://github.com/topics/pdf-editor) [pymupdf](https://github.com/topics/pymupdf) [pyside6](https://github.com/topics/pyside6) [python](https://github.com/topics/python) [qt6](https://github.com/topics/qt6)

### Resources

[Readme](https://github.com/gradia64/Plico#readme-ov-file)

[GPL-3.0 license](https://github.com/gradia64/Plico#GPL-3.0-1-ov-file)

[Activity](https://github.com/gradia64/Plico/activity)