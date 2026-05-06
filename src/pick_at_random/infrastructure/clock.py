"""System clock adapter.

Provides the local-wall-clock ISO 8601 string written into the PDF
header. Slovenian-locale prose rendering of the same instant happens in
the PDF writer via Babel; this clock just reports a machine-readable
timestamp.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


class SystemClock:
    """Wraps :func:`datetime.now` against a configured IANA timezone."""

    def __init__(self, timezone: str) -> None:
        if not timezone:
            raise ValueError("timezone must be a non-empty IANA name.")
        self._tz = ZoneInfo(timezone)

    def now_local_iso(self) -> str:
        return datetime.now(self._tz).isoformat(timespec="seconds")
