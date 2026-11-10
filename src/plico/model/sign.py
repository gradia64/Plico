"""Digital signatures: PAdES over the file that comes out of a save.

A signature is not an edit of the page list. It is computed over the *bytes*
of a file, so any later modification — even one this model knows how to undo —
breaks it, and the only way to sign is to produce a file and sign that. This
module therefore writes a whole new file, exactly like compression does, and
the window adopts the result.

Signing and verification are pyHanko's: it builds the CMS structure, the
``/ByteRange`` and the incremental update around it, and it is also the only
thing in the process that understands what it produced. Checking a signature
needs the certificate chain rules, the digest over the ranges and the diff
between revisions — not something to re-implement here.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import logging
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pymupdf
from asn1crypto import keys as asn1keys
from asn1crypto import x509 as asn1x509
from cryptography import x509
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.crypt import AuthStatus
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.text import TextBoxStyle
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec, SigSeedSubFilter
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.sign.validation.status import ModificationLevel, SignatureCoverageLevel
from pyhanko.stamp import TextStampStyle
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.registry import SimpleCertificateStore
from PySide6.QtCore import QCoreApplication

from .document import open_for_reading
from .forms import ANNOT_WIDGET

# pyHanko reports a refused certificate chain and a policy violation by logging
# the whole traceback at ERROR level. Both are ordinary answers here -- an
# untrusted certificate is the *normal* case, since Plico ships no store -- and
# the user reads the verdict in the dialog, not the log. Silencing the two
# loggers keeps a GUI launched from a terminal from printing pages of stack
# tracebacks for something it just told the user in a sentence.
logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)

# The name of the field a new signature goes into. A file may carry several
# signatures, and a second one would need another name; the window only ever
# makes the first, so a fixed name is enough.
DEFAULT_FIELD = "Firma"

# The CMS blob is stored as a hexadecimal string, so half of what is reserved is
# padding: 16 KiB of room hold an 8 KiB signature, which is a certificate chain
# of a few elements. pyHanko can estimate a tight size, and a chain longer than
# the estimate would not fit at all; erring on the generous side costs nothing
# that matters in a PDF.
RESERVED = 16384

# Points. The default box sits where a signature line would: bottom-right, this
# far from the edges of an unrotated page.
STAMP_WIDTH = 200.0
STAMP_HEIGHT = 70.0
STAMP_MARGIN = 36.0
STAMP_FONT_SIZE = 9


class SigningError(Exception):
    """Something went wrong with a certificate, in words the user can read."""


@dataclass(frozen=True)
class Identity:
    """Who a certificate belongs to."""

    common_name: str
    organization: str
    country: str
    not_before: datetime
    not_after: datetime

    @property
    def label(self) -> str:
        """The name to show in a list: common name, then organisation."""
        if self.organization:
            return f"{self.common_name} ({self.organization})"
        return self.common_name


@dataclass(frozen=True)
class SignatureRequest:
    """What the user chose in the signing dialog.

    ``page`` is ``None`` for an invisible signature, the shape used when the
    document is signed to be *valid* rather than to be looked at; otherwise
    ``box`` is where the visible stamp goes, in PDF coordinates (bottom-left
    origin, unrotated page), which is the space ``/Rect`` is written in.
    """

    certificate: str
    password: str = ""
    reason: str = ""
    location: str = ""
    field_name: str = DEFAULT_FIELD
    page: int | None = None
    box: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class Signature:
    """One signature found in a file, as far as it can be judged."""

    field_name: str
    identity: Identity | None
    signed_at: datetime | None
    algorithm: str
    covers_whole_file: bool
    intact: bool
    valid: bool
    trusted: bool
    changed: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Whether the signature is sound and still covers the whole file."""
        return self.error is None and self.intact and self.valid and not self.changed


def _name_of(path: str) -> str:
    return os.path.basename(path) or path


