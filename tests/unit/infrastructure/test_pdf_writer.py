"""Unit smoke tests for ReportLabPdfWriter (real reportlab, tmp paths)."""

from __future__ import annotations

from pathlib import Path

from pick_at_random.domain.models import Dataset, NtpDraw, ReportMetadata, Row
from pick_at_random.infrastructure.pdf_writer import ReportLabPdfWriter


def _metadata(headers: tuple[str, ...] = ("ime", "mesto")) -> ReportMetadata:
    return ReportMetadata(
        hostname="ws-001",
        username="blaz",
        local_iso_timestamp="2026-05-05T14:32:00+02:00",
        workflow_description="Naključno razvrščanje, opis postopka.",
        ntp_draw=NtpDraw(
            server="time.arnes.si",
            unix_nanoseconds=1_778_155_200_123_456_789,
            iso_timestamp="2026-05-05T12:00:00.123456+00:00",
        ),
        original_headers=headers,
    )


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
        import pytest

        with pytest.raises(ValueError, match="locale"):
            ReportLabPdfWriter(locale="")
