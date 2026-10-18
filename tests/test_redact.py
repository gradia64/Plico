"""Redaction: the geometry, the commands and the real removal of the text.

The four matrices of ``model/redact.py`` were read from
PyMuPDF's ``Page.rotation_matrix``, and here they are compared again against
PyMuPDF: if a PyMuPDF update changed them, the suite fails instead of
silently moving a rectangle.

The last part is the one that really counts: after saving, the marked text
must no longer *exist* in the file, not merely be covered by a
black rectangle.
"""

import pymupdf
import pytest

from plico.model import LEVELS_BY_KEY, DocumentModel, RedactionRect, save_as, save_compressed
from plico.model.commands import AddRedaction, AdjustRedaction, RemoveRedaction
from plico.model.redact import (
    derotation_matrix,
    map_point,
    map_rect,
    rotation_matrix,
    unrotated_size,
)

SEGRETO = "SEGRETO"
PUBBLICO = "PUBBLICO"


def _pdf_with_text(path: str, rotation: int = 0, pages: int = 1) -> None:
    """Two well-separated words on an A4: one to redact, one to keep."""
    with pymupdf.open() as doc:
        for _ in range(pages):
            page = doc.new_page(width=595, height=842)
            page.insert_text((100, 100), SEGRETO, fontsize=20)
            page.insert_text((100, 700), PUBBLICO, fontsize=20)
        if rotation:
            doc[0].set_rotation(rotation)
        doc.save(path)


def _secret_rect(path: str) -> RedactionRect:
    """The rectangle to redact, read from the source page.

    ``search_for`` returns coordinates in the NON-rotated space: it is the
    same space in which the model stores the redactions, so no
    conversion is needed here.
    """
    with pymupdf.open(path) as doc:
        box = doc[0].search_for(SEGRETO)[0]
    return RedactionRect.from_corners(box.x0, box.y0, box.x1, box.y1)


# --------------------------------------------------------------------- #
#  Geometry
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("degrees", [0, 90, 180, 270])
def test_the_matrices_are_the_pymupdf_ones(tmp_path, degrees: int) -> None:
    """Not «similar»: identical to the ones MuPDF uses for the same page."""
    src = str(tmp_path / "g.pdf")
    with pymupdf.open() as doc:
        doc.new_page(width=595, height=842).set_rotation(degrees)
        doc.save(src)

    with pymupdf.open(src) as doc:
        page = doc[0]
        avanti = page.rotation_matrix
        indietro = page.derotation_matrix

    nostra = rotation_matrix(595, 842, degrees)
    assert (avanti.a, avanti.b, avanti.c, avanti.d, avanti.e, avanti.f) == pytest.approx(nostra)
    nostra_inversa = derotation_matrix(595, 842, degrees)
    assert (indietro.a, indietro.b, indietro.c, indietro.d, indietro.e, indietro.f) == pytest.approx(
        nostra_inversa
    )


@pytest.mark.parametrize("degrees", [0, 90, 180, 270])
def test_round_trip_through_view_space(degrees: int) -> None:
    """What the user draws must come back where it was, without drift."""
    rect = RedactionRect.from_corners(100.0, 78.5, 197.8, 106.0)

    in_view = map_rect(rect, rotation_matrix(595, 842, degrees))
    indietro = map_rect(in_view, derotation_matrix(595, 842, degrees))

    assert indietro.x0 == pytest.approx(rect.x0, abs=1e-9)
    assert indietro.y0 == pytest.approx(rect.y0, abs=1e-9)
    assert indietro.x1 == pytest.approx(rect.x1, abs=1e-9)
    assert indietro.y1 == pytest.approx(rect.y1, abs=1e-9)


@pytest.mark.parametrize(
    "degrees,width,height",
    [(0, 595, 842), (90, 842, 595), (180, 595, 842), (270, 842, 595)],
)
def test_in_view_space_the_rect_stays_inside_the_page(
    degrees: int, width: int, height: int
) -> None:
    rect = RedactionRect.from_corners(100.0, 100.0, 200.0, 130.0)
    in_view = map_rect(rect, rotation_matrix(595, 842, degrees))

    assert in_view.x0 >= -1e-9
    assert in_view.y0 >= -1e-9
    assert in_view.x1 <= width + 1e-9
    assert in_view.y1 <= height + 1e-9


def test_a_point_follows_the_matrix() -> None:
    """The simplest case, to fix the convention (a·x + c·y + e, …)."""
    x, y = map_point(10.0, 20.0, (2.0, 0.0, 0.0, 3.0, 5.0, 7.0))
    assert (x, y) == pytest.approx((25.0, 67.0))


