# Tax App

CRA-focused toolkit for estimating personal income tax, preparing full T1
returns, and assembling/validating EFILE XML (T619/T1/T183).

---

## Repo map 🗺️


```text
repo-root/
├─ .github/workflows/        CI: Ruff, mypy, pytest, Playwright
├─ .hypothesis/constants/    Hypothesis/fuzzing configs
├─ PyPDF2/                   Local PDF helpers / patches
├─ app/                      Main application code
│  ├─ api/                   Preparer FastAPI (T1/T619/T183 HTTP API)
│  ├─ core/                  Domain models, calculators, validators
│  ├─ efile/                 XML builders, transmission client, retention logic
│  ├─ main.py                Estimator FastAPI application
│  ├─ lifespan.py            Shared startup/shutdown manager
│  └─ schemas/               CRA XSD cache (T619, T1, T183, etc.)
├─ docs/                     Operational docs (e.g. CRA suitability checklist)
├─ inbox/                    Sample inputs / wizard data
├─ scripts/                  Replay, reject scan, coverage gate, IFT mock, purge
├─ tests/                    Unit, e2e, golden XML, fuzz suites
├─ typings/                  Typing fixes / optional stubs
├─ .env.example              Example env configuration
├─ .gitignore
├─ CHANGELOG.md
├─ License                   Proprietary license (no use without permission)
├─ README.md                 ← 📍 you are here
├─ mypy.ini                  Static typing configuration
├─ pyrightconfig.json        Pyright configuration
├─ pytest.ini                Pytest configuration
├─ requirements.txt          Python dependencies
├─ user_data.example.toml    Sample estimator input
└─ user_data.toml            Default estimator input
```

Use this map as the mental “directory sign” at the repo entrance.

---

## Components

* **Estimator API** (`app/main.py`): quick personal tax estimates for annual
  slips and payroll checks.
* **Preparer API** (`app/api/http.py`): end-to-end T1 workflow including
  validation, XML assembly (T619/T1/T183), EFILE transmission helpers,
  printouts, and certification tooling.
* **Support packages**: reusable calculators, schema cache, artifact retention,
  and ingestion scripts.

### `app/` layout

```text
app/
├─ api/            Preparer FastAPI application
├─ core/           Domain models, calculators, validators
├─ efile/          XML builders, transmission client, retention logic
├─ main.py         Estimator FastAPI application
├─ lifespan.py     Shared startup/shutdown manager
└─ schemas/        CRA XSD cache (T619, T1, T183, etc.)
```

---

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

---

## Native OCR and browser prerequisites

OCR features depend on native binaries in addition to the Python packages listed
in `requirements.txt`.

* **Tesseract OCR** – install the CLI binary that matches your platform.
* **Poppler utilities** – required by `pdf2image` for PDF rasterization.

CI runners and developer workstations should install these prerequisites before
running the OCR flows so that `pytesseract` and `pdf2image` can invoke the
underlying binaries. For Playwright smoke tests, run:

```bash
playwright install
```

after `pip install -r requirements.txt` to download the supported browsers.

---

## Guided wizard (no JSON typing)

The estimator includes a prompt-driven CLI so you can answer questions without
worrying about Python syntax or JSON formatting.

```bash
python -m app.main
python -m app.main help box14
python -m app.main checklist
```

It picks up answers automatically before prompting: files passed with `--data`,
root-level `user_data.*`, then `inbox/*.toml|json|txt|csv`. Files like
`inbox/*.pdf` or `*.xlsx` are listed as reminders.

Wizard tips:

* `--profile NAME` for personal profiles under `profiles/<slug>.toml`
  (history snapshots + trash bin).
* Combine `--data PATH` with profiles; add `--quick` to revisit only required
  prompts.
* `--color {auto,always,never}` (or `--no-color`) to control colors.
* `?` at any prompt for contextual help; `help topics` for full guide list.
* `checklist` to generate a tailored document checklist.
* After review you get a diff of all changes; profiles save automatically unless
  `--no-save` is provided.

`user_data.toml` remains available for quick runs or CI. Copy
`user_data.example.toml` or drop files into `inbox/` (see `inbox/README.txt`)
when you are not using profiles.

