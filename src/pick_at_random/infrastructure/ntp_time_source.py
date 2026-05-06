"""NTP-backed TimeSource adapter.

Queries an NTP server with :class:`ntplib.NTPClient` and converts the
server's transmit timestamp into an :class:`NtpDraw`. The transmit
timestamp's float seconds are scaled to nanoseconds to produce the
64-bit integer seed used by the randomizer.

Network failures (DNS, timeout, malformed response) are translated into
:class:`NtpFetchError`. There is intentionally no fallback to local
time -- silently substituting local time would defeat the
external-witness property the workflow relies on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import ntplib

from pick_at_random.domain.models import NtpDraw


class NtpFetchError(RuntimeError):
    """Raised when the NTP query fails for any reason."""


class _NtpClient(Protocol):
    def request(
        self, host: str, version: int = ..., port: str = ..., timeout: float = ...
    ) -> ntplib.NTPStats: ...


class NtpTimeSource:
    """Fetches the current time from a configured NTP server."""

    def __init__(
        self,
        server: str,
        version: int = 4,
        timeout_seconds: float = 5.0,
        *,
        client: _NtpClient | None = None,
    ) -> None:
        if not server:
            raise ValueError("server must be a non-empty hostname.")
        if version not in (3, 4):
            raise ValueError(f"version must be 3 or 4, got {version}.")
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {timeout_seconds}.")
        self._server = server
        self._version = version
        self._timeout = timeout_seconds
        self._client: _NtpClient = client or ntplib.NTPClient()

    def fetch(self) -> NtpDraw:
        try:
            response = self._client.request(
                self._server, version=self._version, timeout=self._timeout
            )
        except (ntplib.NTPException, OSError) as exc:
            raise NtpFetchError(f"NTP query failed for {self._server!r}: {exc}") from exc

        tx_time = float(response.tx_time)
        if tx_time <= 0:
            raise NtpFetchError(f"NTP server {self._server!r} returned non-positive timestamp.")

        unix_nanoseconds = round(tx_time * 1_000_000_000)
        iso_timestamp = datetime.fromtimestamp(tx_time, tz=UTC).isoformat(timespec="microseconds")
        return NtpDraw(
            server=self._server,
            unix_nanoseconds=unix_nanoseconds,
            iso_timestamp=iso_timestamp,
        )
