"""Fake adapters used by the application unit tests.

Each fake satisfies one of the ports defined in
``pick_at_random.application.ports`` and records its calls so tests can
assert orchestration order without touching real I/O.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from pick_at_random.domain.models import Dataset, NtpDraw, ReportMetadata, Row


@dataclass
class FakeCsvReader:
    dataset: Dataset
    calls: list[str] = field(default_factory=list)

    def read(self, source: str) -> Dataset:
        self.calls.append(source)
        return self.dataset


@dataclass
class DeterministicRandomizer:
    """Real shuffle, just isolated from third-party deps for tests."""

    calls: list[tuple[int, int]] = field(default_factory=list)

    def shuffle(self, dataset: Dataset, seed: int) -> tuple[Row, ...]:
        self.calls.append((dataset.row_count, seed))
        rng = random.Random(seed)  # noqa: S311 - test fake, deterministic by design
        items = list(dataset.rows)
        rng.shuffle(items)
        return tuple(items)


@dataclass
class RecordingPdfWriter:
    calls: list[tuple[str, tuple[Row, ...], ReportMetadata]] = field(default_factory=list)

    def write(
        self,
        destination: str,
        shuffled_rows: tuple[Row, ...],
        metadata: ReportMetadata,
    ) -> None:
        self.calls.append((destination, shuffled_rows, metadata))


@dataclass
class RecordingSigner:
    calls: list[str] = field(default_factory=list)

    def sign(self, pdf_path: str) -> None:
        self.calls.append(pdf_path)


@dataclass
class FixedClock:
    iso: str = "2026-05-05T14:32:00+02:00"

    def now_local_iso(self) -> str:
        return self.iso


@dataclass
class FixedHostInfo:
    hostname: str = "ws-001"
    username: str = "blaz"


@dataclass
class FakeTimeSource:
    draw: NtpDraw = field(
        default_factory=lambda: NtpDraw(
            server="time.arnes.si",
            unix_nanoseconds=1_780_000_000_123_456_789,
            iso_timestamp="2026-05-05T12:00:00.123456+00:00",
        )
    )
    calls: int = 0

    def fetch(self) -> NtpDraw:
        self.calls += 1
        return self.draw


@dataclass
class CallOrderRecorder:
    """Shared event log used to verify the use case's orchestration order."""

    events: list[str] = field(default_factory=list)
