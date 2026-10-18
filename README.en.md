<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/Lang-Italiano-green?style=for-the-badge" alt="Italiano"></a>
  <a href="README.fr.md"><img src="https://img.shields.io/badge/Lang-Français-blue?style=for-the-badge" alt="Français"></a>
  <a href="README.de.md"><img src="https://img.shields.io/badge/Lang-Deutsch-blue?style=for-the-badge" alt="Deutsch"></a>
  <a href="README.es.md"><img src="https://img.shields.io/badge/Lang-Español-orange?style=for-the-badge" alt="Español"></a>
</p>

# Plico

A true native PDF editor for Linux, built with **Qt6** and **PySide6**, using
**PyMuPDF** to read and render PDFs and **pikepdf** (qpdf) to compress them.

> The PDF file is never touched until you save.

## Features

- **Rotate, delete, reorder** pages (drag & drop in the thumbnail bar)
- **Merge** another PDF: its pages are appended to the ones already open
  without copying anything, because every virtual page knows which source
  document it belongs to. You can also merge an image (a photographed
  receipt tacked onto the end of a PDF)
- **Create a PDF from images** (_File → Create from images…_, `Ctrl+Shift+N`):
  photos and scans — PNG, JPEG, TIFF, BMP, GIF — become one page each, in
  the chosen order. A scan keeps its real size (an A4 at 300 dpi stays an
  A4), a phone photo is fitted to a portrait A4, and JPEGs are embedded
  without being recompressed
- **Extract pages** (split) into a new file with a range like `1-3,5,8` —
  the typed order is preserved, so this doubles as reordering
- **Undo/Redo** in full, backed by `QUndoStack`
- **Asynchronous rendering** in a separate thread — the UI never blocks
- **Lazy rendering**: only the visible pages are rendered, not the whole
  document
- **Byte-budgeted page cache**, LRU for thumbnails
- **Save to a temporary file**: the original PDF is never touched.
  `Ctrl+S` saves to the open file (or to the last "Save as"), `Ctrl+Shift+S`
  asks where; the title marks unsaved changes with `*`, and closing or
  opening another file asks before losing them. `Ctrl+W` (_File → Close_)
  closes the document while keeping the window open
- **Compressed save** at three levels, plus "images only" and "pages to
  resample": the gain is the real one, measured on the file actually written
  (and the "light" level is lossless)
- **True redaction**: draw a zone over the data to remove, or drag over the
  words, and at save time the text is **removed**, not covered — what
  remains can no longer be copied or searched. Form fields and notes under
  the zone go too, while redacting a word leaves the lines above and below
  untouched
- **Fill AcroForm forms**: type on the page, with the "Form" dock in view —
  text, including multi-line, checkboxes and dropdowns — and the values land
  in the file at save time, with undo/redo
- **Minimal text editing**: a click on a line opens an editor on the page;
  the old text is removed from the file and the new one written in the same
  spot, with the same size, colour and — when installed — the same font.
  Nearby lines stay intact even with single line spacing
- **OCR** (_Edit → Recognise text…_, `Ctrl+Shift+O`): a scan becomes
  **searchable and selectable** without changing its appearance — the
  recognised text is written under the image, invisible. You choose which
  pages and in which language, and each run is a single undo step
- **Signing** (_File → Sign…_, `Ctrl+Shift+D`): a **PAdES** signature with
  your own certificate, invisible or printed in a box on the page, and
  _File → Verify signatures…_ to read back who signed and whether the
  document was touched afterwards. A second signature is appended without
  breaking the first

### Acceptance requirement

