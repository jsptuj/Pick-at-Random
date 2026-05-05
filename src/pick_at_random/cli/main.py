"""CLI composition root.

Wires concrete adapters into :class:`ShuffleAndReportUseCase` and
maps unexpected exceptions to localised Slovenian error messages
with non-zero exit codes.

Usage::

    python -m pick_at_random.cli.main <csv_path> [--out PATH] [--ntp-server HOST]

Environment variables (see ``.env.example``) are read on every run; an
optional ``.env`` file in the working directory supplies defaults that
real environment variables override.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import IO

from pick_at_random.application.ports import TimeSource
from pick_at_random.application.use_cases import (
    ShuffleAndReportRequest,
    ShuffleAndReportResult,
    ShuffleAndReportUseCase,
)
from pick_at_random.domain.randomizer import NTP_SEEDED_DESCRIPTION_SL
from pick_at_random.infrastructure.clock import SystemClock
from pick_at_random.infrastructure.config import (
    Settings,
    apply_dotenv,
    load_dotenv,
)
from pick_at_random.infrastructure.csv_reader import SniffingCsvReader
from pick_at_random.infrastructure.host_info import SystemHostInfo
from pick_at_random.infrastructure.ntp_time_source import NtpFetchError, NtpTimeSource
from pick_at_random.infrastructure.pdf_writer import ReportLabPdfWriter
from pick_at_random.infrastructure.randomizer import NtpSeededRandomizer
from pick_at_random.infrastructure.signer import (
    PyHankoSigner,
    SignerConfigError,
    SignerError,
)

EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_NTP = 2
EXIT_FILE = 3
EXIT_SIGNER_CONFIG = 4
EXIT_SIGNER_RUNTIME = 5
EXIT_VALIDATION = 6


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pick-at-random",
        description=(
            "Naključno razvrsti vrstice iz datoteke CSV in izdela "
            "digitalno podpisan PDF (slovenščina)."
        ),
    )
    parser.add_argument(
        "csv_path",
        help="Pot do vhodne datoteke CSV.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Pot do izhodne datoteke PDF. Privzeto: "
            "<OUTPUT_DIR>/pick-at-random_<YYYYMMDD-HHMMSS>.pdf"
        ),
    )
    parser.add_argument(
        "--ntp-server",
        default=None,
        help="Začasna preglasitev nastavitve NTP_SERVER.",
    )
    return parser.parse_args(argv)


def load_settings(
    base_env: Mapping[str, str] | None = None,
    *,
    dotenv_path: str | Path = ".env",
) -> Settings:
    """Read environment + optional ``.env`` and build :class:`Settings`."""
    env: dict[str, str] = dict(os.environ if base_env is None else base_env)
    apply_dotenv(env, load_dotenv(dotenv_path))
    return Settings.from_env(env)


def resolve_pdf_path(out: str | None, settings: Settings, *, now: datetime) -> str:
    if out:
        return out
    stamp = now.strftime("%Y%m%d-%H%M%S")
    return str(Path(settings.output_dir) / f"pick-at-random_{stamp}.pdf")


TimeSourceFactory = Callable[[str, int, float], TimeSource]


def build_use_case(
    settings: Settings,
    *,
    ntp_server_override: str | None = None,
    time_source_factory: TimeSourceFactory | None = None,
) -> ShuffleAndReportUseCase:
    """Compose the real adapters into the use case.

    ``time_source_factory`` is an opt-in seam for tests: if provided, it
    is called with the resolved ``ntp_server`` and the configured timeout
    / version and must return a :class:`TimeSource`. Production callers
    should leave it as ``None`` so the real :class:`NtpTimeSource` is used.
    """
    ntp_server = ntp_server_override or settings.ntp_server
    time_source: TimeSource
    if time_source_factory is None:
        time_source = NtpTimeSource(
            server=ntp_server,
            version=settings.ntp_version,
            timeout_seconds=settings.ntp_timeout_seconds,
        )
    else:
        time_source = time_source_factory(
            ntp_server, settings.ntp_version, settings.ntp_timeout_seconds
        )

    signer = PyHankoSigner(
        p12_path=settings.signature_p12_path,
        p12_password=settings.signature_p12_password,
        field_name=settings.signature_field_name,
        reason=settings.signature_reason,
        location=settings.signature_location,
        contact=settings.signature_contact,
    )
    return ShuffleAndReportUseCase(
        csv_reader=SniffingCsvReader(),
        randomizer=NtpSeededRandomizer(),
        pdf_writer=ReportLabPdfWriter(locale=settings.app_locale),
        signer=signer,
        clock=SystemClock(settings.app_timezone),
        host_info=SystemHostInfo(),
        time_source=time_source,
        workflow_description=NTP_SEEDED_DESCRIPTION_SL,
    )


def format_success_message(result: ShuffleAndReportResult) -> str:
    return (
        "Naključno razvrščanje uspešno.\n"
        f"PDF: {result.pdf_path}\n"
        f"Število vrstic: {result.row_count}\n"
        f"NTP strežnik: {result.ntp_server}\n"
        f"Seme: {result.seed}"
    )


def map_error_to_slovenian(exc: BaseException) -> tuple[str, int]:
    if isinstance(exc, NtpFetchError):
        return f"NTP strežnik ni dosegljiv: {exc}", EXIT_NTP
    if isinstance(exc, FileNotFoundError):
        return f"Datoteka ne obstaja: {exc}", EXIT_FILE
    if isinstance(exc, SignerConfigError):
        return (
            f"Napačna konfiguracija digitalnega podpisa: {exc}",
            EXIT_SIGNER_CONFIG,
        )
    if isinstance(exc, SignerError):
        return f"Digitalno podpisovanje ni uspelo: {exc}", EXIT_SIGNER_RUNTIME
    if isinstance(exc, ValueError):
        return f"Napaka v konfiguraciji ali vhodu: {exc}", EXIT_VALIDATION
    return f"Nepričakovana napaka: {exc}", EXIT_GENERIC


def _ensure_utf8_streams() -> None:
    """Best-effort switch of stdout/stderr to UTF-8 on Windows consoles.

    On Linux containers stdout is already UTF-8 and the call is a no-op.
    On Windows the default code page is cp1250/cp852 which mangles
    Slovenian diacritics; ``reconfigure`` (Python 3.7+) flips the
    streams in-place.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - non-critical hardening
                pass


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    base_env: Mapping[str, str] | None = None,
    dotenv_path: str | Path = ".env",
    time_source_factory: TimeSourceFactory | None = None,
) -> int:
    _ensure_utf8_streams()
    out_stream: IO[str] = stdout if stdout is not None else sys.stdout
    err_stream: IO[str] = stderr if stderr is not None else sys.stderr

    args = parse_args(argv)
    try:
        settings = load_settings(base_env, dotenv_path=dotenv_path)
        pdf_path = resolve_pdf_path(args.out, settings, now=datetime.now())
        use_case = build_use_case(
            settings,
            ntp_server_override=args.ntp_server,
            time_source_factory=time_source_factory,
        )
        result = use_case.execute(
            ShuffleAndReportRequest(csv_path=args.csv_path, pdf_path=pdf_path)
        )
    except Exception as exc:  # noqa: BLE001 - top-level boundary maps to exit code
        message, exit_code = map_error_to_slovenian(exc)
        print(f"Napaka: {message}", file=err_stream)
        return exit_code

    print(format_success_message(result), file=out_stream)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
