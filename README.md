# Tax App

Comprehensive CRA-focused toolkit comprising:

- **Estimator API** (`app/main.py`): quick personal tax estimates for annual slips and payroll checks.
- **Preparer API** (`app/api/http.py`): end-to-end T1 workflow including validation, XML assembly (T619/T1/T183), EFILE transmission helpers, printouts, and certification tooling.
- **Support packages**: reusable calculators, schema cache, artifact retention, and ingestion scripts.

## Project layout

```
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

```bash
cd "C:\Users\Joud2\OneDrive\Desktop\Coding\Playground\Tax_App"
python -m venv .venv
. .venv\Scripts\activate
pip install -r requirements.txt
```

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

Set vars in the terminal before launching the preparer API, e.g.:

```bash
set FEATURE_EFILE_XML=true
set EFILE_SOFTWARE_ID_CERT=YOUR_SOFTWARE_ID
set EFILE_TRANSMITTER_ID_CERT=YOUR_TRANSMITTER_ID
set EFILE_ENDPOINT_CERT=https://cra-cert-endpoint
```

## CRA tooling highlights

- **Schema validation**: XSD-validated T1/T183/T619 XML with `sbmt_ref_id` sequence IDs.
- **Artifact retention**: encrypted T183 (and optional T2183) storage, purge scripts.
- **Transmission resilience**: duplicate digest detection, exponential backoff, circuit breaker, masked logging.
- **Cert support**: `scripts/run_cert_tests.py`, `scripts/replay_payloads.py`, `scripts/reject_scan.py`.
- **Health visibility**: `/health` includes build metadata, feature flags, schema digests, and last submission ID.

## Testing

Run the full suite:

```bash
pytest
```

Golden XML fixtures live in `tests/golden/`; fuzz tests rely on Hypothesis.

## Additional docs

- [CRA EFILE Suitability Checklist](docs/efile_suitability.md)
- Scripts folder contains utilities for certification, replay, reject analysis, and the local IFT mock (`scripts/ift_mock.py`).

---

Need help? See the interactive docs (`/docs`) or open `tests/unit/` for examples.