A **300-page** PDF opens in under 2 seconds and stays responsive: at open
time only 2 pages and ~12 thumbnails are rendered, not 300. The page cache
holds at most a handful of entries regardless of document size. Covered by
[`test_large_document_stays_responsive`](https://github.com/gradia64/Plico/blob/main/tests/test_integration.py).

## Architecture

```
plico/
├── pyproject.toml
└── src/plico/
    ├── app.py                 # entry point
    ├── main_window.py         # MainWindow + worker/model/view wiring
    ├── model/
    │   ├── document.py        # DocumentModel, PageItem
    │   ├── commands.py        # QUndoCommand: RotatePage, DeletePage, AddRedaction, SetFieldValue…
    │   ├── redact.py          # redaction rectangles, rotation matrices
    │   ├── forms.py           # AcroForm fields: read, write, clear
    │   ├── textedit.py        # editing one text line: span, check, rewrite
    │   ├── ocr.py             # recognition with Tesseract, invisible layer, languages
    │   ├── sign.py            # PAdES signing with pyHanko and signature re-reading
    │   ├── images.py          # images to PDF: A4, dpi, EXIF, intact JPEGs
    │   ├── save.py            # save_as(), save_compressed(), extract_pages()
    │   ├── assemble.py        # pages from several PDFs, form fields intact
    │   └── optimize.py        # compression levels, optimize_in_place()
    ├── rendering/
    │   └── worker.py          # RenderWorker in QThread
    └── widgets/
        ├── page_view.py       # QScrollArea: rendering, fit-width, HiDPI, redaction, fields
        ├── thumbnail_bar.py   # QListView + model + cache, lazy loading
        ├── form_panel.py      # "Form" dock: one editor per field
        ├── ocr.py             # language/page dialog and recognition task
        ├── sign.py            # signing and verification dialogs
        └── compress.py        # options dialog, format_size, task
```

### Key concept

The model never modifies the PDF: it is only a list of **virtual pages**.
Each virtual page is a pair `(source_id, source_index)` plus the rotation
chosen by the user. Everything derives from this list:

- **undo/redo**: manipulates a Python list, not the file
- **merging**: adding a PDF only appends pages pointing at a second
  `source_id`; no page is copied
- **rendering**: the worker opens the source documents read-only, on demand,
  and renders without coordinating with the model
- **saving**: materialises the list by copying each source once and then
  placing the pages in order in the output file — copying twice from the
  same source would rename or lose form fields

A page's identity is always the pair `(source_id, source_index)`, never
`source_index` alone: after a merge two pages regularly share the same index
in different documents, and using only one would collapse them into a single
page (wrong thumbnail, pixmap reused from the cache by mistake).

The views **observe the model**: `PageView` and `ThumbnailBar` connect to the
`changed` / `page_changed` signals, so an undo is reflected on both
automatically, with no need for the window to remember to refresh them.

### Rotation: two values, not one

`base_rotation` is the PDF's original `/Rotate`, `rotation` is the offset
chosen by the user. Rendering composes the two, saving writes the sum
(`total_rotation`). Cache keys include the rotation, otherwise a rotated
page would reuse the previous thumbnail.

### Saving over the open file

Saving over the same file you are reading is allowed: the new document is
written to a temporary file in the same directory and replaces the original
only at the end. A write error therefore never destroys the user's file.

After a merge there is more than one source, so the check covers **all**
sources: saving over any of the open PDFs goes through the temporary file,
because PyMuPDF cannot write into a document it is reading.

After saving over the open file, Plico **reopens** the saved file: that is
the document now, with deletions, rotations and redactions already inside.
That is why the changes made up to that point can no longer be undone.
Extracting pages over an open file, instead, is not allowed.

### Compression: where the gain really comes from

"Save compressed" (`Ctrl+Shift+C`) writes a smaller copy of the virtual
document — so it respects deletions, reordering and rotations — and leaves
the original PDFs untouched.

| Level | What it does | Lossless? |
| --- | --- | --- |
| **Light** | merges fragmented content streams, compacts the structure | yes |
| **Medium** | as above, plus images above 200 dpi brought down to 150 (quality 80) | no |
| **Strong** | images above 150 dpi brought down to 96 (quality 60) | no |

The biggest gain does not come from images but from mutool's `clean`: a PDF
that has been through copies and edits carries hundreds of tiny content
streams, and merging them is worth, on a text document, 188 KB → 12 KB
(6%). On a scan the structure has nothing to give, and only the work on
images counts (a 3.4 MB JPEG over 3 pages stays at 100% with "light",
drops to 52% with "medium" and to 36% with "strong").

The level says _how much_, not _what_: two extra choices sit under the
dropdown. **"Images only"** skips file repacking — useful on a scan, where
the gain is in the images, while on a text-only document it gains nothing and
the program says so instead of writing an identical copy. **"Pages to
resample"** leaves the images of the other pages intact, useful when heavy
scans sit among text pages. There is one case where nothing is gained: if
two pages share the same image, compressing only one would force the other
to get its own copy, and the file would grow — then nothing is written and
the message explains why.

The gain is not an estimate: the compressed file is really written (next to
the destination) and only afterwards does the program say how much it
weighs, adopting it only if it gained.

Compression runs in a separate thread, so the window stays responsive even
on large files.

### Redaction: the text really goes away

`Ctrl+Shift+X` (_Edit → Redact zone_) activates the tool: drag a rectangle
over the data to remove, a plain click on a zone cancels it, `Esc` exits.
An already drawn zone is **corrected without redrawing it**: the corners
resize it, the centre moves it. Zones stay **editable until you save** —
they are undo commands like the others (`Ctrl+Z`).

The result **shows right away**, without saving and reopening. With the tool
on, zones are dark rectangles with handles, so you can correct them; as soon
as you turn it off (`Esc`) the page and its thumbnail show the **real
preview**: the redactions applied to an in-memory copy of the page, by the
same code as the save, so you also see what goes away with the words (a
border, part of an image). Every mark is confirmed by a notice over the page,
and the window title counts the redactions still to apply. Before writing the
file — save, sign, compressed copy, page extraction — Plico asks for
confirmation with the number of zones and the pages, because from there the
content cannot be recovered.

At save time PyMuPDF rewrites the content streams and **removes** the words
that fall inside the zone: neither the text nor the image under the
rectangle remains in the file. A black rectangle drawn on top — what many
tools do — would leave the secret copyable and searchable. The **notes**
and **form fields** touched by the zone go too: a field filled with a name
would otherwise stay in the file, value included.

`Ctrl+Shift+F` (_Edit → Redact word…_) instead searches for a word on **all**
pages and marks every occurrence in one go, as a single undo step. It also
searches text recognised by OCR, even before saving. It turns no tool on: the
pages show the preview of the removed occurrences at once.

`Ctrl+Shift+L` (_Edit → Redact selection_) is the third route, the one
expected by anyone who has used an editor: drag over the words to remove and
they are marked **in full**, one by one, with a mark as tight as the word.
The drag is a single gesture, so one `Ctrl+Z` undoes the whole selection;
dragging where there is no text leaves nothing; a click on a mark removes
it, as with a zone, and a mark can be moved and resized too. It also works
on words read by OCR.

Four things to know:

- words are taken **whole** (a mark in the middle of a word would hide
  nothing), and the minimum unit is the word, not the letter;
- a word mark — from _Redact word_ or _Redact selection_ — removes the text
  of **its line only**: with single line spacing the letters of the lines
  above and below touch its box, and stay where they are. A **drawn** zone,
  instead, removes everything it touches, because that is what was drawn,
  and the same holds for a word mark that has been moved or resized;
- `apply_redactions()` also removes vector graphics touching the rectangle,
  so a border or a table straddling the mark can disappear;
- a click on a mark removes it even if the mouse moved one pixel: it is a
  click, not a drag, and `Ctrl+Z` puts it back exactly where it was.

PDF metadata, instead, is not a risk: the output file is rebuilt from the
pages alone, so `/Info`, XMP and attachments never make it through.

### Text editing: one line at a time

`Ctrl+Shift+T` (_Edit → Edit text_) activates the tool: a click on a line
**already present** in the PDF opens a small editor over it, **Enter**
confirms, **Esc** cancels. A click where there is no text, or on a page
that is only an image (a scan), says so next to the pointer. The tool
corrects text that is there: it does not add new text in an empty spot. The
correction shows immediately on the page and is a command like the others
(`Ctrl+Z`); it enters the file only at save time, where the old text is
**removed** from the content stream — not covered — and the new one written
in the same spot. Background, table borders and text beside it stay, as do
the lines above and below: the old text is removed from a band around the
line, not from its box, which with single line spacing would also touch the
neighbours.

It is a _minimal_ edit, and says so: text that does not fit in the free
space (up to the cell border, the next word or the page margin, even on a
rotated page) is shrunk down to 80% and rejected beyond that, with the
reason in the status bar. Vertical text and Type3 fonts are not edited. The
font is the document's when it can be reused, otherwise the same one
installed on the system, otherwise a look-alike (serif, sans or monospace)
with the same style.

### Forms: filling the PDF, not just reading it

You fill in **on the page**: a click on a text field opens the editor where
the field is, a checkbox is ticked where you clicked it, a radio button
chooses the answer it represents. The **Form** dock (on the right) lists the
fields of the page in view and stays the route for those that cannot be
typed on the page — dropdowns, multi-line text, read-only fields. Values
stay **editable until you save** and go through the same undo/redo as the
rest (`Ctrl+Z`).

An AcroForm field is not PDF content but an annotation with a value, and
Plico treats it as such: field **descriptions** come from the source, the
**values** you write live in the model, and `save.py` applies them while
materialising the pages — before redactions, so a redaction over a field
carries it away. The value drawn on the page is the model's, that is, the
one that _will be_ in the file.

A field is written **only if you touch it**: one never opened keeps the
value it had in the source, which is not the same as emptying it. A group
of radio buttons is **one question** — the dock shows it as a dropdown of
answers — and you can also choose by clicking one on the page. Signatures
belong to _File → Sign…_.

### OCR: making a scan searchable

_Edit → Recognise text…_ (`Ctrl+Shift+O`) reads the chosen pages with
Tesseract and writes an **invisible text layer** under the image (render
mode 3). The page looks identical, but the text can be selected, copied,
searched with `Ctrl+F` — and _Redact word_ (`Ctrl+Shift+F`) finally finds
it, which on an unmarked scan is impossible. It finds it right away, not
only after saving: the layer enters the file at save time, but search also
looks at the words just recognised.

Recognition costs (about half a second per A4 page at 300 dpi), so it is
not automatic: you say which pages (current, current and following, or the
whole document) and in which language, with Italian and English together as
the proposal. It runs in the thread pool with a cancellable progress bar —
while it runs the window accepts no page edits on the pages it is reading —
and each run is **a single** undo step: one `Ctrl+Z` removes the layer from
all pages at once. At the end a notice over the page says on how many pages it
read text (or that it found none), besides the status bar.

The layer's font is one of the Base-14 and is not embedded, so making a
scan searchable adds not a byte. Words already in the PDF are not rewritten:
a page half text and half scan does not end up with doubled text.

Language data (`*.traineddata`) goes in `~/.local/share/plico/tessdata/`,
no root needed; the Flatpak already ships Italian, English, Spanish, French
and German, and proposes the interface language together with English. The
Tesseract library must be present: in the Flatpak it is compiled in (see
Flatpak), on a distribution it is the `tesseract` / `libtesseract` package.

### Signing: a signed PDF, not a stamp

_File → Sign…_ (`Ctrl+Shift+D`) signs the document with a PKCS#12
certificate (`.p12` / `.pfx`) and produces a **PAdES** signature — the PDF
signature profile European readers recognise. You choose whether the
signature stays invisible or appears in a box at the bottom right with name,
date and reason: the box is page content, so it cannot be removed without
breaking the signature.

Four things this implementation does and one it does not:

- **The signature is the last byte of the file.** First the document is
  materialised (with all fields filled, text rewritten, redactions applied,
  pages rotated), then it is signed. The reverse order would produce a
  signature covering a different version of the document from the one the
  user sees.
- **Signing adopts the signed file.** After _Sign…_ the session points at
  the new file, because continuing to work on the page list that generated
  it would lose the signature at the next save.
- **A second signature is appended to the first.** If the signed document
  has no unsaved changes, the new signature is appended to the file as it
  stands (an incremental update) and the first stays valid. With unsaved
  changes the file has to be rewritten and the previous signature would no
  longer cover anything, so it is removed and only the new one remains: the
  program says so beforehand and asks whether to continue.
- **Saving over a signed file asks first.** A normal save rewrites the PDF
  from scratch: the signature is gone, and the saved file does not carry a
  broken one in its place. The program says so and waits for a "yes",
  instead of just doing it.
- **It does not decide who to trust.** Plico ships no authority store: a
  valid, intact signature from an unknown certificate is shown as "intact,
  but the certificate is not among those you consider trusted". You add the
  certificates you trust one by one (`.pem` files) and they stay in
  `QSettings`.

_File → Verify signatures…_ re-reads the signatures from the **file on
disk** and distinguishes the cases that matter: intact and trusted; intact
but from an unknown certificate (amber, not red: it is still a real
signature); intact but on a document **modified after signing** — valid only
for the signed version; **broken** signature, i.e. the content it covered
changed (red, always, even if the file has later revisions); invalid
signature or expired certificate. A module that was never signed is not
mistaken for a signed document.

### Desktop integration (KDE)

- **Icons from the theme** (`QIcon.fromTheme`: `document-open`,
  `document-save-as`, `edit-undo`, `object-rotate-right`, `zoom-in`, …): no
  graphic assets in the package. If the theme does not provide the icon, the
  action simply has no icon instead of showing an empty square.
- **Five languages**: Italian, English, Spanish, French and German, including
  in Qt's standard dialog buttons and in the store metadata (see
  "Translating Plico").
