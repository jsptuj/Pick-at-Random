"""PyHanko-based PKCS#12 PDF signer.

Embeds a PAdES-compatible digital signature into an existing PDF in
place. The signature uses the PKCS#12 (`.p12` / `.pfx`) keystore whose
path and passphrase are read from environment-backed
:class:`~pick_at_random.infrastructure.config.Settings`.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers


class SignerConfigError(ValueError):
    """Raised on misconfiguration (missing keystore, bad password, ...)."""


class SignerError(RuntimeError):
    """Raised on signing failure (PDF I/O, pyhanko internals, ...)."""


class PyHankoSigner:
    """Signs a PDF in place with a PKCS#12 keystore loaded once on construction."""

    def __init__(
        self,
        *,
        p12_path: str,
        p12_password: str,
        field_name: str,
        reason: str,
        location: str,
        contact: str,
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
            location=location or None,
            contact_info=contact or None,
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
