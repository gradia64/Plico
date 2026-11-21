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
        <location filename="../widgets/compress.py" line="154" />
        <source>
Il file non viene ricompattato: cambiano solo le immagini.</source>
        <translation>
The file is not repacked: only the images change.</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="166" />
        <source>Le immagini di tutte le pagine vengono ricampionate.</source>
        <translation>The images of every page are resampled.</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="179" />
        <source>Le immagini di {0} pagine vengono ricampionate.</source>
        <translation>The images of {0} pages are resampled.</translation>
    </message>
    <message>
        <location filename="../widgets/compress.py" line="181" />
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
    <name>DocumentModel</name>
    <message>
        <location filename="../model/document.py" line="276" />
        <source>Il documento ha {0} pagine: Plico ne apre al massimo {1}.</source>
        <translation>The document has {0} pages: Plico opens at most {1}.</translation>
    </message>
    <message>
        <location filename="../model/document.py" line="367" />
        <source>Con l'unione il documento avrebbe {0} pagine: Plico ne apre al massimo {1}.</source>
        <translation>Merged, the document would have {0} pages: Plico opens at most {1}.</translation>
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
        <location filename="../widgets/form_panel.py" line="113" />
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
        <location filename="../main_window.py" line="2557" />
        <location filename="../main_window.py" line="2542" />
        <location filename="../main_window.py" line="2064" />
        <location filename="../main_window.py" line="1930" />
        <location filename="../main_window.py" line="1926" />
        <location filename="../main_window.py" line="222" />
        <source>Pronto</source>
        <translation>Ready</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="267" />
        <source>Miniature</source>
        <translation>Thumbnails</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="273" />
        <source>Storico azioni</source>
        <translation>History</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="288" />
        <source>Modulo</source>
        <translation>Form</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="364" />
        <source>&amp;File</source>
        <translation>&amp;File</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="367" />
        <source>A&amp;pri…</source>
        <translation>&amp;Open…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="371" />
        <source>C&amp;rea da immagini…</source>
        <translation>C&amp;reate from Images…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="378" />
        <source>&amp;Salva</source>
        <translation>&amp;Save</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="382" />
        <source>Salva con &amp;nome…</source>
        <translation>Save &amp;As…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="390" />
        <source>&amp;Unisci PDF…</source>
        <translation>&amp;Merge PDF…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="398" />
        <source>Es&amp;trai pagine…</source>
        <translation>E&amp;xtract Pages…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="406" />
        <source>Salva c&amp;ompresso…</source>
        <translation>Save Com&amp;pressed…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="415" />
        <source>&amp;Firma…</source>
        <translation>S&amp;ign…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="423" />
        <source>&amp;Verifica le firme…</source>
        <translation>&amp;Verify Signatures…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="433" />
        <source>&amp;Chiudi</source>
        <translation>&amp;Close</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="440" />
        <source>&amp;Esci</source>
        <translation>&amp;Quit</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="441" />
        <source>&amp;Modifica</source>
        <translation>&amp;Edit</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2201" />
        <location filename="../main_window.py" line="443" />
        <source>Annulla</source>
        <translation>Undo</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="448" />
        <source>Ripeti</source>
        <translation>Redo</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="455" />
        <source>&amp;Trova…</source>
        <translation>&amp;Find…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="471" />
        <source>Elimina pagina</source>
        <translation>Delete Page</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="478" />
        <source>Cancella &amp;zona</source>
        <translation>Erase &amp;Area</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="485" />
        <source>Trascina un rettangolo sul contenuto da eliminare: testo e immagini
sotto di esso spariscono dal file, non vengono solo coperti.
Un clic su una zona la ripristina. Diventa definitivo solo al salvataggio.</source>
        <translation>Drag a rectangle over the content to delete: the text and images
under it are removed from the file, not just covered.
A click on an area restores it. It becomes final only when you save.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="494" />
        <source>Cancella &amp;selezione</source>
        <translation>Erase &amp;Selection</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="503" />
        <source>Trascina sulle parole da eliminare: la selezione si allarga ai
confini delle parole, così nessuna resta tagliata a metà.
Un clic su una zona la ripristina. Diventa definitivo solo al salvataggio.</source>
        <translation>Drag over the words to delete: the selection grows to the
word boundaries, so no word is left cut in half.
A click on an area restores it. It becomes final only when you save.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="513" />
        <source>Cancella &amp;parola…</source>
        <translation>Erase &amp;Word…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="523" />
        <source>&amp;Modifica testo</source>
        <translation>Edit &amp;Text</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="529" />
        <source>Corregge il testo già presente nel PDF: clic su una riga,
Invio conferma, Esc annulla. Il testo nuovo entra nel file
solo al salvataggio.</source>
        <translation>Corrects text already in the PDF: click a line,