- **Session state in `QSettings`** (`~/.config/Plico/plico.conf`): window
  geometry, dock and toolbar layout, and zoom factor.

## Requirements

- Python ≥ 3.11
- PySide6 ≥ 6.7
- PyMuPDF (pymupdf) ≥ 1.24.3
- pikepdf ≥ 9 (targeted compression)
- pyHanko ≥ 0.37 (PAdES signing; brings cryptography and validation)
- Tesseract (library, 4 or 5) and at least one language data file for OCR —
  the Flatpak ships both

## Installation

```
pip install -e ".[dev]"
```

The entry point accepts the files to open, as a desktop app is expected to:

```
plico relazione.pdf              # opens
plico a.pdf b.pdf                # opens a.pdf and merges b.pdf into it
plico ricevuta.jpg a.pdf         # builds a document from the photo and merges a.pdf
```

It also accepts `file:///…` URLs, which some launchers pass. The `.desktop`
file still expects paths (`Exec=plico %F`).

## Flatpak

Packaging lives in `flatpak/` and is meant to be publishable on Flathub.

| File | Role |
| --- | --- |
| `io.github.gradia64.plico.json` | application manifest |
| `python3-pymupdf.json` | module for PyMuPDF, with wheel and pinned `sha256` |
| `python3-pikepdf.json` | module for pikepdf, with wheel and pinned `sha256` |
| `python3-pyhanko.json` | module for pyHanko and its dependencies, always from wheels |
| `io.github.gradia64.plico.desktop` | launcher (registers `application/pdf`, receives paths with `%F`) |
| `io.github.gradia64.plico.metainfo.xml` | AppStream metadata |
| `io.github.gradia64.plico.svg` | icon |

