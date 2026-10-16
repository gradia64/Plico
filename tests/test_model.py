"""Model, commands and save layer: pure logic, testable without a UI.

The tests marked BUG document the defects found in review: they fail with
the current code and turn green once the corresponding fix is applied.
"""

import pymupdf
import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QUndoStack

from plico.model.commands import AppendDocument, DeletePage, MovePage, RotatePage
from plico.model.document import DocumentModel, PageItem, PasswordRequired
from plico.model.save import _contiguous_runs, extract_pages, parse_page_ranges, save_as

# --- fixtures -------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture
def mixed_pdf(tmp_path):
    """A 3-page PDF with different formats: bugs like #1 are invisible on uniform A4."""
    path = tmp_path / "mixed.pdf"
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)   # A4 portrait
    doc.new_page(width=842, height=595)   # A4 landscape
    doc.new_page(width=420, height=595)   # ~A5
    doc.save(str(path))
    return str(path)


@pytest.fixture
def mixed_model(mixed_pdf, qapp):
    m = DocumentModel()
    m.open(mixed_pdf)
    return m


# --- parse_page_ranges ----------------------------------------------------

def test_parse_ranges_basic():
    assert parse_page_ranges("1-3,5", 10) == [0, 1, 2, 4]

def test_parse_ranges_preserves_order():
    assert parse_page_ranges("5,1-3", 10) == [4, 0, 1, 2]

def test_parse_ranges_reversed_raises():
    with pytest.raises(ValueError):
        parse_page_ranges("5-2", 10)

def test_parse_ranges_out_of_bounds_raises():
    # BUG 4: today the range is materialized BEFORE validation,
    # so "1-5000000" builds half a million indices before
    # refusing. The contract is already correct (ValueError); the fix makes it O(1).
    with pytest.raises(ValueError):
        parse_page_ranges("1-5000000", 3)


@pytest.mark.parametrize("spec", ["", "   ", "1-", "-3", "1-a", "a", "1;2"])
def test_parse_ranges_rejects_malformed(spec):
    """A malformed split must be refused, not interpreted halfway."""
    with pytest.raises(ValueError):
        parse_page_ranges(spec, 10)


def test_parse_ranges_tolerates_a_stray_separator():
    """An extra separator is not an error: '1,,2' means '1,2'.

    Deliberate choice: only an EMPTY selection is an error (no page
    to extract), an empty token loses nothing.
    """
    assert parse_page_ranges("1,,2", 5) == [0, 1]


@pytest.mark.parametrize("spec", ["0", "11", "1-11", "8-12"])
def test_parse_ranges_rejects_out_of_bounds(spec):
    """Better an error than an extraction that silently loses pages."""
    with pytest.raises(ValueError):
        parse_page_ranges(spec, 10)


def test_parse_ranges_whitespace_ok_and_bounds_inclusive():
    assert parse_page_ranges(" 1 , 3-4 ", 4) == [0, 2, 3]
    assert parse_page_ranges("1-1", 1) == [0]


# --- _contiguous_runs -------------------------------------------------------

def test_contiguous_runs_break_on_source_and_gap():
    items = [
        PageItem(source_index=0, base_rotation=0, source_id=0),
        PageItem(source_index=1, base_rotation=0, source_id=0),
        PageItem(source_index=5, base_rotation=0, source_id=1),  # source change
        PageItem(source_index=6, base_rotation=0, source_id=1),
        PageItem(source_index=2, base_rotation=0, source_id=0),  # return → new run
        PageItem(source_index=9, base_rotation=0, source_id=0),  # gap → new run
    ]
    runs = [[(i.source_id, i.source_index) for i in r] for r in _contiguous_runs(items)]
    assert runs == [
        [(0, 0), (0, 1)],
        [(1, 5), (1, 6)],
        [(0, 2)],
        [(0, 9)],
    ]


# --- commands and model consistency -----------------------------------------

def test_delete_keeps_page_sizes_aligned(mixed_model):
    """BUG 1: page_sizes does not follow pages in structural commands.

    Fails with the current code (page_sizes stays at 3 after the delete).
    With fix 1 it turns green and then obsolete: the size will migrate
    onto the item and page_sizes will disappear altogether.
    """
    DeletePage(mixed_model, 0).redo()
    assert len(mixed_model.page_sizes) == len(mixed_model.pages)

def test_delete_preserves_sizes_on_items(mixed_model):
    """Post-fix 1 contract: the size lives on the item, not in a parallel list."""
    DeletePage(mixed_model, 0).redo()
    assert (round(mixed_model.pages[0].width_pt),
            round(mixed_model.pages[0].height_pt)) == (842, 595)

