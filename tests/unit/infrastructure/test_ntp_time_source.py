"""Unit tests for NtpTimeSource (no real network)."""

from __future__ import annotations

from dataclasses import dataclass

import ntplib
import pytest

from pick_at_random.infrastructure.ntp_time_source import (
    NtpFetchError,
    NtpTimeSource,
)


@dataclass
class _FakeResponse:
    tx_time: float


class _FakeClient:
    def __init__(self, response: _FakeResponse | None = None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[tuple[str, int, float]] = []

    def request(
        self, host: str, version: int = 4, port: str = "ntp", timeout: float = 5.0
    ) -> ntplib.NTPStats:
        self.calls.append((host, version, timeout))
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response  # type: ignore[return-value]


class TestConstruction:
    def test_rejects_empty_server(self) -> None:
        with pytest.raises(ValueError, match="server"):
            NtpTimeSource(server="", client=_FakeClient(_FakeResponse(1.0)))

    @pytest.mark.parametrize("v", [1, 2, 5, -1])
    def test_rejects_invalid_version(self, v: int) -> None:
        with pytest.raises(ValueError, match="version"):
            NtpTimeSource(server="t", version=v, client=_FakeClient(_FakeResponse(1.0)))

    def test_rejects_non_positive_timeout(self) -> None:
        with pytest.raises(ValueError, match="timeout"):
            NtpTimeSource(
                server="t",
                timeout_seconds=0,
                client=_FakeClient(_FakeResponse(1.0)),
            )


class TestFetch:
    def test_returns_draw_with_nanoseconds_seed(self) -> None:
        from datetime import UTC, datetime

        tx_time = 1_778_155_200.123_456
        expected_iso = (
            datetime.fromtimestamp(tx_time, tz=UTC)
            .isoformat(timespec="microseconds")
        )
        client = _FakeClient(_FakeResponse(tx_time=tx_time))
        ts = NtpTimeSource(server="time.arnes.si", client=client)

        draw = ts.fetch()

        assert draw.server == "time.arnes.si"
        assert draw.unix_nanoseconds == int(round(tx_time * 1_000_000_000))
        assert draw.seed == draw.unix_nanoseconds
        assert draw.iso_timestamp == expected_iso
        assert draw.iso_timestamp.endswith("+00:00")

    def test_passes_configured_version_and_timeout_to_client(self) -> None:
        client = _FakeClient(_FakeResponse(tx_time=1_778_155_200.0))
        ts = NtpTimeSource(
            server="example.org",
            version=3,
            timeout_seconds=2.5,
            client=client,
        )
        ts.fetch()
        assert client.calls == [("example.org", 3, 2.5)]

    def test_translates_ntp_exception(self) -> None:
        client = _FakeClient(exc=ntplib.NTPException("timeout"))
        ts = NtpTimeSource(server="time.arnes.si", client=client)
        with pytest.raises(NtpFetchError, match="time.arnes.si"):
            ts.fetch()

    def test_translates_os_error(self) -> None:
        client = _FakeClient(exc=OSError("dns lookup failed"))
        ts = NtpTimeSource(server="time.arnes.si", client=client)
        with pytest.raises(NtpFetchError, match="time.arnes.si"):
            ts.fetch()

    def test_rejects_non_positive_timestamp(self) -> None:
        client = _FakeClient(_FakeResponse(tx_time=0.0))
        ts = NtpTimeSource(server="time.arnes.si", client=client)
        with pytest.raises(NtpFetchError, match="non-positive"):
            ts.fetch()
