"""The «Segnalibri» panel: reading, editing and saving the outline."""

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication, QInputDialog

from plico.main_window import MainWindow
from plico.model import AppendDocument, Bookmark, DeletePage, DocumentModel, SetOutline, save_as
from plico.model import outline as ops


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    mw = MainWindow()
    yield mw
    mw.shutdown_worker()
    mw.deleteLater()
    qapp.processEvents()


def _book(path: str, toc=None, pages: int = 4) -> None:
    with pymupdf.open() as doc:
        for i in range(pages):
            doc.new_page().insert_text((72, 72), f"pagina {i + 1}")
        doc.set_toc(toc if toc is not None else [[1, "Uno", 1], [2, "Uno.a", 2], [1, "Due", 3]])
        doc.save(path)


def _toc(path: str) -> list[list]:
    with pymupdf.open(path) as doc:
        return doc.get_toc(simple=True)


def _b(level: int, title: str, page: int = 0) -> Bookmark:
    return Bookmark(level, title, 0, page)


def _shape(outline: list[Bookmark]) -> list[tuple[int, str]]:
    return [(b.level, b.title) for b in outline]


# -- pure edits ---------------------------------------------------------------

TREE = [_b(1, "A", 0), _b(2, "A1", 1), _b(3, "A1x", 1), _b(2, "A2", 2), _b(1, "B", 3)]


def test_remove_takes_the_subtree() -> None:
    assert _shape(ops.remove(TREE, 1)) == [(1, "A"), (2, "A2"), (1, "B")]
    assert len(TREE) == 5  # the list given is left alone


def test_moves_swap_whole_siblings() -> None:
    assert _shape(ops.move_down(TREE, 1)) == [(1, "A"), (2, "A2"), (2, "A1"), (3, "A1x"), (1, "B")]
    assert _shape(ops.move_up(TREE, 4)) == [(1, "B"), (1, "A"), (2, "A1"), (3, "A1x"), (2, "A2")]
    assert ops.move_up(TREE, 0) is None
    assert ops.move_up(TREE, 1) is None  # first child: no sibling before it
    assert ops.move_down(TREE, 3) is None  # last child
    assert ops.move_down(TREE, 4) is None


def test_levels_move_with_the_subtree() -> None:
    assert _shape(ops.indent(TREE, 3)) == [(1, "A"), (2, "A1"), (3, "A1x"), (3, "A2"), (1, "B")]
    assert _shape(ops.indent(TREE, 4)) == [(1, "A"), (2, "A1"), (3, "A1x"), (2, "A2"), (2, "B")]
    assert ops.indent(TREE, 0) is None and ops.indent(TREE, 1) is None
    assert _shape(ops.outdent(TREE, 1)) == [(1, "A"), (1, "A1"), (2, "A1x"), (2, "A2"), (1, "B")]
    assert ops.outdent(TREE, 0) is None


def test_a_new_bookmark_goes_in_page_order() -> None:
    positions = [0, 1, 1, 2, 3]
    assert ops.insertion_point(TREE, positions, 0) == 4  # after A's subtree
    assert ops.insertion_point(TREE, positions, 3) == 5
    assert ops.insertion_point(TREE, [5, 5, 5, 5, 6], 0) == 0
    new = ops.add(TREE, 4, _b(3, "Nuovo", 2))
    assert _shape(new)[4] == (1, "Nuovo")
    assert _shape(ops.rename(TREE, 0, "Alfa"))[0] == (1, "Alfa")


# -- model ----------------------------------------------------------------------


def test_the_outline_is_read_merged_and_undone(qapp, tmp_path) -> None:
    first = str(tmp_path / "a.pdf")
    second = str(tmp_path / "b.pdf")
    _book(first)
    _book(second, [[1, "Allegato", 2]], pages=2)
    model = DocumentModel()
    model.open(first)
    assert _shape(model.outline) == [(1, "Uno"), (2, "Uno.a"), (1, "Due")]
    items = model.read_source(len(model.sources), second)
    command = AppendDocument(model, len(model.sources), second, items)
    command.redo()
    assert model.outline[-1] == Bookmark(1, "Allegato", 1, 1)
    command.undo()
    assert len(model.outline) == 3
    rename = SetOutline(model, ops.rename(model.outline, 0, "Primo"), "rinomina")
    rename.redo()
    assert model.outline[0].title == "Primo"
    rename.undo()
    assert model.outline[0].title == "Uno"
    model.close()
    assert model.outline == []


def test_an_edited_outline_is_saved(qapp, tmp_path) -> None:
    path = str(tmp_path / "a.pdf")
    out = str(tmp_path / "salvato.pdf")
    _book(path)
    model = DocumentModel()
    model.open(path)
    edited = ops.add(ops.remove(model.outline, 0), 1, Bookmark(1, "Ultima", 0, 3))
    SetOutline(model, edited, "modifica").redo()
    save_as(model, out)
    assert _toc(out) == [[1, "Due", 3], [1, "Ultima", 4]]


# -- panel ----------------------------------------------------------------------


def _titles(window) -> list[str]:
    return [b.title for b in window._doc_model.outline]


def test_the_panel_edits_through_the_undo_stack(window, qapp, tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "a.pdf")
    _book(path)
    assert window.open_path(path)
    panel = window._bookmark_panel
    assert panel._tree.topLevelItemCount() == 2
    assert panel._tree.topLevelItem(0).child(0).text(0) == "Uno.a"

    window._thumb_bar.set_current_row(3)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("  Appendice ", True))
    panel.add()
    assert _titles(window) == ["Uno", "Uno.a", "Due", "Appendice"]
    assert panel.current_index() == 3
    assert window.is_modified()

    panel.select(3)
    panel._buttons["up"].click()
    assert _titles(window) == ["Uno", "Uno.a", "Appendice", "Due"]
    assert panel.current_index() == 2

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Allegato", True))
    panel.rename()
    assert _titles(window)[2] == "Allegato"

    panel.select(0)
    panel.remove()
    assert _titles(window) == ["Allegato", "Due"]
    for _ in range(4):
        window._undo_stack.undo()
    assert _titles(window) == ["Uno", "Uno.a", "Due"]
    assert not window.is_modified()


def test_a_cancelled_or_empty_title_changes_nothing(window, qapp, tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "a.pdf")
    _book(path)
    assert window.open_path(path)
    for answer in (("Titolo", False), ("   ", True)):
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, answer=answer, **k: answer)
        window._bookmark_panel.add()
    assert window._undo_stack.count() == 0


def test_choosing_a_bookmark_shows_its_page(window, qapp, tmp_path) -> None:
    path = str(tmp_path / "a.pdf")
    _book(path)
    assert window.open_path(path)
    panel = window._bookmark_panel
    item = panel._tree.topLevelItem(1)  # «Due», page 3
    panel._chosen(item)
    assert window._thumb_bar.current_row() == 2
    # A bookmark whose page was deleted stays, greyed, and goes nowhere.
    window._undo_stack.push(DeletePage(window._doc_model, 2))
    item = panel._tree.topLevelItem(1)
    assert "eliminata" in item.toolTip(0)
    window._thumb_bar.set_current_row(0)
    panel._chosen(item)
    assert window._thumb_bar.current_row() == 0
