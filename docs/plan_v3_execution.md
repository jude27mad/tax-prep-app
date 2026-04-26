# Plan V3 Execution Roadmap

## Package placement note

Plan V3 packages should be top-level under `app/`:

- `app/explain/`
- `app/confidence/`
- `app/ledger/`
- `app/teefoor/`
- `app/evidence/`

Repo inspection found no existing `explain`, `confidence`, `ledger`, `teefoor`,
or `evidence` packages. The current repo already uses top-level domain packages
such as `app/api`, `app/auth`, `app/db`, `app/efile`, `app/printout`, `app/ui`,
and `app/wizard`. That convention is clearer than placing Plan V3 packages under
`app/core/`, because these features are product and orchestration layers around
the deterministic core rather than tax-year/province calculation internals.

## 1. Plan V3 docs + repo audit

Goal:

- Record Plan V3 product direction, current repo foundation, architectural
  boundaries, and implementation sequence.

Files likely touched:

- `docs/plan_v3.md`
- `docs/plan_v3_execution.md`

Tests expected:

- `python -m ruff check .`
- CLI wizard smoke:
  `python -m app.main --data tests/fixtures/user_data.toml --profile sample --quick --color never --no-save`
- Report existing pytest/mypy baseline blockers if unchanged.

Stop condition:

- Docs capture the repo audit and all Plan V3 decisions without changing runtime
  code, schemas, APIs, tests, or fixtures.

## 2. Explanation models

Goal:

- Add structured explanation contracts that can represent what the deterministic
  tax engine did, which source/evidence supports it, and what the user can verify.

Files likely touched:

- `app/explain/`
- Focused tests under `tests/unit/`

Tests expected:

- Unit tests for model validation, serialization, stable field names, and no
  dependency on AI providers.
- Existing tax calculation tests remain unchanged.

Stop condition:

- Explanation models can describe deterministic outputs without changing tax
  math or filing behavior.

## 3. Deterministic explanation engine

Goal:

- Build an explanation engine that reads `ReturnInput`, `ReturnCalc`, rule
  metadata, and app state to produce deterministic explanations.

Files likely touched:

- `app/explain/`
- `app/core/tax_years/`
- `app/core/provinces/`
- `tax_rules/`

Tests expected:

- Unit tests for income, taxable income, federal tax, provincial tax, credits,
  additions, CPP/EI status, and balance/refund explanations.
- Tests prove explanations derive from deterministic calculation output and
  rules data.

Stop condition:

- The engine explains existing deterministic calculations and does not introduce
  a second calculation path.

## 4. Read-only explanation API

Goal:

- Expose explanation output through a read-only API for current return/session
  state or a supplied return payload.

Files likely touched:

- `app/api/http.py`
- `app/main.py`
- `app/explain/`
- API tests under `tests/unit/`

Tests expected:

- API tests for successful explanations.
- Tests proving requests do not mutate profiles, drafts, documents, T183 state,
  EFILE state, or artifacts.
- Error tests for unsupported years/provinces and invalid payloads.

Stop condition:

- API consumers can request explanations, but all write actions still happen
  only through existing deterministic product endpoints.

## 5. CLI explain mode

Goal:

- Add CLI explanation mode so the permanent wizard surface can explain outcomes
  and next steps.

Files likely touched:

- `app/main.py`
- `app/wizard/`
- `app/explain/`
- CLI tests under `tests/unit/`

Tests expected:

- CLI tests for `explain` behavior with fixture data.
- Smoke tests for `--no-save`, profile loading, non-interactive runs, and help
  text.
- Regression test that explain mode does not save or mutate answers unless an
  existing explicit save path is used.

Stop condition:

- Users can get deterministic explanations in CLI without replacing the wizard
  or creating a separate calculation path.

## 6. Guided confidence primitives

Goal:

- Add deterministic primitives for current state, available actions, safe
  recommendation, and verification path.

Files likely touched:

- `app/confidence/`
- `app/ui/router.py`
- `app/wizard/`
- `app/api/http.py`

Tests expected:

- Unit tests for confidence states, action availability, recommendation
  selection, and verification messages.