Seven non-obvious choices:

- **`base: io.qt.PySide.BaseApp`** instead of installing PySide6 with pip.
  Flathub's BaseApp already contains PySide6 built and aligned with the Qt of
  `org.kde.Platform`, so the bundle does not duplicate Qt nor risk
  overwriting the runtime's version. That is why the application is
  installed with `--no-deps`: PySide6 comes from the runtime, PyMuPDF from
  its module, and pip must not even try to download PySide6 from PyPI.
- **PyMuPDF from a `manylinux` wheel** (`cp310-abi3`, valid for every
  Python ≥ 3.10, hence also for the runtime's 3.13) and not from source:
  building MuPDF inside the manifest would require `swig` and several
  minutes of build.
- **pikepdf from a `cp313` wheel** (the BaseApp's interpreter, which is not
  the venv's) **installed with `--no-deps`**: pikepdf declares `Pillow`,
  `lxml` and `packaging`, but `open()` and `save()` do not import them, and
  `packaging` is already in the BaseApp. If the image APIs or PDF/A support
  were needed, their wheels would have to be added too.
- **pyHanko from wheels, in a single module** (`python3-pyhanko.json`):
  pyHanko pulls in `cryptography`, `asn1crypto`, `aiohttp`, `lxml` and a
  dozen other dependencies, all pure Python or with `manylinux` wheels for
  the BaseApp's 3.13, so they install in one go with `--no-index --no-deps`.
  They are the twenty files listed in the module, each with its own `sha256`:
  digital signing is the part of the program where "roughly that version" is
  not an acceptable answer.
- **Translations are compiled during the build**: `lrelease` exists only in
  Qt's SDK, not in the runtime, and the `.qm` files are the only ones needed
  at runtime. The `plico` module installs the `.ts` files with the package
  and then compiles them into `/app/share/plico/translations`, so the
  compiler does not end up in the bundle.
- **`cleanup-commands: /app/cleanup-BaseApp.sh`**, required by the BaseApp.
- **No home access** (no `--filesystem`): every file goes through the
  portal's file chooser (`org.freedesktop.portal.FileChooser`), which Qt uses
  on its own inside Flatpak. Plico sees the document as
  `/run/user/<uid>/doc/<id>/name.pdf` and reads and writes it there, atomic
  save included (the temporary file in the same folder and `os.replace` work
  in the document portal too); to propose a path in the dialogs it uses the
  real one, which the portal exposes in the extended attribute
  `user.document-portal.host-path`. The launcher uses `%F`, so a double
  click already arrives as a path exported in the portal.

Build and install for your own user:

```
# once: builder, SDK and BaseApp
flatpak remote-add --user --if-not-exists flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.flatpak.Builder//stable \
    org.kde.Sdk//6.11 io.qt.PySide.BaseApp//6.11

# build + install. The cache lives OUTSIDE the project: build-dir/ and
# .flatpak-builder/ inside the tree are found by global searches and contain
# copies of the sources.
flatpak run org.flatpak.Builder --force-clean --user --install \
    --install-deps-from=flathub \
    --state-dir="$HOME/.cache/plico-flatpak/state" \
    "$HOME/.cache/plico-flatpak/build" \
    flatpak/io.github.gradia64.plico.json

flatpak run io.github.gradia64.plico
```

The store **screenshots** live in `flatpak/screenshots/` and are produced by
`tools/screenshots.py` from the real app; in the metainfo they point at
`main`, and at release time they are pinned to the tag.

### Releasing

Flathub does not build from the checkout but from a git tag, pinned to its
commit too. The manifest in `flatpak/` stays the development one
(`type: dir`), and the one to submit is generated by
`tools/flathub_manifest.py` **from the tag**. Before writing it checks that:

- the tag is `v` + the version in `pyproject.toml` + the last `<release>` of
  the metainfo;
- the metainfo screenshots point at the tag and not at `main`;
- the tag is annotated, signed by a key in `.github/allowed_signers` and
  present on `origin` with the same object.

Tags are signed with the **SSH** key (no PGP to keep). Once per checkout:

```
git config gpg.format ssh
git config user.signingkey ~/.ssh/id_ed25519.pub
git config tag.gpgSign true
git config gpg.ssh.allowedSignersFile "$PWD/.github/allowed_signers"
```

For GitHub to show the tag as "Verified", the same key must also be registered
as a _signing key_ of the account (Settings → SSH and GPG keys → New SSH key
→ Signing key).

At every release:

```
# 1. version in pyproject.toml, new <release> and screenshot URLs
#    (…/Plico/vX.Y.Z/flatpak/screenshots/…) in the metainfo; commit and push
# 2. signed, verified, published tag
git tag -s v0.1.0 -m "Plico 0.1.0"
git tag -v v0.1.0
git push origin v0.1.0
# 3. the manifest for Flathub, with the modules it includes
python tools/flathub_manifest.py v0.1.0 ~/flathub/io.github.gradia64.plico
```

`--allow-unsigned --offline` does a dry run on a local unsigned tag.

## Development

```
# tests (no display, thanks to QT_QPA_PLATFORM=offscreen).
# NB: pytest is not in .venv/bin, so run it through python -m
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q

# lint + types
ruff check src/ tests/ tools/
mypy src/plico

# run
plico            # or: python -m plico.app

# store screenshots (flatpak/screenshots), in English or another language
QT_QPA_PLATFORM=offscreen python tools/screenshots.py [it|es|fr|de]
```

**CI** (GitHub Actions, `.github/workflows/`) does the same on every push
and pull request: `ci.yml` runs tests, `ruff` and `mypy` on Python 3.11 and
3.13 and validates metainfo, `.desktop` and manifest; `flatpak.yml`, on
`main` and on demand from the Actions tab, builds the real Flatpak, passes it
to Flathub's linter (`flatpak-builder-lint`) and leaves the `plico.flatpak`
package among the run's artifacts, installable with
`flatpak install --user plico.flatpak`.

### Translating Plico

Plico speaks **Italian**, **English**, **Spanish**, **French** and **German**:
it follows the system language, and a language it does not know gets English.
Strings are in Italian in the code; the other languages' catalogs live in
`src/plico/translations/plico_{en,es,fr,de}.ts` and are edited with Qt
Linguist or a text editor. A new language is one more `plico_xx.ts` file
(CONTESTO.md, "Languages", says what to update together).

`pylupdate6` ships with PyQt6 (`pip install PyQt6` in the venv is enough,
only the tool is needed): without it, `tests/test_i18n.py` skips exactly
the check that warns when a new string is missing from the catalog.

```
# 1. re-extract strings after touching the code (212 messages),
#    into all four catalogs
for l in en es fr de; do
    pylupdate6 -no-obsolete src/plico -ts src/plico/translations/plico_$l.ts
done

# 2. compile: pyside6-lrelease ships with PySide6 (or lrelease from the SDK)
pyside6-lrelease src/plico/translations/plico_de.ts -qm /tmp/plico_de.qm

# 3. try it without installing anything
LANG=de_DE.UTF-8 PLICO_TRANSLATIONS=/tmp plico
```

`tests/test_i18n.py` checks that the catalogs are what the sources produce,
so no new string is left out; `tests/test_translations.py` checks that every
language is complete, keeps the placeholders (`{0}`) and does not give the
same shortcut to two menu entries.

## License

GPL v3 — see [LICENSE](https://github.com/gradia64/Plico/blob/main/LICENSE).

## About

A true native PDF editor for Linux: merge, split, rotate, reorder, save. Qt6 + PySide6 + PyMuPDF.

### Topics

[desktop-application](https://github.com/topics/desktop-application) [flatpak](https://github.com/topics/flatpak) [kde](https://github.com/topics/kde) [linux](https://github.com/topics/linux) [pdf](https://github.com/topics/pdf) [pdf-editor](https://github.com/topics/pdf-editor) [pymupdf](https://github.com/topics/pymupdf) [pyside6](https://github.com/topics/pyside6) [python](https://github.com/topics/python) [qt6](https://github.com/topics/qt6)

### Resources

[Readme](https://github.com/gradia64/Plico#readme-ov-file)

[GPL-3.0 license](https://github.com/gradia64/Plico#GPL-3.0-1-ov-file)

[Activity](https://github.com/gradia64/Plico/activity)