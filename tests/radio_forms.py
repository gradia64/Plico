"""A radio group built by hand, for the tests that need one.

``page.add_widget`` cannot make a radio button at all -- it raises
``ValueError: bad xref`` -- so the group is written the way PDF describes it:
one field (the parent) holding the buttons as kids, each kid carrying the one
state it can show. This is what a file from any other tool looks like, which is
the case Plico has to handle; every test that needs such a file builds it here
instead of each carrying its own copy.
"""

import pikepdf

_ON = b"0 0.5 0 rg 2 2 16 16 re f"
_OFF = b"0.8 g 2 2 16 16 re f"


def _appearance(pdf: pikepdf.Pdf, data: bytes) -> pikepdf.Stream:
    """One drawn state of a button: PDF keeps the option *names* in /AP /N."""
    return pikepdf.Stream(
        pdf,
        data,
        {
            "/Type": pikepdf.Name("/XObject"),
            "/Subtype": pikepdf.Name("/Form"),
            "/BBox": pikepdf.Array([0, 0, 20, 20]),
            "/Resources": pikepdf.Dictionary({}),
        },
    )


def radio_pdf(
    path: str,
    options: tuple[str, ...] = ("primo", "secondo"),
    value: str = "primo",
    rotation: int = 0,
) -> None:
    """A radio group with one button per option, assembled by hand.

    ``page.add_widget`` cannot make a radio button at all -- it raises
    ``ValueError: bad xref`` -- so the group is written the way PDF describes
    it: one field (the parent) holding the buttons as kids, each kid carrying
    the one state it can show. This is what a file from any other tool looks
    like, which is the case Plico has to handle.
    """
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(595, 842))
    parent = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/FT": pikepdf.Name("/Btn"),
                "/T": pikepdf.String("pasto"),
                "/Ff": 32768,
                "/V": pikepdf.Name("/" + value),
            }
        )
    )
    kids = []
    for index, option in enumerate(options):
        kids.append(
            pdf.make_indirect(
                pikepdf.Dictionary(
                    {
                        "/Type": pikepdf.Name("/Annot"),
                        "/Subtype": pikepdf.Name("/Widget"),
                        "/Parent": parent,
                        "/Rect": pikepdf.Array([72 + index * 40, 700, 92 + index * 40, 720]),
                        "/AS": pikepdf.Name("/" + option if option == value else "/Off"),
                        "/F": 4,
                        "/AP": pikepdf.Dictionary(
                            {
                                "/N": pikepdf.Dictionary(
                                    {
                                        "/" + option: _appearance(pdf, _ON),
                                        "/Off": _appearance(pdf, _OFF),
                                    }
                                )
                            }
                        ),
                    }
                )
            )
        )
    parent["/Kids"] = pikepdf.Array(kids)
    page["/Annots"] = pikepdf.Array(kids)
    if rotation:
        page["/Rotate"] = rotation
    pdf.Root["/AcroForm"] = pikepdf.Dictionary(
        {
            "/Fields": pikepdf.Array([parent]),
            "/DA": pikepdf.String("/Helv 0 Tf 0 g"),
        }
    )
    pdf.save(path)
    pdf.close()
