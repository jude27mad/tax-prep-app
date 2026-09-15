# Plan V3 Execution Roadmap

> **Authoritative execution order and status.** This document replaces the old
> numbered sequence, not the product vision in [`plan_v3.md`](plan_v3.md).
> [`filing_channels.md`](filing_channels.md) remains authoritative for filing
> boundaries, including **NO CRA PROTOCOL ASSUMPTIONS**. Consumer filing is
> NETFILE; existing EFILE-shaped code is not a consumer implementation.
>
> **Audit baseline: 2026-09-15, main `32d9f66`.** The foundation contracts are
> present; calculation completeness and a working integrated consumer flow are
> not established. The next implementation is **R1**, followed by **C1**, not
> the explanation engine. This roadmap correction changes documentation only.

## How to use this roadmap

- Use the stable IDs below in PR titles and status updates. Old “phase 3” or
  “plan PR 8” labels are historical references, not GitHub PR numbers or the
  current execution order. Foundation “plan PR 8 / F12” means prior-state
  **contracts**, not completion of the calculations that consume them.
- Keep product doctrine in `plan_v3.md`, execution order/status here, and filing
  constraints in `filing_channels.md`. Do not maintain a second active sequence
  in an untracked local plan. Bring any additional agreed scope into this
  document explicitly before relying on it; this audit does not reconstruct
  the full historical off-repo plan.
- Implement one reviewable slice at a time. Each implementation PR updates its
  row with the merged commit, tests run, remaining gaps, and next ID. Do not mark
  work complete solely because models exist, a route is registered, or CI is green.
- “Complete” means the stated acceptance tests pass for a documented supported
  case, with rule/reference evidence. “Blocked” names the missing evidence or
  decision. Estimates and unsupported cases must not be presented as filing-ready.
- Maintenance remains separate from feature progress. Dependency PRs #97 and
  #109 are intentionally left out of this work; do not merge them as part of it.

## Verified baseline

| Work | Evidence on audited main | Status and limit |
| --- | --- | --- |
| Product/filing docs and explanation models (old phases 1–2) | `docs/`; `app/explain/models.py`; `tests/unit/test_explain_models.py` | Landed; no explanation engine yet |
| Income-line architecture (historical foundation PR 4) | `2a2ae8f`; `app/core/lines.py`; `tests/unit/test_line_architecture.py` | Landed; output structure is not complete tax coverage |
| Withholding and signed refund/balance (foundation PR 5) | `e530066`; `tests/unit/test_withholding_and_refund.py` | Landed; missing credits/repayments still affect the final result |
| Shared estimator computation (foundation PR 6) | `847abe1`, `5c8719f`; `tests/unit/test_single_calculation_path.py` | Landed; keep one tax calculation path |
| T4E, T5007, RC210 models (foundation PR 7) | `105ccd4`, `0fd7c5e`; `tests/unit/test_benchmark_slip_models.py` | T4E/T5007 income plumbing exists; RC210 is not consumed by calculation |
| Prior balances and limits (foundation PR 8 / F12) | `14441c4`, `5048bc8`; `tests/unit/test_prior_tax_state.py` | Contracts/provenance exist; computation deliberately ignores them today |
| Jurisdiction dispatch | `app/core/provinces/__init__.py`, `dispatch_2024.py` | 2025: 12 registrations, excluding QC; 2024: 9, also excluding AB/BC/MB. Registration is not verified filing coverage |
| Security, ingestion, performance and CI cleanup | Main through `32d9f66` | Landed maintenance; not evidence of engine or certification completion |

Specific open gaps verified in the code:

- Both year-specific `compute_return` handlers ignore `prior_tax_state`,
  `tuition_slips`, tuition claims/transfers, `deductions`, and `slips_rc210`.
  A lower-level personal-credit argument exists, but the return adapter does not
  populate it. RRSP contributions are deducted without consuming the prior limit.
- `app/core/slips/t4.py` sums CPP/EI contributions; those helpers do not implement
  annual overpayment reconciliation or its effect on refund/balance.
- `app/main.py` has authentication/session/CSRF middleware and the UI, but not
  the browser's `/prepare`, `/printout/t1`, and `/prepare/efile` endpoints.
  `app/api/http.py` has those endpoints and the UI, but not the same auth/session
  middleware stack. Merely switching servers is not an integrated-flow fix.
