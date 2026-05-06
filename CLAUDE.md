# CLAUDE.md — Pick at Random

This file gives Claude Code the context it needs to work productively on this project.

## 1. Project overview

**Pick at Random** is a Python console application that:

1. Reads a CSV file with **dynamic headers** (the column set is not known in advance).
2. Produces a **randomly ordered** version of the row list.
3. Writes the result to a **digitally signed PDF report** in **Slovenian**.

The randomization is driven by a **timestamp fetched from an official NTP server**.
The NTP timestamp serves as a tamper-evident, externally-witnessed seed for the
shuffle. The PDF records the NTP server, the raw timestamp, and the resulting
seed so that the draw is auditable: anyone replaying the same seed gets the same
order.

> **Trade-off (documented intentionally).** An NTP timestamp is not
> cryptographically unpredictable — an adversary who knows when the program ran
> can guess the seed within seconds of resolution. This is acceptable for an
> auditable, reproducible draw; it is **not** acceptable if the requirement is
> "no one, including the operator, can predict the order." If that requirement
> ever returns, swap the NTP-seeded randomizer for a `secrets.SystemRandom`
> shuffle behind the same port.

The PDF must contain:

- Computer name (hostname). Omitted when running inside a container with
  no `HOST_HOSTNAME` override.
- Username of the OS user who executed the process. Same fallback rule
  as hostname (`HOST_USERNAME` override).
- Input CSV filename (basename only — no host paths).
- Description of the randomization workflow that was used.
- Date and time of execution (local timezone, ISO 8601).
- NTP server queried, the raw NTP timestamp, and the derived integer seed.
- Signing-certificate identity: subject CN, issuer CN, valid-from,
  valid-to. Extracted from the PKCS#12 keystore at signer construction
  time and rendered before the row table.
- Original CSV headers, in order.
- The randomized rows.
- A valid digital signature embedded in the PDF.

## 2. Functional requirements

### 2.1 Input

- A single CSV file path passed as a CLI argument.
- Headers are dynamic: the application must not assume any column names.
- UTF-8 encoded; common delimiters (`,`, `;`, `\t`) auto-detected.
- Reasonable size (the app is single-shot, not a streaming service).

### 2.2 Randomization

- A **single strategy:** `ntp_seeded`. There are no other strategies; the
  algorithm is intentionally simple and auditable.
- Steps:
  1. Query the configured NTP server (env var `NTP_SERVER`, e.g.
     `pool.ntp.org` or `time.arnes.si`) using the SNTPv4 protocol.
  2. Take the returned transmit timestamp with full fractional precision and
     convert it to a 64-bit integer (nanoseconds since the Unix epoch).
  3. Use that integer as the seed for a `random.Random` instance.
  4. Run a Fisher–Yates shuffle over the rows using that seeded RNG.
- The NTP server hostname, the raw timestamp (ISO 8601 + Unix nanoseconds),
  and the derived integer seed are all written into the PDF so the draw is
  reproducible and auditable.
- If the NTP query fails (timeout, DNS error, malformed response), the run
  aborts with a Slovenian error message. There is **no fallback** to local
  time — that would defeat the point of using an external witness.
- The Slovenian description of the workflow is written into the PDF.

### 2.3 Output

- A PDF written to the **host filesystem** via a Docker bind mount
  (see §6 — Docker).
- Filename pattern: `pick-at-random_<YYYYMMDD-HHMMSS>.pdf`.
- All visible text in **Slovenian** (labels, headings, workflow description,
  footer).
- Digitally signed using a PKCS#12 (`.p12` / `.pfx`) certificate whose path
  and passphrase are read from environment variables.

### 2.4 Digital signature

- Embedded PAdES-compatible signature (preferred library: `pyhanko`).
- Signature configuration is read **only** from environment variables — never
  hard-coded, never committed.
- Required env vars (see `.env.example`):
  - `SIGNATURE_P12_PATH` — path inside the container to the `.p12` file.
  - `SIGNATURE_P12_PASSWORD` — passphrase for the `.p12` file.
  - `SIGNATURE_FIELD_NAME` — name of the signature field (default: `PickAtRandomSig1`).
  - `SIGNATURE_REASON` — Slovenian reason string shown in the signature panel.

### 2.5 Host identity

- Inside Docker `socket.gethostname()` returns the container ID and
  `getpass.getuser()` returns the in-container service user. Neither is
  useful on a report shown to humans.