def test_undo_stack_interleaved_roundtrip(mixed_model):
    """Move → Delete → undo → undo: the list comes back identical.

    Checks the assumption everything rests on (LIFO stack = coherent indices)
    without touching page_sizes: the comparison is by page identity.
    """
    stack = QUndoStack()
    stack.push(MovePage(mixed_model, 0, 2))
    stack.push(DeletePage(mixed_model, 0))
    stack.undo()
    stack.undo()
    assert [(p.source_id, p.source_index) for p in mixed_model.pages] == [(0, 0), (0, 1), (0, 2)]

def test_rotate_undo_emits_page_changed(mixed_model):
    """Prerequisite of fix 2: the thumbnail updates on Ctrl+Z only if
    the command emits page_changed ALSO in undo(). Today this is already true
    for the command — it is the ThumbnailBar that does not listen."""
    rows = []
    mixed_model.page_changed.connect(rows.append)
    cmd = RotatePage(mixed_model, 0, 90)
    cmd.redo()
    cmd.undo()
    assert rows == [0, 0]


def test_delete_redo_after_undo_really_deletes(mixed_model):
    """Redo after undo must really delete.

    Regression: the ``else`` branch of DeletePage.redo did insert+pop on the
    same index, i.e. a no-op -- after undo+redo the page stayed in the
    list, so redoing a cancelled deletion deleted nothing.
    """
    stack = QUndoStack()
    stack.push(DeletePage(mixed_model, 0))
    assert mixed_model.page_count == 2
    stack.undo()
    assert mixed_model.page_count == 3
    stack.redo()
    assert mixed_model.page_count == 2
    assert [p.source_index for p in mixed_model.pages] == [1, 2]


def test_sizes_follow_the_pages_through_move_and_delete(mixed_model):
    """The size lives on the item, so it follows the page (BUG 1).

    With the old parallel list, after the delete position 0 read the
    size of the page originally in position 1: on a mix of
    portrait/landscape the layout was measured with the wrong page.
    """
    def sizes(model):
        return [(round(p.width_pt), round(p.height_pt)) for p in model.pages]

    assert sizes(mixed_model) == [(595, 842), (842, 595), (420, 595)]
    DeletePage(mixed_model, 0).redo()
    assert sizes(mixed_model) == [(842, 595), (420, 595)]
    MovePage(mixed_model, 0, 1).redo()
    assert sizes(mixed_model) == [(420, 595), (842, 595)]


# --- saving -----------------------------------------------------------------

def test_save_writes_total_rotation(mixed_model, tmp_path):
    """Rotation round-trip: rotate 90 on a landscape one → the saved
    file has /Rotate 90 and rect already oriented (MuPDF folds /Rotate
    into rect — the same property the viewer depends on)."""
    RotatePage(mixed_model, 1, 90).redo()
    out = tmp_path / "out.pdf"
    save_as(mixed_model, str(out))
    with pymupdf.open(str(out)) as doc:
        assert doc.page_count == 3
        assert doc[1].rotation == 90
        assert (round(doc[1].rect.width), round(doc[1].rect.height)) == (595, 842)

def test_extract_preserves_user_order(mixed_model, tmp_path):
    out = tmp_path / "sel.pdf"
    extract_pages(mixed_model, str(out), [2, 0])   # A5 first, then A4 portrait
    with pymupdf.open(str(out)) as doc:
        assert doc.page_count == 2
        assert round(doc[0].rect.width) == 420
        assert round(doc[1].rect.width) == 595


# --- writing over an open source -----------------------------------------

def test_sources_at_matches_by_inode_not_by_spelling(mixed_model, mixed_pdf, tmp_path):
    """Another way of spelling the same path is the same file."""
    import os

    same = os.path.join(os.path.dirname(mixed_pdf), ".", os.path.basename(mixed_pdf))
    hardlink = str(tmp_path / "hardlink.pdf")
    os.link(mixed_pdf, hardlink)

    assert mixed_model.sources_at(same) == [mixed_pdf]
    assert mixed_model.sources_at(hardlink) == [mixed_pdf]
    assert mixed_model.sources_at(str(tmp_path / "altro.pdf")) == []


def test_extract_over_an_open_source_is_refused(mixed_model, mixed_pdf):
    """A subset written over the source would orphan the other pages.

    The pages not extracted would point to pages that no longer exist
    in the file, and the next save would lose them without saying anything.
    """
    with pytest.raises(ValueError):
        extract_pages(mixed_model, mixed_pdf, [0])
    with pymupdf.open(mixed_pdf) as doc:
        assert doc.page_count == 3, "il sorgente non deve essere toccato"