def test_the_unrotated_size_straightens_odd_quarters() -> None:
    """``width_pt`` comes from ``page.rect``, which has already applied /Rotate."""
    assert unrotated_size(595, 842, 0) == (595, 842)
    assert unrotated_size(595, 842, 180) == (595, 842)
    assert unrotated_size(842, 595, 90) == (595, 842)
    assert unrotated_size(842, 595, 270) == (595, 842)


@pytest.mark.parametrize("degrees", [1, 45, 359])
def test_an_unsupported_rotation_is_an_error(degrees: int) -> None:
    """Better a loud error than a redaction in the wrong place."""
    with pytest.raises(ValueError):
        rotation_matrix(595, 842, degrees)
    with pytest.raises(ValueError):
        derotation_matrix(595, 842, degrees)


def test_a_rect_is_built_from_any_corners() -> None:
    """A drag can start from any corner."""
    rect = RedactionRect.from_corners(200.0, 300.0, 100.0, 150.0)
    assert rect.as_tuple() == (100.0, 150.0, 200.0, 300.0)
    assert rect.width == 100.0
    assert rect.height == 150.0


def test_the_rect_is_clamped_to_the_page() -> None:
    rect = RedactionRect.from_corners(-10.0, -20.0, 700.0, 900.0).clamped_to(595, 842)
    assert rect.as_tuple() == (0.0, 0.0, 595.0, 842.0)


def test_a_moved_rect_keeps_its_size() -> None:
    rect = RedactionRect.from_corners(100.0, 150.0, 200.0, 300.0)
    moved = rect.translated(20.0, -30.0)
    assert moved.as_tuple() == (120.0, 120.0, 220.0, 270.0)
    assert moved.width == rect.width
    assert moved.height == rect.height


def test_dragging_a_corner_leaves_the_others_where_they_are() -> None:
    rect = RedactionRect.from_corners(100.0, 150.0, 200.0, 300.0)
    assert rect.with_corner("br", 260.0, 380.0).as_tuple() == (100.0, 150.0, 260.0, 380.0)
    assert rect.with_corner("tl", 40.0, 50.0).as_tuple() == (40.0, 50.0, 200.0, 300.0)
    assert rect.with_corner("tr", 220.0, 40.0).as_tuple() == (100.0, 40.0, 220.0, 300.0)
    assert rect.with_corner("bl", 60.0, 320.0).as_tuple() == (60.0, 150.0, 200.0, 320.0)


def test_a_corner_dragged_past_the_other_side_turns_the_rect_around() -> None:
    """A rectangle with a negative width hides nothing but draws strangely."""
    rect = RedactionRect.from_corners(100.0, 150.0, 200.0, 300.0)
    assert rect.with_corner("br", 40.0, 360.0).as_tuple() == (40.0, 150.0, 100.0, 360.0)


# --------------------------------------------------------------------- #
#  Commands
# --------------------------------------------------------------------- #

