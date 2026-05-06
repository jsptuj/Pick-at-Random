"""Settings: stdlib-backed env-var loader.

Reads `os.environ`, optionally pre-populated from a `.env` file by
:func:`load_dotenv`. No third-party config library is used — keeps the
dependency surface small and avoids native build steps.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path) -> dict[str, str]:
    """Parse a minimal `.env` file into a ``dict``.

    Supports::

        # comment
        KEY=value
        KEY="quoted value"

    Variable interpolation, multi-line values, and `export` prefixes are
    intentionally not supported. Existing entries in :data:`os.environ`
    are not overwritten by the caller; this function only returns the
    parsed mapping.
    """
    p = Path(path)
    if not p.is_file():
        return {}
    parsed: dict[str, str] = {}
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid .env line (missing '='): {raw_line!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if not key:
            raise ValueError(f"Invalid .env line (empty key): {raw_line!r}")
        parsed[key] = value
    return parsed


def apply_dotenv(env: dict[str, str], overlay: Mapping[str, str]) -> None:
    """Merge ``overlay`` into ``env`` without overwriting existing keys.

    The convention is "real environment wins over .env file" so that
    container deployments can override the file-based defaults.
    """
    for key, value in overlay.items():
        env.setdefault(key, value)


def _require(env: Mapping[str, str], key: str) -> str:
    try:
        value = env[key]
    except KeyError as exc:
        raise ValueError(f"Missing required environment variable: {key}") from exc
    if not value:
        raise ValueError(f"Environment variable {key} must be non-empty.")
    return value


def _optional(env: Mapping[str, str], key: str, default: str) -> str:
    value = env.get(key, default)
    return value if value else default


def _positive_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        result = float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number, got {raw!r}.") from exc
    if result <= 0:
        raise ValueError(f"{key} must be positive, got {result}.")
    return result


def _ntp_version(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        result = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be 3 or 4, got {raw!r}.") from exc
    if result not in (3, 4):
        raise ValueError(f"{key} must be 3 or 4, got {result}.")
    return result


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration assembled from environment variables.

    Construct via :meth:`from_env`; never instantiate directly with
    ad-hoc values from production code.
    """

    signature_p12_path: str
    signature_p12_password: str
    signature_field_name: str
    signature_reason: str
    input_dir: str
    output_dir: str
    ntp_server: str
    ntp_timeout_seconds: float
    ntp_version: int
    app_locale: str
    app_timezone: str
    host_hostname: str | None
    host_username: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source: Mapping[str, str] = os.environ if env is None else env
        return cls(
            signature_p12_path=_require(source, "SIGNATURE_P12_PATH"),
            signature_p12_password=_require(source, "SIGNATURE_P12_PASSWORD"),
            signature_field_name=_optional(source, "SIGNATURE_FIELD_NAME", "PickAtRandomSig1"),
            signature_reason=_require(source, "SIGNATURE_REASON"),
            input_dir=_optional(source, "INPUT_DIR", "/data/in"),
            output_dir=_optional(source, "OUTPUT_DIR", "/data/out"),
            ntp_server=_require(source, "NTP_SERVER"),
            ntp_timeout_seconds=_positive_float(source, "NTP_TIMEOUT_SECONDS", 5.0),
            ntp_version=_ntp_version(source, "NTP_VERSION", 4),
            app_locale=_optional(source, "APP_LOCALE", "sl_SI"),
            app_timezone=_optional(source, "APP_TIMEZONE", "Europe/Ljubljana"),
            host_hostname=source.get("HOST_HOSTNAME") or None,
            host_username=source.get("HOST_USERNAME") or None,
        )
