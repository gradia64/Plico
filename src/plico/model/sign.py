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

from .document import open_for_reading

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
            f"Non riesco a leggere «{_name_of(path)}»: {error.strerror or error}"
        ) from error
    try:
        key, certificate, chain = pkcs12.load_key_and_certificates(
            raw, (password or "").encode()
        )
    except ValueError as error:
        raise SigningError(
            f"Password errata, oppure «{_name_of(path)}» non è un file PKCS#12."
        ) from error
    if key is None or certificate is None:
        raise SigningError(
            f"«{_name_of(path)}» non contiene una chiave privata con il suo certificato."
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
    lines = ["Firmato da %(name)s", "%(ts)s"]
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


def sign_in_place(path: str, request: SignatureRequest) -> None:
    """Sign the file at *path*, replacing it with the signed version.

    *path* is expected to be a temporary written by the save path, so an error
    halfway leaves nothing behind and the caller's own ``os.replace`` keeps its
    guarantee. The permissions are copied across for the same reason the save
    path copies them: the temporary replaces a file that had a mode.
    """
    data = Path(path).read_bytes()
    signed = _sign_bytes(data, request)
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


def _free_field_name(data: bytes, wanted: str) -> str:
    """A signature field name that nothing in *data* is already using.

    Signing an already signed document is allowed -- the window asks first and
    the second signature covers the file as it stands -- but two signatures
    cannot live in one field: pyHanko refuses to fill a field twice. Left
    alone, the second signature would fail on a document it is supposed to
    handle.
    """
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
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


def _sign_bytes(data: bytes, request: SignatureRequest) -> bytes:
    key, certificate, chain = _credentials(request.certificate, request.password)
    identity = _identity_of(certificate)
    signer = _signer(key, certificate, chain)
    field_name = _free_field_name(data, request.field_name)
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
        output = pdf_signer.sign_pdf(
            writer, bytes_reserved=RESERVED, appearance_text_params=params
        )
    except Exception as error:
        raise SigningError(f"Non riesco a firmare il documento: {error}") from error
    return output.getvalue()  # type: ignore[no-any-return]


def is_signed(path: str, password: str = "") -> bool:
    """Whether *path* carries signature fields, without validating them.

    Cheap on purpose: the window asks this every time a document is opened, to
    put "firmato" in the title and to warn before a save that would drop the
    signature. The full check is :func:`read_signatures`.
    """
    try:
        with open_for_reading(path, password) as document:
            return int(document.get_sigflags()) >= 0
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
            f"Non riesco a leggere «{_name_of(path)}»: {error.strerror or error}"
        ) from error
    context = _validation_context(roots)
    try:
        reader = PdfFileReader(io.BytesIO(data), strict=False)
    except Exception as error:
        raise SigningError(f"«{_name_of(path)}» non è un PDF leggibile: {error}") from error
    return [_describe(signature, context) for signature in reader.embedded_signatures]


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
            error=f"Firma illeggibile: {error}",
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


def _certificates_in(path: str) -> list[asn1x509.Certificate]:
    """Every certificate in a PEM file, which may well hold more than one."""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise SigningError(
            f"Non riesco a leggere «{_name_of(path)}»: {error.strerror or error}"
        ) from error
    try:
        certificates = x509.load_pem_x509_certificates(data)
    except ValueError as error:
        raise SigningError(f"«{_name_of(path)}» non contiene certificati PEM.") from error
    return [
        asn1x509.Certificate.load(certificate.public_bytes(Encoding.DER))
        for certificate in certificates
    ]