def test_saved_file_reopened_is_the_document(qapp, tmp_path):
    """The file saved over the source IS the document: reopened, it rebuilds the same file.

    This is the contract MainWindow relies on after an overwrite:
    deletions, rotations and the starting /Rotate are already in the file, so
    the new PageItems have nothing to add.
    """
    source = str(tmp_path / "doc.pdf")
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"PAGINA {i + 1}")
    doc[2].set_rotation(90)
    doc.save(source)
    doc.close()

    model = DocumentModel()
    model.open(source)
    DeletePage(model, 0).redo()
    RotatePage(model, 0, 90).redo()
    save_as(model, source)

    model.open(source)
    assert [(p.source_index, p.base_rotation, p.rotation) for p in model.pages] == [
        (0, 90, 0),
        (1, 90, 0),
    ]
    out = str(tmp_path / "di-nuovo.pdf")
    save_as(model, out)
    with pymupdf.open(out) as d:
        assert [(p.get_text().strip(), p.rotation) for p in d] == [
            ("PAGINA 2", 90),
            ("PAGINA 3", 90),
        ]


# --- "save as" over an existing file ---------------------------------------

def test_a_failed_save_does_not_destroy_the_destination(
    mixed_model, mixed_pdf, tmp_path, monkeypatch
):
    """Over a file never opened, the save still goes through the temporary file.

    The destination is not a source, so the save wrote
    directly over the file: interrupting halfway left it truncated.
    Here the write blows up *after* touching the file, as a full
    disk would.
    """
    from plico.model import save

    destination = str(tmp_path / "importante.pdf")
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "INTATTO")
        doc.save(destination)

    def esplode(model, out_path, pages=None):
        with open(out_path, "wb") as fh:  # the interrupted write
            fh.write(b"%PDF-1.7 troncato")
        raise RuntimeError("disco pieno")

    monkeypatch.setattr(save, "_write_pdf", esplode)

    with pytest.raises(RuntimeError):
        save_as(mixed_model, destination)

    with pymupdf.open(destination) as doc:
        assert doc[0].get_text().strip() == "INTATTO"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "importante.pdf",
        "mixed.pdf",
    ], "nessun temporaneo lasciato in giro"


def test_the_destination_file_keeps_its_permissions(mixed_model, tmp_path):
    """Over an existing file the temporary file carries its permissions.

    PyMuPDF recreates the file when it writes over it, so the original
    mode was lost: it is the temporary swap that has to put it back.
    """
    import os

    destination = str(tmp_path / "protetto.pdf")
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "PRIMA")
        doc.save(destination)
    os.chmod(destination, 0o640)

    save_as(mixed_model, destination)

    assert os.stat(destination).st_mode & 0o777 == 0o640


# --- encrypted sources -----------------------------------------------------

SEGRETA = "segreta"


