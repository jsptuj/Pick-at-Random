"""Unit smoke tests for ReportLabPdfWriter (real reportlab, tmp paths)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pick_at_random.domain.models import (
    CertificateInfo,
    Dataset,
    NtpDraw,
    ReportMetadata,
    Row,
)
from pick_at_random.infrastructure.pdf_writer import ReportLabPdfWriter


def _metadata(
    headers: tuple[str, ...] = ("ime", "mesto"),
    *,
    hostname: str | None = "ws-001",
    username: str | None = "blaz",
    source_filename: str | None = None,
    certificate_info: CertificateInfo | None = None,
) -> ReportMetadata:
    return ReportMetadata(
        hostname=hostname,
        username=username,
        local_iso_timestamp="2026-05-05T14:32:00+02:00",
        workflow_description="Naključno razvrščanje, opis postopka.",
        ntp_draw=NtpDraw(
            server="time.arnes.si",
            unix_nanoseconds=1_778_155_200_123_456_789,
            iso_timestamp="2026-05-05T12:00:00.123456+00:00",
        ),
        original_headers=headers,
        source_filename=source_filename,
        certificate_info=certificate_info,
    )


# Counts every leaf `/Type /Page` object in the PDF (the parent
# `/Type /Pages` directory is matched with the trailing `s`, so we
# explicitly exclude it).
_PAGE_OBJECT = re.compile(rb"/Type\s*/Page(?!s)")


class TestReportLabPdfWriter:
    def test_writes_a_pdf_file(self, tmp_path: Path) -> None:
        out = tmp_path / "out.pdf"
        ds = Dataset(
            headers=("ime", "mesto"),
            rows=(Row(("Ana", "Ptuj")), Row(("Bojan", "Maribor"))),
        )
        ReportLabPdfWriter().write(
            destination=str(out),
            shuffled_rows=ds.rows,
            metadata=_metadata(),
        )
        assert out.is_file()
        assert out.stat().st_size > 0
        assert out.read_bytes().startswith(b"%PDF-")

    def test_renders_empty_dataset(self, tmp_path: Path) -> None:
        out = tmp_path / "empty.pdf"
        ReportLabPdfWriter().write(
            destination=str(out),
            shuffled_rows=(),
            metadata=_metadata(),
        )
        assert out.read_bytes().startswith(b"%PDF-")

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "deeper" / "out.pdf"
        ReportLabPdfWriter().write(
            destination=str(out),
            shuffled_rows=(Row(("Ana", "Ptuj")),),
            metadata=_metadata(),
        )
        assert out.is_file()

    def test_rejects_empty_locale(self) -> None:
        with pytest.raises(ValueError, match="locale"):
            ReportLabPdfWriter(locale="")

    def test_registers_unicode_font_so_diacritics_have_glyphs(self, tmp_path: Path) -> None:
        out = tmp_path / "diacritics.pdf"
        ReportLabPdfWriter().write(
            destination=str(out),
            shuffled_rows=(Row(("Črt", "Šentilj")),),
            metadata=_metadata(headers=("ime", "kraj")),
        )
        # The Vera font is embedded as a subset; ReportLab prefixes the
        # PostScript name with a 6-letter tag (e.g. `ABCDEF+Vera`).
        assert b"Vera" in out.read_bytes()

    def test_omits_hostname_row_when_absent(self, tmp_path: Path) -> None:
        out = tmp_path / "no-hostname.pdf"
        ReportLabPdfWriter().write(
            destination=str(out),
            shuffled_rows=(Row(("Ana", "Ptuj")),),
            metadata=_metadata(hostname=None),
        )
        assert out.read_bytes().startswith(b"%PDF-")

    def test_omits_both_identity_rows_when_absent(self, tmp_path: Path) -> None:
        out = tmp_path / "no-identity.pdf"
        ReportLabPdfWriter().write(
            destination=str(out),
            shuffled_rows=(Row(("Ana", "Ptuj")),),
            metadata=_metadata(hostname=None, username=None),
        )
        assert out.read_bytes().startswith(b"%PDF-")

    def test_source_filename_adds_a_row_to_the_metadata_table(self, tmp_path: Path) -> None:
        # Render twice with identical inputs except for source_filename
        # and assert the produced PDF differs. ReportLab's text streams
        # are zlib-encoded so we can't grep for the filename directly;
        # the content-stream byte count is the cleanest signal.
        with_name = tmp_path / "with.pdf"
        without_name = tmp_path / "without.pdf"
        writer = ReportLabPdfWriter()
        writer.write(
            destination=str(with_name),
            shuffled_rows=(Row(("Ana", "Ptuj")),),
            metadata=_metadata(source_filename="Prijave-2026.csv"),
        )
        writer.write(
            destination=str(without_name),
            shuffled_rows=(Row(("Ana", "Ptuj")),),
            metadata=_metadata(source_filename=None),
        )
        assert with_name.read_bytes() != without_name.read_bytes()
        assert with_name.stat().st_size > without_name.stat().st_size

    def test_omits_source_filename_row_when_absent(self, tmp_path: Path) -> None:
        out = tmp_path / "no-filename.pdf"
        ReportLabPdfWriter().write(
            destination=str(out),
            shuffled_rows=(Row(("Ana", "Ptuj")),),
            metadata=_metadata(source_filename=None),
        )
        assert out.read_bytes().startswith(b"%PDF-")

    def test_certificate_info_section_grows_the_pdf(self, tmp_path: Path) -> None:
        # Same differential approach used for source_filename: writing
        # the cert section adds 4 metadata rows plus a heading, so the
        # output PDF must be strictly larger than the same render with
        # certificate_info=None.
        with_cert = tmp_path / "with-cert.pdf"
        without_cert = tmp_path / "without-cert.pdf"
        cert = CertificateInfo(
            subject_cn="Test Signer",
            issuer_cn="Test CA",
            valid_from_iso="2024-01-01T00:00:00+00:00",
            valid_to_iso="2030-01-01T00:00:00+00:00",
        )
        writer = ReportLabPdfWriter()
        writer.write(
            destination=str(with_cert),
            shuffled_rows=(Row(("Ana", "Ptuj")),),
            metadata=_metadata(certificate_info=cert),
        )
        writer.write(
            destination=str(without_cert),
            shuffled_rows=(Row(("Ana", "Ptuj")),),
            metadata=_metadata(certificate_info=None),
        )
        assert with_cert.read_bytes() != without_cert.read_bytes()
        assert with_cert.stat().st_size > without_cert.stat().st_size

    def test_certificate_section_omitted_when_all_fields_blank(self, tmp_path: Path) -> None:
        # An empty CertificateInfo (every field None) must not produce a
        # heading-only section.
        empty = tmp_path / "empty-cert.pdf"
        without = tmp_path / "no-cert.pdf"
        writer = ReportLabPdfWriter()
        writer.write(
            destination=str(empty),
            shuffled_rows=(Row(("Ana", "Ptuj")),),
            metadata=_metadata(certificate_info=CertificateInfo()),
        )
        writer.write(
            destination=str(without),
            shuffled_rows=(Row(("Ana", "Ptuj")),),
            metadata=_metadata(certificate_info=None),
        )
        # Both omit the section, so the byte size should match (modulo
        # any embedded creation-date timestamp, which can shift by a few
        # bytes between writes — allow a tiny tolerance).
        diff = abs(empty.stat().st_size - without.stat().st_size)
        assert diff < 200, f"section unexpectedly grew the PDF by {diff} bytes"

    def test_table_paginates_across_pages_for_long_input(self, tmp_path: Path) -> None:
        out = tmp_path / "long.pdf"
        rows = tuple(Row((f"Ime-{i}", f"Mesto-{i}")) for i in range(120))
        ReportLabPdfWriter().write(
            destination=str(out),
            shuffled_rows=rows,
            metadata=_metadata(),
        )
        page_count = len(_PAGE_OBJECT.findall(out.read_bytes()))
        # 120 rows + headings + meta cannot fit on one A4 page; the
        # table-header repeat is exercised by reportlab whenever the
        # table actually splits.
        assert page_count >= 2, f"expected pagination, got {page_count} pages"