def _credentials(path: str, password: str) -> tuple[Any, Any, list[Any]]:
    """Load a PKCS#12, turning every failure into an Italian sentence."""
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise SigningError(
            QCoreApplication.translate("Signing", "Non riesco a leggere «{0}»: {1}").format(
                _name_of(path), error.strerror or error
            )
        ) from error
    try:
        key, certificate, chain = pkcs12.load_key_and_certificates(
            raw, (password or "").encode()
        )
    except ValueError as error:
        raise SigningError(
            QCoreApplication.translate(
                "Signing", "Password errata, oppure «{0}» non è un file PKCS#12."
            ).format(_name_of(path))
        ) from error
    if key is None or certificate is None:
        raise SigningError(
            QCoreApplication.translate(
                "Signing", "«{0}» non contiene una chiave privata con il suo certificato."
            ).format(_name_of(path))
        )
    return key, certificate, list(chain or [])


def read_identity(path: str, password: str = "") -> Identity:
    """Read who the certificate in *path* (a PKCS#12 file) belongs to."""
    _, certificate, _ = _credentials(path, password)
    return _identity_of(certificate)


def _identity_of(certificate: x509.Certificate) -> Identity:
    """Build an :class:`Identity` from a ``cryptography`` certificate."""

    def first(oid: x509.ObjectIdentifier) -> str:
        found = certificate.subject.get_attributes_for_oid(oid)
        return str(found[0].value) if found else ""

    return Identity(
        common_name=first(NameOID.COMMON_NAME),
        organization=first(NameOID.ORGANIZATION_NAME),
        country=first(NameOID.COUNTRY_NAME),
        not_before=certificate.not_valid_before_utc,
        not_after=certificate.not_valid_after_utc,
    )


def _identity_from_der(certificate: asn1x509.Certificate) -> Identity:
    """The same, from an ``asn1crypto`` certificate (what pyHanko hands back)."""
    subject = certificate.subject.native
    validity = certificate["tbs_certificate"]["validity"]
    return Identity(
        common_name=subject.get("common_name", ""),
        organization=subject.get("organization_name", ""),
        country=subject.get("country_name", ""),
        not_before=validity["not_before"].native.replace(tzinfo=None),
        not_after=validity["not_after"].native.replace(tzinfo=None),
    )


def stamp_text(reason: str) -> str:
    """The text a visible signature prints, as a template for pyHanko.

    In Italian because it ends up *inside the document*, where the rest of what
    the user reads is Italian too. ``%(name)s`` and ``%(reason)s`` are filled
    by :func:`sign_in_place`; ``%(ts)s`` is the stamping time, which pyHanko
    interpolates itself.
    """
    lines = [QCoreApplication.translate("Signing", "Firmato da %(name)s"), "%(ts)s"]
    if reason.strip():
        lines.append("%(reason)s")
    return "\n".join(lines)


def stamp_box(width: float, height: float) -> tuple[float, float, float, float]:
    """Where a visible signature goes by default, in PDF coordinates.

    PDF coordinates have the origin in the bottom-left corner, so this is the
    rectangle pyHanko writes into ``/Rect`` — not the top-left based one MuPDF
    reports when reading a widget back.

    On a page too small for the default size the stamp shrinks to fit: a box
    hanging off the page edge is cut away by every reader, and half a stamp is
    worse than a small one.
    """
    margin = min(STAMP_MARGIN, width / 4, height / 4)
    stamp_width = min(STAMP_WIDTH, width - 2 * margin)
    stamp_height = min(STAMP_HEIGHT, height - 2 * margin)
    left = width - margin - stamp_width
    return (left, margin, left + stamp_width, margin + stamp_height)


