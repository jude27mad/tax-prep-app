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
|-- app/
|   |-- api/            # Preparer FastAPI application
|   |-- core/           # Domain models, calculators, validators
|   |-- efile/          # XML builders, transmission client, retention logic
|   |-- main.py         # Estimator FastAPI application
|   |-- lifespan.py     # Shared startup/shutdown manager
|   `-- schemas/        # CRA XSD cache (T619, T1, T183, etc.)
|-- docs/               # Operational guidance (e.g., CRA suitability checklist)
|-- scripts/            # Replay, reject scan, coverage gate, IFT mock, purge jobs
|-- tests/              # Unit, e2e, golden XML, fuzz suites
`-- requirements.txt

```

## Quick start (single terminal)

```powershell
cd "C:\Users\Joud2\OneDrive\Desktop\Coding\Playground\Tax_App"
python -m venv .venv
. .venv\Scripts\activate
pip install -r requirements.txt
```

> **Note**
> Form submissions in the FastAPI apps rely on `python-multipart`, which is
> included in `requirements.txt`. Ensure your environment picks up the updated
> dependency when reinstalling requirements.

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

### API schema updates (2025 enhancements)

- **Request slip summaries**: `/prepare` and `/prepare/efile` now accept optional
  `slips_t4_count`, `slips_t4a_count`, and `slips_t5_count` fields when sending
  JSON payloads. When provided, the counts are validated against the attached
  slips and CRA's 50-slip per-type maximum to surface mismatches before filing.
- **RRSP aggregation**: RRSP contributions can be supplied as a direct
  `rrsp_contrib` amount and/or a list of `rrsp_receipts` with individual
  contribution records. The calculator consolidates both sources before applying
  deductions, and validation now enforces non-negative amounts on every receipt.
- **Expanded provincial inputs**: `ReturnInput.province` accepts the 2025 codes
  registered in the dispatch layer (`ON`, `BC`, `AB`, `MB`, `SK`, `NS`, `NB`,
  `NL`, `PE`, `YT`, `NT`, `NU`). Ontario remains the default when omitted, but
  providing the code ensures the correct calculator and additions are applied.
- **Response line items**: The `calc.line_items` payload returned from
  `/prepare` and `/prepare/efile` now reflects combined T4/T4A/T5 incomes and
  RRSP deductions, and includes province-specific addition keys (e.g.
  `ontario_surtax`, `ontario_health_premium`) when the calculator reports them.

## Environment configuration

Key environment variables (defaults shown):

| Variable | Purpose | Default |
| --- | --- | --- |
| `FEATURE_EFILE_XML` | Enable XML transmission flow | `false` |
| `FEATURE_LEGACY_EFILE` | Enable legacy EFILE flow | `false` |
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
set FEATURE_LEGACY_EFILE=true
set EFILE_SOFTWARE_ID_CERT=YOUR_SOFTWARE_ID
set EFILE_TRANSMITTER_ID_CERT=YOUR_TRANSMITTER_ID
set EFILE_ENDPOINT_CERT=https://cra-cert-endpoint
```

### Multipart form parsing

The `/ui` routes rely on Starlette's multipart form parser, which now requires
the `python-multipart` package at runtime. Refresh environments with `pip
install -r requirements.txt` (or `pip install python-multipart`) before running
the UI server and validate with `pip show python-multipart` or `python -c
"import multipart"`. Additional rollout guidance lives in the [migration
notes](docs/efile_suitability.md#migration).

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
