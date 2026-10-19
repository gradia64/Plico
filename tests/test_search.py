"""Ctrl+F: the search the README promised, and that did not exist.

Reported by a review (2026-10-19): the OCR section said a recognised scan could
be searched with Ctrl+F, and there was no such command. These tests pin the
bar: what it finds, which hit is current, how F3 walks, what Esc does, and
that a changed document is searched again.
"""

import time

import pymupdf
import pytest
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from plico.main_window import MainWindow
from plico.model.commands import DeletePage
from plico.widgets.find_bar import DELAY_MS

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    path = str(tmp_path / "doc.pdf")
    with pymupdf.open() as doc:
        for i in range(3):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 100), f"Contratto numero {i + 1}", fontsize=14)
            page.insert_text((72, 700), "contratto in calce", fontsize=14)
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), "Allegato senza la parola", fontsize=14)
        doc.save(path)
    mw = MainWindow()
    mw.resize(900, 700)
    mw.open_document(path)
    _pump()
    yield mw
    mw.shutdown_worker()
    mw.deleteLater()
    qapp.processEvents()


def _pump(seconds: float = 0.5) -> None:
    app = QApplication.instance()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def _search(mw: MainWindow, text: str) -> None:
    mw._open_search()
    mw._find_bar._field.setText(text)
    _pump(DELAY_MS / 1000 + 0.3)


def test_the_find_action_is_ctrl_f_in_the_edit_menu(window):
    modifica = next(a.menu() for a in window.menuBar().actions() if "Modifica" in a.text())
    assert window._find_act in modifica.actions()
    assert window._find_act.shortcut() == QKeySequence(QKeySequence.StandardKey.Find)


def test_every_occurrence_is_found_in_reading_order(window):
    _search(window, "contratto")

    assert window._find_bar.isVisibleTo(window)
    # Case-insensitive, two per page on the first three pages, none on the fourth.
    assert [index for index, _ in window._find_hits] == [0, 0, 1, 1, 2, 2]
    first, second = (rect for index, rect in window._find_hits if index == 0)
    assert first.y0 < second.y0, "dall'alto in basso"
    assert window._find_bar._count.text() == "1 di 6"
    assert window._page_view.search_current() == (0, 0)
    assert len(window._page_view.search_hits(1)) == 2


def test_f3_walks_forward_and_wraps_round(window):
    _search(window, "contratto")
    for _ in range(3):
        window._step_search(1)
    assert window._find_bar._count.text() == "4 di 6"
    assert window._page_view.search_current() == (1, 1)
    assert window._thumb_bar.current_row() == 1, "la miniatura segue l'occorrenza"

    window._find_position = 5
    window._step_search(1)
    assert window._find_bar._count.text() == "1 di 6", "dopo l'ultima si riparte"
    window._step_search(-1)
    assert window._find_bar._count.text() == "6 di 6"


def test_the_search_starts_from_the_page_on_screen(window):
    window._thumb_bar.set_current_row(2)
    _pump(0.1)
    _search(window, "contratto")
    assert window._page_view.search_current() == (2, 0)
    assert window._find_bar._count.text() == "5 di 6"


def test_nothing_found_is_said_and_highlights_nothing(window):
    _search(window, "inesistente")
    assert window._find_hits == []
    assert window._find_bar._count.text() == "Nessun risultato"
    assert window._page_view.search_hits(0) == []
    window._step_search(1)  # nothing to walk: no error


def test_esc_closes_the_bar_and_takes_the_highlights(window):
    _search(window, "contratto")
    window._find_bar._field.setFocus()
    _pump(0.1)

    window._leave_tools()

    assert not window._find_bar.isVisibleTo(window)
    assert window._page_view.search_hits(0) == []
    assert window._page_view.search_current() is None


def test_esc_with_a_tool_on_leaves_the_tool_and_keeps_the_bar(window):
    _search(window, "contratto")
    window._redact_act.setChecked(True)
    window._on_redaction_toggled(True)
    window._page_view.setFocus()
    _pump(0.1)

    window._leave_tools()

    assert not window._redact_act.isChecked()
    assert window._find_bar.isVisibleTo(window)


def test_a_deleted_page_is_searched_again(window):
    _search(window, "contratto")
    window._undo_stack.push(DeletePage(window._doc_model, 0))
    _pump(DELAY_MS / 1000 + 0.3)

    assert [index for index, _ in window._find_hits] == [0, 0, 1, 1]
    assert window._find_bar._count.text().endswith("di 4")


def test_ctrl_f_without_a_document_says_so(qapp):
    mw = MainWindow()
    try:
        mw._open_search()
        assert not mw._find_bar.isVisibleTo(mw)
        assert mw._status.text() == "Nessun documento aperto."
    finally:
        mw.shutdown_worker()
        mw.deleteLater()
