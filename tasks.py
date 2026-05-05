#!/usr/bin/env python
"""Cross-platform task runner for Pick at Random.

Stdlib only — no `make`, no `invoke`, no `nox`. Runs from any shell on
Windows, Linux, or macOS. Targets the current Python interpreter so it
respects the active virtualenv automatically.

Usage:

    python tasks.py <target> [<target> ...]

Targets:

    lint         ruff check (includes import order, security, style)
    format       ruff format --check (verifies formatting without writing)
    format-fix   ruff format (rewrites files in place)
    typecheck    mypy --strict over src/
    test         pytest with coverage; coverage gate enforced via pyproject.toml
    run          run the CLI against a CSV (extra args forwarded after `--`)
    docker-build docker compose build
    docker-run   docker compose run --rm app (extra args forwarded after `--`)
    ci           lint + format-check + typecheck + test (the Stage 6 gate)
    all          alias for ci
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence

PYTHON: list[str] = [sys.executable]


def _run(cmd: Sequence[str]) -> int:
    print(f"$ {shlex.join(cmd)}", flush=True)
    return subprocess.run(list(cmd), check=False).returncode


def lint() -> int:
    return _run([*PYTHON, "-m", "ruff", "check", "src", "tests"])


def format_check() -> int:
    return _run([*PYTHON, "-m", "ruff", "format", "--check", "src", "tests"])


def format_fix() -> int:
    return _run([*PYTHON, "-m", "ruff", "format", "src", "tests"])


def typecheck() -> int:
    return _run([*PYTHON, "-m", "mypy", "--strict", "src/pick_at_random"])


def test() -> int:
    return _run([*PYTHON, "-m", "pytest", "--cov=pick_at_random", "--cov-report=term"])


def run(extra: Sequence[str]) -> int:
    return _run([*PYTHON, "-m", "pick_at_random.cli.main", *extra])


def docker_build() -> int:
    return _run(["docker", "compose", "build"])


def docker_run(extra: Sequence[str]) -> int:
    return _run(["docker", "compose", "run", "--rm", "app", *extra])


def ci() -> int:
    sequence: list[tuple[str, Callable[[], int]]] = [
        ("lint", lint),
        ("format-check", format_check),
        ("typecheck", typecheck),
        ("test", test),
    ]
    failures: list[str] = []
    for name, fn in sequence:
        print(f"\n=== {name} ===", flush=True)
        if fn() != 0:
            failures.append(name)
    print()
    if failures:
        print(f"FAILED: {', '.join(failures)}", flush=True)
        return 1
    print("All gates passed.", flush=True)
    return 0


_TARGETS_NO_ARGS: dict[str, Callable[[], int]] = {
    "lint": lint,
    "format": format_check,
    "format-check": format_check,
    "format-fix": format_fix,
    "typecheck": typecheck,
    "test": test,
    "docker-build": docker_build,
    "ci": ci,
    "all": ci,
}
_TARGETS_WITH_ARGS: dict[str, Callable[[Sequence[str]], int]] = {
    "run": run,
    "docker-run": docker_run,
}


def _split_targets(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        sep = argv.index("--")
        return list(argv[:sep]), list(argv[sep + 1 :])
    return list(argv), []


def main(argv: Sequence[str]) -> int:
    targets, extra = _split_targets(argv)
    if not targets:
        print(__doc__)
        return 0

    for target in targets:
        if target in _TARGETS_NO_ARGS:
            rc = _TARGETS_NO_ARGS[target]()
        elif target in _TARGETS_WITH_ARGS:
            rc = _TARGETS_WITH_ARGS[target](extra)
        else:
            print(f"Unknown target: {target!r}", file=sys.stderr)
            print("Run with no arguments for help.", file=sys.stderr)
            return 2
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
