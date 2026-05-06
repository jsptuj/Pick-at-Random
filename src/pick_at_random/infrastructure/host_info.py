"""Host info adapter: hostname + login user.

Inside a container ``socket.gethostname()`` returns the container ID and
``getpass.getuser()`` returns the in-container service user — neither
identifies the operator who launched the run. This adapter therefore:

1. Prefers caller-supplied values (typically threaded in from
   ``HOST_HOSTNAME`` / ``HOST_USERNAME`` env vars set on the Docker host).
2. Falls back to ``socket`` / ``getpass`` only when the process is *not*
   running inside a Docker container.
3. Returns ``None`` otherwise, so the PDF can omit the row entirely
   rather than print a misleading container ID.
"""

from __future__ import annotations

import getpass
import socket
from pathlib import Path

_DOCKER_MARKER = Path("/.dockerenv")


def _running_in_docker() -> bool:
    return _DOCKER_MARKER.exists()


class SystemHostInfo:
    """Resolves hostname and username at construction time and caches them.

    Caching avoids repeated syscalls and guarantees the PDF header and the
    in-memory ``ReportMetadata`` see the same values even if the
    environment changes between the read and the render.
    """

    def __init__(
        self,
        *,
        host_hostname: str | None = None,
        host_username: str | None = None,
        in_container: bool | None = None,
    ) -> None:
        in_docker = _running_in_docker() if in_container is None else in_container
        self._hostname = self._resolve_hostname(host_hostname, in_docker=in_docker)
        self._username = self._resolve_username(host_username, in_docker=in_docker)

    @staticmethod
    def _resolve_hostname(override: str | None, *, in_docker: bool) -> str | None:
        if override:
            return override
        if in_docker:
            return None
        try:
            value = socket.gethostname()
        except OSError:
            return None
        return value or None

    @staticmethod
    def _resolve_username(override: str | None, *, in_docker: bool) -> str | None:
        if override:
            return override
        if in_docker:
            return None
        try:
            value = getpass.getuser()
        except (OSError, KeyError):
            return None
        return value or None

    @property
    def hostname(self) -> str | None:
        return self._hostname

    @property
    def username(self) -> str | None:
        return self._username