Enter confirms, Esc cancels. The new text goes into the file
only when you save.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="540" />
        <source>&amp;Riconosci testo…</source>
        <translation>&amp;Recognize Text…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="543" />
        <source>Legge il testo delle pagine scansionate e lo rende selezionabile,
cercabile e cancellabile: resta invisibile e non si stampa.</source>
        <translation>Reads the text of scanned pages and makes it selectable,
searchable and erasable: it stays invisible and is not printed.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="559" />
        <source>&amp;Visualizza</source>
        <translation>&amp;View</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="562" />
        <source>Adatta alla &amp;larghezza</source>
        <translation>Fit to &amp;Width</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="570" />
        <source>Zoom a&amp;vanti</source>
        <translation>Zoom &amp;In</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="575" />
        <source>Zoom &amp;indietro</source>
        <translation>Zoom &amp;Out</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="581" />
        <source>&amp;Impostazioni</source>
        <translation>&amp;Settings</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="583" />
        <source>&amp;Configura Plico…</source>
        <translation>&amp;Configure Plico…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="587" />
        <source>&amp;Aiuto</source>
        <translation>&amp;Help</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="588" />
        <source>&amp;Guida di Plico</source>
        <translation>Plico &amp;Handbook</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="593" />
        <source>Cerca &amp;aggiornamenti…</source>
        <translation>Check for &amp;Updates…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2606" />
        <location filename="../main_window.py" line="598" />
        <source>&amp;Scarica Plico {0}…</source>
        <translation>&amp;Download Plico {0}…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="604" />
        <source>&amp;Informazioni su Plico</source>
        <translation>&amp;About Plico</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="611" />
        <source>Strumenti</source>
        <translation>Tools</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="618" />
        <source>Ruota a destra</source>
        <translation>Rotate Right</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="623" />
        <source>Ruota a destra 90°</source>
        <translation>Rotate right 90°</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="627" />
        <source>Ruota a sinistra</source>
        <translation>Rotate Left</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="632" />
        <source>Ruota a sinistra 90°</source>
        <translation>Rotate left 90°</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="658" />
        <source>Apri PDF</source>
        <translation>Open PDF</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1796" />
        <location filename="../main_window.py" line="1609" />
        <location filename="../main_window.py" line="1439" />
        <location filename="../main_window.py" line="1039" />
        <location filename="../main_window.py" line="660" />
        <source>File PDF (*.pdf)</source>
        <translation>PDF files (*.pdf)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1811" />
        <location filename="../main_window.py" line="1756" />
        <location filename="../main_window.py" line="1709" />
        <location filename="../main_window.py" line="1476" />
        <location filename="../main_window.py" line="1080" />
        <location filename="../main_window.py" line="1011" />
        <location filename="../main_window.py" line="902" />
        <location filename="../main_window.py" line="700" />
        <source>Errore</source>
        <translation>Error</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="701" />
        <source>Impossibile aprire:
{0}</source>
        <translation>Cannot open:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="710" />
        <source>Password errata per «{0}».</source>
        <translation>Wrong password for “{0}”.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="712" />
        <source>«{0}» è protetto da una password.</source>
        <translation>“{0}” is protected by a password.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="715" />
        <source>Documento protetto</source>
        <translation>Protected Document</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="785" />
        <source>Aperto: {0}</source>
        <translation>Opened: {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="837" />
        <source>Documento chiuso.</source>
        <translation>Document closed.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2193" />
        <location filename="../main_window.py" line="2134" />
        <location filename="../main_window.py" line="2047" />
        <location filename="../main_window.py" line="1899" />
        <location filename="../main_window.py" line="1879" />
        <location filename="../main_window.py" line="1789" />
        <location filename="../main_window.py" line="1774" />
        <location filename="../main_window.py" line="1598" />
        <location filename="../main_window.py" line="1521" />
        <location filename="../main_window.py" line="1514" />
        <location filename="../main_window.py" line="1396" />
        <location filename="../main_window.py" line="1033" />
        <location filename="../main_window.py" line="1024" />
        <location filename="../main_window.py" line="911" />
        <location filename="../main_window.py" line="849" />
        <source>Attenzione</source>
        <translation>Warning</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2193" />
        <location filename="../main_window.py" line="2134" />
        <location filename="../main_window.py" line="2047" />
        <location filename="../main_window.py" line="1973" />
        <location filename="../main_window.py" line="1899" />
        <location filename="../main_window.py" line="1879" />
        <location filename="../main_window.py" line="1774" />
        <location filename="../main_window.py" line="1598" />
        <location filename="../main_window.py" line="1514" />
        <location filename="../main_window.py" line="1396" />
        <location filename="../main_window.py" line="1033" />
        <location filename="../main_window.py" line="1024" />
        <location filename="../main_window.py" line="849" />
        <source>Nessun documento aperto.</source>
        <translation>No document open.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="855" />
        <source>Unisci PDF</source>
        <translation>Merge PDF</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="857" />
        <source>PDF e immagini ({0});;File PDF (*.pdf);;Immagini ({1})</source>
        <translation>PDFs and images ({0});;PDF files (*.pdf);;Images ({1})</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="903" />
        <source>Impossibile unire:
{0}</source>
        <translation>Cannot merge:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="912" />
        <source>Il documento scelto non contiene pagine.</source>
        <translation>The chosen document contains no pages.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="943" />
        <source>Unite {0} pagine da: {1}</source>
        <translation>Merged {0} pages from: {1}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="962" />
        <source>Crea PDF da immagini</source>
        <translation>Create PDF from Images</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="964" />
        <source>Immagini ({0})</source>
        <translation>Images ({0})</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="990" />
        <source>Creato da {0} immagini, {1} pagine: salvalo con Ctrl+S per tenerlo.</source>
        <translation>Created from {0} images, {1} pages: save it with Ctrl+S to keep it.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1012" />
        <source>Impossibile creare il PDF:
{0}</source>
        <translation>Cannot create the PDF:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1037" />
        <source>Salva con nome</source>
        <translation>Save As</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1059" />
        <source>Il documento è firmato</source>
        <translation>The document is signed</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1060" />
        <source>Salvare «{0}» così com'è toglie la firma: il file nuovo non è firmato.

Continuare?</source>
        <translation>Saving “{0}” as it is removes the signature: the new file is not signed.

Continue?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1080" />
        <source>Impossibile salvare:
{0}</source>
        <translation>Cannot save:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1088" />
        <source>Salvato: {0}</source>
        <translation>Saved: {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1160" />
        <source>Il contenuto di una zona, a pagina {0}, verrà eliminato definitivamente dal file.</source>
        <translation>The content of one area, on page {0}, will be permanently removed from the file.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1164" />
        <source>Il contenuto di {0} zone, a pagina {1}, verrà eliminato definitivamente dal file.</source>
        <translation>The content of {0} areas, on page {1}, will be permanently removed from the file.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1168" />
        <source>Il contenuto di {0} zone, alle pagine {1}, verrà eliminato definitivamente dal file.</source>
        <translation>The content of {0} areas, on pages {1}, will be permanently removed from the file.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1175" />
        <source>Testo, immagini e grafica sotto le zone non si potranno più recuperare da quel file. Il documento aperto resta modificabile.</source>
        <translation>Text, images and graphics under the areas can no longer be recovered from that file. The open document stays editable.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1180" />
        <source>Titolo, autore e segnalibri del documento non verranno copiati: potrebbero contenere il testo eliminato.</source>
        <translation>The document's title, author and bookmarks will not be copied: they could contain the deleted text.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1191" />
        <source>Cancellazione definitiva</source>
        <translation>Permanent removal</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1193" />
        <source>Elimina e salva</source>
        <translation>Remove and save</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1255" />
        <location filename="../main_window.py" line="1213" />
        <source>Senza titolo</source>
        <translation>Untitled</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1220" />
        <source> — firmato</source>
        <translation> — signed</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1228" />
        <source> — una cancellazione da applicare</source>
        <translation> — one removal to apply</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1230" />
        <source> — {0} cancellazioni da applicare</source>
        <translation> — {0} removals to apply</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1528" />
        <location filename="../main_window.py" line="1258" />
        <source>Modifiche non salvate</source>
        <translation>Unsaved Changes</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1259" />
        <source>«{0}» ha modifiche non salvate.
Vuoi salvarle?</source>
        <translation>“{0}” has unsaved changes.
Do you want to save them?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1302" />
        <source>Salvato e riaperto: {0}. Le modifiche ora sono nel file e non si possono più annullare.</source>
        <translation>Saved and reopened: {0}. The changes are now in the file and can no longer be undone.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1332" />
        <source>«{0}» limita stampa, copia o modifica con una password del proprietario.

Se la conosci scrivila: resterà valida anche sul file salvato. Altrimenti lascia vuoto: i limiti restano, con una password del proprietario nuova che nessuno conosce.</source>
        <translation>“{0}” restricts printing, copying or editing with an owner password.

If you know it, type it: it will stay valid on the saved file too. Otherwise leave it empty: the restrictions stay, with a new owner password nobody knows.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1341" />
        <source>Password del proprietario</source>
        <translation>Owner password</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1349" />
        <source>Password del proprietario errata per «{0}».

Riprova, oppure lascia vuoto per usarne una nuova.</source>
        <translation>Wrong owner password for “{0}”.

Try again, or leave it empty to use a new one.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1370" />
        <source>File protetto</source>
        <translation>Protected file</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1371" />
        <source>«{0}» è protetto da una password. Il file che lo sostituisce non avrà password né restrizioni.

Sostituirlo lo stesso?</source>
        <translation>“{0}” is protected by a password. The file replacing it will have no password and no restrictions.

Replace it anyway?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1409" />
        <source>«{0}» è già firmato.

Una seconda firma si aggiunge alla prima, non la sostituisce: vuoi continuare?</source>
        <translation>“{0}” is already signed.

A second signature is added to the first, it does not replace it: do you want to continue?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1414" />
        <source>«{0}» è firmato, ma ha modifiche non salvate.

Per firmarle il file va riscritto, e la firma che porta ora verrà tolta: resterà solo la nuova. Vuoi continuare?</source>
        <translation>“{0}” is signed, but has unsaved changes.

To sign them the file must be rewritten, and its current signature will be removed: only the new one will remain. Do you want to continue?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1421" />
        <source>Documento già firmato</source>
        <translation>Document Already Signed</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1437" />
        <source>Salva e firma</source>
        <translation>Save and Sign</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1476" />
        <source>Impossibile firmare:
{0}</source>
        <translation>Cannot sign:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1488" />
        <source>Documento firmato: {0}</source>
        <translation>Document signed: {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1522" />
        <source>Questo documento non ha ancora un file: salvalo prima di verificarlo.</source>
        <translation>This document has no file yet: save it before verifying it.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1529" />
        <source>Il file «{0}» non contiene ancora le modifiche non salvate.

Verificare lo stesso la copia che sta su disco?</source>
        <translation>The file “{0}” does not contain the unsaved changes yet.

Verify the copy on disk anyway?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1724" />
        <location filename="../main_window.py" line="1696" />
        <location filename="../main_window.py" line="1639" />
        <location filename="../main_window.py" line="1607" />
        <source>Salva compresso</source>
        <translation>Save Compressed</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1640" />
        <source>Compressione in corso…</source>
        <translation>Compressing…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1693" />
        <source>Nessuna compressione: {0}</source>
        <translation>No compression: {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1710" />
        <source>Impossibile salvare il file compresso:
{0}</source>
        <translation>Cannot save the compressed file:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1720" />
        <source>Compresso: {0}</source>
        <translation>Compressed: {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1725" />
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
        <location filename="../main_window.py" line="1738" />
        <source>Questo file non aveva niente da guadagnare: è rimasto di {0}.</source>
        <translation>This file had nothing to gain: it is still {0}.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1745" />
        <source>Il peso sta nelle immagini delle pagine che non hai scelto: prova con tutte le pagine.</source>
        <translation>The weight is in the images of the pages you did not choose: try with all pages.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1757" />
        <source>Impossibile comprimere:
{0}</source>
        <translation>Cannot compress:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1794" />
        <location filename="../main_window.py" line="1779" />
        <source>Estrai pagine</source>
        <translation>Extract Pages</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1780" />
        <source>Pagine da estrarre (es. 1-3,5,8):</source>
        <translation>Pages to extract (e.g. 1-3,5,8):</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1807" />
        <source>Estratte {0} pagine in: {1}</source>
        <translation>Extracted {0} pages to: {1}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1812" />
        <source>Impossibile estrarre:
{0}</source>
        <translation>Cannot extract:
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1890" />
        <source>Cancella zona: trascina un rettangolo sul contenuto da eliminare; un clic su una zona la ripristina.</source>
        <translation>Erase area: drag a rectangle over the content to delete; a click on an area restores it.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1910" />
        <source>Cancella selezione: trascina sulle parole da eliminare; le zone restano modificabili finché non salvi. Un clic su una zona la ripristina.</source>
        <translation>Erase selection: drag over the words to delete; the areas stay editable until you save. A click on an area restores it.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1933" />
        <source>Anteprima: la pagina è come verrà salvata. Una cancellazione da applicare.</source>
        <translation>Preview: the page looks as it will be saved. One removal to apply.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1935" />
        <source>Anteprima: la pagina è come verrà salvata. {0} cancellazioni da applicare.</source>
        <translation>Preview: the page looks as it will be saved. {0} removals to apply.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2058" />
        <source>Modifica testo: clic su una riga del documento per correggerla; Invio conferma, Esc annulla.</source>
        <translation>Edit text: click a line of the document to correct it; Enter confirms, Esc cancels.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2076" />
        <source>Zona segnata a pagina {0}: il contenuto sarà eliminato al salvataggio. Esc per vedere l'anteprima.</source>
        <translation>Area marked on page {0}: its content will be removed when you save. Press Esc to see the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2104" />
        <source>Cancella la selezione su pagina {0}</source>
        <translation>Erase the selection on page {0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2112" />
        <source>{0} parole segnate a pagina {1}: saranno eliminate al salvataggio. Esc per vedere l'anteprima.</source>
        <translation>{0} words marked on page {1}: they will be removed when you save. Press Esc to see the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2117" />
        <source>Una parola segnata a pagina {0}: sarà eliminata al salvataggio. Esc per vedere l'anteprima.</source>
        <translation>One word marked on page {0}: it will be removed when you save. Press Esc to see the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2138" />
        <source>Cancella parola</source>
        <translation>Erase Word</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2139" />
        <source>Parola da eliminare in tutte le pagine:</source>
        <translation>Word to delete on every page:</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2145" />
        <source>Nessuna occorrenza di «{0}».</source>
        <translation>No occurrences of “{0}”.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2148" />
        <source>Cancella «{0}»</source>
        <translation>Erase “{0}”</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2162" />
        <source>Un'occorrenza di «{0}» segnata a pagina {1}: sarà eliminata al salvataggio. La pagina ne mostra già l'anteprima.</source>
        <translation>One occurrence of “{0}” marked on page {1}: it will be removed when you save. The page already shows the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2168" />
        <source>{0} occorrenze di «{1}» segnate a pagina {2}: saranno eliminate al salvataggio. La pagina ne mostra già l'anteprima.</source>
        <translation>{0} occurrences of “{1}” marked on page {2}: they will be removed when you save. The page already shows the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2173" />
        <source>{0} occorrenze di «{1}» segnate su {2} pagine: saranno eliminate al salvataggio. La pagina ne mostra già l'anteprima.</source>
        <translation>{0} occurrences of “{1}” marked on {2} pages: they will be removed when you save. The page already shows the preview.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2201" />
        <source>Riconoscimento del testo…</source>
        <translation>Recognizing text…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2203" />
        <source>Riconosci testo</source>
        <translation>Recognize Text</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2225" />
        <source>Riconoscimento fallito</source>
        <translation>Recognition Failed</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2239" />
        <source>Riconoscimento interrotto: nessun testo letto.</source>
        <translation>Recognition stopped: no text read.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2241" />
        <source>Nessun testo riconosciuto nelle pagine scelte.</source>
        <translation>No text recognized on the chosen pages.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2247" />
        <source>Riconosci testo su una pagina</source>
        <translation>Recognize text on one page</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2249" />
        <source>Riconosci testo su {0} pagine</source>
        <translation>Recognize text on {0} pages</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2256" />
        <source>Riconosciuto testo su una pagina.</source>
        <translation>Recognized text on one page.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2258" />
        <source>Riconosciuto testo su {0} pagine.</source>
        <translation>Recognized text on {0} pages.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2261" />
        <source>Una pagina senza testo.</source>
        <translation>One page without text.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2263" />
        <source>{0} pagine senza testo.</source>
        <translation>{0} pages without text.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2265" />
        <source>Riconoscimento interrotto. </source>
        <translation>Recognition stopped. </translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2312" />
        <source>Campo «{0}» aggiornato.</source>
        <translation>Field “{0}” updated.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2441" />
        <source>Lingua</source>
        <translation>Language</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2442" />
        <source>La nuova lingua sarà usata al prossimo avvio di Plico.</source>
        <translation>The new language will be used the next time Plico starts.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2455" />
        <source>Informazioni su Plico</source>
        <translation>About Plico</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2460" />
        <source>&lt;h3&gt;Plico {0}&lt;/h3&gt;&lt;p&gt;Un vero editor PDF nativo per Linux.&lt;/p&gt;&lt;p&gt;Licenza GPL-3.0 o successiva.&lt;br&gt;&lt;a href="https://github.com/gradia64/Plico"&gt;github.com/gradia64/Plico&lt;/a&gt;&lt;/p&gt;</source>
        <translation>&lt;h3&gt;Plico {0}&lt;/h3&gt;&lt;p&gt;A true native PDF editor for Linux.&lt;/p&gt;&lt;p&gt;Licensed under GPL-3.0 or later.&lt;br&gt;&lt;a href="https://github.com/gradia64/Plico"&gt;github.com/gradia64/Plico&lt;/a&gt;&lt;/p&gt;</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2512" />
        <source>Ricerca di una nuova versione…</source>
        <translation>Looking for a new version…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2568" />
        <location filename="../main_window.py" line="2560" />
        <location filename="../main_window.py" line="2519" />
        <source>Cerca aggiornamenti</source>
        <translation>Check for Updates</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2521" />
        <source>Questo è Plico {0}. Il pacchetto Flatpak non ha accesso alla rete, quindi Plico non può chiedere da sé se c'è una versione più recente: la pagina delle versioni lo dice.</source>
        <translation>This is Plico {0}. The Flatpak package has no network access, so Plico cannot ask by itself whether a newer version is out: the releases page tells you.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2579" />
        <location filename="../main_window.py" line="2527" />
        <source>Apri la pagina</source>
        <translation>Open the Page</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2548" />
        <source>È disponibile Plico {0}: Aiuto → Scarica Plico {0}.</source>
        <translation>Plico {0} is available: Help → Download Plico {0}.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2561" />
        <source>Non è stato possibile controllare gli aggiornamenti.
{0}</source>
        <translation>Could not check for updates.
{0}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2572" />
        <source>È disponibile Plico {0} (questo è {1}). Il gestore dei pacchetti del sistema lo installerà con il prossimo aggiornamento.</source>
        <translation>Plico {0} is available (this is {1}). The system's package manager will install it with the next update.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2577" />
        <source>È disponibile Plico {0} (questo è {1}).</source>
        <translation>Plico {0} is available (this is {1}).</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2581" />
        <source>Plico {0} è la versione più recente.</source>
        <translation>Plico {0} is the latest version.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2587" />
        <source>Controlla una volta al giorno</source>
        <translation>Check once a day</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2640" />
        <source>Plico — clic per mostrare o nascondere, «Esci» dal menu per chiudere</source>
        <translation>Plico — click to show or hide, “Quit” in the menu to close</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2643" />
        <source>Mostra / nascondi</source>
        <translation>Show / hide</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="2647" />
        <source>Esci</source>
        <translation>Quit</translation>
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
        <location filename="../model/ocr.py" line="191" />
        <source>Manca il dato di lingua di Tesseract (un file .traineddata).
Si possono installare i pacchetti tesseract-ocr-ita e tesseract-ocr-eng, oppure copiare i file in {0}.</source>
        <translation>Tesseract language data is missing (a .traineddata file).
You can install the tesseract-ocr-eng and tesseract-ocr-ita packages, or copy the files to {0}.</translation>
    </message>
    <message>
        <location filename="../model/ocr.py" line="208" />
        <source>Tesseract non è utilizzabile: {0}</source>
        <translation>Tesseract cannot be used: {0}</translation>
    </message>
    <message>
        <location filename="../model/ocr.py" line="221" />
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
        <location filename="../widgets/ocr.py" line="126" />
        <source>Come in Estrai pagine: per esempio 3, 4-8 oppure 1-3,5.</source>
        <translation>As in Extract Pages: for example 3, 4-8 or 1-3,5.</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="130" />
        <source>Pagine:</source>
        <translation>Pages:</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="132" />
        <source>Lingua:</source>
        <translation>Language:</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="163" />
        <source>(nessuna lingua installata)</source>
        <translation>(no language installed)</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="186" />
        <source>Nessuna lingua installata: metti i file .traineddata di Tesseract in {0}.</source>
        <translation>No language installed: put Tesseract's .traineddata files in {0}.</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="194" />
        <source>{0} pagine, lingua {1}.</source>
        <translation>{0} pages, language {1}.</translation>
    </message>
    <message>
        <location filename="../widgets/ocr.py" line="196" />
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
        <location filename="../model/save.py" line="759" />
        <source>La pagina {0} non esiste: il documento ne ha {1}.</source>
        <translation>Page {0} does not exist: the document has {1}.</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="774" />
        <source>Intervallo non valido: «{0}»</source>
        <translation>Invalid range: “{0}”</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="777" />
        <source>Intervallo al contrario: «{0}»</source>
        <translation>Backwards range: “{0}”</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="790" />
        <source>Indicazione di pagina non valida: «{0}»</source>
        <translation>Invalid page reference: “{0}”</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="794" />
        <source>Nessuna pagina indicata.</source>
        <translation>No pages given.</translation>
    </message>
</context><context>
    <name>PageView</name>
    <message>
        <location filename="../widgets/page_view.py" line="1392" />
        <source>Nessuna parola nella selezione.</source>
        <translation>No words in the selection.</translation>
    </message>
    <message>
        <location filename="../widgets/page_view.py" line="975" />
        <source>Caricamento…</source>
        <translation>Loading…</translation>
    </message>
    <message>
        <location filename="../widgets/page_view.py" line="1468" />
        <source>Qui non c'è testo: clicca sopra una riga del documento.</source>
        <translation>There is no text here: click on a line of the document.</translation>
    </message>
    <message>
        <location filename="../widgets/page_view.py" line="1472" />
        <source>Questa pagina non contiene testo modificabile: probabilmente è un'immagine, come una scansione.</source>
        <translation>This page contains no editable text: it is probably an image, such as a scan.</translation>
    </message>
    <message>
        <location filename="../widgets/page_view.py" line="1488" />
        <source>Impossibile leggere il testo: {0}</source>
        <translation>Cannot read the text: {0}</translation>
    </message>
    <message>
        <location filename="../widgets/page_view.py" line="1619" />
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
        <location filename="../model/save.py" line="176" />
        <source>Il documento non contiene pagine da salvare.</source>
        <translation>The document contains no pages to save.</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="728" />
        <source>Nessuna pagina da estrarre.</source>
        <translation>No pages to extract.</translation>
    </message>
    <message>
        <location filename="../model/save.py" line="732" />
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
    <name>SettingsDialog</name>
    <message>
        <location filename="../widgets/settings_dialog.py" line="51" />
        <source>Impostazioni</source>
        <translation>Settings</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="54" />
        <source>Automatica (lingua del sistema)</source>
        <translation>Automatic (system language)</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="59" />
        <source>La nuova lingua vale dal prossimo avvio di Plico</source>
        <translation>The new language applies from the next start of Plico</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="61" />
        <source>Se la lingua del sistema non è tra queste, Plico usa l'inglese. La scelta vale dal prossimo avvio.</source>
        <translation>If the system language is not among these, Plico uses English. The choice applies from the next start.</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="68" />
        <source>Lingua</source>
        <translation>Language</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="70" />
        <source>Lingua dell'interfaccia:</source>
        <translation>Interface language:</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="73" />
        <source>Mostra l'icona nell'area di notifica</source>
        <translation>Show the icon in the notification area</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="76" />
        <source>Chiudendo la finestra, riducila nell'area di notifica invece di uscire</source>
        <translation>When closing the window, minimize it to the notification area instead of quitting</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="80" />
        <source>La X nasconde la finestra e Plico resta attivo: clic sull'icona per riaprirla, «Esci» dal menu dell'icona o Ctrl+Q per chiudere davvero.</source>
        <translation>The X hides the window and Plico keeps running: click the icon to reopen it, “Quit” in the icon's menu or Ctrl+Q to really close.</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="90" />
        <source>Area di notifica</source>
        <translation>Notification area</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="97" />
        <source>Questo desktop non offre un'area di notifica.</source>
        <translation>This desktop offers no notification area.</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="102" />
        <source>Controlla una volta al giorno se c'è una nuova versione</source>
        <translation>Check once a day for a new version</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="105" />
        <source>Aggiornamenti</source>
        <translation>Updates</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="109" />
        <source>Plico chiede a GitHub il numero dell'ultima versione e non invia nient'altro. Finché la casella è vuota, non si collega a niente.</source>
        <translation>Plico asks GitHub for the number of the latest version and sends nothing else. While the box is unchecked, it connects to nothing.</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="117" />
        <source>Questo pacchetto Flatpak non ha accesso alla rete: «Aiuto → Cerca aggiornamenti…» apre la pagina delle versioni.</source>
        <translation>This Flatpak package has no network access: “Help → Check for Updates…” opens the releases page.</translation>
    </message>
    <message>
        <location filename="../widgets/settings_dialog.py" line="122" />
        <source>Plico è installato dal gestore dei pacchetti del sistema, che lo tiene aggiornato.</source>
        <translation>Plico is installed by the system's package manager, which keeps it up to date.</translation>
    </message>
</context><context>
    <name>SignDialog</name>
    <message>
        <location filename="../widgets/sign.py" line="62" />
        <source>Firma il documento</source>
        <translation>Sign the Document</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="67" />
        <source>File del certificato (.p12)</source>
        <translation>Certificate file (.p12)</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="68" />
        <source>Sfoglia…</source>
        <translation>Browse…</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="76" />
        <source>Password del certificato</source>
        <translation>Certificate password</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="84" />
        <source>Perché firmi (facoltativo)</source>
        <translation>Why you are signing (optional)</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="86" />
        <source>Dove (facoltativo)</source>
        <translation>Where (optional)</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="88" />
        <source>Riquadro visibile sulla pagina</source>
        <translation>Visible box on the page</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="95" />
        <source>pagina</source>
        <translation>page</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="100" />
        <source>Certificato</source>
        <translation>Certificate</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="101" />
        <source>Password</source>
        <translation>Password</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="103" />
        <source>Motivo</source>
        <translation>Reason</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="104" />
        <source>Luogo</source>
        <translation>Location</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="108" />
        <source>La firma copre il file appena salvato: il documento si riapre dalla copia firmata e ogni modifica successiva la annulla.</source>
        <translation>The signature covers the file just saved: the document reopens from the signed copy, and any later change voids it.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="119" />
        <source>Firma</source>
        <translation>Sign</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="141" />
        <source>Scegli il certificato</source>
        <translation>Choose the Certificate</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="147" />
        <source>Certificati (*.p12 *.pfx);;Tutti i file (*)</source>
        <translation>Certificates (*.p12 *.pfx);;All files (*)</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="170" />
        <source>Il certificato è scaduto il {0}.</source>
        <translation>The certificate expired on {0}.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="178" />
        <source>Il certificato è valido solo dal {0}.</source>
        <translation>The certificate is valid only from {0}.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="184" />
        <source>{0}
valido fino al {1}</source>
        <translation>{0}
valid until {1}</translation>
    </message>
</context><context>
    <name>SignatureDialog</name>
    <message>
        <location filename="../widgets/sign.py" line="226" />
        <source>Firme del documento</source>
        <translation>Document Signatures</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="237" />
        <source>Aggiungi un certificato fidato…</source>
        <translation>Add a Trusted Certificate…</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="239" />
        <source>Chiudi</source>
        <translation>Close</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="254" />
        <source>Scegli un certificato da considerare fidato</source>
        <translation>Choose a certificate to trust</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="263" />
        <source>Certificato fidato</source>
        <translation>Trusted certificate</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="290" />
        <source>Il documento non contiene firme.</source>
        <translation>The document contains no signatures.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="347" />
        <source>La firma è rotta: il contenuto che copriva è stato cambiato dopo la firma.</source>
        <translation>The signature is broken: the content it covered was changed after signing.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="355" />
        <source>La firma è integra, ma il documento è stato modificato dopo: vale solo per la versione che è stata firmata.</source>
        <translation>The signature is intact, but the document was modified afterwards: it is valid only for the version that was signed.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="364" />
        <source>La firma non è valida: non corrisponde al certificato che la porta.</source>
        <translation>The signature is not valid: it does not match the certificate that carries it.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="372" />
        <source>Firma integra e valida. Il certificato però non è fra quelli che consideri fidati: aggiungi la sua autorità per sapere chi ha firmato.</source>
        <translation>Intact and valid signature. However, the certificate is not among those you trust: add its authority to know who signed.</translation>
    </message>
    <message>
        <location filename="../widgets/sign.py" line="380" />
        <source>Firma valida e firmatario attendibile.</source>
        <translation>Valid signature and trusted signer.</translation>
    </message>
</context><context>
    <name>Signing</name>
    <message>
        <location filename="../model/sign.py" line="678" />
        <location filename="../model/sign.py" line="620" />
        <location filename="../model/sign.py" line="527" />
        <location filename="../model/sign.py" line="159" />
        <source>Non riesco a leggere «{0}»: {1}</source>
        <translation>Cannot read “{0}”: {1}</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="169" />
        <source>Password errata, oppure «{0}» non è un file PKCS#12.</source>
        <translation>Wrong password, or “{0}” is not a PKCS#12 file.</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="175" />
        <source>«{0}» non contiene una chiave privata con il suo certificato.</source>
        <translation>“{0}” does not contain a private key with its certificate.</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="225" />
        <source>Firmato da %(name)s</source>
        <translation>Signed by %(name)s</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="384" />
        <source>Non riesco a firmare il documento: {0}</source>
        <translation>Cannot sign the document: {0}</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="536" />
        <source>«{0}» non è un PDF leggibile: {1}</source>
        <translation>“{0}” is not a readable PDF: {1}</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="544" />
        <source>«{0}» è protetto da una password che non apre il file.</source>
        <translation>“{0}” is protected by a password that does not open the file.</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="556" />
        <source>Non riesco a leggere le firme di «{0}»: {1}</source>
        <translation>Cannot read the signatures of “{0}”: {1}</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="576" />
        <source>Firma illeggibile: {0}</source>
        <translation>Unreadable signature: {0}</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="686" />
        <location filename="../model/sign.py" line="628" />
        <source>«{0}» non contiene certificati PEM.</source>
        <translation>“{0}” contains no PEM certificates.</translation>
    </message>
    <message>
        <location filename="../model/sign.py" line="655" />
        <source>Non riesco a conservare il certificato in «{0}»: {1}</source>
        <translation>Cannot store the certificate in “{0}”: {1}</translation>
    </message>
</context><context>
    <name>TextEdit</name>
    <message>
        <location filename="../model/textedit.py" line="287" />
        <source>Si può modificare solo testo orizzontale.</source>
        <translation>Only horizontal text can be edited.</translation>
    </message>
    <message>
        <location filename="../model/textedit.py" line="292" />
        <source>Questo testo usa un font Type3 e non si può modificare.</source>
        <translation>This text uses a Type3 font and cannot be edited.</translation>
    </message>
    <message>
        <location filename="../model/textedit.py" line="306" />
        <source>Nessun font disponibile contiene questi caratteri.</source>
        <translation>No available font contains these characters.</translation>
    </message>
    <message>
        <location filename="../model/textedit.py" line="314" />
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
</context><context>
    <name>UpdateChecker</name>
    <message>
        <location filename="../updates.py" line="147" />
        <source>Risposta di GitHub non valida.</source>
        <translation>GitHub's answer is not valid.</translation>
    </message>
    <message>
        <location filename="../updates.py" line="179" />
        <source>Errore HTTP {0} da GitHub.</source>
        <translation>GitHub HTTP error {0}.</translation>
    </message>
    <message>
        <location filename="../updates.py" line="192" />
        <source>Limite di richieste a GitHub raggiunto, riprova più tardi.</source>
        <translation>GitHub request limit reached, try again later.</translation>
    </message>
    <message>
        <location filename="../updates.py" line="195" />
        <source>Limite di richieste a GitHub raggiunto (60 all'ora per indirizzo IP): riprova dopo le {0}.</source>
        <translation>GitHub request limit reached (60 an hour per IP address): try again after {0}.</translation>
    </message>
    <message>
        <location filename="../updates.py" line="234" />
        <source>GitHub non è raggiungibile ({0}).</source>
        <translation>GitHub cannot be reached ({0}).</translation>
    </message>
</context></TS>
