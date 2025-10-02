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
├── app
│   ├── api/            # Preparer FastAPI application
│   ├── core/           # Domain models, calculators, validators
│   ├── efile/          # XML builders, transmission client, retention logic
│   ├── main.py         # Estimator FastAPI application
│   ├── lifespan.py     # Shared startup/shutdown manager
│   └── schemas/        # CRA XSD cache (T619, T1, T183, etc.)
├── docs/               # Operational guidance (e.g., CRA suitability checklist)
├── scripts/            # Replay, reject scan, coverage gate, IFT mock, purge jobs
├── tests/              # Unit, e2e, golden XML, fuzz suites
└── requirements.txt
```

## Quick start (single terminal)

```powershell
cd "C:\Users\Joud2\OneDrive\Desktop\Coding\Playground\Tax_App"
python -m venv .venv
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

- Type natural shorthand such as `57k`, `$12,345`, `yes`, or `no`; the parser
  normalizes them.
- Press `?` during any prompt to open contextual help or run
  `python -m app.main help topics` for the full guide list (T4/T4A/T5 slips,
  tuition credit, Canada Workers Benefit, RRSP advice).
- Use `--data PATH` to run non-interactively or `--no-save` to leave
  `user_data.toml` untouched.
- Run `python -m app.main checklist` to generate the document checklist
  tailored to your answers.
- After the summary, changes are diffed and saved back to `user_data.toml` so
  the next run starts with your latest inputs.

`user_data.toml` ships with sample values; edit it or drop files into
`inbox/` (see `inbox/README.txt`) to preload your own slips.

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
