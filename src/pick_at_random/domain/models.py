"""Domain models for Pick at Random.

These dataclasses are framework-free and contain no I/O. They are the
canonical in-memory representation of the input CSV, the NTP-derived seed,
and the metadata embedded in the produced PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Row:
    """A single CSV record.

    Values are stored as a tuple of strings, positionally aligned with the
    enclosing :class:`Dataset`'s ``headers``. Keeping rows positional rather
    than dict-based preserves the original column order for the PDF report.
    """

    values: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.values)


@dataclass(frozen=True, slots=True)
class Dataset:
    """An ordered collection of rows that share a header schema.

    ``headers`` is the original column order from the CSV. Every row in
    ``rows`` must have the same arity as ``headers``; this invariant is
    checked on construction.
    """

    headers: tuple[str, ...]
    rows: tuple[Row, ...]

    def __post_init__(self) -> None:
        if not self.headers:
            raise ValueError("Dataset must have at least one header column.")
        expected_arity = len(self.headers)
        for index, row in enumerate(self.rows):
            if len(row) != expected_arity:
                raise ValueError(
                    f"Row {index} has {len(row)} values, "
                    f"expected {expected_arity} (matching header count)."
                )

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.headers)


@dataclass(frozen=True, slots=True)
class NtpDraw:
    """The result of querying an NTP server, used to seed the shuffle.

    Attributes:
        server: Hostname of the NTP server that was queried.
        unix_nanoseconds: Transmit timestamp in nanoseconds since the Unix
            epoch. This integer is the seed for the deterministic shuffle.
        iso_timestamp: Human-readable representation of the same instant in
            ISO 8601 form, included in the PDF for auditors.
    """

    server: str
    unix_nanoseconds: int
    iso_timestamp: str

    def __post_init__(self) -> None:
        if not self.server:
            raise ValueError("NtpDraw.server must be a non-empty hostname.")
        if self.unix_nanoseconds <= 0:
            raise ValueError(
                "NtpDraw.unix_nanoseconds must be a positive integer."
            )
        if not self.iso_timestamp:
            raise ValueError("NtpDraw.iso_timestamp must be non-empty.")

    @property
    def seed(self) -> int:
        """The integer seed handed to the Randomizer."""
        return self.unix_nanoseconds


@dataclass(frozen=True, slots=True)
class ReportMetadata:
    """Everything the PDF needs to render its informational header.

    The metadata is assembled by the application layer from injected ports
    (clock, host info, NTP time source) and then handed to the PdfWriter
    adapter. No infrastructure types leak into this dataclass.
    """

    hostname: str
    username: str
    local_iso_timestamp: str
    workflow_description: str
    ntp_draw: NtpDraw
    original_headers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.hostname:
            raise ValueError("ReportMetadata.hostname must be non-empty.")
        if not self.username:
            raise ValueError("ReportMetadata.username must be non-empty.")
        if not self.local_iso_timestamp:
            raise ValueError("ReportMetadata.local_iso_timestamp must be non-empty.")
        if not self.workflow_description:
            raise ValueError("ReportMetadata.workflow_description must be non-empty.")
        if not self.original_headers:
            raise ValueError("ReportMetadata.original_headers must be non-empty.")
