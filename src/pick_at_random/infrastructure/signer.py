"""PyHanko-based PKCS#12 PDF signer.

Embeds a PAdES-compatible digital signature into an existing PDF in
place. The signature uses the PKCS#12 (`.p12` / `.pfx`) keystore whose
path and passphrase are read from environment-backed
:class:`~pick_at_random.infrastructure.config.Settings`.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers

from pick_at_random.domain.models import CertificateInfo


class SignerConfigError(ValueError):
    """Raised on misconfiguration (missing keystore, bad password, ...)."""


class SignerError(RuntimeError):
    """Raised on signing failure (PDF I/O, pyhanko internals, ...)."""


def _lookup_cn(name_native: object) -> str | None:
    """Return the common-name attribute from an asn1crypto-style mapping."""
    if not isinstance(name_native, dict):
        return None
    value = name_native.get("common_name")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _isoformat(value: object) -> str | None:
    """Format a datetime as ISO 8601, returning ``None`` if not a datetime."""
    if not isinstance(value, datetime):
        return None
    return value.isoformat()


class PyHankoSigner:
    """Signs a PDF in place with a PKCS#12 keystore loaded once on construction."""

    def __init__(
        self,
        *,
        p12_path: str,
        p12_password: str,
        field_name: str,
        reason: str,
    ) -> None:
        if not field_name:
            raise SignerConfigError("field_name must be non-empty.")
        if not Path(p12_path).is_file():
            raise SignerConfigError(f"PKCS#12 file not found: {p12_path}")
        try:
            # pyhanko ships py.typed but its load_pkcs12 classmethod is
            # reported as untyped under mypy --strict; the call site is
            # bounded by surrounding type-checked code, so silencing here
            # is safer than relaxing strict mode globally.
            self._signer = signers.SimpleSigner.load_pkcs12(  # type: ignore[no-untyped-call]
                pfx_file=p12_path,
                passphrase=p12_password.encode("utf-8"),
            )
        except Exception as exc:
            raise SignerConfigError(f"Failed to load PKCS#12 keystore: {exc}") from exc
        if self._signer is None:
            raise SignerConfigError(
                f"PKCS#12 keystore at {p12_path} did not yield a usable signer."
            )

        self._field_name = field_name
        self._meta = signers.PdfSignatureMetadata(
            field_name=field_name,
            reason=reason or None,
        )
        self._certificate_info = self._extract_certificate_info(self._signer.signing_cert)

    def certificate_info(self) -> CertificateInfo:
        return self._certificate_info

    @staticmethod
    def _extract_certificate_info(cert: Any) -> CertificateInfo:  # noqa: ANN401 - asn1crypto Certificate is unstubbed
        """Read subject CN, issuer CN, and validity from an asn1crypto cert.

        ``cert`` is the ``signing_cert`` exposed by ``SimpleSigner``. The
        accessors used here (`.subject.native`, `.issuer.native`, the
        validity `not_before` / `not_after` ASN.1 fields) are stable
        public API of asn1crypto, the library pyhanko re-exports.
        """
        try:
            subject_native = cert.subject.native
            issuer_native = cert.issuer.native
            validity = cert["tbs_certificate"]["validity"]
            not_before = validity["not_before"].native
            not_after = validity["not_after"].native
        except Exception:  # noqa: BLE001 - degrade gracefully on exotic certs
            return CertificateInfo()

        return CertificateInfo(
            subject_cn=_lookup_cn(subject_native),
            issuer_cn=_lookup_cn(issuer_native),
            valid_from_iso=_isoformat(not_before),
            valid_to_iso=_isoformat(not_after),
        )

    def sign(self, pdf_path: str) -> None:
        path = Path(pdf_path)
        if not path.is_file():
            raise SignerError(f"PDF file not found: {pdf_path}")

        try:
            with path.open("rb") as inf:
                writer = IncrementalPdfFileWriter(inf)
                fields.append_signature_field(
                    writer,
                    sig_field_spec=fields.SigFieldSpec(sig_field_name=self._field_name),
                )
                pdf_signer = signers.PdfSigner(self._meta, signer=self._signer)
                signed_buffer = BytesIO()
                pdf_signer.sign_pdf(writer, output=signed_buffer)
        except Exception as exc:
            raise SignerError(f"Failed to sign {pdf_path}: {exc}") from exc

        path.write_bytes(signed_buffer.getvalue())