def _encrypted_pdf(
    path, password: str = SEGRETA, user_password: str | None = None
) -> str:
    """One page with a readable word, locked with *password*."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "PAGINA SEGRETA", fontsize=20)
    doc.save(
        str(path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="proprietario",
        user_pw=password if user_password is None else user_password,
    )
    doc.close()
    return str(path)


def test_an_encrypted_file_asks_for_a_password(qapp, tmp_path):
    """``open`` refuses without a password and leaves the model untouched."""
    path = _encrypted_pdf(tmp_path / "cifrato.pdf")

    model = DocumentModel()
    with pytest.raises(PasswordRequired) as raised:
        model.open(path)

    assert raised.value.path == path
    assert raised.value.wrong is False
    assert model.pages == []
    assert model.sources == []


def test_a_wrong_password_is_reported_as_wrong(qapp, tmp_path):
    path = _encrypted_pdf(tmp_path / "cifrato.pdf")

    model = DocumentModel()
    with pytest.raises(PasswordRequired) as raised:
        model.open(path, "sbagliata")

    assert raised.value.wrong is True
    assert model.pages == []


def test_the_password_opens_the_file_and_is_kept(qapp, tmp_path):
    """It is kept because the worker and the save have to open the file again."""
    path = _encrypted_pdf(tmp_path / "cifrato.pdf")

    model = DocumentModel()
    model.open(path, SEGRETA)

    assert model.page_count == 1
    assert model.passwords == {path: SEGRETA}


def test_an_owner_only_password_is_not_asked_for(qapp, tmp_path):
    """An empty user password is the common case: it must open unasked."""
    path = _encrypted_pdf(tmp_path / "solo-proprietario.pdf", user_password="")

    model = DocumentModel()
    model.open(path)

    assert model.page_count == 1
    assert model.passwords == {}


def test_saving_an_encrypted_source_needs_it_again(qapp, tmp_path):
    """The save opens the sources on its own: without the password, no pages."""
    path = _encrypted_pdf(tmp_path / "cifrato.pdf")
    out = tmp_path / "out.pdf"

    model = DocumentModel()
    model.open(path, SEGRETA)
    save_as(model, str(out))

    with pymupdf.open(out) as saved:
        assert "PAGINA SEGRETA" in saved[0].get_text()


def test_the_saved_copy_of_an_encrypted_file_is_plain(qapp, tmp_path):
    """The output is rebuilt from pages, so it carries no encryption."""
    path = _encrypted_pdf(tmp_path / "cifrato.pdf")
    out = tmp_path / "out.pdf"

    model = DocumentModel()
    model.open(path, SEGRETA)
    save_as(model, str(out))

    with pymupdf.open(out) as saved:
        assert saved.needs_pass == 0


def test_merging_an_encrypted_file_asks_too(mixed_model, qapp, tmp_path):
    path = _encrypted_pdf(tmp_path / "cifrato.pdf")

    with pytest.raises(PasswordRequired):
        mixed_model.append_document(path)

    assert mixed_model.page_count == 3, "il rifiuto non deve toccare il modello"
    assert mixed_model.append_document(path, SEGRETA) == 1
    assert mixed_model.page_count == 4
    assert mixed_model.passwords == {path: SEGRETA}


# --- merging is undoable ---------------------------------------------------

def _one_page_pdf(path, text: str) -> str:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), text, fontsize=20)
    doc.save(str(path))
    doc.close()
    return str(path)


def _merge(model, path: str) -> QUndoStack:
    """Merge *path* the way the window does: read the pages, then push."""
    items = model.read_source(len(model.sources), path)
    stack = QUndoStack()
    stack.push(AppendDocument(model, len(model.sources), path, items))
    return stack


def test_a_merge_goes_on_the_undo_stack(mixed_model, mixed_pdf, qapp, tmp_path):
    other = _one_page_pdf(tmp_path / "altro.pdf", "AGGIUNTA")

    stack = _merge(mixed_model, other)

    assert mixed_model.page_count == 4
    assert mixed_model.sources == [mixed_pdf, other]
    assert stack.count() == 1
    assert not stack.isClean(), "un'unione non ancora salvata e` una modifica"
    assert stack.undoText() == "Unisci «altro.pdf»"


def test_undoing_a_merge_takes_the_pages_away(mixed_model, mixed_pdf, qapp, tmp_path):
    other = _one_page_pdf(tmp_path / "altro.pdf", "AGGIUNTA")

    stack = _merge(mixed_model, other)
    stack.undo()

    assert mixed_model.page_count == 3
    assert mixed_model.sources == [mixed_pdf]
    assert stack.isClean(), "tornati al documento di partenza"


def test_redoing_a_merge_puts_them_back(mixed_model, mixed_pdf, qapp, tmp_path):
    other = _one_page_pdf(tmp_path / "altro.pdf", "AGGIUNTA")

    stack = _merge(mixed_model, other)
    stack.undo()
    stack.redo()

    assert mixed_model.page_count == 4
    assert mixed_model.sources == [mixed_pdf, other]
    assert [item.source_id for item in mixed_model.pages] == [0, 0, 0, 1]
    assert mixed_model.pages[-1].source_index == 0


def test_two_merges_undo_in_reverse_order(mixed_model, mixed_pdf, qapp, tmp_path):
    first = _one_page_pdf(tmp_path / "primo.pdf", "PRIMO")
    second = _one_page_pdf(tmp_path / "secondo.pdf", "SECONDO")
    stack = QUndoStack()
    for path in (first, second):
        items = mixed_model.read_source(len(mixed_model.sources), path)
        stack.push(AppendDocument(mixed_model, len(mixed_model.sources), path, items))

    assert mixed_model.sources == [mixed_pdf, first, second]
    stack.undo()
    assert mixed_model.sources == [mixed_pdf, first]
    stack.undo()
    assert mixed_model.sources == [mixed_pdf]
    assert mixed_model.page_count == 3

    stack.redo()
    stack.redo()
    assert mixed_model.sources == [mixed_pdf, first, second]
    assert mixed_model.page_count == 5
    assert [item.source_id for item in mixed_model.pages] == [0, 0, 0, 1, 2]
