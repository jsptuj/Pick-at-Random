"""Integration test exercising the CLI ``main()`` end-to-end.

The real adapters are wired in; only :class:`NtpTimeSource` is replaced
via the ``time_source_factory`` injection seam so the test is offline.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pytest

from pick_at_random.cli.main import EXIT_FILE, EXIT_NTP, EXIT_OK, main
from pick_at_random.domain.models import NtpDraw
from pick_at_random.infrastructure.ntp_time_source import NtpFetchError
from tests.integration.conftest import SigningKeystore


@dataclass
class _StaticTimeSource:
    server: str

    def fetch(self) -> NtpDraw:
        return NtpDraw(
            server=self.server,
            unix_nanoseconds=1_778_155_200_123_456_789,
            iso_timestamp="2026-05-07T12:00:00.123456+00:00",
        )


def _static_factory(server: str, _version: int, _timeout: float) -> _StaticTimeSource:
    return _StaticTimeSource(server=server)


def _failing_factory(_server: str, _version: int, _timeout: float) -> object:
    class _Boom:
        def fetch(self) -> NtpDraw:  # pragma: no cover - signature only
            raise NtpFetchError("simulated outage")

    return _Boom()


def _env_for(keystore: SigningKeystore, *, output_dir: Path) -> dict[str, str]:
    return {
        "SIGNATURE_P12_PATH": str(keystore.p12_path),
        "SIGNATURE_P12_PASSWORD": keystore.p12_password,
        "SIGNATURE_REASON": "Naključno razvrščanje seznama",
        "SIGNATURE_LOCATION": "Ptuj, Slovenija",
        "SIGNATURE_CONTACT": "podpora@example.si",
        "NTP_SERVER": "time.arnes.si",
        "OUTPUT_DIR": str(output_dir),
    }


def _write_sample_csv(path: Path) -> None:
    path.write_text(
        "ime,mesto,starost\nAna,Ptuj,30\nBojan,Maribor,25\nČrt,Šentilj,42\n",
        encoding="utf-8",
    )


@pytest.mark.integration
class TestCliMain:
    def test_happy_path_writes_signed_pdf_and_returns_zero(
        self, tmp_path: Path, signing_keystore: SigningKeystore
    ) -> None:
        csv_path = tmp_path / "in.csv"
        out_pdf = tmp_path / "out.pdf"
        _write_sample_csv(csv_path)

        stdout = io.StringIO()
        stderr = io.StringIO()
        rc = main(
            [str(csv_path), "--out", str(out_pdf)],
            stdout=stdout,
            stderr=stderr,
            base_env=_env_for(signing_keystore, output_dir=tmp_path),
            dotenv_path=tmp_path / "nonexistent.env",
            time_source_factory=_static_factory,
        )

        assert rc == EXIT_OK, stderr.getvalue()
        assert stderr.getvalue() == ""
        assert out_pdf.is_file()
        assert out_pdf.read_bytes().startswith(b"%PDF-")

        out = stdout.getvalue()
        assert "Naključno razvrščanje uspešno." in out
        assert f"PDF: {out_pdf}" in out
        assert "Število vrstic: 3" in out

    def test_default_output_path_uses_output_dir_and_timestamp(
        self, tmp_path: Path, signing_keystore: SigningKeystore
    ) -> None:
        csv_path = tmp_path / "in.csv"
        out_dir = tmp_path / "outputs"
        out_dir.mkdir()
        _write_sample_csv(csv_path)

        stdout = io.StringIO()
        rc = main(
            [str(csv_path)],
            stdout=stdout,
            stderr=io.StringIO(),
            base_env=_env_for(signing_keystore, output_dir=out_dir),
            dotenv_path=tmp_path / "nonexistent.env",
            time_source_factory=_static_factory,
        )

        assert rc == EXIT_OK
        produced = list(out_dir.glob("pick-at-random_*.pdf"))
        assert len(produced) == 1
        assert produced[0].read_bytes().startswith(b"%PDF-")

    def test_ntp_server_flag_overrides_env(
        self, tmp_path: Path, signing_keystore: SigningKeystore
    ) -> None:
        csv_path = tmp_path / "in.csv"
        out_pdf = tmp_path / "out.pdf"
        _write_sample_csv(csv_path)

        stdout = io.StringIO()
        rc = main(
            [
                str(csv_path),
                "--out",
                str(out_pdf),
                "--ntp-server",
                "time.override.example",
            ],
            stdout=stdout,
            stderr=io.StringIO(),
            base_env=_env_for(signing_keystore, output_dir=tmp_path),
            dotenv_path=tmp_path / "nonexistent.env",
            time_source_factory=_static_factory,
        )

        assert rc == EXIT_OK
        assert "NTP strežnik: time.override.example" in stdout.getvalue()

    def test_missing_csv_returns_file_exit_code(
        self, tmp_path: Path, signing_keystore: SigningKeystore
    ) -> None:
        out_pdf = tmp_path / "out.pdf"

        stderr = io.StringIO()
        rc = main(
            [str(tmp_path / "missing.csv"), "--out", str(out_pdf)],
            stdout=io.StringIO(),
            stderr=stderr,
            base_env=_env_for(signing_keystore, output_dir=tmp_path),
            dotenv_path=tmp_path / "nonexistent.env",
            time_source_factory=_static_factory,
        )

        assert rc == EXIT_FILE
        err = stderr.getvalue()
        assert "Datoteka ne obstaja" in err
        assert not out_pdf.exists()

    def test_ntp_failure_returns_ntp_exit_code_and_slovenian_message(
        self, tmp_path: Path, signing_keystore: SigningKeystore
    ) -> None:
        csv_path = tmp_path / "in.csv"
        out_pdf = tmp_path / "out.pdf"
        _write_sample_csv(csv_path)

        stderr = io.StringIO()
        rc = main(
            [str(csv_path), "--out", str(out_pdf)],
            stdout=io.StringIO(),
            stderr=stderr,
            base_env=_env_for(signing_keystore, output_dir=tmp_path),
            dotenv_path=tmp_path / "nonexistent.env",
            time_source_factory=_failing_factory,
        )

        assert rc == EXIT_NTP
        assert "NTP strežnik ni dosegljiv" in stderr.getvalue()

    def test_uses_dotenv_when_real_env_lacks_keys(
        self, tmp_path: Path, signing_keystore: SigningKeystore
    ) -> None:
        csv_path = tmp_path / "in.csv"
        out_pdf = tmp_path / "out.pdf"
        _write_sample_csv(csv_path)

        dotenv = tmp_path / ".env"
        env_lines = "\n".join(
            f"{k}={v}"
            for k, v in _env_for(signing_keystore, output_dir=tmp_path).items()
        )
        dotenv.write_text(env_lines + "\n", encoding="utf-8")

        rc = main(
            [str(csv_path), "--out", str(out_pdf)],
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            base_env={},
            dotenv_path=dotenv,
            time_source_factory=_static_factory,
        )
        assert rc == EXIT_OK
        assert out_pdf.is_file()
