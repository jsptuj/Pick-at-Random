# Pick at Random

Console application that reads a CSV file with dynamic headers and produces a **randomly ordered, digitally signed PDF report in Slovenian**. The shuffle is seeded by a timestamp fetched from a configured NTP server, so every run records an externally-witnessed seed that makes the draw reproducible and auditable.

- **Input:** UTF-8 CSV (`,`, `;`, or `\t` auto-detected; BOM tolerated; headers may be any column set).
- **Output:** PAdES-signed PDF at `./data/out/pick-at-random_<YYYYMMDD-HHMMSS>.pdf`.
- **Deployment:** Docker (one-shot job), or local Python.

---

## Quick start (Docker — recommended)

You need only Docker Desktop / Engine + a PKCS#12 keystore.

1. **Copy the env template:**
   ```
   cp .env.example .env
   ```
   Edit `.env` — at minimum set `SIGNATURE_P12_PASSWORD` and confirm `NTP_SERVER`.
2. **Drop your `.p12` keystore** at `./secrets/signing.p12` (this is the host path the default `.env` expects).
3. **Drop your input CSV** at `./data/in/<your-file>.csv`.
4. **Run:**
   ```
   docker compose run --rm app /data/in/<your-file>.csv
   ```

The signed PDF lands on the host at `./data/out/pick-at-random_<YYYYMMDD-HHMMSS>.pdf`.

> **Git Bash on Windows users:** prefix the command with `MSYS_NO_PATHCONV=1`, otherwise Git Bash rewrites `/data/in/...` to `C:/Program Files/Git/data/in/...`. PowerShell, cmd, and Linux/macOS shells aren't affected.

### Override the NTP server for one run

```
docker compose run --rm app /data/in/sample.csv --ntp-server time.cloudflare.com
```

---

## Quick start (local development)

```
python -m venv .venv
.venv\Scripts\activate                    # Windows PowerShell / cmd
# source .venv/bin/activate                 # Linux / macOS
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .

# Provide env vars (export them, or use python-dotenv-style .env in cwd):
python -m pick_at_random.cli.main data/in/sample.csv
```

The same `.env` file is read automatically when present in the working directory.

### Quality gates

```
python tasks.py ci         # lint + format check + mypy --strict + pytest --cov
python tasks.py test       # pytest with coverage
python tasks.py format-fix # apply ruff format in place
```

---

## Generating a self-signed `.p12` (for testing)

For real deployments, use a CA-issued certificate. For a quick smoke test, generate a self-signed PKCS#12 keystore:

```bash
python - <<'PY'
import datetime
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization.pkcs12 import serialize_key_and_certificates
from cryptography.x509.oid import NameOID

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, "SI"),
    x509.NameAttribute(NameOID.COMMON_NAME, "Pick at Random Test"),
])
now = datetime.datetime.now(datetime.UTC)
cert = (x509.CertificateBuilder()
    .subject_name(subject).issuer_name(subject)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - datetime.timedelta(hours=1))
    .not_valid_after(now + datetime.timedelta(days=365))
    .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True,
        key_encipherment=False, data_encipherment=False, key_agreement=False,
        key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .sign(key, hashes.SHA256()))
Path("secrets").mkdir(exist_ok=True)
Path("secrets/signing.p12").write_bytes(
    serialize_key_and_certificates(name=b"signer", key=key, cert=cert, cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(b"changeme")))
print("wrote secrets/signing.p12 (password: changeme)")
PY
```

Then set `SIGNATURE_P12_PASSWORD=changeme` in your `.env` and you're ready to run.

---

## Configuration (`.env`)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SIGNATURE_P12_PATH` | yes | — | Path to the PKCS#12 keystore **inside the container** (e.g. `/run/secrets/signing.p12`). |
| `SIGNATURE_P12_PASSWORD` | yes | — | Passphrase for the keystore. |
| `SIGNATURE_FIELD_NAME` | no | `PickAtRandomSig1` | Name of the signature field embedded in the PDF. |
| `SIGNATURE_REASON` | yes | — | Slovenian reason string shown in the signature panel. |
| `SIGNATURE_LOCATION` | yes | — | Signing location string. |
| `SIGNATURE_CONTACT` | yes | — | Contact info for the signer. |
| `INPUT_DIR` | no | `/data/in` | Default input directory (informational). |
| `OUTPUT_DIR` | no | `/data/out` | Where the timestamped PDF is written when `--out` is omitted. |
| `NTP_SERVER` | yes | — | Hostname of the NTP server queried to seed the shuffle. |
| `NTP_TIMEOUT_SECONDS` | no | `5` | Query timeout. |
| `NTP_VERSION` | no | `4` | SNTP protocol version (`3` or `4`). |
| `APP_LOCALE` | no | `sl_SI` | Locale used for date/time formatting in the PDF. |
| `APP_TIMEZONE` | no | `Europe/Ljubljana` | IANA timezone for the report's local timestamp. |

The CLI reads `os.environ` first; values in `.env` are layered underneath without overwriting real env vars.

---

## Randomization model

A single strategy: **NTP-seeded Fisher–Yates**.

1. The CLI fetches the current time from `NTP_SERVER` over UDP/123 (SNTPv4).
2. The transmit timestamp is converted to a 64-bit integer of nanoseconds since the Unix epoch.
3. That integer seeds a `random.Random` (Mersenne Twister), which then runs a Fisher–Yates shuffle over the rows.
4. The PDF records the **server hostname**, the **raw ISO timestamp**, and the **derived integer seed** — anyone with those three values can reproduce the exact draw.

