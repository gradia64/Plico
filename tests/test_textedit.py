"""Minimal text editing (model/textedit.py): one span replaced, its look kept.

Every test checks the materialised result the way a reader would meet it:
the text layer after a save-and-reopen, the pixels, the drawings. A span
that only *looks* replaced but still carries the old words in its content
stream would be the worst possible outcome, so "old text gone" is asserted
everywhere.
"""

import os

import pymupdf
import pytest

from plico.model import textedit
from plico.model.textedit import (
    FROM_DOCUMENT,
    FROM_FALLBACK,
    FROM_SYSTEM,
    MIN_SCALE,
    apply_edit,
    check_edit,
    span_at,
)

RED = 0xC00000
# The same red as a PDF colour; 192/255, not 0.75, so it survives the round trip.
RED_RGB = (192 / 255, 0, 0)


def _reopened(doc: pymupdf.Document) -> pymupdf.Document:
    """What a reader opens: the document saved and parsed again."""
    return pymupdf.open("pdf", doc.tobytes(garbage=4, deflate=True))


def _span(page: pymupdf.Page, words: str) -> textedit.TextSpan:
    hit = page.search_for(words)[0]
    span = span_at(page, (hit.x0 + hit.x1) / 2, (hit.y0 + hit.y1) / 2)
    assert span is not None, f"nessuno span sotto «{words}»"
    return span


def _embedded(page: pymupdf.Page, point, text: str, **kwargs) -> None:
    """Text in an EMBEDDED font that has a character map, like most producers' full fonts."""
    if "F0" not in [f[4] for f in page.get_fonts()]:
        page.insert_font(fontname="F0", fontbuffer=pymupdf.Font("tiro").buffer)
    page.insert_text(point, text, fontname="F0", fontsize=12, **kwargs)


@pytest.fixture
def no_system_fonts(monkeypatch):
    """Make the font choice independent of what this machine has installed."""
    monkeypatch.setattr(textedit, "_system_font_path", lambda name: None)


# --- finding the span ---------------------------------------------------------


def test_span_at_describes_the_span_under_the_point():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Totale: 120 euro", color=RED_RGB)

    span = _span(page, "120")

    assert span.text == "Totale: 120 euro"
    assert span.origin == pytest.approx((72, 100))
    assert span.size == pytest.approx(12)
    assert span.color == RED
    assert span.horizontal and not span.type3


def test_span_at_on_an_empty_spot_is_none():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Testo")
    assert span_at(page, 400, 600) is None


def test_a_point_just_outside_the_box_still_finds_the_span():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Vicino")
    box = _span(page, "Vicino").bbox

    assert span_at(page, box[0] - textedit.HIT_TOLERANCE / 2, (box[1] + box[3]) / 2) is not None
    assert span_at(page, box[0] - textedit.HIT_TOLERANCE * 3, (box[1] + box[3]) / 2) is None


def test_the_nearest_span_wins_between_two_lines():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Sopra")
    _embedded(page, (72, 106 + 16), "Sotto")
    sopra, sotto = _span(page, "Sopra").bbox, _span(page, "Sotto").bbox
    # In the gap, nearer the first box than the second.
    assert sotto[1] - sopra[3] > 2.5, "no gap between the lines"
    assert span_at(page, 80, sopra[3] + 1.0).text == "Sopra"
    assert span_at(page, 80, sotto[1] - 1.0).text == "Sotto"


def test_span_is_in_page_space_whatever_the_rotate():
    """Same rectangle with /Rotate 0 and 90: the space redactions live in (§4)."""
    rects = []
    for rotation in (0, 90):
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        _embedded(page, (100, 200), "Ruotata")
        page.set_rotation(rotation)
        rects.append(_span(page, "Ruotata").bbox)
    assert rects[0] == pytest.approx(rects[1])


# --- what the edit keeps and what it removes -----------------------------------


def test_edit_replaces_the_text_and_removes_the_old_one():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Importo 12.400 euro")

    apply_edit(page, _span(page, "12.400"), "Importo 13.950 euro")

    testo = _reopened(doc)[0].get_text()
    assert "13.950" in testo
    assert "12.400" not in testo, "il testo vecchio deve sparire dal content stream"


def test_neighbouring_spans_and_lines_survive():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Prima")
    page.insert_text((140, 100), "accanto", fontname="helv", fontsize=12)
    _embedded(page, (72, 116), "Riga sotto")

    apply_edit(page, _span(page, "Prima"), "Dopo")

    testo = _reopened(doc)[0].get_text()
    assert "Dopo" in testo and "accanto" in testo and "Riga sotto" in testo
    assert "Prima" not in testo


