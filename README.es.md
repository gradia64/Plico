<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/Lang-Italiano-green?style=for-the-badge" alt="Italiano"></a>
  <a href="README.en.md"><img src="https://img.shields.io/badge/Lang-English-blue?style=for-the-badge" alt="English"></a>
  <a href="README.fr.md"><img src="https://img.shields.io/badge/Lang-Français-blue?style=for-the-badge" alt="Français"></a>
  <a href="README.de.md"><img src="https://img.shields.io/badge/Lang-Deutsch-blue?style=for-the-badge" alt="Deutsch"></a>
</p>

# Plico

Un verdadero editor PDF nativo para Linux, creado con **Qt6** y **PySide6**, que
usa **PyMuPDF** para leer y renderizar PDFs y **pikepdf** (qpdf) para
comprimirlos.

> El archivo PDF no se toca hasta que guardas.

## Características

- **Rotar, eliminar, reordenar** páginas (arrastrar y soltar en la barra de miniaturas)
- **Unir** otro PDF: sus páginas se añaden a las ya abiertas sin copiar
  nada, porque cada página virtual sabe a qué documento fuente pertenece.
  También se puede unir una imagen (un recibo fotografiado al final de un PDF)
- **Crear un PDF a partir de imágenes** (_Archivo → Crear desde imágenes…_,
  `Ctrl+Shift+N`): fotos y escaneos — PNG, JPEG, TIFF, BMP, GIF — se
  convierten en una página cada uno, en el orden elegido. Un escaneo mantiene
  su tamaño real (un A4 a 300 dpi sigue siendo un A4), una foto de teléfono
  se ajusta a un A4 vertical, y los JPEG se incrustan sin recomprimirse
- **Extraer páginas** (dividir) en un archivo nuevo con un rango como
  `1-3,5,8` — el orden escrito se conserva, así que también sirve para
  reordenar
- **Ajustes** (*Ajustes → Configurar Plico…*, `Ctrl+Mayús+,`): el idioma de
  la interfaz — automático, es decir el del sistema, o uno entre italiano,
  inglés, francés, alemán y español; con una lengua de sistema que Plico no
  tiene se usa el inglés — y el icono en el área de notificación. Con el
  icono también se puede hacer que la X reduzca Plico al área de notificación
  en lugar de cerrarlo: se sale desde *Archivo → Salir* (`Ctrl+Q`) o desde
  «Salir» en el menú del icono. El idioma cambia en el próximo inicio
- **Deshacer/Rehacer** completo, respaldado por `QUndoStack`
- **Renderizado asíncrono** en un hilo separado — la interfaz nunca se bloquea
- **Renderizado perezoso**: solo se renderizan las páginas visibles, no todo
  el documento
- **Caché de páginas con presupuesto de bytes**, LRU para miniaturas
- **Guardado en archivo temporal**: el PDF original nunca se toca.
  `Ctrl+S` guarda en el archivo abierto (o en el último «Guardar como»),
  `Ctrl+Shift+S` pregunta dónde; el título marca los cambios sin guardar con
  `*`, y cerrar o abrir otro archivo pregunta antes de perderlos. `Ctrl+W`
  (_Archivo → Cerrar_) cierra el documento dejando la ventana abierta
- **Guardado comprimido** en tres niveles, más «solo imágenes» y «páginas a
  remuestrear»: la ganancia es la real, medida sobre el archivo realmente
  escrito (y el nivel «ligero» es sin pérdida)
- **Redacción verdadera**: se dibuja una zona sobre los datos a eliminar, o
  se arrastra sobre las palabras, y al guardar el texto se **elimina**, no se
  cubre — lo que queda ya no se puede copiar ni buscar. También desaparecen
  los campos de formulario y las notas bajo la zona, mientras que redactar
  una palabra no toca las líneas de arriba y abajo
- **Rellenar formularios AcroForm**: se escribe sobre la página, con el panel
  «Formulario» a la vista — texto, incluso multilínea, casillas y listas
  desplegables — y los valores llegan al archivo al guardar, con
  deshacer/rehacer
- **Edición mínima de texto**: un clic en una línea la abre en un editor
  sobre la página; el texto viejo se quita del archivo y el nuevo se escribe
  en el mismo sitio, con el mismo tamaño, color y — cuando está instalado —
  la misma fuente. Las líneas cercanas quedan intactas incluso con
  interlineado simple
