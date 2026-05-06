"""Unit tests for SystemClock."""

from __future__ import annotations

import re

import pytest

from pick_at_random.infrastructure.clock import SystemClock


class TestSystemClock:
    def test_now_local_iso_returns_iso8601_with_offset(self) -> None:
        clock = SystemClock("Europe/Ljubljana")
        result = clock.now_local_iso()
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$", result), result

    def test_rejects_empty_timezone(self) -> None:
        with pytest.raises(ValueError, match="timezone"):
            SystemClock("")

    def test_rejects_unknown_timezone(self) -> None:
        with pytest.raises(Exception):  # noqa: B017, PT011 - ZoneInfoNotFoundError
            SystemClock("Not/A/Real/Zone")
