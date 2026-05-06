"""Application use cases.

The single use case orchestrates the eight ports defined in
``ports.py`` and the :class:`Randomizer` from the domain layer. It is
pure Python and contains no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from pick_at_random.application.ports import (
    Clock,
    CsvReader,
    HostInfo,
    PdfWriter,
    Signer,
    TimeSource,
)
from pick_at_random.domain.models import ReportMetadata
from pick_at_random.domain.randomizer import Randomizer


@dataclass(frozen=True, slots=True)
class ShuffleAndReportRequest:
    """Inputs to a single run.

    ``source_filename`` is a presentational hint shown on the PDF (e.g.
    ``Prijave-2026.csv``). The CLI populates it from ``csv_path``; the
    use case does not synthesise one because the application layer must
    not import path libraries.
    """

    csv_path: str
    pdf_path: str
    source_filename: str | None = None


@dataclass(frozen=True, slots=True)
class ShuffleAndReportResult:
    """Summary of a successful run, suitable for stdout / logs."""

    pdf_path: str
    row_count: int
    seed: int
    ntp_server: str


class ShuffleAndReportUseCase:
    """Reads a CSV, fetches NTP time, shuffles, writes a PDF, and signs it.

    All collaborators are injected as ports so the use case has no direct
    dependency on infrastructure libraries. Instantiated once per run by
    the CLI composition root.
    """

    def __init__(
        self,
        *,
        csv_reader: CsvReader,
        randomizer: Randomizer,
        pdf_writer: PdfWriter,
        signer: Signer,
        clock: Clock,
        host_info: HostInfo,
        time_source: TimeSource,
        workflow_description: str,
    ) -> None:
        if not workflow_description:
            raise ValueError("workflow_description must be non-empty.")
        self._csv_reader = csv_reader
        self._randomizer = randomizer
        self._pdf_writer = pdf_writer
        self._signer = signer
        self._clock = clock
        self._host_info = host_info
        self._time_source = time_source
        self._workflow_description = workflow_description

    def execute(self, request: ShuffleAndReportRequest) -> ShuffleAndReportResult:
        dataset = self._csv_reader.read(request.csv_path)
        ntp_draw = self._time_source.fetch()
        shuffled_rows = self._randomizer.shuffle(dataset, ntp_draw.seed)

        metadata = ReportMetadata(
            hostname=self._host_info.hostname,
            username=self._host_info.username,
            local_iso_timestamp=self._clock.now_local_iso(),
            workflow_description=self._workflow_description,
            ntp_draw=ntp_draw,
            original_headers=dataset.headers,
            source_filename=request.source_filename,
            certificate_info=self._signer.certificate_info(),
        )

        self._pdf_writer.write(
            destination=request.pdf_path,
            shuffled_rows=shuffled_rows,
            metadata=metadata,
        )
        self._signer.sign(request.pdf_path)

        return ShuffleAndReportResult(
            pdf_path=request.pdf_path,
            row_count=dataset.row_count,
            seed=ntp_draw.seed,
            ntp_server=ntp_draw.server,
        )
