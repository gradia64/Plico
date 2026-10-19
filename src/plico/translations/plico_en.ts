<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="en_US" sourcelanguage="it">
    <context>
    <name>AddRedaction</name>
    <message>
        <location filename="../model/commands.py" line="157" />
        <source>Cancella zona su pagina {0}</source>
        <translation>Erase area on page {0}</translation>
    </message>
</context><context>
    <name>AppendDocument</name>
    <message>
        <location filename="../model/commands.py" line="121" />
        <source>Unisci «{0}»</source>
        <translation>Merge “{0}”</translation>
    </message>
</context><context>
    <name>CompressionDialog</name>
    <message>
        <location filename="../widgets/compress.py" line="35" />
        <source>{0} byte</source>
        <translation>{0} bytes</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="61" />
        <source>Salva compresso</source>
        <translation>Save Compressed</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="64" />
        <source>Livello di compressione:</source>
        <translation>Compression level:</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="75" />
        <source>Solo le immagini, senza ricompattare il file</source>
        <translation>Images only, without repacking the file</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="77" />
        <source>La ricompattazione non perde nulla: saltarla ha senso solo per lasciare il file com'è dovunque non ci siano immagini.</source>
        <translation>Repacking loses nothing: skipping it only makes sense to leave the file as it is wherever there are no images.</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="84" />
        <source>tutte</source>
        <translation>all</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="87" />
        <source>Pagine da ricampionare:</source>
        <translation>Pages to resample:</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="152" />
        <source>
Il file non viene ricompattato: cambiano solo le immagini.</source>
        <translation>
The file is not repacked: only the images change.</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="164" />
        <source>Le immagini di tutte le pagine vengono ricampionate.</source>
        <translation>The images of every page are resampled.</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="177" />
        <source>Le immagini di {0} pagine vengono ricampionate.</source>
        <translation>The images of {0} pages are resampled.</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="179" />
        <source>Le immagini di una pagina vengono ricampionate.</source>
        <translation>The images of one page are resampled.</translation>
    </message>
</context><context>
    <name>CompressionLevel</name>
    <message>
        <location filename="../model/optimize.py" line="96" />
        <source>Leggera</source>
        <translation>Light</translation>
    </message>
    <message>
        <location filename="../model/optimize.py" line="97" />
        <source>Senza alcuna perdita: fonde i content stream e ricompatta il file con qpdf. Le immagini non vengono toccate, quindi su una scansione non guadagna quasi nulla.</source>
        <translation>Lossless: merges the content streams and repacks the file with qpdf. Images are left untouched, so on a scan it gains almost nothing.</translation>
    </message>
    <message>
        <location filename="../model/optimize.py" line="106" />
        <source>Media</source>
        <translation>Medium</translation>
    </message>
    <message>
        <location filename="../model/optimize.py" line="107" />
        <source>Come Leggera, e in più ricampiona a 150 dpi le immagini che superano i 200 dpi, salvandole in JPEG a qualità 80.</source>
        <translation>Like Light, and also resamples images above 200 dpi to 150 dpi, saving them as JPEG at quality 80.</translation>
    </message>
    <message>
        <location filename="../model/optimize.py" line="118" />
        <source>Forte</source>
        <translation>Strong</translation>
    </message>
    <message>
        <location filename="../model/optimize.py" line="119" />
        <source>Come Media, ma scende a 96 dpi e qualità 60: file molto più piccoli, immagini visibilmente morbide.</source>
        <translation>Like Medium, but goes down to 96 dpi and quality 60: much smaller files, visibly softer images.</translation>
    </message>
</context><context>
    <name>DeletePage</name>
    <message>
        <location filename="../model/commands.py" line="46" />
        <source>Elimina pagina {0}</source>
        <translation>Delete page {0}</translation>
    </message>
</context><context>
    <name>EditText</name>
    <message>
        <location filename="../model/commands.py" line="312" />
        <source>Modifica testo su pagina {0}</source>
        <translation>Edit text on page {0}</translation>
    </message>
</context><context>
    <name>FindBar</name>
    <message>
        <location filename="../widgets/find_bar.py" line="54" />
        <source>Trova nel documento</source>
        <translation>Find in the document</translation>
    </message>
    <message>
        <location filename="../widgets/find_bar.py" line="59" />
        <source>Occorrenza precedente (Maiusc+F3)</source>
        <translation>Previous match (Shift+F3)</translation>
    </message>
    <message>
        <location filename="../widgets/find_bar.py" line="61" />
        <source>Occorrenza successiva (F3)</source>
        <translation>Next match (F3)</translation>
    </message>
    <message>
        <location filename="../widgets/find_bar.py" line="63" />
        <source>Chiudi la ricerca (Esc)</source>
        <translation>Close the search (Esc)</translation>
    </message>
    <message>
        <location filename="../widgets/find_bar.py" line="68" />
        <source>Trova:</source>
        <translation>Find:</translation>
    </message>
    <message>
        <location filename="../widgets/find_bar.py" line="131" />
        <source>{0} di {1}</source>
        <translation>{0} of {1}</translation>
    </message>
    <message>
        <location filename="../widgets/find_bar.py" line="133" />
        <source>Nessun risultato</source>
        <translation>No results</translation>
    </message>
