"""End-to-end integration test for Stage 3.

Wires the real adapters (CSV reader, PDF writer, signer, system clock,
host info, randomizer) into the application use case. The NTP source
is replaced by a fake to keep the test offline; the rest is fully real.

Stage 3 exit criterion: a real signed PDF is produced and pyhanko's
own validator reports the signature as both valid and intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from asn1crypto import pem
from asn1crypto import x509 as asn1_x509
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

from pick_at_random.application.use_cases import (
    ShuffleAndReportRequest,
    ShuffleAndReportUseCase,
)
from pick_at_random.domain.models import NtpDraw
from pick_at_random.domain.randomizer import NTP_SEEDED_DESCRIPTION_SL
from pick_at_random.infrastructure.clock import SystemClock
from pick_at_random.infrastructure.csv_reader import SniffingCsvReader
from pick_at_random.infrastructure.host_info import SystemHostInfo
from pick_at_random.infrastructure.pdf_writer import ReportLabPdfWriter
from pick_at_random.infrastructure.randomizer import NtpSeededRandomizer
from pick_at_random.infrastructure.signer import PyHankoSigner
from tests.integration.conftest import SigningKeystore


@dataclass
class _StaticTimeSource:
    """Replaces NTP with a fixed draw so the test is offline-safe."""

    def fetch(self) -> NtpDraw:
        return NtpDraw(
            server="time.test.invalid",
            unix_nanoseconds=1_778_155_200_123_456_789,
            iso_timestamp="2026-05-07T12:00:00.123456+00:00",
        )


def _write_sample_csv(path: Path) -> None:
    path.write_text(
        "ime,mesto,starost\n"
        "Ana,Ptuj,30\n"
        "Bojan,Maribor,25\n"
        "Črt,Šentilj,42\n"
        "Žana,Češča vas,38\n"
        "Edvard,Ljubljana,51\n",
        encoding="utf-8",
    )


def _trust_anchor_from_pem(pem_bytes: bytes) -> asn1_x509.Certificate:
    if pem.detect(pem_bytes):
        _, _, der_bytes = pem.unarmor(pem_bytes)
    else:
        der_bytes = pem_bytes
    return asn1_x509.Certificate.load(der_bytes)


@pytest.mark.integration
class TestEndToEnd:
    def test_certificate_info_extracted_from_keystore(
        self, signing_keystore: SigningKeystore
    ) -> None:
        signer = PyHankoSigner(
            p12_path=str(signing_keystore.p12_path),
            p12_password=signing_keystore.p12_password,
            field_name="PickAtRandomSig1",
            reason="test",
        )
        info = signer.certificate_info()

        assert info.subject_cn == "Pick at Random Self-Signed"
        assert info.issuer_cn == "Pick at Random Self-Signed"
        # Conftest builds the cert with notBefore = now - 1 hour and
        # notAfter = now + 365 days; both must be ISO 8601 strings.
        assert info.valid_from_iso is not None
        assert info.valid_to_iso is not None
        assert "T" in info.valid_from_iso
        assert "T" in info.valid_to_iso

    def test_pipeline_produces_valid_signed_pdf(
        self, tmp_path: Path, signing_keystore: SigningKeystore
    ) -> None:
        csv_path = tmp_path / "in.csv"
        pdf_path = tmp_path / "out.pdf"
        _write_sample_csv(csv_path)

        signer = PyHankoSigner(
            p12_path=str(signing_keystore.p12_path),
            p12_password=signing_keystore.p12_password,
            field_name="PickAtRandomSig1",
            reason="Naključno razvrščanje seznama",
        )
        use_case = ShuffleAndReportUseCase(
            csv_reader=SniffingCsvReader(),
            randomizer=NtpSeededRandomizer(),
            pdf_writer=ReportLabPdfWriter(locale="sl_SI"),
            signer=signer,
            clock=SystemClock("Europe/Ljubljana"),
            host_info=SystemHostInfo(in_container=False),
            time_source=_StaticTimeSource(),
            workflow_description=NTP_SEEDED_DESCRIPTION_SL,
        )

        result = use_case.execute(
            ShuffleAndReportRequest(csv_path=str(csv_path), pdf_path=str(pdf_path))
        )

        assert result.row_count == 5
        assert pdf_path.is_file()
        pdf_bytes = pdf_path.read_bytes()
        assert pdf_bytes.startswith(b"%PDF-")
        assert pdf_bytes.rstrip().endswith(b"%%EOF")

        # Validate the embedded signature against the self-signed cert.
        trust_root = _trust_anchor_from_pem(signing_keystore.cert_pem)
        vc = ValidationContext(
            trust_roots=[trust_root],
            allow_fetching=False,
            revocation_mode="soft-fail",
        )
        with pdf_path.open("rb") as inf:
            reader = PdfFileReader(inf)
            assert len(reader.embedded_signatures) == 1
            embedded = reader.embedded_signatures[0]
            status = validate_pdf_signature(embedded, signer_validation_context=vc)

        assert status.intact is True
        assert status.valid is True
        assert status.trusted is True

    def test_same_seed_produces_same_row_order_across_runs(
        self, tmp_path: Path, signing_keystore: SigningKeystore
    ) -> None:
        csv_path = tmp_path / "in.csv"
        _write_sample_csv(csv_path)

        signer = PyHankoSigner(
            p12_path=str(signing_keystore.p12_path),
            p12_password=signing_keystore.p12_password,
            field_name="PickAtRandomSig1",
            reason="Naključno razvrščanje seznama",
        )

        def _make_use_case() -> ShuffleAndReportUseCase:
            return ShuffleAndReportUseCase(
                csv_reader=SniffingCsvReader(),
                randomizer=NtpSeededRandomizer(),
                pdf_writer=ReportLabPdfWriter(locale="sl_SI"),
                signer=signer,
                clock=SystemClock("Europe/Ljubljana"),
                host_info=SystemHostInfo(in_container=False),
                time_source=_StaticTimeSource(),
                workflow_description=NTP_SEEDED_DESCRIPTION_SL,
            )

        a = _make_use_case().execute(
            ShuffleAndReportRequest(csv_path=str(csv_path), pdf_path=str(tmp_path / "a.pdf"))
        )
        b = _make_use_case().execute(
            ShuffleAndReportRequest(csv_path=str(csv_path), pdf_path=str(tmp_path / "b.pdf"))
        )
        assert a.seed == b.seed
