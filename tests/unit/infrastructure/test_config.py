"""Unit tests for Settings and the .env parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from pick_at_random.infrastructure.config import (
    Settings,
    apply_dotenv,
    load_dotenv,
)


def _full_env(**overrides: str) -> dict[str, str]:
    base = {
        "SIGNATURE_P12_PATH": "/secrets/sign.p12",
        "SIGNATURE_P12_PASSWORD": "topsecret",
        "SIGNATURE_REASON": "Naključno razvrščanje",
        "NTP_SERVER": "time.arnes.si",
    }
    base.update(overrides)
    return base


class TestSettingsFromEnv:
    def test_defaults_applied(self) -> None:
        s = Settings.from_env(_full_env())
        assert s.signature_field_name == "PickAtRandomSig1"
        assert s.input_dir == "/data/in"
        assert s.output_dir == "/data/out"
        assert s.ntp_timeout_seconds == 5.0
        assert s.ntp_version == 4
        assert s.app_locale == "sl_SI"
        assert s.app_timezone == "Europe/Ljubljana"
        assert s.host_hostname is None
        assert s.host_username is None

    def test_overrides_applied(self) -> None:
        env = _full_env(
            SIGNATURE_FIELD_NAME="OtherSig",
            INPUT_DIR="/in",
            OUTPUT_DIR="/out",
            NTP_TIMEOUT_SECONDS="2.5",
            NTP_VERSION="3",
            APP_LOCALE="en_US",
            APP_TIMEZONE="UTC",
            HOST_HOSTNAME="my-laptop",
            HOST_USERNAME="alice",
        )
        s = Settings.from_env(env)
        assert s.signature_field_name == "OtherSig"
        assert s.input_dir == "/in"
        assert s.output_dir == "/out"
        assert s.ntp_timeout_seconds == 2.5
        assert s.ntp_version == 3
        assert s.app_locale == "en_US"
        assert s.app_timezone == "UTC"
        assert s.host_hostname == "my-laptop"
        assert s.host_username == "alice"

    def test_blank_host_identity_normalises_to_none(self) -> None:
        s = Settings.from_env(_full_env(HOST_HOSTNAME="", HOST_USERNAME=""))
        assert s.host_hostname is None
        assert s.host_username is None

    @pytest.mark.parametrize(
        "missing",
        [
            "SIGNATURE_P12_PATH",
            "SIGNATURE_P12_PASSWORD",
            "SIGNATURE_REASON",
            "NTP_SERVER",
        ],
    )
    def test_missing_required_raises(self, missing: str) -> None:
        env = _full_env()
        env.pop(missing)
        with pytest.raises(ValueError, match=missing):
            Settings.from_env(env)

    @pytest.mark.parametrize(
        "missing",
        [
            "SIGNATURE_P12_PATH",
            "SIGNATURE_P12_PASSWORD",
            "SIGNATURE_REASON",
            "NTP_SERVER",
        ],
    )
    def test_empty_required_raises(self, missing: str) -> None:
        env = _full_env(**{missing: ""})
        with pytest.raises(ValueError, match=missing):
            Settings.from_env(env)

    @pytest.mark.parametrize(
        ("raw", "match"),
        [
            ("0", "positive"),
            ("-1", "positive"),
            ("abc", "number"),
        ],
    )
    def test_invalid_ntp_timeout_raises(self, raw: str, match: str) -> None:
        env = _full_env(NTP_TIMEOUT_SECONDS=raw)
        with pytest.raises(ValueError, match=match):
            Settings.from_env(env)

    @pytest.mark.parametrize("raw", ["2", "5", "abc", "-1"])
    def test_invalid_ntp_version_raises(self, raw: str) -> None:
        env = _full_env(NTP_VERSION=raw)
        with pytest.raises(ValueError, match="NTP_VERSION"):
            Settings.from_env(env)

    def test_blank_optional_falls_back_to_default(self) -> None:
        s = Settings.from_env(_full_env(NTP_TIMEOUT_SECONDS=""))
        assert s.ntp_timeout_seconds == 5.0


class TestLoadDotenv:
    def test_parses_simple_pairs(self, tmp_path: Path) -> None:
        p = tmp_path / ".env"
        p.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
        assert load_dotenv(p) == {"FOO": "bar", "BAZ": "qux"}

    def test_skips_blank_and_comment_lines(self, tmp_path: Path) -> None:
        p = tmp_path / ".env"
        p.write_text("# header\n\nA=1\n# trailing\nB=2\n", encoding="utf-8")
        assert load_dotenv(p) == {"A": "1", "B": "2"}

    def test_strips_surrounding_quotes(self, tmp_path: Path) -> None:
        p = tmp_path / ".env"
        p.write_text("A=\"hello world\"\nB='plain'\n", encoding="utf-8")
        assert load_dotenv(p) == {"A": "hello world", "B": "plain"}

    def test_returns_empty_when_missing(self, tmp_path: Path) -> None:
        assert load_dotenv(tmp_path / "nope.env") == {}

    def test_invalid_line_raises(self, tmp_path: Path) -> None:
        p = tmp_path / ".env"
        p.write_text("INVALID_LINE\n", encoding="utf-8")
        with pytest.raises(ValueError, match="="):
            load_dotenv(p)

    def test_empty_key_raises(self, tmp_path: Path) -> None:
        p = tmp_path / ".env"
        p.write_text("=value\n", encoding="utf-8")
        with pytest.raises(ValueError, match="empty key"):
            load_dotenv(p)


class TestApplyDotenv:
    def test_does_not_overwrite_existing_env(self) -> None:
        env = {"A": "from_real_env"}
        apply_dotenv(env, {"A": "from_file", "B": "from_file"})
        assert env == {"A": "from_real_env", "B": "from_file"}
