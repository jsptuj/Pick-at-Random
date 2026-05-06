"""Unit tests for SystemHostInfo."""

from __future__ import annotations

from pick_at_random.infrastructure.host_info import SystemHostInfo


class TestSystemHostInfoOnHost:
    """Outside Docker the adapter falls back to socket / getpass."""

    def test_returns_non_empty_hostname_and_username(self) -> None:
        info = SystemHostInfo(in_container=False)
        assert info.hostname
        assert info.username

    def test_values_are_cached(self) -> None:
        info = SystemHostInfo(in_container=False)
        assert info.hostname == info.hostname
        assert info.username == info.username


class TestSystemHostInfoInsideContainer:
    """Inside Docker the adapter must not leak the container ID / user."""

    def test_returns_none_when_no_overrides_provided(self) -> None:
        info = SystemHostInfo(in_container=True)
        assert info.hostname is None
        assert info.username is None

    def test_uses_overrides_when_provided(self) -> None:
        info = SystemHostInfo(
            host_hostname="my-laptop",
            host_username="alice",
            in_container=True,
        )
        assert info.hostname == "my-laptop"
        assert info.username == "alice"

    def test_blank_overrides_treated_as_missing(self) -> None:
        info = SystemHostInfo(
            host_hostname="",
            host_username="",
            in_container=True,
        )
        assert info.hostname is None
        assert info.username is None


class TestOverrideWinsOutsideContainer:
    def test_explicit_override_wins_even_outside_container(self) -> None:
        info = SystemHostInfo(
            host_hostname="forced-host",
            host_username="forced-user",
            in_container=False,
        )
        assert info.hostname == "forced-host"
        assert info.username == "forced-user"
