"""Ports (Protocols) consumed by the application layer.

Each Protocol defines the contract that an infrastructure adapter must
satisfy. Paths are passed as plain strings so that no I/O library
(``os``, ``pathlib``) is imported in this layer; adapters convert to
their preferred path type internally.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pick_at_random.domain.models import (
    CertificateInfo,
    Dataset,
    NtpDraw,
    ReportMetadata,
    Row,
)


@runtime_checkable
class CsvReader(Protocol):
    """Reads a CSV file into a Dataset.

    The implementation handles delimiter sniffing, BOM stripping, and
    UTF-8 decoding. The returned Dataset carries the original header order.
    """

    def read(self, source: str) -> Dataset: ...  # pragma: no cover


@runtime_checkable
class PdfWriter(Protocol):
    """Writes the unsigned PDF report.

    The PDF must contain the metadata header (hostname, username, local
    timestamp, workflow description, NTP draw block) and the shuffled rows
    rendered under the original headers.
    """

    def write(
        self,
        destination: str,
        shuffled_rows: tuple[Row, ...],
        metadata: ReportMetadata,
    ) -> None: ...  # pragma: no cover


@runtime_checkable
class Signer(Protocol):
    """Embeds a digital signature into an existing PDF in place.

    The use case also asks the signer to expose its loaded certificate's
    identity so that the same details that will appear in the PDF's
    digital-signature panel can also be printed in plain text on the
    report itself.
    """

    def sign(self, pdf_path: str) -> None: ...  # pragma: no cover

    def certificate_info(self) -> CertificateInfo: ...  # pragma: no cover


@runtime_checkable
class Clock(Protocol):
    """Returns the current local wall-clock time as an ISO 8601 string."""

    def now_local_iso(self) -> str: ...  # pragma: no cover


@runtime_checkable
class HostInfo(Protocol):
    """Exposes the OS hostname and the calling user's name.

    Either property may return ``None`` when the underlying value cannot
    be trusted — for example when the process runs inside a container
    and ``socket.gethostname()`` would only yield the container ID. The
    ``PdfWriter`` adapter omits the corresponding row from the report.
    """

    @property
    def hostname(self) -> str | None: ...  # pragma: no cover

    @property
    def username(self) -> str | None: ...  # pragma: no cover


@runtime_checkable
class TimeSource(Protocol):
    """Queries an NTP server and returns the resulting :class:`NtpDraw`.

    Implementations must raise on transport failure rather than returning
    a fallback timestamp; falling back to local time would defeat the
    "external witness" property the NTP-seeded workflow relies on.
    """

    def fetch(self) -> NtpDraw: ...  # pragma: no cover