</context><context>
    <name>FormPanel</name>
    <message>
        <location filename="../widgets/form_panel.py" line="54" />
        <source>Questa pagina non ha campi compilabili.</source>
        <translation>This page has no fillable fields.</translation>
    </message>
    <message>
        <location filename="../widgets/form_panel.py" line="110" />
        <source>(senza nome)</source>
        <translation>(unnamed)</translation>
    </message>
</context><context>
    <name>Images</name>
    <message>
        <location filename="../model/images.py" line="72" />
        <source>«{0}» è già un PDF: aprilo, oppure aggiungilo con Unisci.</source>
        <translation>“{0}” is already a PDF: open it, or add it with Merge.</translation>
    </message>
    <message>
        <location filename="../model/images.py" line="84" />
        <source>«{0}» non è un'immagine che si possa leggere.</source>
        <translation>“{0}” is not an image that can be read.</translation>
    </message>
    <message>
        <location filename="../model/images.py" line="98" />
        <source>Nessuna immagine da convertire.</source>
        <translation>No images to convert.</translation>
    </message>
</context><context>
    <name>MainWindow</name>
    <message>
        <location filename="../main_window.py" line="1790" />
        <location filename="../main_window.py" line="1656" />
        <location filename="../main_window.py" line="1652" />
        <location filename="../main_window.py" line="176" />
        <source>Pronto</source>
        <translation>Ready</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="218" />
        <source>Miniature</source>
        <translation>Thumbnails</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="224" />
        <source>Storico azioni</source>
        <translation>History</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="239" />
        <source>Modulo</source>
        <translation>Form</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="279" />
        <source>&amp;File</source>
        <translation>&amp;File</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="282" />
        <source>A&amp;pri…</source>
        <translation>&amp;Open…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="286" />
        <source>C&amp;rea da immagini…</source>
        <translation>C&amp;reate from Images…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="293" />
        <source>&amp;Salva</source>
        <translation>&amp;Save</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="297" />
        <source>Salva con &amp;nome…</source>
        <translation>Save &amp;As…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="305" />
        <source>&amp;Unisci PDF…</source>
        <translation>&amp;Merge PDF…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="313" />
        <source>&amp;Estrai pagine…</source>
        <translation>E&amp;xtract Pages…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="321" />
        <source>Salva &amp;compresso…</source>
        <translation>Save Com&amp;pressed…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="330" />
        <source>&amp;Firma…</source>
        <translation>S&amp;ign…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="338" />
        <source>&amp;Verifica le firme…</source>
        <translation>&amp;Verify Signatures…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="348" />
        <source>&amp;Chiudi</source>
        <translation>&amp;Close</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="355" />
        <source>&amp;Esci</source>
        <translation>&amp;Quit</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="356" />
        <source>&amp;Modifica</source>
        <translation>&amp;Edit</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1927" />
        <location filename="../main_window.py" line="358" />
        <source>Annulla</source>
        <translation>Undo</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="363" />
        <source>Ripeti</source>
        <translation>Redo</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="370" />
        <source>&amp;Trova…</source>
        <translation>&amp;Find…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="386" />
        <source>Elimina pagina</source>
        <translation>Delete Page</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="393" />
        <source>Cancella &amp;zona</source>
        <translation>Erase &amp;Area</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="400" />
        <source>Trascina un rettangolo sul contenuto da eliminare: testo e immagini
sotto di esso spariscono dal file, non vengono solo coperti.
Un clic su una zona la ripristina. Diventa definitivo solo al salvataggio.</source>
        <translation>Drag a rectangle over the content to delete: the text and images
under it are removed from the file, not just covered.
A click on an area restores it. It becomes final only when you save.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="409" />
        <source>Cancella &amp;selezione</source>
        <translation>Erase &amp;Selection</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="418" />
        <source>Trascina sulle parole da eliminare: la selezione si allarga ai
confini delle parole, così nessuna resta tagliata a metà.
Un clic su una zona la ripristina. Diventa definitivo solo al salvataggio.</source>
        <translation>Drag over the words to delete: the selection grows to the
