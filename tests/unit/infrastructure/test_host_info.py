"""Unit tests for SystemHostInfo."""

from __future__ import annotations

from pick_at_random.infrastructure.host_info import SystemHostInfo


class TestSystemHostInfo:
    def test_returns_non_empty_hostname_and_username(self) -> None:
        info = SystemHostInfo()
        assert info.hostname
        assert info.username

    def test_values_are_cached(self) -> None:
        info = SystemHostInfo()
        assert info.hostname == info.hostname
        assert info.username == info.username