- UI/API/CLI adapter tests for rendering the same primitive state without
  changing business logic.

Stop condition:

- The product can answer "what is happening, what can I do, what is safest, and
  how do I verify it" from deterministic state.

## 7. Refund waterfall

Goal:

- Explain refund or balance due as a deterministic waterfall from income,
  deductions, federal tax, provincial tax, additions, credits, withholding, and
  final balance.

Files likely touched:

- `app/explain/`
- `app/confidence/`
- `app/ui/router.py`
- `app/main.py`

Tests expected:

- Unit tests that waterfall totals reconcile to `ReturnCalc`.
- CLI/API/UI tests for refund, balance owing, and zero-balance cases.
- Regression tests for Ontario additions such as surtax and health premium.

Stop condition:

- Users can see why the refund or balance exists and which deterministic parts
  contributed to it.

## 8. Source/proof ledger

Goal:

- Add a source/proof ledger that ties calculations, inputs, documents, rules,
  generated artifacts, and verification signals together.

Files likely touched:

- `app/ledger/`
- `app/core/rules/`
- `tax_rules/`
- `app/db/models.py`
- `app/ui/slip_ingest.py`
- `app/efile/`

Tests expected:

- Unit tests for ledger record creation and serialization.
- Tests that rule citations and document provenance can be attached to
  explanations.
- Tests that ledger records do not expose raw private data when a masked or
  summarized reference is required.

Stop condition:

- Explanation and confidence surfaces can point to source/evidence records
  without inventing proof or exposing unnecessary private data.

## 9. TeeFoor contract/safety package

Goal:

- Add TeeFoor's read-only contract, safety router, and forbidden-action tests
  before any AI provider integration.

Files likely touched:

- `app/teefoor/`
- `app/explain/`
- `app/confidence/`
- `app/ledger/`
- Safety tests under `tests/unit/`

Tests expected:

- Router tests for explain, guide, source, route-to-app-action, and refuse
  outcomes.
- Tests that TeeFoor cannot calculate tax math, mutate filing data, submit,
  edit, upload/delete files, connect to CRA, pull files, apply credits, sign
  T183, transmit, or retain session-private tax context.

Stop condition:

- TeeFoor boundaries are executable and enforced by tests before provider
  planning continues.

## 10. TeeFoor Mirror lightweight skeleton

Goal:

- Add a lightweight privacy transparency surface that shows TeeFoor visibility,
  limits, and session-only behavior.

Files likely touched:

- `app/ui/router.py`
- `app/ui/templates/`
- `app/ui/static/`
- `app/teefoor/`

Tests expected:

- UI tests for Mirror visibility states.
- Tests that the Mirror does not require an AI provider and does not persist
  private session context.
- Lightweight rendering checks for older/mobile devices.

Stop condition:

- Users can see what TeeFoor can see, what it cannot do, and which actions
  remain under user control.

## 11. Evidence pack MVP

Goal:

- Generate an evidence pack that summarizes deterministic results, relevant
  inputs, source/proof ledger entries, generated artifacts, and verification
  steps.

Files likely touched:

- `app/evidence/`
- `app/ledger/`
- `app/explain/`
- `app/printout/`
- `app/efile/`
- API/UI/CLI integration points

Tests expected:

- Unit tests for evidence pack contents and redaction/masking.
- API/CLI tests for pack generation.
- Regression tests proving evidence export does not transmit or mutate a return.

Stop condition:

- A user can export proof for review without triggering filing actions or
  changing return state.

## 12. AI provider router planning/stubs only

Goal:

- Add disabled-by-default provider planning and stubs for future TeeFoor
  integration without making network calls.

Files likely touched:

- `app/teefoor/providers.py`
- `app/teefoor/`
- `app/config.py`
- Docs and tests

Tests expected:

- Tests proving provider integrations are disabled by default.
- Tests proving no network calls occur in stubs.
- Tests for explicit routing through TeeFoor safety and Mirror visibility
  contracts.

Stop condition:

- The repo has clear provider boundaries and no live AI dependency, while the
  deterministic explanation, confidence, ledger, Mirror, and evidence contracts
  remain the source of product behavior.