- The `HostInfo` adapter therefore prefers `HOST_HOSTNAME` /
  `HOST_USERNAME` env vars (passed through by `docker-compose.yml` from
  the operator's shell), falls back to `socket.gethostname()` /
  `getpass.getuser()` only when the process is **not** running inside a
  container, and otherwise returns `None`. The PDF omits the
  corresponding row entirely rather than display a misleading value.

## 3. Non-functional requirements

- **Clean architecture / hexagonal layering.** Domain logic must not import
  I/O libraries. CSV reading, PDF writing, signing, and the NTP client live
  at the edges, behind ports.
- **Reproducible draws.** Given the same NTP timestamp, the shuffle produces
  the same order. The `TimeSource` and `Randomizer` ports let tests inject a
  fake timestamp.
- **One outbound network call:** UDP/123 to the configured NTP server. No
  other network traffic at runtime — signing uses a local PKCS#12, not a
  remote KMS. Container does **not** need general internet egress, only
  NTP.
- **Reproducible builds** via pinned `requirements.txt` and a multi-stage
  Dockerfile.
- **Slovenian locale-aware date/time** rendering (e.g. `4. maj 2026, 14:32`).

## 4. Architecture

Layered (hexagonal) structure. The `domain/` and `application/` layers are
framework-free pure Python; `infrastructure/` and `cli/` contain the adapters.

```
src/
  pick_at_random/
    __init__.py
    domain/
      __init__.py
      models.py            # Row, Dataset, ReportMetadata
      randomizer.py        # Randomizer protocol + workflow descriptions
    application/
      __init__.py
      use_cases.py         # ShuffleAndReportUseCase
      ports.py             # CsvReader, PdfWriter, Signer, Clock, HostInfo, TimeSource (Protocols)
    infrastructure/
      __init__.py
      csv_reader.py        # CsvReader implementation (csv + Sniffer)
      pdf_writer.py        # ReportLab-based PdfWriter (Slovenian labels)
      signer.py            # pyhanko-based PKCS#12 Signer
      host_info.py         # socket.gethostname + getpass.getuser
      clock.py             # SystemClock (local wall-clock for the report header)
      ntp_time_source.py   # ntplib-based TimeSource (queries NTP_SERVER)
      randomizer.py        # NtpSeededRandomizer (Fisher-Yates, seeded by NTP)
      config.py            # stdlib-based Settings (reads os.environ + .env)
    cli/
      __init__.py
      main.py              # argparse entrypoint, wires the use case
tests/
  unit/
  integration/
.env.example
.gitignore
.dockerignore
Dockerfile
docker-compose.yml
pyproject.toml
requirements.txt
requirements-dev.txt
README.md
CLAUDE.md
```

Dependency rule: arrows point inward only.
`cli` → `infrastructure` → `application` → `domain`. Nothing in `domain` or
`application` may `import` from `infrastructure` or `cli`.

## 5. Configuration (`.env` / `.env.example`)

`.env` is **never** committed. `.env.example` is committed and documents every
key the app reads. Copy `.env.example` to `.env` and fill in real values
locally.

`.env.example` should include at least:

```
# --- Digital signature ---
SIGNATURE_P12_PATH=/run/secrets/signing.p12
SIGNATURE_P12_PASSWORD=changeme
SIGNATURE_FIELD_NAME=PickAtRandomSig1
SIGNATURE_REASON=Naključno razvrščanje seznama

# --- Output ---
OUTPUT_DIR=/data/out
INPUT_DIR=/data/in

# --- Randomization (NTP-seeded) ---
# Hostname of the NTP server used as the entropy/witness source.
NTP_SERVER=time.arnes.si
# Query timeout in seconds.
NTP_TIMEOUT_SECONDS=5
# SNTP version (3 or 4).
NTP_VERSION=4

# --- Locale / formatting ---
APP_LOCALE=sl_SI
APP_TIMEZONE=Europe/Ljubljana

# --- Host identity (optional; blank => row omitted from PDF) ---
HOST_HOSTNAME=
HOST_USERNAME=
```

`.gitignore` must include at minimum:

```
.env
*.p12
*.pfx
data/
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
dist/
build/
```

## 6. Docker

The application runs through `docker compose`. The PDF output is written to
the **host filesystem** via a bind mount, not a named volume.

`docker-compose.yml` should:

- Build from the local `Dockerfile`.
- Mount `./data/in` → `/data/in` (read-only) for input CSVs.
- Mount `./data/out` → `/data/out` (read-write) for produced PDFs.
- Mount the signing certificate as a Docker secret or bind-mounted file.
- Read environment variables from `.env`.
- Use a non-root user inside the container.
- Run as a one-shot job (`restart: "no"`).

Typical invocation:

```
docker compose run --rm app /data/in/example.csv
```

`Dockerfile` should be multi-stage:

1. Builder: install build deps, compile wheels.
2. Runtime: slim Python base, copy wheels, create non-root user, set
   `WORKDIR`, `ENTRYPOINT ["python", "-m", "pick_at_random.cli.main"]`.

## 7. Development stages

Work through these stages in order. Each stage has a clear exit criterion;
do not move on until the criterion is met.

### Stage 0 — Project bootstrap
- Create the directory layout from §4.
- Write `pyproject.toml` (build-system + project metadata + tool configs for
  `ruff`, `mypy`, `pytest`).
- Pin dependencies in `requirements.txt` and `requirements-dev.txt`.
- Add `.gitignore`, `.dockerignore`, `.env.example`, empty `README.md`.
- **Exit:** `pip install -r requirements-dev.txt` succeeds in a clean venv.

### Stage 1 — Domain model
- Define `Row`, `Dataset`, `ReportMetadata`, `NtpDraw` as immutable dataclasses.
  `NtpDraw` carries the server hostname, the raw NTP timestamp, and the
  derived integer seed.
- Define the `Randomizer` protocol (takes `Dataset` + `seed: int`, returns the
  shuffled rows) and the Slovenian workflow description constant.
- 100% unit-tested with no I/O.
- **Exit:** `pytest tests/unit/domain` is green; `mypy --strict src/pick_at_random/domain` is clean.

### Stage 2 — Application use case
- Implement `ShuffleAndReportUseCase` that depends only on ports.
- Cover the happy path and edge cases (empty CSV, single row, duplicate rows)
  with fakes.
- **Exit:** `pytest tests/unit/application` is green.

### Stage 3 — Infrastructure adapters
- `CsvReader` with delimiter sniffing and UTF-8 BOM handling.
- `PdfWriter` rendering Slovenian labels, dynamic headers, hostname,
  username, timestamp, the workflow description, and the NTP draw block
  (server, timestamp, seed).
- `Signer` using `pyhanko` and the PKCS#12 from env.
- `Clock`, `HostInfo`, `Settings` (stdlib `os.environ` + a tiny `.env` parser; no third-party config library).
- `NtpTimeSource` using `ntplib`, honouring `NTP_SERVER`,
  `NTP_TIMEOUT_SECONDS`, `NTP_VERSION`. Raises a typed error on failure.
- `NtpSeededRandomizer` (the only `Randomizer` implementation).
- **Exit:** integration test produces a real signed PDF in a tmp dir and
  `pyhanko sign validate` reports a valid signature.

### Stage 4 — CLI wiring
- `argparse` entrypoint accepting `<csv_path> [--out ...] [--ntp-server ...]`.
  `--ntp-server` overrides the env value for one-off runs.
- Wires concrete adapters into the use case (composition root).
- Exits with non-zero status and a Slovenian error message on failure
  (including a clear "NTP strežnik ni dosegljiv" message).
- **Exit:** `python -m pick_at_random.cli.main sample.csv` produces a signed
  PDF locally.

### Stage 5 — Containerization
- Author the multi-stage `Dockerfile`.
- Author `docker-compose.yml` with bind mounts and non-root user.
- Verify `docker compose run --rm app /data/in/sample.csv` writes a PDF to
  `./data/out` on the host with correct ownership.
- **Exit:** the same command works on a clean checkout after only
  `cp .env.example .env` and supplying a real `.p12`.

### Stage 6 — Quality gates
- `ruff check`, `ruff format --check`, `mypy --strict`, `pytest --cov` all
  green.
- Coverage threshold: ≥ 90% for `domain` and `application`.
- Add a `Makefile` (or `tasks.py`) with `lint`, `typecheck`, `test`, `run`,
  `docker-build`, `docker-run` targets.
- **Exit:** a single `make ci` command runs every gate.

### Stage 7 — Documentation
- Write `README.md`: what it does, how to run locally, how to run via Docker,
  required env vars, sample `.p12` instructions, troubleshooting.
- Document the randomization strategies and the signature trust model.
- **Exit:** a new contributor can produce a signed PDF from a fresh clone
  using only `README.md`.

### Stage 8 — Hardening (optional, before first real use)
- Validate that the certificate's `notBefore`/`notAfter` covers "now".
- Reject CSVs larger than a configurable byte limit.
- Add a `--dry-run` flag that skips signing for smoke tests.
- Log to stderr in structured form (one JSON object per line).

## 8. Conventions for Claude

- **Language inside the code:** identifiers, comments, log messages, and
  exception messages are in **English**. Only user-facing PDF content and
  CLI error messages shown to the operator are in **Slovenian**.
- **Type hints everywhere.** `mypy --strict` must stay clean.
- **Shuffle only via the seeded `random.Random` instance** that the
  `Randomizer` is constructed with. The seed comes from the NTP draw, never
  from `time.time()`, never from a hard-coded value, never from
  `random.seed()` global state.
- **Never hard-code secrets, paths, or hostnames.** Pull them from
  `Settings` (env-backed).
- **Domain layer purity.** If you find yourself importing `csv`,
  `reportlab`, `pyhanko`, `socket`, `getpass`, `os`, or `datetime` inside
  `domain/` or `application/`, stop — that belongs behind a port.
- **Tests first for new behavior.** Add a failing unit test in
  `tests/unit/...` before implementing.
- **Small, focused commits.** One logical change per commit; commit
  messages in English, imperative mood.
- **Don't commit `.env`, `*.p12`, `*.pfx`, or anything under `data/`.**