- Slip sign validation after rounding remains open in
  [issue #100](https://github.com/jude27mad/tax-prep-app/issues/100).
- `app/confidence/`, `app/ledger/`, `app/teefoor/`, and `app/evidence/` do not yet
  exist. `app/explain/` contains models only.

## Execution queue

All rows are **pending** at the audit baseline unless marked otherwise. This is
an implementation order, not a claim that one PR must contain a whole milestone.
The Ontario TY2025 benchmark is a checkpoint, not a silent reduction of the
product's eventual scope. Keep existing 2024/other-jurisdiction behavior covered
by regressions and identify unsupported cases honestly.

| ID | Deliverable | Dependency / completion gate |
| --- | --- | --- |
| R0 | This roadmap correction | Docs-only proposal; complete when merged |
| R1 | Input coverage and validation boundary | Next implementation; acceptance below |
| C1 | Non-refundable credits and tuition state | R1; first calculation milestone, in small category-specific PRs |
| C2 | RRSP deduction limits and contribution state | R1/C1 contracts; verify interactions with credits |
| C3 | CWB and RC210 reconciliation | C1/C2; explicit eligibility inputs and independently checked results |
| C4 | Year-correct CPP/EI treatment and overpayments | C1–C3 integration; reconcile deductions, credits and refundable amounts |
| C5 | Ontario calculation completion for benchmark scope | C1–C4; province-specific credits/additions and boundary fixtures |
| B1 | TY2025 reference-return checkpoint | C1–C5; reference evidence and line-by-line reconciliation |
| R2 | Integrated consumer app and filing-channel boundary | After R1; must pass before B2; keep live transmission disabled |
| C6 | Remaining declared support coverage and rules audit | B1; close or explicitly gate every gap in the R1 matrix |
| B2 | Engine and consumer-flow readiness | B1, R2, C6; all engine/flow acceptance criteria below |
| X1 | Deterministic explanation engine | B2; preserve the original phase-3 contract below |
| X2 | Refund waterfall data and reconciliation | X1; before API/CLI/UI adapters, which land with X3–X5 |
| X3 / X4 | Read-only explanation API / CLI explain mode | X1/X2; permanent CLI, no second calculator |
| X5 | Guided confidence primitives and adapters | X1–X4; state/action/verification contracts |
| X6 | Source/proof ledger | X1/X5 plus rule/input provenance established during engine work |
| X7 / X8 | TeeFoor safety / Mirror | X6, then X7; read-only and session-only |
| X9 | Evidence pack | X6 and applicable explanation/privacy contracts; no submission side effects |
| X10 | Disabled provider stubs | X7–X9; no live AI calls or new provider dependency |
| N1 | Official NETFILE integration and certification | Blocked pending official developer material; separate release gate, not satisfied by B2 or X10 |

N1 material can be obtained while implementation proceeds; it does not block
protocol-independent calculation or explanation work. Do not contact CRA or
transmit test/production returns without the required user authorization and
official procedure. A mock CERT rehearsal is not NETFILE certification.

## Immediate implementation: R1, then C1

### R1 — Input coverage and validation boundary

Scope: `app/core/models.py`, `app/core/validate/pre_submit.py`, shared calculation
entry points, their API/UI/CLI adapters, and focused tests. Add a versioned
coverage matrix keyed by tax year, jurisdiction and input/feature. For every
accepted amount and eligibility field, record its consumer/calculation, tests,
and whether it is implemented, explicitly out of scope, or not yet implemented.
Include all `DeductionCreditInputs`, tuition, prior-state, RC210 and household
fields, plus slip fields that affect deductions/repayments rather than income.

Acceptance:

- Non-default inputs that require missing calculation work produce a stable,
  field-specific blocking issue on the full-return path. Estimate-only behavior
  is explicitly labelled. Do not reject a legitimate zero-effect claim merely
  because it does not change the final total; verify intermediate lines too.
- The same unsupported-case decision applies to API, UI, CLI and filing
  readiness; direct full-return consumers cannot bypass it. Preserve the shared
  tax engine rather than adding separate calculations in adapters.
- Resolve #100's validation-boundary choice explicitly: either reject before
  cent quantization and adapt callers to structured errors, or preserve raw
  values for the existing collected-issue contract. Test restricted amounts as
  Decimal/string/JSON number, sub-cent negatives, valid zero/negative zero and
  caller error handling. Do not apply a blanket negative-value ban to fields
  whose supported semantics allow negatives.
- Reject unsupported tax years/jurisdictions consistently at public calculation
  boundaries. Test the existing low-level provincial fallback to 2025 so it
  cannot silently label an unsupported year as a supported return.
- Add regression tests demonstrating currently ignored inputs are flagged;
  replace each flag only when its calculation and reference tests land. Where
  old full-return tests assert that unsupported inputs are ignored, replace
  those assertions with the new explicit blocking behavior; preserve model
  serialization/provenance tests and unchanged supported-return regressions.

### C1 — First calculation milestone: credits and tuition

Keep the existing line/computation contracts and one calculation path. Land
small, independently reviewed slices rather than all tax-credit categories in
one PR. Verify each category against the applicable year's official forms and
worksheets before encoding formulas, rates, thresholds or rounding.

Acceptance:

- Wire supported personal credits into the return calculation, including
  applicable employment and CPP/EI credit bases; distinguish base contributions
  from enhanced amounts/deductions and reconcile with C4 to avoid double counting.
- Implement tuition use/transfer/carryforward with separate federal/Ontario
  balances, claim limits, provenance, and explicit opening-to-closing movement.
  A missing balance/limit must not be silently treated as a verified zero.
- Implement medical, donation and student-loan-interest treatment in separate
  slices, or keep their R1 blocks until their rules and tests are complete.
  Do not feed every amount into a single undifferentiated credit-rate multiplier.
- Test zero/low-tax, income thresholds, transfer limits, multiple slips,
  prior-year balances, missing provenance, and 2024/2025 isolation as applicable.
- Replace the relevant R1 blocking assertions (or remaining historical
  calculation-neutrality assertions) in `test_prior_tax_state.py` / benchmark
  slip tests with reference-backed calculation tests when those inputs become
  active. Preserve unrelated validation/provenance regressions; update comments
  that currently say “nothing consumes this” in the same implementation PR.

## Remaining engine milestone contracts

- **C2 — RRSP:** distinguish receipts/contributions from the chosen allowable
  deduction, consume established limits and unused contributions, account for
  supported HBP/LLP treatment or keep it explicitly blocked, prevent duplicate
  receipt/manual counting, and report closing balances. Test limits, missing
  information, repayment treatment and interactions with net income/credits.
- **C3 — CWB/RC210:** establish household/student/residency and other required
  eligibility inputs, compute the supported entitlement and reconcile advances
  without treating RC210 as ordinary income. Test no advance, partial advance,
  eligibility boundaries and zero entitlement using independent references.
- **C4 — CPP/EI:** use year-correct annual rules, supported exemptions and
  multi-employer reconciliation; separate paid amounts, deductions, credits and
  overpayments. Test caps and under/overpayment cases and their effect on balance.
  Do not assume the existing payroll estimator proves annual-return correctness.
- **C5 — Ontario:** audit credits, tuition balances, tax reduction, surtax and
  health premium for the supported cases, with correct income/credit bases and
  boundary fixtures. Existing brackets/additions are reusable, not proof of
  completeness. Missing eligibility inputs must block the affected case.
- **C6 — Coverage/rules:** finish remaining in-scope items from R1, including
  applicable slip repayment/offset logic and jurisdiction/year gaps. Record
  source URLs, tax years, form/worksheet references and rounding expectations
  alongside rules/fixtures. Move verified values into the existing rules loader
  where appropriate; do not build a second rules engine. Do not expand or shrink
  the launch envelope without an explicit product decision recorded here.

## Acceptance gates

### B1 — Reference-return checkpoint

The historical TY2025 benchmark targets are a **$1,650.54 refund**, **$1,633.00
CWB**, and **$13,953.81 tuition carryforward**. They are candidate reference
values, not independently verified by this roadmap change. The audit found no
complete input-to-output benchmark fixture proving all three; `13953.81` also
appears as an *opening* balance in prior-state unit tests, which does not prove
the benchmark's closing balance.

Before B1 can pass, establish a sanitized full input fixture, the precise meaning
of each target (including opening vs closing tuition and entitlement vs advances),
tax year/province, and the independent reference return or official worksheets.
Do not commit real SINs, tax documents or credentials. If source evidence is
missing, mark B1 blocked rather than inventing inputs or adjusting the engine to
fit the three totals. Verify all relevant lines and intermediate balances, not
only the refund; correct a historical target only with documented evidence.

B1 is a reassessment checkpoint: compare the implementation with this roadmap,
record uncovered cases and proceed to C6/B2. One matching return is not full
coverage or certification.

### R2 — Consumer app and filing-channel boundary

- Choose and document one supported consumer deployment entry point with the
  authentication, session, CSRF and security-header stack. Connect the browser's
  compute/print routes to it without bypassing authorization or creating a
  second calculation path. Keep legacy entry points compatible or clearly gated.
- Preserve tenant ownership and safe artifact paths for all computation and
  download operations. Test unauthenticated/cross-tenant requests and CSRF
  failure alongside the successful path.
- Implement the protocol-neutral filing-channel boundary from
  `filing_channels.md` §5. Quarantine preparer-only T183/T619/XML controls from
  the consumer UI; retain reusable transport/storage code. Consumer transmission
  must return a clear unavailable/pending-specification state, not fall through
  to the legacy EFILE implementation.
- Browser acceptance: sign in, create/edit a supported return, upload/apply a
  synthetic slip, calculate, inspect issues/results, download the printout, and
  verify transmission stays blocked. Exercise real routes and middleware in one
  deployed app, not just a mocked successful `fetch`. No live CRA calls in tests.

### B2 — Engine and consumer-flow readiness

- Every declared supported case in the R1 matrix has reference-backed tests;
  every unsupported material input is visibly blocked. A registered province,
  model field or route is not by itself a support claim. Record the actual
  launch year/jurisdiction/case envelope before marking B2 complete.
- Supported returns reconcile income, deductions, credits, withholding,
  refundable amounts and final refund/balance. Test refund, amount owing and
  zero balance, thresholds, missing inputs, multiple slips and year isolation.
- B1 and R2 pass; API/UI/CLI results agree for equivalent supported inputs.
  Calculation readiness remains distinct from permission to transmit to CRA.
- Existing CI gates stay enabled: Ruff, mypy, migrations round-trip,
  non-Playwright pytest, Playwright smoke, CLI smoke and mock CERT rehearsal.
  Add substantive cases to those gates rather than weakening/skipping assertions.
  CI success alone does not independently validate tax rules.
- Review calculation changes against their reference evidence before merge.
  Record unresolved limitations and the next task in this document. Only then
  begin X1; do not advertise the app as certified or launch-ready on this basis.

## Preserved product-layer contracts

These are the existing Plan V3 contracts with stable IDs. The execution queue
above controls their order; their original numbering is retained only as a
cross-reference. X2's adapter tests land with X3–X5 so waterfall data can precede
the surfaces that render it. Each starts only after its stated dependencies.

## Package placement note

Plan V3 packages should be top-level under `app/`:

- `app/explain/`
- `app/confidence/`
- `app/ledger/`
- `app/teefoor/`
- `app/evidence/`

At the audit baseline, `explain` contains models; `confidence`, `ledger`,
`teefoor`, and `evidence` are not present. The repo uses top-level domain packages
such as `app/api`, `app/auth`, `app/db`, `app/efile`, `app/printout`, `app/ui`,
and `app/wizard`. That convention is clearer than placing Plan V3 packages under
`app/core/`, because these features are product and orchestration layers around
the deterministic core rather than tax-year/province calculation internals.

## Contract R0 — Docs and audit (original phase 1)

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

## Contract X0 — Explanation models (original phase 2, landed)

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

## Contract X1 — Deterministic explanation engine (original phase 3)

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

## Contract X3 — Read-only explanation API (original phase 4)

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

## Contract X4 — CLI explain mode (original phase 5)

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

## Contract X5 — Guided confidence primitives (original phase 6)

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

## Contract X2 — Refund waterfall (original phase 7)

Goal:

- Explain refund or balance due as a deterministic waterfall from income,
  deductions, federal tax, provincial tax, additions, credits, withholding, and
  final balance, including refundable credits and contribution overpayments
  when applicable to the supported return.

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

## Contract X6 — Source/proof ledger (original phase 8)

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

## Contract X7 — TeeFoor contract/safety package (original phase 9)

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

## Contract X8 — TeeFoor Mirror lightweight skeleton (original phase 10)

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

## Contract X9 — Evidence pack (original phase 11)

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

## Contract X10 — Disabled provider stubs (original phase 12)

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
