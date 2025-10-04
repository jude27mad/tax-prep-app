# Tax App

Comprehensive CRA-focused toolkit comprising:

- **Estimator API** (`app/main.py`): quick personal tax estimates for annual slips
  and payroll checks.
- **Preparer API** (`app/api/http.py`): end-to-end T1 workflow including
  validation, XML assembly (T619/T1/T183), EFILE transmission helpers,
  printouts, and certification tooling.
- **Support packages**: reusable calculators, schema cache, artifact retention,
  and ingestion scripts.

## Project layout

```text
.
â”œâ”€â”€ app
â”‚   â”œâ”€â”€ api/            # Preparer FastAPI application
â”‚   â”œâ”€â”€ core/           # Domain models, calculators, validators
â”‚   â”œâ”€â”€ efile/          # XML builders, transmission client, retention logic
â”‚   â”œâ”€â”€ main.py         # Estimator FastAPI application
â”‚   â”œâ”€â”€ lifespan.py     # Shared startup/shutdown manager
python -m app.main --year 2025  # override the default explicitly (2026 planned)
  for restores. Manage them with:

  ```bash
  python -m app.main profiles list
  python -m app.main profiles show SAMPLE
  python -m app.main profiles switch family-2025
  python -m app.main profiles rename old new
  python -m app.main profiles delete sample
  ```
- Use `--year YYYY` to override the tax year that drives the provincial adapter.
  2025 is the default; the flag is wired for 2026 once adapters land.
- Combine `--data PATH` with `--quick` when everything is pre-filled. Adding
  `--color never --no-save` keeps output deterministic and avoids writing to
  disk during automation.
- Need a headless smoke test? The wizard skips all prompts when data is
  complete, so the CI command works locally too:

  ```bash
  python -m app.main \
    --data tests/fixtures/user_data.toml \
    --profile sample \
    --quick \
    --color never \
    --no-save
  ```
- Control colors with `--color {auto,always,never}` (or `--no-color`). Rich
  tables appear when installed; otherwise the wizard prints plain text. CI
  should stick to `--color never` so logs stay ANSI-free.

| Province / Territory | 2025 support | 2026 roadmap |
| --- | --- | --- |
| Alberta (AB) | Yes | Planned |
| British Columbia (BC) | Yes | Planned |
| Manitoba (MB) | Yes | Planned |
| New Brunswick (NB) | Yes | Planned |
| Newfoundland & Labrador (NL) | Yes | Planned |
| Nova Scotia (NS) | Yes | Planned |
| Ontario (ON) | Yes | Planned |
| Prince Edward Island (PE) | Yes | Planned |
| Saskatchewan (SK) | Yes | Planned |
| Yukon (YT) | Yes | Planned |
| Northwest Territories (NT) | Yes | Planned |
| Nunavut (NU) | Yes | Planned |
| Quebec (QC) | Separate (use Revenu Quebec) | Separate workflow |

Quebec returns require the Revenu Quebec platforms today; the CLI `--year` flag is wired for the next CRA season so the adapters can drop in as soon as they are published.
Docs: Swagger UI at <http://127.0.0.1:8000/docs> and ReDoc at
<http://127.0.0.1:8000/redoc>. The OpenAPI JSON lives at `/openapi.json` if you
prefer to explore with Postman or Bruno.
Docs: Swagger UI at <http://127.0.0.1:8001/docs> and ReDoc at
<http://127.0.0.1:8001/redoc>.
. .venv\Scripts\activate
pip install -r requirements.txt
```

## Guided wizard (no JSON typing)

The estimator now includes a prompt-driven CLI so you can answer questions
without worrying about Python syntax or JSON formatting.

```bash
python -m app.main           # start the wizard (auto-saves answers)
python -m app.main help box14
python -m app.main checklist
```

It picks up answers automatically before prompting: files passed with `--data`,
root-level `user_data.*`, then `inbox/*.toml|json|txt|csv`. Files like
`inbox/*.pdf` or `*.xlsx` are listed as reminders.

Wizard tips:

- Use `--profile NAME` to load or create a personal profile. Each profile lives
  under `profiles/<slug>.toml` with automatic history snapshots and a trash bin
  for restores. Manage them with `python -m app.main profiles
  list|show|switch|rename|delete|restore`.