word boundaries, so no word is left cut in half.
A click on an area restores it. It becomes final only when you save.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="428" />
        <source>Cancella &amp;parola…</source>
        <translation>Erase &amp;Word…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="438" />
        <source>&amp;Modifica testo</source>
        <translation>Edit &amp;Text</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="444" />
        <source>Corregge il testo già presente nel PDF: clic su una riga,
Invio conferma, Esc annulla. Il testo nuovo entra nel file
solo al salvataggio.</source>
        <translation>Corrects text already in the PDF: click a line,
Enter confirms, Esc cancels. The new text goes into the file
only when you save.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="455" />
        <source>&amp;Riconosci testo…</source>
        <translation>&amp;Recognize Text…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="458" />
        <source>Legge il testo delle pagine scansionate e lo rende selezionabile,
cercabile e cancellabile: resta invisibile e non si stampa.</source>
        <translation>Reads the text of scanned pages and makes it selectable,
searchable and erasable: it stays invisible and is not printed.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="474" />
        <source>&amp;Visualizza</source>
        <translation>&amp;View</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="477" />
        <source>Adatta alla &amp;larghezza</source>
        <translation>Fit to &amp;Width</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="485" />
        <source>Zoom a&amp;vanti</source>
        <translation>Zoom &amp;In</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="490" />
        <source>Zoom &amp;indietro</source>
        <translation>Zoom &amp;Out</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="495" />
        <source>Strumenti</source>
        <translation>Tools</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="502" />
        <source>Ruota a destra</source>
        <translation>Rotate Right</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="507" />
        <source>Ruota a destra 90°</source>
        <translation>Rotate right 90°</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="511" />
        <source>Ruota a sinistra</source>
        <translation>Rotate Left</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="516" />
        <source>Ruota a sinistra 90°</source>
        <translation>Rotate left 90°</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="542" />
        <source>Apri PDF</source>
        <translation>Open PDF</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1524" />
        <location filename="../main_window.py" line="1359" />
        <location filename="../main_window.py" line="1235" />
        <location filename="../main_window.py" line="915" />
        <location filename="../main_window.py" line="544" />
        <source>File PDF (*.pdf)</source>
        <translation>PDF files (*.pdf)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1537" />
        <location filename="../main_window.py" line="1484" />
        <location filename="../main_window.py" line="1438" />
        <location filename="../main_window.py" line="1254" />
        <location filename="../main_window.py" line="954" />
        <location filename="../main_window.py" line="887" />
        <location filename="../main_window.py" line="778" />
        <location filename="../main_window.py" line="577" />
        <source>Errore</source>
        <translation>Error</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="578" />
        <source>Impossibile aprire:
{0}</source>
        <translation>Cannot open:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="587" />
        <source>Password errata per «{0}».</source>
        <translation>Wrong password for “{0}”.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="589" />
        <source>«{0}» è protetto da una password.</source>
        <translation>“{0}” is protected by a password.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="592" />
        <source>Documento protetto</source>
        <translation>Protected Document</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="662" />
        <source>Aperto: {0}</source>
        <translation>Opened: {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="714" />
        <source>Documento chiuso.</source>
        <translation>Document closed.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1919" />
        <location filename="../main_window.py" line="1860" />
        <location filename="../main_window.py" line="1773" />
        <location filename="../main_window.py" line="1625" />
        <location filename="../main_window.py" line="1605" />
        <location filename="../main_window.py" line="1517" />
        <location filename="../main_window.py" line="1502" />
        <location filename="../main_window.py" line="1348" />
        <location filename="../main_window.py" line="1299" />
        <location filename="../main_window.py" line="1292" />
        <location filename="../main_window.py" line="1192" />
        <location filename="../main_window.py" line="909" />
        <location filename="../main_window.py" line="900" />
        <location filename="../main_window.py" line="787" />
        <location filename="../main_window.py" line="726" />
        <source>Attenzione</source>
        <translation>Warning</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1919" />
        <location filename="../main_window.py" line="1860" />
        <location filename="../main_window.py" line="1773" />
        <location filename="../main_window.py" line="1699" />
        <location filename="../main_window.py" line="1625" />
        <location filename="../main_window.py" line="1605" />
        <location filename="../main_window.py" line="1502" />
        <location filename="../main_window.py" line="1348" />
        <location filename="../main_window.py" line="1292" />
        <location filename="../main_window.py" line="1192" />
        <location filename="../main_window.py" line="909" />
        <location filename="../main_window.py" line="900" />
        <location filename="../main_window.py" line="726" />
        <source>Nessun documento aperto.</source>
        <translation>No document open.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="732" />
        <source>Unisci PDF</source>
        <translation>Merge PDF</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="734" />
        <source>PDF e immagini ({0});;File PDF (*.pdf);;Immagini ({1})</source>
        <translation>PDFs and images ({0});;PDF files (*.pdf);;Images ({1})</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="779" />
        <source>Impossibile unire:
{0}</source>
        <translation>Cannot merge:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="788" />
        <source>Il documento scelto non contiene pagine.</source>
        <translation>The chosen document contains no pages.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="819" />
        <source>Unite {0} pagine da: {1}</source>
        <translation>Merged {0} pages from: {1}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="838" />
        <source>Crea PDF da immagini</source>
        <translation>Create PDF from Images</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="840" />
        <source>Immagini ({0})</source>
        <translation>Images ({0})</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="866" />
        <source>Creato da {0} immagini, {1} pagine: salvalo con Ctrl+S per tenerlo.</source>
        <translation>Created from {0} images, {1} pages: save it with Ctrl+S to keep it.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="888" />
        <source>Impossibile creare il PDF:
{0}</source>
        <translation>Cannot create the PDF:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="913" />
        <source>Salva con nome</source>
        <translation>Save As</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="933" />
        <source>Il documento è firmato</source>
        <translation>The document is signed</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="934" />
        <source>Salvare «{0}» così com'è toglie la firma: il file nuovo non è firmato.

Continuare?</source>
        <translation>Saving “{0}” as it is removes the signature: the new file is not signed.

Continue?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="954" />
        <source>Impossibile salvare:
{0}</source>
        <translation>Cannot save:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="962" />
        <source>Salvato: {0}</source>
        <translation>Saved: {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1034" />
        <source>Il contenuto di una zona, a pagina {0}, verrà eliminato definitivamente dal file.</source>
        <translation>The content of one area, on page {0}, will be permanently removed from the file.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1038" />
        <source>Il contenuto di {0} zone, a pagina {1}, verrà eliminato definitivamente dal file.</source>
        <translation>The content of {0} areas, on page {1}, will be permanently removed from the file.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1042" />
        <source>Il contenuto di {0} zone, alle pagine {1}, verrà eliminato definitivamente dal file.</source>
        <translation>The content of {0} areas, on pages {1}, will be permanently removed from the file.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1049" />
        <source>Testo, immagini e grafica sotto le zone non si potranno più recuperare da quel file. Il documento aperto resta modificabile.</source>
        <translation>Text, images and graphics under the areas can no longer be recovered from that file. The open document stays editable.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1060" />
        <source>Cancellazione definitiva</source>
        <translation>Permanent removal</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1062" />
        <source>Elimina e salva</source>
        <translation>Remove and save</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1124" />
        <location filename="../main_window.py" line="1082" />
        <source>Senza titolo</source>
        <translation>Untitled</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1089" />
        <source> — firmato</source>
        <translation> — signed</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1097" />
        <source> — una cancellazione da applicare</source>
        <translation> — one removal to apply</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1099" />
        <source> — {0} cancellazioni da applicare</source>
        <translation> — {0} removals to apply</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1306" />
        <location filename="../main_window.py" line="1127" />
        <source>Modifiche non salvate</source>
        <translation>Unsaved Changes</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1128" />
        <source>«{0}» ha modifiche non salvate.
Vuoi salvarle?</source>
        <translation>“{0}” has unsaved changes.
Do you want to save them?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1170" />
        <source>Salvato e riaperto: {0}. Le modifiche ora sono nel file e non si possono più annullare.</source>
        <translation>Saved and reopened: {0}. The changes are now in the file and can no longer be undone.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1205" />
        <source>«{0}» è già firmato.

Una seconda firma si aggiunge alla prima, non la sostituisce: vuoi continuare?</source>
        <translation>“{0}” is already signed.

A second signature is added to the first, it does not replace it: do you want to continue?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1210" />
        <source>«{0}» è firmato, ma ha modifiche non salvate.

Per firmarle il file va riscritto, e la firma che porta ora verrà tolta: resterà solo la nuova. Vuoi continuare?</source>
        <translation>“{0}” is signed, but has unsaved changes.

To sign them the file must be rewritten, and its current signature will be removed: only the new one will remain. Do you want to continue?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1217" />
        <source>Documento già firmato</source>
        <translation>Document Already Signed</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1233" />
        <source>Salva e firma</source>
        <translation>Save and Sign</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1254" />
        <source>Impossibile firmare:
{0}</source>
        <translation>Cannot sign:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1266" />
        <source>Documento firmato: {0}</source>
        <translation>Document signed: {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1300" />
        <source>Questo documento non ha ancora un file: salvalo prima di verificarlo.</source>
        <translation>This document has no file yet: save it before verifying it.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1307" />
        <source>Il file «{0}» non contiene ancora le modifiche non salvate.

Verificare lo stesso la copia che sta su disco?</source>
        <translation>The file “{0}” does not contain the unsaved changes yet.

Verify the copy on disk anyway?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1453" />
        <location filename="../main_window.py" line="1425" />
        <location filename="../main_window.py" line="1387" />
        <location filename="../main_window.py" line="1357" />
        <source>Salva compresso</source>
        <translation>Save Compressed</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1388" />
        <source>Compressione in corso…</source>
        <translation>Compressing…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1422" />
        <source>Nessuna compressione: {0}</source>
        <translation>No compression: {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1439" />
        <source>Impossibile salvare il file compresso:
{0}</source>
        <translation>Cannot save the compressed file:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1449" />
        <source>Compresso: {0}</source>
        <translation>Compressed: {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1454" />
        <source>Scritto:
{0}

Prima: {1}
Dopo: {2}
Risparmiato: {3} ({4}%)</source>
        <translation>Written:
{0}

Before: {1}
After: {2}
Saved: {3} ({4}%)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1467" />
        <source>Questo file non aveva niente da guadagnare: è rimasto di {0}.</source>
        <translation>This file had nothing to gain: it is still {0}.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1474" />
        <source>Il peso sta nelle immagini delle pagine che non hai scelto: prova con tutte le pagine.</source>
        <translation>The weight is in the images of the pages you did not choose: try with all pages.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1485" />
        <source>Impossibile comprimere:
{0}</source>
        <translation>Cannot compress:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1522" />
        <location filename="../main_window.py" line="1507" />
        <source>Estrai pagine</source>
        <translation>Extract Pages</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1508" />
        <source>Pagine da estrarre (es. 1-3,5,8):</source>
        <translation>Pages to extract (e.g. 1-3,5,8):</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1533" />
        <source>Estratte {0} pagine in: {1}</source>
        <translation>Extracted {0} pages to: {1}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1538" />
        <source>Impossibile estrarre:
{0}</source>
        <translation>Cannot extract:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1616" />
        <source>Cancella zona: trascina un rettangolo sul contenuto da eliminare; un clic su una zona la ripristina.</source>
        <translation>Erase area: drag a rectangle over the content to delete; a click on an area restores it.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1636" />
        <source>Cancella selezione: trascina sulle parole da eliminare; le zone restano modificabili finché non salvi. Un clic su una zona la ripristina.</source>
        <translation>Erase selection: drag over the words to delete; the areas stay editable until you save. A click on an area restores it.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1659" />
        <source>Anteprima: la pagina è come verrà salvata. Una cancellazione da applicare.</source>
        <translation>Preview: the page looks as it will be saved. One removal to apply.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1661" />
        <source>Anteprima: la pagina è come verrà salvata. {0} cancellazioni da applicare.</source>
        <translation>Preview: the page looks as it will be saved. {0} removals to apply.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1784" />
        <source>Modifica testo: clic su una riga del documento per correggerla; Invio conferma, Esc annulla.</source>
        <translation>Edit text: click a line of the document to correct it; Enter confirms, Esc cancels.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1802" />
        <source>Zona segnata a pagina {0}: il contenuto sarà eliminato al salvataggio. Esc per vedere l'anteprima.</source>
        <translation>Area marked on page {0}: its content will be removed when you save. Press Esc to see the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1830" />
        <source>Cancella la selezione su pagina {0}</source>
        <translation>Erase the selection on page {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1838" />
        <source>{0} parole segnate a pagina {1}: saranno eliminate al salvataggio. Esc per vedere l'anteprima.</source>
        <translation>{0} words marked on page {1}: they will be removed when you save. Press Esc to see the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1843" />
        <source>Una parola segnata a pagina {0}: sarà eliminata al salvataggio. Esc per vedere l'anteprima.</source>
        <translation>One word marked on page {0}: it will be removed when you save. Press Esc to see the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1864" />
        <source>Cancella parola</source>
        <translation>Erase Word</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1865" />
        <source>Parola da eliminare in tutte le pagine:</source>
        <translation>Word to delete on every page:</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1871" />
        <source>Nessuna occorrenza di «{0}».</source>
        <translation>No occurrences of “{0}”.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1874" />
        <source>Cancella «{0}»</source>
        <translation>Erase “{0}”</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1888" />
        <source>Un'occorrenza di «{0}» segnata a pagina {1}: sarà eliminata al salvataggio. La pagina ne mostra già l'anteprima.</source>
        <translation>One occurrence of “{0}” marked on page {1}: it will be removed when you save. The page already shows the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1894" />
        <source>{0} occorrenze di «{1}» segnate a pagina {2}: saranno eliminate al salvataggio. La pagina ne mostra già l'anteprima.</source>
        <translation>{0} occurrences of “{1}” marked on page {2}: they will be removed when you save. The page already shows the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1899" />
        <source>{0} occorrenze di «{1}» segnate su {2} pagine: saranno eliminate al salvataggio. La pagina ne mostra già l'anteprima.</source>
        <translation>{0} occurrences of “{1}” marked on {2} pages: they will be removed when you save. The page already shows the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1927" />
        <source>Riconoscimento del testo…</source>
        <translation>Recognizing text…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1929" />
        <source>Riconosci testo</source>
        <translation>Recognize Text</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1951" />
        <source>Riconoscimento fallito</source>
        <translation>Recognition Failed</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1965" />
        <source>Riconoscimento interrotto: nessun testo letto.</source>
        <translation>Recognition stopped: no text read.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1967" />
        <source>Nessun testo riconosciuto nelle pagine scelte.</source>
        <translation>No text recognized on the chosen pages.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1973" />
        <source>Riconosci testo su una pagina</source>
        <translation>Recognize text on one page</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1975" />
        <source>Riconosci testo su {0} pagine</source>
        <translation>Recognize text on {0} pages</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1982" />
        <source>Riconosciuto testo su una pagina.</source>
        <translation>Recognized text on one page.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1984" />
        <source>Riconosciuto testo su {0} pagine.</source>
        <translation>Recognized text on {0} pages.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1987" />
        <source>Una pagina senza testo.</source>
        <translation>One page without text.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1989" />
        <source>{0} pagine senza testo.</source>
        <translation>{0} pages without text.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1991" />
        <source>Riconoscimento interrotto. </source>
        <translation>Recognition stopped. </translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2038" />
        <source>Campo «{0}» aggiornato.</source>
        <translation>Field “{0}” updated.</translation>
    </message>
</context><context>
    <name>MovePage</name>
    <message>
        <location filename="../model/commands.py" line="75" />
        <source>Sposta pagina {0}</source>
        <translation>Move page {0}</translation>
    </message>
</context><context>
    <name>MoveRedaction</name>
    <message>
        <location filename="../model/commands.py" line="217" />
        <source>Sposta zona su pagina {0}</source>
        <translation>Move area on page {0}</translation>
    </message>
</context><context>
    <name>Ocr</name>
    <message>
        <location filename="../model/ocr.py" line="187" />
        <source>Manca il dato di lingua di Tesseract (un file .traineddata).
Si possono installare i pacchetti tesseract-ocr-ita e tesseract-ocr-eng, oppure copiare i file in {0}.</source>
        <translation>Tesseract language data is missing (a .traineddata file).
You can install the tesseract-ocr-eng and tesseract-ocr-ita packages, or copy the files to {0}.</translation>
    </message>
    <message>
        <location filename="../model/ocr.py" line="204" />
        <source>Tesseract non è utilizzabile: {0}</source>
        <translation>Tesseract cannot be used: {0}</translation>
    </message>
    <message>
        <location filename="../model/ocr.py" line="217" />
        <source>Manca il dato di lingua di Tesseract.</source>
        <translation>Tesseract language data is missing.</translation>
    </message>
</context><context>
    <name>OcrDialog</name>
    <message>
        <location filename="../widgets/ocr.py" line="95" />
        <source>Riconosci testo</source>
        <translation>Recognize Text</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="108" />
        <source>Il testo riconosciuto entra nel PDF come strato invisibile: lo si può
selezionare, cercare e copiare, ma non si stampa e non si vede.
Entra nel file solo al salvataggio, come ogni altra modifica.</source>
        <translation>The recognized text goes into the PDF as an invisible layer: it can be
selected, searched and copied, but it is not printed and not seen.
It goes into the file only when you save, like any other change.</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="122" />
        <source>Pagine:</source>
        <translation>Pages:</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="123" />
        <source>Lingua:</source>
        <translation>Language:</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="154" />
        <source>(nessuna lingua installata)</source>
        <translation>(no language installed)</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="177" />
        <source>Nessuna lingua installata: metti i file .traineddata di Tesseract in {0}.</source>
        <translation>No language installed: put Tesseract's .traineddata files in {0}.</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="185" />
        <source>{0} pagine, lingua {1}.</source>
        <translation>{0} pages, language {1}.</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="187" />
        <source>Una pagina, lingua {0}.</source>
        <translation>One page, language {0}.</translation>
    </message>
</context><context>
    <name>OcrPage</name>
    <message>
        <location filename="../model/commands.py" line="384" />
        <source>Riconosci testo su pagina {0}</source>
        <translation>Recognize text on page {0}</translation>
    </message>
</context><context>
    <name>PageRanges</name>
    <message>
        <location filename="../model/save.py" line="482" />
        <source>La pagina {0} non esiste: il documento ne ha {1}.</source>
        <translation>Page {0} does not exist: the document has {1}.</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="497" />
        <source>Intervallo non valido: «{0}»</source>
        <translation>Invalid range: “{0}”</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="500" />
        <source>Intervallo al contrario: «{0}»</source>
        <translation>Backwards range: “{0}”</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="513" />
        <source>Indicazione di pagina non valida: «{0}»</source>
        <translation>Invalid page reference: “{0}”</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="517" />
        <source>Nessuna pagina indicata.</source>
        <translation>No pages given.</translation>
    </message>
</context><context>
    <name>PageView</name>
    <message>
        <location filename="../widgets/page_view.py" line="1378" />
        <source>Nessuna parola nella selezione.</source>
        <translation>No words in the selection.</translation>
    </message>
    <message>
        <location filename="../widgets/page_view.py" line="963" />
        <source>Caricamento…</source>
        <translation>Loading…</translation>
    </message>
    <message>
        <location filename="../widgets/page_view.py" line="1454" />
        <source>Qui non c'è testo: clicca sopra una riga del documento.</source>
        <translation>There is no text here: click on a line of the document.</translation>
    </message>
    <message>
        <location filename="../widgets/page_view.py" line="1458" />
        <source>Questa pagina non contiene testo modificabile: probabilmente è un'immagine, come una scansione.</source>
        <translation>This page contains no editable text: it is probably an image, such as a scan.</translation>
    </message>
    <message>
        <location filename="../widgets/page_view.py" line="1474" />
        <source>Impossibile leggere il testo: {0}</source>
        <translation>Cannot read the text: {0}</translation>
    </message>
    <message>
        <location filename="../widgets/page_view.py" line="1604" />
        <source>Impossibile verificare la modifica: {0}</source>
        <translation>Cannot check the change: {0}</translation>
    </message>
</context><context>
    <name>RemoveRedaction</name>
    <message>
        <location filename="../model/commands.py" line="179" />
        <source>Ripristina zona su pagina {0}</source>
        <translation>Restore area on page {0}</translation>
    </message>
</context><context>
    <name>ResizeRedaction</name>
    <message>
        <location filename="../model/commands.py" line="219" />
        <source>Ridimensiona zona su pagina {0}</source>
        <translation>Resize area on page {0}</translation>
    </message>
</context><context>
    <name>RotatePage</name>
    <message>
        <location filename="../model/commands.py" line="25" />
        <source>Ruota pagina {0}</source>
        <translation>Rotate page {0}</translation>
    </message>
</context><context>
    <name>Save</name>
    <message>
        <location filename="../model/save.py" line="173" />
        <source>Il documento non contiene pagine da salvare.</source>
        <translation>The document contains no pages to save.</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="451" />
        <source>Nessuna pagina da estrarre.</source>
        <translation>No pages to extract.</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="455" />
        <source>Non si possono estrarre pagine sopra un documento aperto: scegli un altro file.</source>
        <translation>Pages cannot be extracted over an open document: choose another file.</translation>
    </message>
</context><context>
    <name>SetFieldValue</name>
    <message>
        <location filename="../model/commands.py" line="252" />
        <source>Campo «{0}» su pagina {1}</source>
        <translation>Field “{0}” on page {1}</translation>
    </message>
</context><context>
    <name>SignDialog</name>
    <message>
        <location filename="../widgets/sign.py" line="60" />
        <source>Firma il documento</source>
        <translation>Sign the Document</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="65" />
        <source>File del certificato (.p12)</source>
        <translation>Certificate file (.p12)</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="66" />
        <source>Sfoglia…</source>
        <translation>Browse…</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="74" />
        <source>Password del certificato</source>
        <translation>Certificate password</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="80" />
        <source>Perché firmi (facoltativo)</source>
        <translation>Why you are signing (optional)</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="82" />
        <source>Dove (facoltativo)</source>
        <translation>Where (optional)</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="84" />
        <source>Riquadro visibile sulla pagina</source>
        <translation>Visible box on the page</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="91" />
        <source>pagina</source>
        <translation>page</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="96" />
        <source>Certificato</source>
        <translation>Certificate</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="97" />
        <source>Password</source>
        <translation>Password</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="99" />
        <source>Motivo</source>
        <translation>Reason</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="100" />
        <source>Luogo</source>
        <translation>Location</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="104" />
        <source>La firma copre il file appena salvato: il documento si riapre dalla copia firmata e ogni modifica successiva la annulla.</source>
        <translation>The signature covers the file just saved: the document reopens from the signed copy, and any later change voids it.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="115" />
        <source>Firma</source>
        <translation>Sign</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="137" />
        <source>Scegli il certificato</source>
        <translation>Choose the Certificate</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="139" />
        <source>Certificati (*.p12 *.pfx *.pem);;Tutti i file (*)</source>
        <translation>Certificates (*.p12 *.pfx *.pem);;All files (*)</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="163" />
        <source>Il certificato è scaduto il {0}.</source>
        <translation>The certificate expired on {0}.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="168" />
        <source>{0}
valido fino al {1}</source>
        <translation>{0}
valid until {1}</translation>
    </message>
</context><context>
    <name>SignatureDialog</name>
    <message>
        <location filename="../widgets/sign.py" line="209" />
        <source>Firme del documento</source>
        <translation>Document Signatures</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="219" />
        <source>Aggiungi un certificato fidato…</source>
        <translation>Add a Trusted Certificate…</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="221" />
        <source>Chiudi</source>
        <translation>Close</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="236" />
        <source>Scegli un certificato da considerare fidato</source>
        <translation>Choose a certificate to trust</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="262" />
        <source>Il documento non contiene firme.</source>
        <translation>The document contains no signatures.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="312" />
        <source>La firma è rotta: il contenuto che copriva è stato cambiato dopo la firma.</source>
        <translation>The signature is broken: the content it covered was changed after signing.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="320" />
        <source>La firma è integra, ma il documento è stato modificato dopo: vale solo per la versione che è stata firmata.</source>
        <translation>The signature is intact, but the document was modified afterwards: it is valid only for the version that was signed.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="329" />
        <source>La firma non è valida: non corrisponde al certificato che la porta.</source>
        <translation>The signature is not valid: it does not match the certificate that carries it.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="337" />
        <source>Firma integra e valida. Il certificato però non è fra quelli che consideri fidati: aggiungi la sua autorità per sapere chi ha firmato.</source>
        <translation>Intact and valid signature. However, the certificate is not among those you trust: add its authority to know who signed.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="345" />
        <source>Firma valida e firmatario attendibile.</source>
        <translation>Valid signature and trusted signer.</translation>
    </message>
</context><context>
    <name>Signing</name>
    <message>
        <location filename="../model/sign.py" line="524" />
        <location filename="../model/sign.py" line="440" />
        <location filename="../model/sign.py" line="156" />
        <source>Non riesco a leggere «{0}»: {1}</source>
        <translation>Cannot read “{0}”: {1}</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="166" />
        <source>Password errata, oppure «{0}» non è un file PKCS#12.</source>
        <translation>Wrong password, or “{0}” is not a PKCS#12 file.</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="172" />
        <source>«{0}» non contiene una chiave privata con il suo certificato.</source>
        <translation>“{0}” does not contain a private key with its certificate.</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="222" />
        <source>Firmato da %(name)s</source>
        <translation>Signed by %(name)s</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="359" />
        <source>Non riesco a firmare il documento: {0}</source>
        <translation>Cannot sign the document: {0}</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="449" />
        <source>«{0}» non è un PDF leggibile: {1}</source>
        <translation>“{0}” is not a readable PDF: {1}</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="457" />
        <source>«{0}» è protetto da una password che non apre il file.</source>
        <translation>“{0}” is protected by a password that does not open the file.</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="469" />
        <source>Non riesco a leggere le firme di «{0}»: {1}</source>
        <translation>Cannot read the signatures of “{0}”: {1}</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="489" />
        <source>Firma illeggibile: {0}</source>
        <translation>Unreadable signature: {0}</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="532" />
        <source>«{0}» non contiene certificati PEM.</source>
        <translation>“{0}” contains no PEM certificates.</translation>
    </message>
</context><context>
    <name>TextEdit</name>
    <message>
        <location filename="../model/textedit.py" line="284" />
        <source>Si può modificare solo testo orizzontale.</source>
        <translation>Only horizontal text can be edited.</translation>
    </message>
    <message>
        <location filename="../model/textedit.py" line="289" />
        <source>Questo testo usa un font Type3 e non si può modificare.</source>
        <translation>This text uses a Type3 font and cannot be edited.</translation>
    </message>
    <message>
        <location filename="../model/textedit.py" line="303" />
        <source>Nessun font disponibile contiene questi caratteri.</source>
        <translation>No available font contains these characters.</translation>
    </message>
    <message>
        <location filename="../model/textedit.py" line="311" />
        <source>Il testo nuovo non ci sta: andrebbe rimpicciolito al {0}%.</source>
        <translation>The new text does not fit: it would have to shrink to {0}%.</translation>
    </message>
</context><context>
    <name>ThumbnailModel</name>
    <message>
        <location filename="../widgets/thumbnail_bar.py" line="113" />
        <source>Pagina {0}</source>
        <translation>Page {0}</translation>
    </message>
</context></TS>