def sign_in_place(
    path: str, request: SignatureRequest, document_password: str | None = None
) -> None:
    """Sign the file at *path*, replacing it with the signed version.

    *path* is expected to be a temporary written by the save path, so an error
    halfway leaves nothing behind and the caller's own ``os.replace`` keeps its
    guarantee. The permissions are copied across for the same reason the save
    path copies them: the temporary replaces a file that had a mode.

    *document_password* unlocks an encrypted *path*: the signature is appended
    as an incremental update, encrypted like the rest of the file.
    """
    data = Path(path).read_bytes()
    signed = _sign_bytes(data, request, document_password)
    descriptor, temporary = tempfile.mkstemp(
        dir=os.path.dirname(path) or ".", suffix=".pdf.tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(signed)
        os.chmod(temporary, os.stat(path).st_mode & 0o7777)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def _signer(
    key: Any, certificate: x509.Certificate, chain: Sequence[x509.Certificate]
) -> signers.SimpleSigner:
    """A pyHanko signer that carries the whole chain, not just the leaf.

    Built here rather than with ``SimpleSigner.load_pkcs12()`` because that one
    takes a path, re-reads the file and logs a traceback to stderr when the
    password is wrong — and the wrong password is a normal thing for a user to
    type, not an accident to print.
    """
    store = SimpleCertificateStore()
    for extra in chain:
        store.register(asn1x509.Certificate.load(extra.public_bytes(Encoding.DER)))
    return signers.SimpleSigner(
        signing_cert=asn1x509.Certificate.load(certificate.public_bytes(Encoding.DER)),
        signing_key=asn1keys.PrivateKeyInfo.load(
            key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
        ),
        cert_registry=store,
    )


def _free_field_name(data: bytes, wanted: str, password: str | None = None) -> str:
    """A signature field name that nothing in *data* is already using.

    Signing an already signed document is allowed -- the window asks first and
    the second signature covers the file as it stands -- but two signatures
    cannot live in one field: pyHanko refuses to fill a field twice. Left
    alone, the second signature would fail on a document it is supposed to
    handle.
    """
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            # Before any page is touched: see document.open_for_reading.
            if password:
                document.authenticate(password)
            taken = {
                widget.field_name
                for page in document
                for widget in (page.widgets() or ())
                if widget.field_name and widget.field_type_string == "Signature"
            }
    except Exception:  # noqa: BLE001 -- the worst case is the clash pyHanko reports
        return wanted
    if wanted not in taken:
        return wanted
    number = 2
    while f"{wanted} {number}" in taken:
        number += 1
    return f"{wanted} {number}"


def _sign_bytes(
    data: bytes, request: SignatureRequest, document_password: str | None = None
) -> bytes:
    key, certificate, chain = _credentials(request.certificate, request.password)
    identity = _identity_of(certificate)
    signer = _signer(key, certificate, chain)
    field_name = _free_field_name(data, request.field_name, document_password)
    metadata = signers.PdfSignatureMetadata(
        field_name=field_name,
        reason=request.reason or None,
        location=request.location or None,
        subfilter=SigSeedSubFilter.PADES,
    )
    box: tuple[int, int, int, int] | None = None
    if request.box is not None:
        left, bottom, right, top = request.box
        box = (round(left), round(bottom), round(right), round(top))
    spec = SigFieldSpec(
        sig_field_name=field_name,
        on_page=request.page or 0,
        box=box,
    )
    visible = request.box is not None
    style = (
        TextStampStyle(
            stamp_text=stamp_text(request.reason),
            text_box_style=TextBoxStyle(font_size=STAMP_FONT_SIZE, border_width=1),
        )
        if visible
        else None
    )
    params = {"name": identity.common_name, "reason": request.reason} if visible else None
    pdf_signer = signers.PdfSigner(
        metadata, signer=signer, stamp_style=style, new_field_spec=spec
    )
    try:
        writer = IncrementalPdfFileWriter(io.BytesIO(data))
        if document_password:
            writer.encrypt(document_password)
        output = pdf_signer.sign_pdf(
            writer, bytes_reserved=RESERVED, appearance_text_params=params
        )
    except Exception as error:
        raise SigningError(
            QCoreApplication.translate("Signing", "Non riesco a firmare il documento: {0}").format(error)
        ) from error
    return output.getvalue()  # type: ignore[no-any-return]


def holds_signature(doc: pymupdf.Document, xref: int) -> bool:
    """Whether a signature widget holds a signature (a /V), on itself or its field.

    An empty signature field -- a place left for a signature to come -- has
    none, and is form content, not a signature.
    """
    kind: str = doc.xref_get_key(xref, "V")[0]
    if kind != "null":
        return True
    parent_kind, reference = doc.xref_get_key(xref, "Parent")
    if parent_kind == "xref" and reference:
        kind = doc.xref_get_key(int(reference.split()[0]), "V")[0]
        return kind != "null"
    return False


def signature_widgets(doc: pymupdf.Document) -> list[tuple[int, int]]:
    """Every signature widget of *doc*, as (page index, xref).

    Xrefs and not Widget objects: a widget keeps only a weak reference to its
    page, and the pages here go out of scope one after the other. Read from
    ``annot_xrefs()`` and the field type, not from ``page.widgets()``: that
    walk is quadratic in the widgets of a page, and a 140 KB file with ten
    thousand fields froze the window for a minute and a half when it was
    opened (reported by a pentest); this is linear.
    """
    found = []
    for index in range(len(doc)):
        page = doc[index]
        for xref, kind, *_ in page.annot_xrefs():
            if kind == ANNOT_WIDGET and _field_type(doc, xref) == "/Sig":
                found.append((index, xref))
    return found


def _field_type(doc: pymupdf.Document, xref: int) -> str | None:
    """The /FT of the field *xref* belongs to, inherited from its parents."""
    seen = set()
    while xref and xref not in seen:
        seen.add(xref)
        kind, value = doc.xref_get_key(xref, "FT")
        if kind == "name":
            return str(value)
        kind, value = doc.xref_get_key(xref, "Parent")
        xref = int(value.split()[0]) if kind == "xref" else 0
    return None


def is_signed(path: str, password: str = "") -> bool:
    """Whether *path* carries signature fields, without validating them.

    Cheap on purpose: the window asks this every time a document is opened, to
    put "firmato" in the title and to warn before a save that would drop the
    signature. The full check is :func:`read_signatures`.
    """
    # Not /SigFlags: its "SignaturesExist" bit is a hint the file writes about
    # itself, and a signed document with the bit cleared (or no /SigFlags at
    # all) read as unsigned -- the warning before a save that drops the
    # signature never came (reported by a pentest). A signature field lives
    # in the AcroForm, so a document without one is answered at once; the
    # others are answered by their fields. An EMPTY signature field -- a form
    # prepared for signing -- is not a signature: holds_signature wants a /V.
    try:
        with open_for_reading(path, password) as document:
            if not document.is_form_pdf:
                return False
            return any(
                holds_signature(document, xref)
                for _, xref in signature_widgets(document)
            )
    except Exception:  # noqa: BLE001 -- unreadable is "not signed" for our purposes
        return False


def read_signatures(
    path: str, roots: Sequence[str] = (), password: str = ""
) -> list[Signature]:
    """Validate every signature in *path*.

    *roots* are PEM files the user chose to trust. With none, signatures are
    still checked for integrity and for whether the document was modified after
    signing, but ``trusted`` stays false: Plico ships no certificate store, and
    claiming to know who a certificate belongs to would be the one lie a
    signature tool cannot afford.
    """
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise SigningError(
            QCoreApplication.translate("Signing", "Non riesco a leggere «{0}»: {1}").format(
                _name_of(path), error.strerror or error
            )
        ) from error
    context = _validation_context(roots)
    try:
        reader = PdfFileReader(io.BytesIO(data), strict=False)
    except Exception as error:
        raise SigningError(
            QCoreApplication.translate("Signing", "«{0}» non è un PDF leggibile: {1}").format(_name_of(path), error)
        ) from error
    # An encrypted file must be unlocked before pyHanko reads a single object:
    # without it ``embedded_signatures`` raised PdfKeyNotAvailableError, which
    # is no SigningError, out of the dialog -- with the right password sitting
    # in the model all along (reported by a review, reproduced).
    if reader.encrypted and reader.decrypt(password).status is AuthStatus.FAILED:
        raise SigningError(
            QCoreApplication.translate(
                "Signing", "«{0}» è protetto da una password che non apre il file."
            ).format(_name_of(path))
        )
    try:
        return [_describe(signature, context) for signature in reader.embedded_signatures]
    except SigningError:
        raise
    # pyHanko's reader raises its own types for a damaged file, and the dialog
    # needs a sentence, not a traceback.
    except Exception as error:
        raise SigningError(
            QCoreApplication.translate("Signing", "Non riesco a leggere le firme di «{0}»: {1}").format(
                _name_of(path), error
            )
        ) from error


def _describe(embedded: Any, context: ValidationContext) -> Signature:
    try:
        status = validate_pdf_signature(embedded, signer_validation_context=context)
    except Exception as error:  # noqa: BLE001 -- one broken signature must not hide the rest
        return Signature(
            field_name=str(getattr(embedded, "field_name", "")),
            identity=None,
            signed_at=None,
            algorithm="",
            covers_whole_file=False,
            intact=False,
            valid=False,
            trusted=False,
            changed=False,
            error=QCoreApplication.translate("Signing", "Firma illeggibile: {0}").format(error),
        )
    certificate = embedded.signer_cert
    covers = status.coverage == SignatureCoverageLevel.ENTIRE_FILE
    changed = not covers or status.modification_level not in (
        ModificationLevel.NONE,
        ModificationLevel.LTA_UPDATES,
    )
    return Signature(
        field_name=str(embedded.field_name),
        identity=_identity_from_der(certificate) if certificate is not None else None,
        signed_at=status.signer_reported_dt,
        algorithm=status.md_algorithm or "",
        covers_whole_file=covers,
        intact=bool(status.intact),
        valid=bool(status.valid),
        trusted=bool(status.trusted),
        changed=changed,
    )


def _validation_context(roots: Sequence[str]) -> ValidationContext:
    """A context that never goes to the network, with the roots the user gave."""
    trusted: list[asn1x509.Certificate] = []
    for root in roots:
        trusted.extend(_certificates_in(root))
    return ValidationContext(trust_roots=trusted, allow_fetching=False)


def keep_root(path: str, directory: str) -> str:
    """Copy the trusted root *path* into *directory*, and return the copy.

    What the user approved is the certificate they picked, not the path it
    happened to be read from: a path kept in the settings was read again at
    every verification, so whoever could replace that file -- a later
    download with the same name, another user in a shared folder -- chose
    who counted as a trusted signer (reported by a pentest). The copy lives
    in a directory only the user can enter, named after its SHA-256, and
    :func:`kept_root_intact` refuses it if the content no longer matches.
    """
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise SigningError(
            QCoreApplication.translate("Signing", "Non riesco a leggere «{0}»: {1}").format(
                _name_of(path), error.strerror or error
            )
        ) from error
    try:
        x509.load_pem_x509_certificates(data)
    except ValueError as error:
        raise SigningError(
            QCoreApplication.translate("Signing", "«{0}» non contiene certificati PEM.").format(_name_of(path))
        ) from error
    os.makedirs(directory, mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    kept = os.path.join(directory, hashlib.sha256(data).hexdigest() + ".pem")
    descriptor, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temporary, kept)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
    return kept


def kept_root_intact(path: str, directory: str) -> bool:
    """Whether *path* is a copy made by :func:`keep_root` and still holds it."""
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(directory):
        return False
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    return os.path.basename(path) == hashlib.sha256(data).hexdigest() + ".pem"


def _certificates_in(path: str) -> list[asn1x509.Certificate]:
    """Every certificate in a PEM file, which may well hold more than one."""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise SigningError(
            QCoreApplication.translate("Signing", "Non riesco a leggere «{0}»: {1}").format(
                _name_of(path), error.strerror or error
            )
        ) from error
    try:
        certificates = x509.load_pem_x509_certificates(data)
    except ValueError as error:
        raise SigningError(
            QCoreApplication.translate("Signing", "«{0}» non contiene certificati PEM.").format(_name_of(path))
        ) from error
    return [
        asn1x509.Certificate.load(certificate.public_bytes(Encoding.DER))
        for certificate in certificates
    ]