- Combine `--data PATH` with profiles to preload answers from files; add
  `--quick` to revisit only the required prompts when everything else is filled
  in already.
- Control colors with `--color {auto,always,never}` (or `--no-color`). If Rich
  is installed the wizard renders tables; otherwise it falls back to plain
  text.
- Type `?` at any prompt for contextual help or run `python -m app.main help
  topics` for the full guide list (T4/T4A/T5 slips, tuition credit, Canada
  Workers Benefit, RRSP advice).
- Run `python -m app.main checklist` to generate the document checklist
  tailored to your answers.
- After the review screen you get a diff of all changes. Profiles save
  automatically unless you pass `--no-save`; without a profile the wizard
  still updates `user_data.toml` for backwards compatibility.

`user_data.toml` remains available for quick runs or CI. Copy
`user_data.example.toml` or drop files into `inbox/` (see `inbox/README.txt`)
when you are not using profiles.

## Provincial coverage

The estimator currently supports 2025 provincial tax for Ontario, British Columbia, Alberta, Manitoba, Saskatchewan, Nova Scotia, New Brunswick, Newfoundland and Labrador, Prince Edward Island, Yukon, Northwest Territories, and Nunavut (Québec handled separately). The wizard and API accept two-letter province codes (`province=ON`, `BC`, `AB`, `MB`); more provinces will be added in upcoming phases.

## Running the APIs

Open separate terminals for each API (activate `.venv` in both).

### Estimator (port 8000)

```bash
uvicorn app.main:app --reload --port 8000
```

Docs: <http://127.0.0.1:8000/docs>

### Preparer (port 8001)

```bash
uvicorn app.api.http:app --reload --port 8001
```

Docs: <http://127.0.0.1:8001/docs>

Stop any server with `Ctrl+C`.

## Environment configuration

Key environment variables (defaults shown):

| Variable | Purpose | Default |
| --- | --- | --- |
| `FEATURE_EFILE_XML` | Enable XML transmission flow | `false` |
| `EFILE_ENV` | Environment selector (`CERT`/`PROD`) | `CERT` |
| `EFILE_SOFTWARE_ID_CERT` / `EFILE_SOFTWARE_ID_PROD` | CRA Software IDs | `TAXAPP-CERT`, `TAXAPP-PROD` |
| `EFILE_TRANSMITTER_ID_CERT` / `EFILE_TRANSMITTER_ID_PROD` | CRA Transmitter IDs | `900000`, `900001` |
| `EFILE_ENDPOINT_CERT` / `EFILE_ENDPOINT_PROD` | CRA endpoints | `http://127.0.0.1:9000`, `https://prod-placeholder` |
| `SOFTWARE_VERSION` | Application version string | `0.0.3` |
| `T183_CRYPTO_KEY` | Optional Fernet key for encrypted T183/T2183 retention | unset |
| `RETENTION_T2183_ENABLED` | Toggle T2183 retention | `false` |

Set variables in the terminal before launching the preparer API, for example:

```powershell
set FEATURE_EFILE_XML=true
set EFILE_SOFTWARE_ID_CERT=YOUR_SOFTWARE_ID
set EFILE_TRANSMITTER_ID_CERT=YOUR_TRANSMITTER_ID
set EFILE_ENDPOINT_CERT=https://cra-cert-endpoint
```

## CRA tooling highlights

- **Schema validation**: XSD-validated T1/T183/T619 XML with `sbmt_ref_id`
  sequence IDs.
- **Artifact retention**: encrypted T183 (and optional T2183) storage, purge
  scripts.
- **Transmission resilience**: duplicate digest detection, exponential
  backoff, circuit breaker, masked logging.
- **Cert support**: `scripts/run_cert_tests.py`, `scripts/replay_payloads.py`,
  `scripts/reject_scan.py`.
- **Health visibility**: `/health` includes build metadata, feature flags,
  schema digests, and last submission ID.

## Testing

Run the full suite:

```bash
pytest
```

Golden XML fixtures live in `tests/golden/`; fuzz tests rely on Hypothesis.

## Additional docs

- [CRA EFILE Suitability Checklist](docs/efile_suitability.md)
- Scripts folder contains utilities for certification, replay, reject analysis,
  and the local IFT mock (`scripts/ift_mock.py`).

---

Need help? See the interactive docs (`/docs`) or open `tests/unit/` for
examples.
