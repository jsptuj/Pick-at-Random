"""CSV reader adapter.

Reads a UTF-8 (optionally BOM-prefixed) CSV file into a
:class:`Dataset`. Delimiter is auto-detected with :class:`csv.Sniffer`
over a leading sample; the same sample also seeds the dialect that the
reader uses.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pick_at_random.domain.models import Dataset, Row

_SNIFF_SAMPLE_BYTES = 8192
_DEFAULT_DELIMITERS = ",;\t|"


class SniffingCsvReader:
    """Reads a CSV file using `csv.Sniffer` for delimiter detection."""

    def read(self, source: str) -> Dataset:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"CSV file not found: {source}")

        text = path.read_text(encoding="utf-8-sig")
        sample = text[:_SNIFF_SAMPLE_BYTES]
        if not sample.strip():
            raise ValueError(f"CSV file is empty: {source}")

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=_DEFAULT_DELIMITERS)
        except csv.Error:
            dialect = csv.excel

        reader = csv.reader(text.splitlines(), dialect=dialect)
        try:
            raw_headers = next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV file has no header row: {source}") from exc

        headers = tuple(h.strip() for h in raw_headers)
        if not any(headers):
            raise ValueError(f"CSV header row is empty: {source}")

        rows = tuple(Row(values=tuple(record)) for record in reader if record)
        return Dataset(headers=headers, rows=rows)