def test_adding_a_redaction_is_undoable(tmp_path) -> None:
    src = str(tmp_path / "doc.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)
    seen: list[int] = []
    model.page_changed.connect(seen.append)

    rect = _secret_rect(src)
    command = AddRedaction(model, 0, rect)

    command.redo()
    assert model.pages[0].redactions == [rect]
    assert seen == [0], "la pagina deve ridisegnarsi subito"

    command.undo()
    assert model.pages[0].redactions == []
    assert seen == [0, 0], "anche l'annullamento deve ridisegnare"

    command.redo()
    assert model.pages[0].redactions == [rect], "un redo dopo l'undo deve rimetterla"


def test_removing_a_redaction_is_undoable(tmp_path) -> None:
    src = str(tmp_path / "doc.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)
    rect = _secret_rect(src)
    model.pages[0].redactions.append(rect)

    command = RemoveRedaction(model, 0, rect)
    command.redo()
    assert model.pages[0].redactions == []

    command.undo()
    assert model.pages[0].redactions == [rect], "l'undo deve rimetterla dov'era"

    command.redo()
    assert model.pages[0].redactions == []


def test_moving_a_redaction_is_undoable(tmp_path) -> None:
    """One gesture, one step: the rectangle goes back where it was."""
    src = str(tmp_path / "doc.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)
    drawn: list[int] = []
    model.page_changed.connect(drawn.append)

    before = _secret_rect(src)
    AddRedaction(model, 0, before).redo()
    after = before.translated(30.0, 15.0)
    command = AdjustRedaction(model, 0, 0, before, after, moved=True)

    command.redo()
    assert model.pages[0].redactions == [after]
    assert drawn == [0, 0], "anche lo spostamento deve far ridisegnare la pagina"

    command.undo()
    assert model.pages[0].redactions == [before]

    command.redo()
    assert model.pages[0].redactions == [after], "un redo dopo l'undo deve rimetterla"


def test_resizing_a_redaction_is_undoable(tmp_path) -> None:
    src = str(tmp_path / "doc.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)
    before = _secret_rect(src)
    AddRedaction(model, 0, before).redo()
    after = before.with_corner("br", before.x1 + 40.0, before.y1 + 20.0)
    command = AdjustRedaction(model, 0, 0, before, after, moved=False)

    command.redo()
    assert model.pages[0].redactions == [after]
    assert after.x0 == before.x0, "l'angolo opposto non si muove"

    command.undo()
    assert model.pages[0].redactions == [before]


# --------------------------------------------------------------------- #
#  Saving: here you see whether the redaction is real
# --------------------------------------------------------------------- #

def test_the_marked_text_is_no_longer_in_the_file(tmp_path) -> None:
    """The test that counts: removed, not covered."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].redactions.append(_secret_rect(src))
    save_as(model, out)

    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
    assert SEGRETO not in text, "il testo marcato e` ancora nel documento"
    assert PUBBLICO in text, "la redazione ha portato via anche il resto"


def test_the_source_is_not_touched(tmp_path) -> None:
    """The project invariant: as long as you do not save, the PDF is not touched."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].redactions.append(_secret_rect(src))
    save_as(model, out)

    with pymupdf.open(src) as doc:
        assert SEGRETO in doc[0].get_text(), "la redazione e` finita sulla sorgente"


def _pdf_with_notes(path: str) -> None:
    """One word to redact and two sticky notes: one on it, one far away."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 100), SEGRETO, fontsize=20)
        page.insert_text((100, 700), PUBBLICO, fontsize=20)
        page.add_text_annot(pymupdf.Point(108, 98), SEGRETO)
        page.add_text_annot(pymupdf.Point(108, 698), PUBBLICO)
        doc.save(path)


def _notes_of(path: str) -> list[str]:
    with pymupdf.open(path) as doc:
        return [annot.info["content"] for annot in doc[0].annots() or []]


def test_an_annotation_on_a_redaction_goes_with_the_text(tmp_path) -> None:
    """``apply_redactions`` removes the content but leaves the annotations.

    Measured: a sticky note repeating the redacted word survived the save, so
    the redaction leaked exactly what it was meant to hide. It has to go.
    """
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_notes(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].redactions.append(_secret_rect(src))
    save_as(model, out)

    assert SEGRETO not in _notes_of(out), "la nota sopra la redazione e` rimasta"


def test_an_annotation_away_from_the_redaction_stays(tmp_path) -> None:
    """The rule is «touches», not «is on the same page»: everything else stays."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_notes(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].redactions.append(_secret_rect(src))
    save_as(model, out)

    assert PUBBLICO in _notes_of(out), "la nota lontana e` stata tolta"


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_the_redaction_also_holds_with_a_rotated_page(tmp_path, rotation: int) -> None:
    """The page rotates, the rectangle stays on the same words."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].rotation = rotation
    assert model.pages[0].total_rotation == rotation
    model.pages[0].redactions.append(_secret_rect(src))
    save_as(model, out)

    with pymupdf.open(out) as doc:
        page = doc[0]
        assert page.rotation == rotation, "il salvataggio ha perso la rotazione"
        text = page.get_text()
    assert SEGRETO not in text, "ruotando, il rettangolo e` finito altrove"
    assert PUBBLICO in text


def test_a_page_rotated_in_the_source(tmp_path) -> None:
    """If the /Rotate is in the starting file, the model carries it along."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_text(src, rotation=90)

    model = DocumentModel()
    model.open(src)
    assert model.pages[0].base_rotation == 90
    assert model.pages[0].unrotated_size == (595, 842)
    model.pages[0].redactions.append(_secret_rect(src))
    save_as(model, out)

    with pymupdf.open(out) as doc:
        assert doc[0].rotation == 90
        assert SEGRETO not in doc[0].get_text()
        assert PUBBLICO in doc[0].get_text()


def test_a_redaction_lands_on_its_own_page(tmp_path) -> None:
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_text(src, pages=3)

    model = DocumentModel()
    model.open(src)
    model.pages[1].redactions.append(_secret_rect(src))
    save_as(model, out)

    with pymupdf.open(out) as doc:
        assert SEGRETO in doc[0].get_text(), "la prima pagina non era marcata"
        assert SEGRETO not in doc[1].get_text(), "la seconda pagina non e` stata redatta"
        assert SEGRETO in doc[2].get_text(), "la terza pagina non era marcata"


def test_the_text_disappears_when_saving_compressed_too(tmp_path) -> None:
    """The two save paths must apply the same redactions."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].redactions.append(_secret_rect(src))
    save_compressed(model, out, LEVELS_BY_KEY["light"])

    with pymupdf.open(out) as doc:
        assert SEGRETO not in doc[0].get_text()
        assert PUBBLICO in doc[0].get_text()


def test_without_redactions_the_text_stays(tmp_path) -> None:
    """Counter-check: the redaction path does not activate by mistake."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)
    save_as(model, out)

    with pymupdf.open(out) as doc:
        assert SEGRETO in doc[0].get_text()
        assert PUBBLICO in doc[0].get_text()


# --------------------------------------------------------------------- #
#  Searching for a word and marking it everywhere
# --------------------------------------------------------------------- #


def test_find_text_finds_occurrences_on_every_page(tmp_path) -> None:
    """The search looks at every page, not only the one on screen."""
    src = str(tmp_path / "doc.pdf")
    _pdf_with_text(src, pages=3)

    model = DocumentModel()
    model.open(src)

    trovati = model.find_text(SEGRETO)
    assert sorted(trovati) == [0, 1, 2]
    assert all(len(rects) == 1 for rects in trovati.values())


def test_find_text_finds_several_occurrences_on_one_page(tmp_path) -> None:
    src = str(tmp_path / "doc.pdf")
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 100), SEGRETO, fontsize=20)
        page.insert_text((100, 300), SEGRETO, fontsize=20)
        page.insert_text((100, 700), PUBBLICO, fontsize=20)
        doc.save(src)

    model = DocumentModel()
    model.open(src)

    assert len(model.find_text(SEGRETO)[0]) == 2


def test_find_text_finds_nothing_where_there_is_nothing(tmp_path) -> None:
    src = str(tmp_path / "doc.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)

    assert model.find_text("INESISTENTE") == {}
    assert model.find_text("") == {}


def test_find_text_changes_nothing(tmp_path) -> None:
    """Searching is a read: no redaction is born by itself."""
    src = str(tmp_path / "doc.pdf")
    _pdf_with_text(src, pages=2)

    model = DocumentModel()
    model.open(src)
    model.find_text(SEGRETO)

    assert all(not item.redactions for item in model.pages)


def test_find_text_does_not_repeat_over_an_existing_mark(tmp_path) -> None:
    """Searching twice for the same word does not stack identical rectangles."""
    src = str(tmp_path / "doc.pdf")
    _pdf_with_text(src)

    model = DocumentModel()
    model.open(src)

    first = model.find_text(SEGRETO)
    assert len(first[0]) == 1
    model.pages[0].redactions.extend(first[0])

    assert model.find_text(SEGRETO) == {}


def test_find_text_follows_the_virtual_list_after_a_merge(tmp_path) -> None:
    """The occurrences are indexed on the pages of the model, not of the file."""
    first = str(tmp_path / "a.pdf")
    second = str(tmp_path / "b.pdf")
    _pdf_with_text(first)
    _pdf_with_text(second)

    model = DocumentModel()
    model.open(first)
    model.append_document(second)
    model.pages.pop(0)

    assert list(model.find_text(SEGRETO)) == [0]


def test_find_text_and_the_redaction_it_produces_really_delete(tmp_path) -> None:
    """The full round: search, mark, save, verify."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_text(src, pages=3)

    model = DocumentModel()
    model.open(src)
    for index, rects in model.find_text(SEGRETO).items():
        model.pages[index].redactions.extend(rects)
    save_as(model, out)

    with pymupdf.open(out) as doc:
        assert doc.page_count == 3
        for page in doc:
            assert SEGRETO not in page.get_text()
            assert PUBBLICO in page.get_text()


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_find_text_also_holds_with_a_rotated_page(tmp_path, rotation: int) -> None:
    """The search answers in the space the redaction expects."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _pdf_with_text(src, rotation=rotation)

    model = DocumentModel()
    model.open(src)
    trovati = model.find_text(SEGRETO)
    assert len(trovati[0]) == 1
    model.pages[0].redactions.extend(trovati[0])
    save_as(model, out)

    with pymupdf.open(out) as doc:
        assert doc[0].rotation == rotation
        assert SEGRETO not in doc[0].get_text()
        assert PUBBLICO in doc[0].get_text()


# --------------------------------------------------------------------- #
#  Marks fitted to words: the lines around them stay whole
# --------------------------------------------------------------------- #


def _three_lines(path: str, leading: float, font: str) -> None:
    """A word to redact on the middle line, at ordinary single spacing."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        size = 12
        page.insert_text((72, 300 - size * leading), "Riga sopra yyy", fontsize=size, fontname=font)
        page.insert_text((72, 300), f"Il codice {SEGRETO} qui", fontsize=size, fontname=font)
        page.insert_text((72, 300 + size * leading), "Riga sotto innocente", fontsize=size, fontname=font)
        doc.save(path)


@pytest.mark.parametrize("font", ["helv", "tiro"])
@pytest.mark.parametrize("leading", [1.0, 1.15, 1.2])
def test_a_searched_word_goes_without_touching_the_lines_around_it(
    tmp_path, leading: float, font: str
) -> None:
    """A glyph box reaches into the next line at single spacing: the search
    hit used to take «o innocente» off the line below together with the word."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _three_lines(src, leading, font)

    model = DocumentModel()
    model.open(src)
    model.pages[0].redactions.extend(model.find_text(SEGRETO)[0])
    save_as(model, out)

    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
    assert SEGRETO not in text
    assert "Riga sopra yyy" in text
    assert "Riga sotto innocente" in text
    assert "Il codice" in text and "qui" in text


@pytest.mark.parametrize("leading", [1.0, 1.15, 1.2])
def test_a_selected_word_goes_without_touching_the_lines_around_it(
    tmp_path, leading: float
) -> None:
    """The same for the words a selection picks (``words_on``)."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _three_lines(src, leading, "helv")

    model = DocumentModel()
    model.open(src)
    with pymupdf.open(src) as doc:
        hit = doc[0].search_for(SEGRETO)[0]
    word = next(
        rect
        for rect in model.words_on(0)
        if rect.x0 <= (hit.x0 + hit.x1) / 2 <= rect.x1 and rect.y0 <= hit.y1 and hit.y0 <= rect.y1
        and rect.y0 < 300 < rect.y1
    )
    assert word.snug
    model.pages[0].redactions.append(word)
    save_as(model, out)

    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
    assert SEGRETO not in text
    assert "Riga sopra yyy" in text
    assert "Riga sotto innocente" in text


def test_a_drawn_zone_still_deletes_everything_it_touches(tmp_path) -> None:
    """Only marks fitted to words are narrowed: a zone means what was drawn."""
    src = str(tmp_path / "doc.pdf")
    out = str(tmp_path / "out.pdf")
    _three_lines(src, 1.2, "helv")

    model = DocumentModel()
    model.open(src)
    zone = RedactionRect.from_corners(60, 300 - 12 * 1.2 - 10, 400, 300 + 12 * 1.2 + 3)
    assert not zone.snug
    model.pages[0].redactions.append(zone)
    save_as(model, out)

    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
    assert "Riga sopra" not in text
    assert SEGRETO not in text
    assert "innocente" not in text


def test_a_mark_moved_or_resized_is_a_drawn_zone() -> None:
    """A word box nudged across two half lines would put its band in the gap
    between them and delete nothing: once touched, it deletes all it covers."""
    word = RedactionRect.from_corners(10, 10, 50, 26, snug=True)
    assert word.clamped_to(595, 842).snug
    assert not word.translated(0, 8).snug
    assert not word.with_corner("br", 60, 40).snug
    assert word.text_band().y0 > word.y0 and word.text_band().y1 < word.y1
    zone = RedactionRect.from_corners(10, 10, 50, 26)
    assert zone.text_band() == zone


def test_a_mark_fitted_to_words_still_blanks_the_picture_under_it(tmp_path) -> None:
    """On a scan the word is pixels as well: the narrow band is for the text
    only, the image under the whole mark is still wiped."""
    src = str(tmp_path / "scan.pdf")
    out = str(tmp_path / "out.pdf")
    with pymupdf.open() as doc:
        page = doc.new_page(width=200, height=200)
        black = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
        black.clear_with(0)
        page.insert_image(page.rect, pixmap=black)
        doc.save(src)

    model = DocumentModel()
    model.open(src)
    model.pages[0].redactions.append(RedactionRect.from_corners(50, 50, 150, 70, snug=True))
    save_as(model, out)

    with pymupdf.open(out) as doc:
        pixmap = doc[0].get_pixmap(clip=pymupdf.Rect(100, 52, 101, 53))
    # Near the edge of the mark, outside the text band: white, not the scan.
    assert pixmap.pixel(0, 0) != (0, 0, 0)
