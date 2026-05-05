"""Host info adapter: hostname + login user."""

from __future__ import annotations

import getpass
import socket


class SystemHostInfo:
    """Resolves hostname and username at construction time and caches them.

    Caching avoids repeated syscalls and guarantees the PDF header and the
    in-memory ``ReportMetadata`` see the same values even if the
    environment changes between the read and the render.
    """

    def __init__(self) -> None:
        self._hostname = socket.gethostname()
        self._username = getpass.getuser()

    @property
    def hostname(self) -> str:
        return self._hostname

    @property
    def username(self) -> str:
        return self._username