---

## Provincial coverage

The estimator currently supports 2025 provincial tax for:

* Ontario, British Columbia, Alberta, Manitoba, Saskatchewan,
  Nova Scotia, New Brunswick, Newfoundland and Labrador,
  Prince Edward Island, Yukon, Northwest Territories, Nunavut
  (Québec handled separately).

The wizard and API accept two-letter province codes (`ON`, `BC`, `AB`, `MB`);
Ontario remains the default when omitted.

---

## Running the APIs

Open separate terminals for each API (activate `.venv` in both).

### Estimator (port 8000)

```bash
uvicorn app.main:app --reload --port 8000
```

Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Preparer (port 8001)

```bash
uvicorn app.api.http:app --reload --port 8001
```

Docs: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)

Stop any server with `Ctrl+C`.

---

## API schema updates (2025 enhancements)

* Optional slip count fields with validation:
  `slips_t4_count`, `slips_t4a_count`, `slips_t5_count`.
* RRSP aggregation via `rrsp_contrib` and `rrsp_receipts` list.
* Expanded `ReturnInput.province` support for the 2025 codes.
* `calc.line_items` now reflects combined incomes, RRSP deductions, and
  province-specific additions.

---

## Environment configuration

Key environment variables (defaults shown):

| Variable                                                  | Purpose                                       | Default                                             |
| --------------------------------------------------------- | --------------------------------------------- | --------------------------------------------------- |
| `FEATURE_EFILE_XML`                                       | Enable XML transmission flow                  | `false`                                             |
| `FEATURE_LEGACY_EFILE`                                    | Enable legacy EFILE flow                      | `false`                                             |
| `EFILE_ENV`                                               | Environment selector (`CERT`/`PROD`)          | `CERT`                                              |
| `EFILE_SOFTWARE_ID_CERT` / `EFILE_SOFTWARE_ID_PROD`       | CRA Software IDs                              | `TAXAPP-CERT`, `TAXAPP-PROD`                        |
| `EFILE_TRANSMITTER_ID_CERT` / `EFILE_TRANSMITTER_ID_PROD` | CRA Transmitter IDs                           | `900000`, `900001`                                  |
| `EFILE_ENDPOINT_CERT` / `EFILE_ENDPOINT_PROD`             | CRA endpoints                                 | `http://127.0.0.1:9000`, `https://prod-placeholder` |
| `SOFTWARE_VERSION`                                        | Application version string                    | `0.0.3`                                             |
| `T183_CRYPTO_KEY`                                         | Fernet key for encrypted T183/T2183 retention | unset                                               |
| `RETENTION_T2183_ENABLED`                                 | Toggle T2183 retention                        | `false`                                             |

Example (PowerShell):

```powershell
set FEATURE_EFILE_XML=true
set FEATURE_LEGACY_EFILE=true
set EFILE_SOFTWARE_ID_CERT=YOUR_SOFTWARE_ID
set EFILE_TRANSMITTER_ID_CERT=YOUR_TRANSMITTER_ID
set EFILE_ENDPOINT_CERT=https://cra-cert-endpoint
```

### Multipart form parsing

The `/ui` routes rely on Starlette’s multipart form parser, which requires
`python-multipart` at runtime. Refresh environments with:

```bash
pip install -r requirements.txt
```

and validate with:

```bash
python -c "import python_multipart"
```

Additional rollout guidance lives in the
`docs/efile_suitability.md#migration` notes.

---

## CRA tooling highlights

* XSD-validated T1/T183/T619 XML with `sbmt_ref_id` sequence IDs.
* Encrypted T183 (and optional T2183) storage, plus purge scripts.
* Duplicate digest detection, backoff, circuit breaker, masked logging.
* Cert helpers: `scripts/run_cert_tests.py`,
  `scripts/replay_payloads.py`, `scripts/reject_scan.py`.
* `/health` includes build metadata, feature flags, schema digests,
  and last submission ID.

---

Need help? Check the interactive docs (`/docs`) or browse `tests/unit/` for
usage examples.
