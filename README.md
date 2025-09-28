# Tax Preparer App
Closed, paid preparer software scaffold with modules for transmission, validations, print-forms, and API.

**Default filing year: 2025** (2024 remains available for backfiling through Jan 30, 2026.)

## Quick start
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.api.http:app --reload --port 8000
http://127.0.0.1:8000/docs

## API example (2025)
`ash
curl -X POST http://127.0.0.1:8000/tax/2025/compute \
  -H "Content-Type: application/json" \
  -d '{
        "taxable_income": 85000,
        "net_income": 85000,
        "personal_credit_amounts": {
          "cpp_contrib": "4034.10",
          "ei_premiums": "1077.48"
        }
      }'
`

## Reference rates (CRA 2025)
- **Federal**: brackets at ,375 / ,750 / ,882 / ,414 with blended 14.5% first-bracket rate; BPA max ,129 phased to ,538 (Finance Canada indexation notice, Nov 2024).
- **Ontario**: brackets at ,886 / ,775 / ,000 / ,000; BPA ,747; surtax on Ontario basic tax over ,710 (20%) and ,307 (+36%) (CRA 2025 Ontario payroll tables).

## Packages
- app/core: domain models, calculators, validators
- app/efile: transmission payloads, serializer, client, error map, T183, storage
- app/printout: PDF print-and-mail fallback
- app/api: FastAPI endpoints
- tests: unit and e2e