def test_background_and_drawings_are_left_alone():
    """No fill and no line-art removal: a shaded cell stays shaded, borders stay."""
    doc = pymupdf.open()
    page = doc.new_page()
    cella = pymupdf.Rect(60, 80, 300, 110)
    page.draw_rect(cella, color=(0, 0, 0), fill=(1, 0.9, 0.6))
    _embedded(page, (72, 100), "3.200 euro")
    disegni = len(page.get_drawings())

    apply_edit(page, _span(page, "3.200"), "3.450 euro")

    letta = _reopened(doc)[0]
    assert len(letta.get_drawings()) == disegni
    # A point of the cell above the glyphs: still the cell's colour, not white.
    pixel = letta.get_pixmap().pixel(64, 84)
    assert all(abs(a - b) <= 2 for a, b in zip(pixel, (255, 230, 153), strict=True)), pixel


def test_colour_and_size_are_kept():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Scadenza 30 settembre", color=RED_RGB)

    apply_edit(page, _span(page, "Scadenza"), "Scadenza 15 ottobre")

    nuovo = _span(_reopened(doc)[0], "15 ottobre")
    assert nuovo.color == RED
    assert nuovo.size == pytest.approx(12)
    assert nuovo.origin == pytest.approx((72, 100))


def test_edit_on_a_rotated_page_keeps_the_rotate():
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _embedded(page, (100, 200), "Consulenza")
    page.set_rotation(90)
    prima = _span(page, "Consulenza").bbox

    apply_edit(page, _span(page, "Consulenza"), "Consulente")

    letta = _reopened(doc)[0]
    assert letta.rotation == 90
    dopo = _span(letta, "Consulente").bbox
    assert dopo[:2] == pytest.approx(prima[:2], abs=0.5), "nello stesso punto della pagina"


def test_an_empty_replacement_just_removes_the_text():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Da togliere")

    apply_edit(page, _span(page, "togliere"), "")

    assert "togliere" not in _reopened(doc)[0].get_text()


# --- fitting ------------------------------------------------------------------


def test_a_longer_text_may_use_the_free_room_on_its_right():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Licenze")

    scelta = apply_edit(page, _span(page, "Licenze"), "Licenze software")

    assert scelta.scale == 1.0


def test_a_table_border_bounds_the_room():
    """The neighbouring cell is another block: its border must still stop the text."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_line((130, 85), (130, 105))
    _embedded(page, (72, 100), "Licenze")
    page.insert_text((136, 100), "1.150 euro", fontname="helv", fontsize=12)

    span = _span(page, "Licenze")
    assert span.room < 130 - span.bbox[2]

    with pytest.raises(ValueError):
        check_edit(page, span, "Licenze software e servizi")


def test_text_in_another_block_bounds_the_room():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Voce")
    page.insert_text((200, 100), "Importo", fontname="helv", fontsize=12)

    span = _span(page, "Voce")
    assert span.bbox[2] + span.room <= 200


def test_slightly_too_long_is_shrunk_and_far_too_long_is_refused():
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_line((150, 85), (150, 105))
    _embedded(page, (72, 100), "Consulenza")
    span = _span(page, "Consulenza")
    disponibile = span.width + span.room

    font = pymupdf.Font("tiro")
    # Find a text needing between MIN_SCALE and 100% of the room.
    testo = "Consulenza"
    while font.text_length(testo, fontsize=12) <= disponibile:
        testo += "e"
    scelta = check_edit(page, span, testo)
    assert MIN_SCALE <= scelta.scale < 1.0

    with pytest.raises(ValueError, match="non ci sta"):
        check_edit(page, span, "Consulenza legale, fiscale e del lavoro")


def test_a_refused_edit_leaves_the_page_untouched():
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_line((150, 85), (150, 105))
    _embedded(page, (72, 100), "Consulenza")

    with pytest.raises(ValueError):
        apply_edit(page, _span(page, "Consulenza"), "Consulenza legale, fiscale e del lavoro")

    assert "Consulenza" in _reopened(doc)[0].get_text()


def test_vertical_text_is_refused():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((300, 300), "Verticale", fontname="helv", fontsize=12, rotate=90)

    span = _span(page, "Verticale")
    assert not span.horizontal
    with pytest.raises(ValueError, match="orizzontale"):
        check_edit(page, span, "Altro")


# --- choosing the font --------------------------------------------------------


def test_the_documents_own_font_comes_first():
    doc = pymupdf.open()
    page = doc.new_page()
    _embedded(page, (72, 100), "Testo")
    assert check_edit(page, _span(page, "Testo"), "Altro").source == FROM_DOCUMENT


def test_a_font_without_the_glyphs_falls_back_by_style(no_system_fonts):
    """Base-14 text is not embedded at all: the look-alike comes from the flags."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Grassetto", fontname="hebo", fontsize=12)

    scelta = check_edit(page, _span(page, "Grassetto"), "Neretto")

    assert scelta.source == FROM_FALLBACK
    assert scelta.font_name == "Helvetica-Bold"


