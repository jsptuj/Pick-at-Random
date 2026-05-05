"""Unit tests for the CLI helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pick_at_random.application.use_cases import ShuffleAndReportResult
from pick_at_random.cli.main import (
    EXIT_FILE,
    EXIT_GENERIC,
    EXIT_NTP,
    EXIT_SIGNER_CONFIG,
    EXIT_SIGNER_RUNTIME,
    EXIT_VALIDATION,
    format_success_message,
    map_error_to_slovenian,
    parse_args,
    resolve_pdf_path,
)
from pick_at_random.infrastructure.config import Settings
from pick_at_random.infrastructure.ntp_time_source import NtpFetchError
from pick_at_random.infrastructure.signer import SignerConfigError, SignerError


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "signature_p12_path": "/p.p12",
        "signature_p12_password": "x",
        "signature_field_name": "F",
        "signature_reason": "r",
        "signature_location": "l",
        "signature_contact": "c",
        "input_dir": "/in",
        "output_dir": "/out",
        "ntp_server": "time.arnes.si",
        "ntp_timeout_seconds": 5.0,
        "ntp_version": 4,
        "app_locale": "sl_SI",
        "app_timezone": "Europe/Ljubljana",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestParseArgs:
    def test_csv_path_is_required(self) -> None:
        with pytest.raises(SystemExit):
            parse_args([])

    def test_minimal_invocation(self) -> None:
        args = parse_args(["sample.csv"])
        assert args.csv_path == "sample.csv"
        assert args.out is None
        assert args.ntp_server is None

    def test_full_invocation(self) -> None:
        args = parse_args(
            ["a.csv", "--out", "b.pdf", "--ntp-server", "time.example"]
        )
        assert args.csv_path == "a.csv"
        assert args.out == "b.pdf"
        assert args.ntp_server == "time.example"


class TestResolvePdfPath:
    def test_uses_explicit_out_when_given(self) -> None:
        s = _settings(output_dir="/data/out")
        result = resolve_pdf_path("/custom/path.pdf", s, now=datetime(2026, 5, 5))
        assert result == "/custom/path.pdf"

    def test_uses_timestamped_default_when_out_missing(self) -> None:
        s = _settings(output_dir="/data/out")
        result = resolve_pdf_path(
            None, s, now=datetime(2026, 5, 5, 14, 32, 7)
        )
        assert (
            result == str(Path("/data/out") / "pick-at-random_20260505-143207.pdf")
        )

    def test_empty_out_falls_back_to_default(self) -> None:
        s = _settings(output_dir="/o")
        result = resolve_pdf_path("", s, now=datetime(2026, 1, 2, 3, 4, 5))
        assert result.endswith("pick-at-random_20260102-030405.pdf")


class TestFormatSuccessMessage:
    def test_renders_all_fields_in_slovenian(self) -> None:
        result = ShuffleAndReportResult(
            pdf_path="/out/x.pdf",
            row_count=5,
            seed=1234567890123456789,
            ntp_server="time.arnes.si",
        )
        text = format_success_message(result)
        assert "Naključno razvrščanje uspešno." in text
        assert "PDF: /out/x.pdf" in text
        assert "Število vrstic: 5" in text
        assert "NTP strežnik: time.arnes.si" in text
        assert "Seme: 1234567890123456789" in text


class TestMapErrorToSlovenian:
    def test_ntp_fetch_error(self) -> None:
        msg, code = map_error_to_slovenian(NtpFetchError("timeout"))
        assert "NTP strežnik ni dosegljiv" in msg
        assert code == EXIT_NTP

    def test_file_not_found(self) -> None:
        msg, code = map_error_to_slovenian(FileNotFoundError("missing.csv"))
        assert "Datoteka ne obstaja" in msg
        assert code == EXIT_FILE

    def test_signer_config_error(self) -> None:
        msg, code = map_error_to_slovenian(SignerConfigError("bad p12"))
        assert "konfiguracija digitalnega podpisa" in msg
        assert code == EXIT_SIGNER_CONFIG

    def test_signer_runtime_error(self) -> None:
        msg, code = map_error_to_slovenian(SignerError("crash"))
        assert "Digitalno podpisovanje ni uspelo" in msg
        assert code == EXIT_SIGNER_RUNTIME

    def test_value_error(self) -> None:
        msg, code = map_error_to_slovenian(ValueError("missing var"))
        assert "Napaka v konfiguraciji ali vhodu" in msg
        assert code == EXIT_VALIDATION

    def test_generic_exception(self) -> None:
        msg, code = map_error_to_slovenian(RuntimeError("oops"))
        assert "Nepričakovana napaka" in msg
        assert code == EXIT_GENERIC