If the NTP query fails (timeout, DNS error, malformed response), the run aborts with `Napaka: NTP strežnik ni dosegljiv: …` and exit code `2`. There is **no fallback to local time** — substituting it would defeat the external-witness property.

> **Trade-off (deliberate).** An NTP timestamp is **not** cryptographically unpredictable. An adversary who knows when the program ran can guess the seed within seconds of resolution. This is acceptable for an *auditable, reproducible* draw; it is **not** acceptable if the requirement is "no one, including the operator, can predict the order." For that workload, swap `NtpSeededRandomizer` for a `secrets.SystemRandom`-backed implementation behind the same `Randomizer` port — the rest of the pipeline doesn't change.

---

## Signature trust model

The signer is `pyhanko` driven by a local PKCS#12 keystore. It produces an embedded PAdES-compatible signature.

- **Local keys only.** No remote KMS, HSM, or signing service is contacted at runtime — the container can run without internet egress beyond the NTP query.
- **Operator-trusted root.** The `.p12` is supplied by the operator. No root certificate is bundled with this software.
- **Validation.** Anyone validating the PDF needs the signer's certificate (or its CA chain). For self-signed test certs, validators will report the signature as `intact + valid` but `untrusted` until the cert is added to the trust store.
- **Compliance scope.** This software does **not** implement long-term validation (LTV), timestamping (RFC 3161), or revocation checking. Add a `pyhanko` `TimeStamper` and a `ValidationContext` with revocation policies if your audit regime requires those — both can be plugged in without touching domain or application code.

---

## CLI reference

```
pick-at-random [--out OUT] [--ntp-server NTP_SERVER] csv_path
```

| Flag | Description |
|---|---|
| `csv_path` (positional) | Path to the input CSV file. |
| `--out PATH` | Output PDF path. Default: `${OUTPUT_DIR}/pick-at-random_<YYYYMMDD-HHMMSS>.pdf`. |
| `--ntp-server HOST` | Override `NTP_SERVER` for this run only. |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success — PDF written and signed. |
| 1 | Unexpected error. |
| 2 | NTP query failed (`Napaka: NTP strežnik ni dosegljiv: …`). |
| 3 | Input file not found (`Napaka: Datoteka ne obstaja: …`). |
| 4 | Signer configuration error — `.p12` missing, wrong password, etc. |
| 5 | Signing runtime error from pyhanko. |
| 6 | Validation error — bad env var, malformed CSV, etc. |

---

## Output structure

The signed PDF contains:

- Title: **Naključna razvrstitev**.
- Metadata block: hostname, username, local execution time (Slovenian-locale formatted via Babel, e.g. `5. maj 2026, 14:32`).
- Workflow description (the canonical Slovenian explanation of the NTP-seeded shuffle).
- NTP draw block: server, raw ISO timestamp, integer seed.
- Results table: an ordinal column (`Zap. št.`) plus the original CSV headers, with the rows in their shuffled order.
- One PAdES signature, anchored at the bottom of the document.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `getaddrinfo failed` from NTP | DNS or network egress blocked | Try `--ntp-server <hostname>` with a server reachable from your network, or open UDP/123 outbound. |
| `Failed building wheel for pydantic-core` | Old pip + missing wheel | This project no longer depends on pydantic-core. If you see it, you're on an older branch — update with `git pull` and reinstall. |
| `Napačna konfiguracija digitalnega podpisa: PKCS#12 file not found` | Wrong `SIGNATURE_P12_PATH` | The path is read **inside the container**. The default `/run/secrets/signing.p12` corresponds to host-side `./secrets/signing.p12`. Make sure the file is there. |
| `MAC verification failed` | Wrong `SIGNATURE_P12_PASSWORD` | Update the password in `.env`. |
| Slovenian characters render as `?` in CLI output (Windows) | Console code page isn't UTF-8 | The CLI reconfigures stdout to UTF-8 automatically. If you still see mangled text, run `chcp 65001` in the terminal first. |
| Container says `CSV file not found: C:/Program Files/Git/...` | Git Bash path conversion | Prefix the command with `MSYS_NO_PATHCONV=1` or use PowerShell. |
| PDF "trusted" check fails when validating self-signed | Expected — the cert isn't in any trust store | Add the cert to your trust store, or read `status.intact` and `status.valid` directly. |

---

## Project layout

```
src/pick_at_random/
  domain/         # Row, Dataset, NtpDraw, ReportMetadata, Randomizer Protocol
  application/    # Ports + ShuffleAndReportUseCase (no I/O)
  infrastructure/ # CSV reader, PDF writer, signer, NTP client, clock, host info, settings
  cli/            # argparse composition root + Slovenian error mapping
tests/
  unit/           # Per-package unit tests (domain, application, infrastructure, cli)
  integration/    # End-to-end pipeline + CLI integration tests
Dockerfile          # multi-stage builder + slim runtime, non-root user
docker-compose.yml  # bind mounts data/in (ro), data/out (rw), secrets (ro)
tasks.py            # cross-platform task runner; `python tasks.py ci`
```

Architecture rule: arrows point inward only — `cli` → `infrastructure` → `application` → `domain`. The `domain` and `application` packages import nothing from `infrastructure`, `cli`, or third-party I/O libraries.

---

## See also

- **`CLAUDE.md`** — full development plan, stage-by-stage exit criteria, conventions for contributors and AI assistants.
- **`.env.example`** — canonical list of every env var the app reads.
- **`pyproject.toml`** — pinned dependencies, `ruff` / `mypy` / `pytest` / coverage configuration.
