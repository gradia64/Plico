"""Building a PDF out of pages of other PDFs, with their form fields intact.

``insert_pdf()`` copies a range of pages and the form fields on them, and it
does that right exactly once per source. Copying from the same source a second
time -- which is what a reordered document, a duplicated page or an
interleaved merge all need -- goes wrong in two ways, both measured on
PyMuPDF 1.28:

* a field whose widgets sit on several pages (one parent, one kid per page,
  the way form designers build a repeated field) loses the widget of the
  later copy: the page comes out with no field at all;
* a field met again is renamed to keep names unique (``nome`` →
  ``nome [12]``), so one field of the source becomes two in the file.

Neither ``join_duplicates`` nor keeping the graft map (``final=0``) helps, and
``Document.select()`` drops the whole AcroForm. So every source is copied in
ONE call, as the span from the first to the last page it contributes, and the
document is put in order afterwards inside the output, where ``move_page()``
and ``fullcopy_page()`` keep the fields as they are. The pages of the span
that are not wanted are deleted -- and since ``delete_page()`` leaves their
fields behind in /Fields, value and all, :func:`prune_fields` takes away
every field no page shows any more: a page the user deleted must not leave its
filled-in values in the file.
"""

import re

import pymupdf

_REFERENCE = re.compile(r"(\d+)\s+\d+\s+R")


def assemble(
    out: pymupdf.Document,
    order: list[tuple[pymupdf.Document, int]],
    join_duplicates: bool = False,
) -> None:
    """Append to the empty *out* the pages *order* names, in that order.

    Each entry is a source document and a page index in it; a page may be
    named more than once. Afterwards ``out[j]`` is the copy of ``order[j]``.

    Different sources are told apart by identity. Fields with the same name in
    two of them stay two fields (MuPDF renames the second), which is right for
    two documents; *join_duplicates* makes them one, for the caller whose
    sources are two copies of the SAME document.
    """
    assert len(out) == 0, "assemble() builds a document from nothing"
    spans: dict[int, tuple[pymupdf.Document, list[int]]] = {}
    for doc, index in order:
        spans.setdefault(id(doc), (doc, []))[1].append(index)

    # One copy per source: its span, minus the pages nobody asked for.
    where: dict[tuple[int, int], int] = {}
    for key, (doc, indices) in spans.items():
        wanted = sorted(set(indices))
        low, high = wanted[0], wanted[-1]
        base = len(out)
        # Two fields of ONE source with the same name are one field to PDF and
        # to the model (a value is written by name), and MuPDF renames the
        # second even within a single copy. Joining is right for the source's
        # own names, never for another source's: the first copy can join
        # freely, a later one goes through a copy of its own first when it
        # has names to join.
        source: pymupdf.Document = doc
        staged: pymupdf.Document | None = None
        if base > 0 and not join_duplicates and _repeats_a_name(doc):
            staged = pymupdf.open()
            staged.insert_pdf(doc, from_page=low, to_page=high, join_duplicates=True)
            source, low, high = staged, 0, high - low
            wanted = [index - wanted[0] for index in wanted]
            indices_map = dict(zip(wanted, sorted(set(indices)), strict=True))
        else:
            indices_map = {index: index for index in wanted}
        out.insert_pdf(
            source,
            from_page=low,
            to_page=high,
            join_duplicates=base == 0 or join_duplicates,
        )
        if staged is not None:
            staged.close()
        keep = set(wanted)
        for index in range(high, low - 1, -1):
            if index not in keep:
                out.delete_page(base + index - low)
        for slot, index in enumerate(wanted):
            where[(key, indices_map[index])] = base + slot
    if len(out) != len(where):
        raise RuntimeError("pagine copiate e pagine attese non corrispondono")
    prune_fields(out)

    # A page named twice is copied inside the output, where the copy keeps
    # its fields; then every page is moved to its slot.
    seen: set[tuple[int, int]] = set()
    targets: list[int] = []
    for doc, index in order:
        page = where[(id(doc), index)]
        if (id(doc), index) in seen:
            out.fullcopy_page(page)
            page = len(out) - 1
        seen.add((id(doc), index))
        targets.append(page)
    current = list(range(len(out)))
    for slot, page in enumerate(targets):
        position = current.index(page)
        if position != slot:
            # Every slot before this one is settled, so the page is further
            # down: moving it in front of the page now at *slot* puts it there.
            out.move_page(position, slot)
            current.insert(slot, current.pop(position))


def _repeats_a_name(doc: pymupdf.Document) -> bool:
    """Whether two top-level fields of *doc* share a name."""
    target = acroform_key(doc, "Fields")
    if target is None:
        return False
    kind, fields = doc.xref_get_key(*target)
    if kind != "array":
        return False
    names = [doc.xref_get_key(int(n), "T")[1] for n in _REFERENCE.findall(fields)]
    return len(names) != len(set(names))


def acroform_key(doc: pymupdf.Document, key: str) -> tuple[int, str] | None:
    """Where to write *key* of the AcroForm: an object and a key path in it.

    ``xref_set_key(catalog, "AcroForm/Fields", …)`` writes through an inline
    dictionary but not through an indirect one -- there it leaves the string
    "fitz: replace me!" where the array should be (measured). The AcroForm is
    therefore resolved first. ``None`` when the document has no form.
    """
    catalog = doc.pdf_catalog()
    kind, value = doc.xref_get_key(catalog, "AcroForm")
    if kind == "xref":
        return int(value.split()[0]), key
    if kind == "dict":
        return catalog, f"AcroForm/{key}"
    return None


def prune_fields(doc: pymupdf.Document) -> None:
    """Drop from the AcroForm every field that no page shows any more.

    Run after the copy, and again by the save after the redactions: a mark
    deletes the WIDGET, and a field whose value lives in a parent node (the
    shape Acrobat writes: /FT, /T and /V on the parent, the widget a kid)
    stayed reachable from /Fields with its /V -- the redacted value, in the
    file (reported by a review, reproduced). Pruned, nothing reaches it and
    ``garbage=4`` drops it.
    """
    target = acroform_key(doc, "Fields")
    if target is None:
        return
    kind, fields = doc.xref_get_key(*target)
    if kind != "array":
        return
    live = {
        xref
        for index in range(len(doc))
        for xref, annot_type, _ in doc[index].annot_xrefs()
        if annot_type == pymupdf.PDF_ANNOT_WIDGET  # type: ignore[attr-defined]
    }
    kept_nodes: set[int] = set()

    def keep(xref: int) -> bool:
        kids_kind, kids = doc.xref_get_key(xref, "Kids")
        if kids_kind != "array":
            alive = xref in live
        else:
            survivors: list[int] = []
            for kid in (int(number) for number in _REFERENCE.findall(kids)):
                if kid not in survivors and keep(kid):
                    survivors.append(kid)
            doc.xref_set_key(xref, "Kids", _array(survivors))
            # A field can be its own widget AND have kids; either keeps it.
            alive = bool(survivors) or xref in live
        if alive:
            kept_nodes.add(xref)
        return alive

    top = [xref for xref in (int(n) for n in _REFERENCE.findall(fields)) if keep(xref)]
    doc.xref_set_key(*target, _array(top))
    co_target = acroform_key(doc, "CO")
    assert co_target is not None
    co_kind, co = doc.xref_get_key(*co_target)
    if co_kind == "array":
        calculated = [int(n) for n in _REFERENCE.findall(co) if int(n) in kept_nodes]
        doc.xref_set_key(*co_target, _array(calculated))


def _array(xrefs: list[int]) -> str:
    return "[" + " ".join(f"{xref} 0 R" for xref in xrefs) + "]"