- **OCR** (_Editar → Reconocer texto…_, `Ctrl+Shift+O`): un escaneo se vuelve
  **buscable y seleccionable** sin cambiar su aspecto — el texto reconocido
  se escribe bajo la imagen, invisible. Se eligen qué páginas y en qué idioma,
  y cada ejecución es un solo paso de deshacer
- **Firma** (_Archivo → Firmar…_, `Ctrl+Shift+D`): una firma **PAdES** con
  tu propio certificado, invisible o impresa en un recuadro en la página, y
  _Archivo → Verificar firmas…_ para releer quién firmó y si el documento se
  tocó después. Una segunda firma se añade a la primera sin romperla

### Requisito de aceptación

Un PDF de **300 páginas** se abre en menos de 2 segundos y sigue siendo
reactivo: al abrirse se renderizan 2 páginas y ~12 miniaturas, no 300. La
caché de páginas contiene como mucho unas pocas entradas, independientemente
del tamaño del documento. Cubierto por
[`test_large_document_stays_responsive`](https://github.com/gradia64/Plico/blob/main/tests/test_integration.py).

## Arquitectura

```
plico/
├── pyproject.toml
└── src/plico/
    ├── app.py                 # punto de entrada
    ├── main_window.py         # MainWindow + cableado worker/model/view
    ├── model/
    │   ├── document.py        # DocumentModel, PageItem
    │   ├── commands.py        # QUndoCommand: RotatePage, DeletePage, AddRedaction, SetFieldValue…
    │   ├── redact.py          # rectángulos de redacción, matrices de rotación
    │   ├── forms.py           # campos AcroForm: lectura, escritura, vaciado
    │   ├── textedit.py        # edición de una línea de texto: span, verificación, reescritura
    │   ├── ocr.py             # reconocimiento con Tesseract, capa invisible, idiomas
    │   ├── sign.py            # firma PAdES con pyHanko y relecura de firmas
    │   ├── images.py          # de imágenes a PDF: A4, dpi, EXIF, JPEG intactos
    │   ├── save.py            # save_as(), save_compressed(), extract_pages()
    │   ├── assemble.py        # páginas de varios PDFs, campos de formulario intactos
    │   └── optimize.py        # niveles de compresión, optimize_in_place()
    ├── rendering/
    │   └── worker.py          # RenderWorker en QThread
    └── widgets/
        ├── page_view.py       # QScrollArea: renderizado, ajuste de ancho, HiDPI, redacción, campos
        ├── thumbnail_bar.py   # QListView + modelo + caché, carga perezosa
        ├── form_panel.py      # panel «Formulario»: un editor por campo
        ├── ocr.py             # diálogo de idiomas/páginas y tarea de reconocimiento
        ├── sign.py            # diálogos de firma y verificación de firmas
        └── compress.py        # diálogo de opciones, format_size, tarea
```

### Concepto clave

El modelo nunca modifica el PDF: es solo una lista de **páginas virtuales**.
Cada página virtual es un par `(source_id, source_index)` más la rotación
elegida por el usuario. Todo deriva de esta lista:

- **deshacer/rehacer**: manipula una lista de Python, no el archivo
- **unión**: añadir un PDF solo añade páginas que apuntan a un segundo
  `source_id`; no se copia ninguna página
- **renderizado**: el worker abre los documentos fuente en solo lectura, a
  petición, y renderiza sin coordinarse con el modelo
- **guardado**: materializa la lista copiando cada fuente una sola vez y luego
  colocando las páginas en orden en el archivo de salida — copiar dos veces
  de la misma fuente renombraría o perdería los campos del formulario

La identidad de una página es siempre el par `(source_id, source_index)`,
nunca solo `source_index`: tras una unión dos páginas tienen normalmente el
mismo índice en documentos distintos, y usar solo uno las colapsaría en una
sola (miniatura incorrecta, pixmap reutilizado de la caché por error).

Las vistas **observan el modelo**: `PageView` y `ThumbnailBar` se conectan a
las señales `changed` / `page_changed`, de modo que un deshacer se refleja
automáticamente en ambas sin que la ventana tenga que recordar actualizarlas.

### Rotación: dos valores, no uno

`base_rotation` es el `/Rotate` original del PDF, `rotation` es el desfase
elegido por el usuario. El renderizado compone ambos, el guardado escribe la
suma (`total_rotation`). Las claves de caché incluyen la rotación, de lo
contrario una página rotada reutilizaría la miniatura anterior.

### Guardar sobre el archivo abierto

Guardar sobre el mismo archivo que se está leyendo está permitido: el nuevo
documento se escribe en un archivo temporal en la misma carpeta y sustituye
al original solo al final. Un error de escritura no destruye por tanto el
archivo del usuario.

Tras una unión hay más de una fuente, así que la comprobación cubre **todas**
las fuentes: guardar sobre cualquiera de los PDFs abiertos pasa por el
archivo temporal, porque PyMuPDF no puede escribir en un documento que está
leyendo.

Tras guardar sobre el archivo abierto, Plico **reabre** el archivo guardado:
ese es el documento ahora, con eliminaciones, rotaciones y redacciones ya
dentro. Por eso los cambios hechos hasta ahí ya no se pueden deshacer.
Extraer páginas sobre un archivo abierto, en cambio, no está permitido.

### Compresión: dónde se gana de verdad

«Guardar comprimido» (`Ctrl+Shift+C`) escribe una copia más pequeña del
documento virtual — por tanto respeta eliminaciones, reordenaciones y
rotaciones — y deja intactos los PDFs de partida.

| Nivel | Qué hace | ¿Sin pérdida? |
| --- | --- | --- |
| **Ligero** | fusiona los content stream fragmentados, compacta la estructura | sí |
| **Medio** | como arriba, más imágenes por encima de 200 dpi reducidas a 150 (calidad 80) | no |
| **Fuerte** | imágenes por encima de 150 dpi reducidas a 96 (calidad 60) | no |

La mayor ganancia no viene de las imágenes sino del `clean` de mutool: un
PDF que ha pasado por copias y ediciones arrastra cientos de content stream
diminutos, y fusionarlos vale, en un documento de texto, 188 KB → 12 KB
(6%). En un escaneo la estructura no tiene nada que dar, y solo cuenta el
trabajo sobre las imágenes (un JPEG de 3,4 MB en 3 páginas se queda al
100% con «ligero», baja al 52% con «medio» y al 36% con «fuerte»).

El nivel dice _cuánto_, no _qué_: bajo el desplegable hay dos opciones más.
**«Solo las imágenes»** salta la recompactación del archivo — sirve en un
escaneo, donde la ganancia está en las imágenes, mientras que en un
documento solo de texto no gana nada y el programa lo dice en lugar de
escribir una copia idéntica. **«Páginas a remuestrear»** deja intactas las
imágenes de las otras páginas, útil cuando entre escaneos pesados hay páginas
de texto. Hay un caso en el que no se gana nada: si dos páginas comparten la
misma imagen, comprimir solo una obligaría a la otra a tener su propia copia,
y el archivo crecería — entonces no se escribe nada, y el mensaje lo explica.

La ganancia no es una estimación: el archivo comprimido se escribe de verdad
(junto al destino) y solo después el programa dice cuánto pesa, adoptándolo
solo si ganó.

La compresión corre en un hilo separado, así que la ventana sigue reactiva
incluso con archivos grandes.

### Redacción: el texto se va de verdad

`Ctrl+Shift+X` (_Editar → Redactar zona_) activa la herramienta: se arrastra
un rectángulo sobre los datos a eliminar, un clic seco sobre una zona la
cancela, `Esc` sale. Una zona ya dibujada se **corrige sin rehacerla**: las
esquinas la redimensionan, el centro la mueve. Las zonas quedan
**editables hasta que guardas** — son comandos de deshacer como los demás
(`Ctrl+Z`) y la vista previa oscura en la página muestra exactamente dónde
acabarán.

Al guardar, PyMuPDF reescribe los content stream y **quita** las palabras
que caen dentro de la zona: en el archivo no quedan ni el texto ni la imagen
bajo el rectángulo. Un rectángulo negro dibujado encima — lo que hacen
bastantes herramientas — dejaría el secreto copiable y buscable. Con el
contenido se van también las **notas** y los **campos del formulario** que
la zona toca: un campo rellenado con un nombre quedaría de otro modo en el
archivo, valor incluido.

`Ctrl+Shift+F` (_Editar → Redactar palabra…_) busca en cambio una palabra en
**todas** las páginas y marca cada ocurrencia de un golpe, como un solo paso
de deshacer. Busca también en el texto reconocido por OCR, incluso antes de
guardar.

`Ctrl+Shift+L` (_Editar → Redactar selección_) es la tercera vía, la que
espera quien ha usado un editor: se arrastra sobre las palabras a eliminar y
se marcan **enteras**, una por una, con una marca tan ajustada como la
palabra. El arrastre es un solo gesto, así que un `Ctrl+Z` deshace toda la
selección; arrastrar donde no hay texto no deja nada; un clic sobre una marca
la quita, como en la zona, y una marca también se mueve y redimensiona.
Funciona también sobre las palabras leídas por OCR.

Cuatro cosas que saber:

- las palabras se toman **enteras** (una marca a mitad de palabra no
  ocultaría nada), y la unidad mínima es la palabra, no la letra;
- una marca de palabra — de _Redactar palabra_ o de _Redactar selección_ —
  quita el texto de **su línea solo**: con interlineado simple las letras de
  las líneas de arriba y abajo tocan su recuadro, y se quedan donde están.
  Una zona **dibujada**, en cambio, elimina todo lo que toca, porque es lo
  que se dibujó, y lo mismo vale para una marca de palabra que se ha movido
  o redimensionado;
- `apply_redactions()` también elimina la gráfica vectorial que toca el
  rectángulo, así que un borde o una tabla a horcajadas de la marca pueden
  desaparecer;
- un clic sobre una marca la quita aunque el ratón se haya movido un píxel:
  es un clic, no un arrastre, y `Ctrl+Z` la devuelve exactamente donde
  estaba.

Los metadatos del PDF, en cambio, no son un riesgo: el archivo de salida se
reconstruye solo a partir de las páginas, así que `/Info`, el XMP y los
adjuntos nunca llegan.

### Edición de texto: una línea a la vez

`Ctrl+Shift+T` (_Editar → Editar texto_) activa la herramienta: un clic en
una línea **ya presente** en el PDF abre un pequeño editor sobre ella,
**Intro** confirma, **Esc** cancela. Un clic donde no hay texto, o en una
página que es solo una imagen (un escaneo), lo dice junto al puntero. La
herramienta corrige el texto que hay: no añade texto nuevo en un hueco vacío.
La corrección se ve enseguida en la página y es un comando como los demás
(`Ctrl+Z`); entra en el archivo solo al guardar, donde el texto viejo se
**quita** del content stream — no se cubre — y el nuevo se escribe en el
mismo sitio. El fondo, los bordes de las tablas y el texto de al lado quedan,
y también las líneas de arriba y abajo: el texto viejo se quita de una banda
alrededor de la línea, no de su recuadro, que con interlineado simple tocaría
también a las vecinas.

Es una edición _mínima_, y lo dice: un texto que no cabe en el espacio libre
(hasta el borde de la celda, la palabra siguiente o el margen de la página,
incluso en una página rotada) se encoge hasta el 80% y más allá se rechaza,
con el motivo en la barra de estado. No se editan el texto vertical ni las
fuentes Type3. La fuente es la del documento cuando se puede reutilizar, si
no la misma instalada en el sistema, si no una parecida (serif, sans o
monoespaciada) con el mismo estilo.

### Formularios: rellenar el PDF, no solo leerlo

Se rellena **sobre la página**: un clic en un campo de texto abre el editor
donde está el campo, una casilla se marca donde la clicaste, un botón de
opción elige la respuesta que representa. El panel **Formulario** (a la
derecha) lista los campos de la página en vista y sigue siendo la vía para
los que no se escriben en la página — listas desplegables, texto
multilínea, campos de solo lectura. Los valores quedan **editables hasta
que guardas** y pasan por el mismo deshacer/rehacer que el resto (`Ctrl+Z`).

Un campo AcroForm no es contenido del PDF sino una anotación con un valor, y
Plico lo trata como tal: las **descripciones** de los campos vienen de la
fuente, los **valores** que escribes viven en el modelo, y `save.py` los
aplica mientras materializa las páginas — antes de las redacciones, así que
una redacción sobre un campo se lo lleva. El valor dibujado en la página es
el del modelo, es decir, el que _estará_ en el archivo.

Un campo se escribe **solo si lo tocas**: uno que nunca se abrió conserva el
valor que tenía en la fuente, que no es lo mismo que vaciarlo. Un grupo de
botones de opción es **una sola pregunta** — el panel lo muestra como una
lista desplegable con las respuestas — y también se puede elegir haciendo
clic en uno en la página. Las firmas pertenecen a _Archivo → Firmar…_.

### OCR: hacer buscable un escaneo

_Editar → Reconocer texto…_ (`Ctrl+Shift+O`) lee las páginas elegidas con
Tesseract y escribe bajo la imagen una **capa de texto invisible** (modo de
renderizado 3). La página se ve idéntica, pero el texto se puede
seleccionar, copiar, buscar con `Ctrl+F` — y _Redactar palabra_
(`Ctrl+Shift+F`) por fin lo encuentra, cosa imposible en un escaneo sin
marcar. Lo encuentra enseguida, no solo después de guardar: la capa entra en
el archivo al guardar, pero la búsqueda también mira las palabras recién
reconocidas.

El reconocimiento cuesta (alrededor de medio segundo por página A4 a 300
dpi), por eso no es automático: se dice qué páginas (la actual, la actual y
las siguientes, o todo el documento) y en qué idioma, con italiano e inglés
juntos como propuesta. Corre en el pool de hilos con una barra de progreso
cancelable — mientras corre la ventana no acepta ediciones en las páginas
que está leyendo — y cada ejecución es **un solo** paso de deshacer: un
`Ctrl+Z` quita la capa de todas las páginas de una vez.

La fuente de la capa es una de las Base-14 y no se incrusta, así que hacer
buscable un escaneo no añade un byte. Las palabras que el PDF ya contenía
no se reescriben: una página mitad texto y mitad escaneo no acaba con el
texto duplicado.

Los datos de idioma (`*.traineddata`) van en
`~/.local/share/plico/tessdata/`, sin root; el Flatpak ya trae italiano,
inglés, español, francés y alemán, y propone el idioma de la interfaz junto
con el inglés. La biblioteca Tesseract debe estar presente: en el Flatpak
está compilada dentro (ver Flatpak), en una distribución es el paquete
`tesseract` / `libtesseract`.

### Firma: un PDF firmado, no un sello

_Archivo → Firmar…_ (`Ctrl+Shift+D`) firma el documento con un certificado
PKCS#12 (`.p12` / `.pfx`) y produce una firma **PAdES** — el perfil de
firma PDF que los lectores europeos reconocen. Se elige si la firma queda
invisible o aparece en un recuadro abajo a la derecha con nombre, fecha y
motivo: el recuadro es contenido de la página, así que no se puede quitar
sin romper la firma.

Cuatro cosas que esta implementación hace y una que no:

- **La firma es el último byte del archivo.** Primero se materializa el
  documento (con todos los campos rellenados, el texto reescrito, las
  redacciones aplicadas, las páginas rotadas), luego se firma. El orden
  inverso produciría una firma que cubre una versión del documento distinta
  de la que ve el usuario.
- **Firmar adopta el archivo firmado.** Tras _Firmar…_ la sesión apunta al
  nuevo archivo, porque seguir trabajando sobre la lista de páginas que lo
  generó significaría perder la firma en el siguiente guardado.
- **Una segunda firma se añade a la primera.** Si el documento firmado no
  tiene cambios sin guardar, la firma nueva se añade al archivo tal cual (una
  actualización incremental) y la primera sigue válida. Con cambios sin
  guardar el archivo hay que reescribirlo y la firma anterior ya no cubriría
  nada, así que se quita y queda solo la nueva: el programa lo dice antes y
  pregunta si continuar.
- **Guardar sobre un archivo firmado pregunta antes.** Un guardado normal
  reescribe el PDF desde cero: la firma ya no está, y el archivo guardado no
  lleva una rota en su lugar. El programa lo dice y espera un «sí», en
  lugar de hacerlo y ya.
- **No decide en quién confiar.** Plico no trae consigo ningún almacén de
  autoridades: una firma íntegra y válida de un certificado desconocido se
  muestra como «íntegra, pero el certificado no está entre los que
  consideras de confianza». Se añaden los certificados en los que confías
  uno por uno (archivos `.pem`) y quedan en `QSettings`.

_Archivo → Verificar firmas…_ relee las firmas del **archivo en disco** y
distingue los casos que importan: firma íntegra y de confianza; íntegra pero
de un certificado desconocido (ámbar, no rojo: es igualmente una firma
verdadera); íntegra pero sobre un documento **modificado después de firmar**
— válida solo para la versión firmada; firma **rota**, es decir, el
contenido que cubría ha cambiado (rojo, siempre, incluso si el archivo tiene
revisiones posteriores); firma no válida o certificado caducado. Un módulo
que nunca se firmó no se confunde con un documento firmado.

### Integración con el escritorio (KDE)

- **Iconos del tema** (`QIcon.fromTheme`: `document-open`, `document-save-as`,
  `edit-undo`, `object-rotate-right`, `zoom-in`, …): ningún recurso gráfico
  en el paquete. Si el tema no proporciona el icono, la acción queda sin
  icono en lugar de mostrar un cuadrado vacío.
- **Cinco idiomas**: italiano, inglés, español, francés y alemán, incluso en
  los botones de los diálogos estándar de Qt y en los metadatos de la
  tienda (ver «Traducir Plico»).
- **Estado de la sesión en `QSettings`** (`~/.config/Plico/plico.conf`):
  geometría de la ventana, disposición de paneles y barra de herramientas, y
  factor de zoom.

## Requisitos

- Python ≥ 3.11
- PySide6 ≥ 6.7
- PyMuPDF (pymupdf) ≥ 1.24.3
- pikepdf ≥ 9 (compresión dirigida)
- pyHanko ≥ 0.37 (firma PAdES; trae consigo criptografía y validación)
- Tesseract (biblioteca, 4 o 5) y al menos un dato de idioma para el OCR —
  el Flatpak trae ambos

## Instalación

```
pip install -e ".[dev]"
```

El punto de entrada acepta los archivos a abrir, como se espera de una app
de escritorio:

```
plico relazione.pdf              # abre
plico a.pdf b.pdf                # abre a.pdf y le une b.pdf
plico ricevuta.jpg a.pdf         # crea un documento a partir de la foto y le une a.pdf
```

Acepta también las URL `file:///…` que pasan algunos lanzadores. El archivo
`.desktop` pide de todos modos rutas (`Exec=plico %F`).

## Flatpak

El empaquetado está en `flatpak/` y está pensado para publicarse en Flathub.

| Archivo | Rol |
| --- | --- |
| `io.github.gradia64.plico.json` | manifiesto de la aplicación |
| `python3-pymupdf.json` | módulo para PyMuPDF, con wheel y `sha256` fijados |
| `python3-pikepdf.json` | módulo para pikepdf, con wheel y `sha256` fijados |
| `python3-pyhanko.json` | módulo para pyHanko y sus dependencias, siempre desde wheels |
| `io.github.gradia64.plico.desktop` | lanzador (registra `application/pdf`, recibe rutas con `%F`) |
| `io.github.gradia64.plico.metainfo.xml` | metadatos AppStream |
| `io.github.gradia64.plico.svg` | icono |

Ocho decisiones no obvias:

- **`base: io.qt.PySide.BaseApp`** en lugar de instalar PySide6 con pip. La
  BaseApp de Flathub ya contiene PySide6 compilado y alineado con el Qt de
  `org.kde.Platform`, así que el bundle no duplica Qt ni arriesga sobrescribir
  la versión del runtime. Por eso la instalación de la aplicación usa
  `--no-deps`: PySide6 viene del runtime, PyMuPDF de su módulo, y pip no
  debe ni intentar descargar PySide6 de PyPI.
- **PyMuPDF desde un wheel `manylinux`** (`cp310-abi3`, válido para todo
  Python ≥ 3.10, por tanto también para el 3.13 del runtime) y no desde
  fuentes: compilar MuPDF dentro del manifiesto requeriría `swig` y varios
  minutos de build.
- **pikepdf desde un wheel `cp313`** (el intérprete de la BaseApp, que no es
  el del venv) **instalado con `--no-deps`**: pikepdf declara `Pillow`,
  `lxml` y `packaging`, pero `open()` y `save()` no los importan, y
  `packaging` ya está en la BaseApp. Si se necesitaran las API sobre imágenes
  o el soporte PDF/A, habría que añadir también sus wheels.
- **pyHanko desde wheels, en un solo módulo** (`python3-pyhanko.json`):
  pyHanko arrastra consigo `cryptography`, `asn1crypto`, `aiohttp`, `lxml` y
  una decena de dependencias más, todas puras Python o con wheel `manylinux`
  para el 3.13 de la BaseApp, así que se instalan de una vez con
  `--no-index --no-deps`. Son los veinte archivos listados en el módulo,
  cada uno con su `sha256`: la firma digital es la parte del programa en la
  que «más o menos esa versión» no es una respuesta aceptable.
- **Las traducciones se compilan durante el build**: `lrelease` existe solo
  en el SDK de Qt, no en el runtime, y los `.qm` son los únicos archivos que
  se necesitan en runtime. El módulo `plico` instala los `.ts` con el paquete
  y luego los compila en `/app/share/plico/translations`, así que el
  compilador no acaba en el bundle.
- **`cleanup-commands: /app/cleanup-BaseApp.sh`**, requerido por la BaseApp.
- **Sin acceso a la home** (nada de `--filesystem`): cada archivo pasa por el
  selector de archivos del portal (`org.freedesktop.portal.FileChooser`), que
  Qt usa por su cuenta dentro de Flatpak. Plico ve el documento como
  `/run/user/<uid>/doc/<id>/nombre.pdf` y lo lee y escribe ahí, guardado
  atómico incluido (el temporal en la misma carpeta y `os.replace` funcionan
  también en el document portal); para proponer una ruta en los diálogos usa
  en cambio la real, que el portal expone en el atributo extendido
  `user.document-portal.host-path`. El lanzador usa `%F`, así que un doble
  clic ya llega como ruta exportada en el portal.
- **`--talk-name=org.kde.StatusNotifierWatcher`**, el único permiso D-Bus: sin
  él, dentro de la sandbox el área de notificación no existe y el icono de
  los Ajustes no aparece (probado en Plasma). Qt registra el icono con su
  nombre único en el bus, así que no hace falta poseer otros nombres. El icono
  es opcional y está apagado por defecto.

Compilar e instalar en tu propia cuenta:

```
# una sola vez: builder, SDK y BaseApp
flatpak remote-add --user --if-not-exists flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.flatpak.Builder//stable \
    org.kde.Sdk//6.11 io.qt.PySide.BaseApp//6.11

# build + install. La caché está FUERA del proyecto: build-dir/ y
# .flatpak-builder/ dentro del árbol los encuentran las búsquedas globales y
# contienen copias de las fuentes.
flatpak run org.flatpak.Builder --force-clean --user --install \
    --install-deps-from=flathub \
    --state-dir="$HOME/.cache/plico-flatpak/state" \
    "$HOME/.cache/plico-flatpak/build" \
    flatpak/io.github.gradia64.plico.json

flatpak run io.github.gradia64.plico
```

Las **capturas** de la tienda están en `flatpak/screenshots/` y las produce
`tools/screenshots.py` desde la app real; en el metainfo apuntan al tag de la
última versión, y cada versión los mueve a su nuevo tag.

### Lanzamiento

Flathub no construye desde el checkout sino desde un tag git, fijado también
a su commit. El manifiesto de `flatpak/` sigue siendo el de desarrollo
(`type: dir`), y el que se envía lo genera `tools/flathub_manifest.py`
**desde el tag**. Antes de escribir comprueba que:

- el tag sea `v` + la versión de `pyproject.toml` + el último `<release>`
  de la metainfo;
- las capturas de la metainfo apunten al tag y no a `main`;
- el tag esté anotado, firmado por una clave de `.github/allowed_signers` y
  presente en `origin` con el mismo objeto.

Los tags se firman con la clave **SSH** (nada de PGP que guardar). Una vez
por checkout:

```
git config gpg.format ssh
git config user.signingkey ~/.ssh/id_ed25519.pub
git config tag.gpgSign true
git config gpg.ssh.allowedSignersFile "$PWD/.github/allowed_signers"
```

Para que GitHub muestre el tag como «Verified», la misma clave debe
registrarse también como _signing key_ de la cuenta (Settings → SSH and GPG
keys → New SSH key → Signing key).

En cada lanzamiento:

```
# 1. versión en pyproject.toml, nuevo <release> y URL de las capturas
#    (…/Plico/vX.Y.Z/flatpak/screenshots/…) en la metainfo; commit y push
# 2. tag firmado, verificado, publicado
git tag -s v0.1.0 -m "Plico 0.1.0"
git tag -v v0.1.0
git push origin v0.1.0
# 3. el manifiesto para Flathub, con los módulos que incluye
python tools/flathub_manifest.py v0.1.0 ~/flathub/io.github.gradia64.plico
```

`--allow-unsigned --offline` hace una prueba en seco sobre un tag local no
firmado.

## Desarrollo

```
# tests (sin display, gracias a QT_QPA_PLATFORM=offscreen).
# NB: pytest no está en .venv/bin, así que se pasa por python -m
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q

# lint + tipos
ruff check src/ tests/ tools/
mypy src/plico

# arranque
plico            # o: python -m plico.app

# capturas para la tienda (flatpak/screenshots), en inglés o en otro idioma
QT_QPA_PLATFORM=offscreen python tools/screenshots.py [it|es|fr|de]
```

La **CI** (GitHub Actions, `.github/workflows/`) hace lo mismo en cada push
y pull request: `ci.yml` ejecuta tests, `ruff` y `mypy` en Python 3.11 y 3.13
y valida metainfo, `.desktop` y manifiesto; `flatpak.yml`, en `main` y a
petición desde la pestaña Actions, construye el Flatpak real, lo pasa al
linter de Flathub (`flatpak-builder-lint`) y deja el paquete `plico.flatpak`
entre los artefactos de la run, instalable con
`flatpak install --user plico.flatpak`.

### Traducir Plico

Plico habla **italiano**, **inglés**, **español**, **francés** y **alemán**:
sigue el idioma del sistema, y un idioma que no conoce recibe el inglés. Las
cadenas están en italiano en el código; los catálogos de los demás idiomas
están en `src/plico/translations/plico_{en,es,fr,de}.ts` y se modifican con
Qt Linguist o con un editor de texto. Un idioma nuevo es un archivo
`plico_xx.ts` más (CONTESTO.md, «Los idiomas», dice qué actualizar junto).

`pylupdate6` viene con PyQt6 (`pip install PyQt6` en el venv basta, solo se
necesita la herramienta): sin ella, `tests/test_i18n.py` se salta justo la
comprobación que avisa cuando falta una cadena nueva en el catálogo.

```
# 1. reextraer las cadenas tras tocar el código,
#    en los cuatro catálogos
for l in en es fr de; do
    pylupdate6 -no-obsolete src/plico -ts src/plico/translations/plico_$l.ts
done

# 2. compilar: pyside6-lrelease viene con PySide6 (o lrelease del SDK)
pyside6-lrelease src/plico/translations/plico_de.ts -qm /tmp/plico_de.qm

# 3. probarla sin instalar nada
LANG=de_DE.UTF-8 PLICO_TRANSLATIONS=/tmp plico
```

`tests/test_i18n.py` comprueba que los catálogos sean los que producen las
fuentes, así que ninguna cadena nueva se queda fuera;
`tests/test_translations.py` que cada idioma esté completo, conserve los
marcadores de posición (`{0}`) y no dé el mismo atajo a dos entradas del
menú.

## Licencia

GPL v3 — ver [LICENSE](https://github.com/gradia64/Plico/blob/main/LICENSE).

## About

Un verdadero editor PDF nativo para Linux: unir, dividir, rotar, reordenar, guardar. Qt6 + PySide6 + PyMuPDF.

### Topics

[desktop-application](https://github.com/topics/desktop-application) [flatpak](https://github.com/topics/flatpak) [kde](https://github.com/topics/kde) [linux](https://github.com/topics/linux) [pdf](https://github.com/topics/pdf) [pdf-editor](https://github.com/topics/pdf-editor) [pymupdf](https://github.com/topics/pymupdf) [pyside6](https://github.com/topics/pyside6) [python](https://github.com/topics/python) [qt6](https://github.com/topics/qt6)

### Resources

[Readme](https://github.com/gradia64/Plico#readme-ov-file)

[GPL-3.0 license](https://github.com/gradia64/Plico#GPL-3.0-1-ov-file)

[Activity](https://github.com/gradia64/Plico/activity)