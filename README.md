# Pick at Random

Console application that reads a CSV file with dynamic headers and produces a randomly ordered, digitally signed PDF report in Slovenian. The shuffle is seeded by a timestamp fetched from a configured NTP server, so every run records an externally-witnessed seed that makes the draw reproducible and auditable.

## Run via Docker

This is the supported deployment path. PDFs are written to the host filesystem via a bind mount.

1. **Configure secrets and env vars.**
   ```
   cp .env.example .env
   # edit .env: set SIGNATURE_P12_PASSWORD and any other site-specific values
   ```
2. **Drop your PKCS#12 keystore** at `./secrets/signing.p12` (the path the default `.env` expects).
3. **Place your input CSV** under `./data/in/`, e.g. `./data/in/sample.csv`.
4. **Run a one-shot job:**
   ```
   docker compose run --rm app /data/in/sample.csv
   ```
   The signed PDF appears under `./data/out/` as `pick-at-random_<YYYYMMDD-HHMMSS>.pdf`.

Override the NTP server for a single run with `--ntp-server <host>`:
```
docker compose run --rm app /data/in/sample.csv --ntp-server time.cloudflare.com
```

## Run locally (developer mode)

```
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux/macOS
pip install -r requirements-dev.txt
pip install -e .

# Set the same env vars from .env in your shell, then:
python -m pick_at_random.cli.main path/to/input.csv
```

## Development stages and project layout

See `CLAUDE.md` for the full development plan, the architecture, the env-var contract, and the conventions that apply to contributions.