def test_characters_outside_latin1_are_written_correctly(no_system_fonts):
    """insert_text() with a Base-14 font turns «Łódź» into «·ód·»: TextWriter does not."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Licenze", fontname="helv", fontsize=12)

    apply_edit(page, _span(page, "Licenze"), "Łódź ő")

    assert "Łódź ő" in _reopened(doc)[0].get_text()


def test_an_installed_font_is_found_by_postscript_name(monkeypatch):
    if textedit._system_font_path("LiberationSerif") is None:
        pytest.skip("Liberation Serif non è installato qui")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_font(
        fontname="F1", fontfile=textedit._system_font_path("LiberationSerif")
    )
    page.insert_text((72, 100), "Liberation", fontname="F1", fontsize=12)
    span = _span(page, "Liberation")
    # The embedded copy would win; pretend it is a glyph-indexed subset.
    monkeypatch.setattr(textedit, "_embedded_font", lambda page, name: None)
    assert check_edit(page, span, "Altro").source == FROM_SYSTEM


def test_fc_match_answering_with_another_font_is_not_believed():
    """fc-match always returns *something*: a made-up name must give None."""
    assert textedit._system_font_path("NessunFontSiChiamaCosi-Regular") is None


# --- in the save pipeline -----------------------------------------------------


def test_edit_after_insert_pdf_and_font_subsetting(tmp_path):
    """The path save.py will take: copy the page, edit it, subset, save."""
    sorgente = pymupdf.open()
    pagina = sorgente.new_page()
    _embedded(pagina, (72, 100), "Importo 12.400 euro")

    out = pymupdf.open()
    out.insert_pdf(sorgente)
    apply_edit(out[0], _span(out[0], "12.400"), "Importo 13.950 euro")

    pieno = str(tmp_path / "pieno.pdf")
    out.save(pieno, garbage=4, deflate=True)
    out.subset_fonts()
    ridotto = str(tmp_path / "ridotto.pdf")
    out.save(ridotto, garbage=4, deflate=True)

    assert os.path.getsize(ridotto) < os.path.getsize(pieno)
    with pymupdf.open(ridotto) as letto:
        testo = letto[0].get_text()
        assert "13.950" in testo and "12.400" not in testo


# --- the lines around the edited one ----------------------------------------


@pytest.mark.parametrize("font", ["helv", "tiro"])
@pytest.mark.parametrize("leading", [1.0, 1.15, 1.2])
def test_editing_a_line_leaves_the_lines_around_it_whole(no_system_fonts, leading, font):
    """A span's box runs from ascender to descender, so at ordinary single
    spacing it reaches the lines above and below: redacting it used to delete
    «Seconda riga T» together with the line actually edited."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100 - 12 * leading), "Riga sopra yyy", fontsize=12, fontname=font)
    page.insert_text((72, 100), "Prima riga gjpq", fontsize=12, fontname=font)
    page.insert_text((72, 100 + 12 * leading), "Seconda riga TALL", fontsize=12, fontname=font)

    apply_edit(page, _span(page, "Prima riga"), "Riga nuova")

    text = _reopened(doc)[0].get_text()
    assert "Prima riga" not in text and "gjpq" not in text
    assert "Riga nuova" in text
    assert "Riga sopra yyy" in text
    assert "Seconda riga TALL" in text


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_the_room_ends_at_the_page_edge_on_a_rotated_page(rotation):
    """``page.rect`` is turned by /Rotate, the spans are not: on a quarter
    turn the right edge was taken from the page's height, 842 instead of 595."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((400, 100), "Corto", fontsize=12)
    page.set_rotation(rotation)

    span = _span(page, "Corto")

    assert span.bbox[2] + span.room <= 595 - 36
