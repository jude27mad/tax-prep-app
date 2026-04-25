# Plan V3 Product Foundation

## 1. Product thesis

Plan V3 makes Tax App a deterministic Canadian tax filing engine with a guided
consumer experience around it.

The product direction is:

- A deterministic Canadian tax filing engine is the source of truth.
- The app does the tax work deterministically: intake, validation, calculation,
  filing readiness, artifacts, and eventual transmission.
- Guided Confidence System helps the user understand their current return state,
  available actions, recommended safe next step, and post-action verification.
- TeeFoor is a read-only tax explainer that explains the app's deterministic
  work, guides users through confusion, answers tax-process questions, and
  recommends next steps.
- TeeFoor Mirror makes AI visibility transparent by showing what TeeFoor can
  see, what it cannot see, what it is using, and what actions remain under user
  control.
- Source/evidence proof ties calculations and recommendations back to source
  rules, user-provided evidence, generated artifacts, and verification steps.
- The CLI wizard remains a permanent product surface.
- Normal consumers get a web/mobile-first UI.
- Future B2B gets API, white-label UI, embedded filing, compliance docs, audit
  logs, data export, admin dashboards, webhooks, sandbox clients, and partner
  support console.

Plan V3 examples are mentality examples, not fixed scripts, fixed UI copy, or
hardcoded UI rules. They show how the app and TeeFoor should approach user
confusion: understand the current session state, show available actions,
recommend a safe path, and explain how the user can verify afterward.

## 2. Current repo foundation

The repository already has a substantial filing foundation:

- `README.md` describes the Tax App as a CRA-focused toolkit for estimating
  personal income tax, preparing T1 returns, and assembling/validating EFILE XML
  with T619/T1/T183 support.
- `.github/workflows/ci.yml` runs Ruff, mypy, Alembic migration round-trip,
  non-Playwright pytest, Playwright smoke tests, CLI wizard smoke, and a CERT
  rehearsal bundle.
- `pytest.ini` defines strict markers for smoke and Playwright smoke tests.
- `.gitignore` excludes virtualenvs, caches, logs, artifacts, CERT bundles,
  profile data, and local SQLite databases.
- `app/core/models.py` defines the core return data contracts, including
  `ReturnInput`, taxpayer and slip models, deduction inputs, T183 metadata, and
  `ReturnCalc`.
- `app/core/tax_years/` dispatches deterministic return computation by tax
  year. Current handlers include 2024 and 2025.
- `app/core/provinces/` dispatches province and territory calculators for
  supported years, with Ontario as the current default.
- `tax_rules/` and `app/core/rules/` support rules-as-data for federal and
  provincial values with citation-oriented rule loading.
- `app/main.py` exposes the estimator FastAPI app, health endpoint, T4 estimate
  endpoints, and the CLI wizard entrypoint.
- `app/wizard/` contains the permanent guided CLI surface, profile persistence,
  input canonicalization, field coercion, help topics, checklist behavior, and
  T4 estimate flow.
- `app/api/http.py` exposes the preparer FastAPI app, `/prepare`,
  `/printout/t1`, XML EFILE preparation/transmission, legacy EFILE guardrails,
  and health metadata.
- `app/ui/router.py` provides the authenticated web UI, profile editing,
  multi-step return form, autosave, T183 consent flow, artifact downloads, and
  slip upload/apply/clear endpoints.
- `app/db/models.py` defines the persistent document vault through `DocumentRow`
  and document lifecycle/status enums.
- `app/ui/slip_ingest.py` implements DB-backed slip staging, file validation,
  PDF/text/image extraction paths, OCR integration, detection application, and
  tenant isolation for staged documents.
- `app/efile/` contains EFILE XML services, T619/T183 builders, gating,
  transmission client, duplicate detection, retention helpers, and masked
  logging support.
- `scripts/cert_rehearsal.py` runs canonical CERT cases, computes returns,
  generates XML/PDF artifacts, validates schemas, and bundles rehearsal output.
- `tests/` covers tax calculations, provincial dispatch, validation, UI router,
  slip ingest, auth, EFILE gating/transmission, golden XML/PDF behavior,
  printouts, fuzzing, and end-to-end upload/apply/preview behavior.

Plan V3 should extend these existing surfaces instead of bypassing them. New
explainability, confidence, ledger, TeeFoor, and evidence features should be
thin layers around deterministic state and artifacts, not parallel tax engines.

## 3. Tax engine vs TeeFoor separation

The tax engine is the source of truth.

The app owns deterministic work:

- collect and normalize user input;
- validate return readiness;
- calculate tax, credits, deductions, balances, and filing readiness;
- generate printouts, XML, T183/T619 artifacts, and evidence packs;
- stage, apply, clear, or retain documents;
- connect to CRA services;
- transmit returns only through explicit product flows controlled by the user.

TeeFoor explains the tax work. TeeFoor may read session state that the product
explicitly exposes to it, describe what the deterministic engine produced,
explain why a step is blocked, recommend the next safe action, and tell the user
how to verify the result afterward.

TeeFoor must not become a second calculator, a hidden form editor, or a filing
agent. If a user asks for math, mutation, upload, delete, CRA connection,
signature, transmission, or persistent memory, TeeFoor routes the request back
to deterministic app controls or declines the action.

## 4. Guided Confidence System doctrine

The app should not give vague homework like "worth checking."

For every important user uncertainty, the product should try to answer four
questions:

1. What does the current return/session state show?
2. What actions are available from here?
3. What is the safest recommended next step?
4. How can the user verify afterward that the step worked?

Guided Confidence should be state-aware and action-aware. It should prefer
specific next steps over generic advice. For example, if a return cannot proceed
because T183 consent is missing, the app should identify that condition, show
the consent action, explain why it is required, and describe the post-consent
verification signal.

Guided Confidence primitives should be deterministic data structures that can be
rendered in web, mobile, CLI, API, and TeeFoor contexts. The product may vary
copy by surface, but the underlying state, available actions, recommendation,
and verification path should come from the app.

## 5. TeeFoor Operating Doctrine

TeeFoor is read-only and session-only.

TeeFoor can:

- explain tax concepts and current app results;
- guide users through confusion;
- answer process questions;
- summarize deterministic return/session state exposed by the app;
- recommend next safe steps;
- point to source/evidence records and verification paths.

TeeFoor cannot:

- calculate tax math;
- mutate filing data;
- submit returns;
- edit answers;
- upload or delete files;
- connect to CRA;
- pull files from CRA or any external account;
- apply credits automatically;
- sign T183;
- transmit anything;
- remember private tax context after the session ends.

TeeFoor responses must preserve user control. It can recommend an action, but
the user must take the action through deterministic product controls.

## 6. TeeFoor Safety Router

TeeFoor needs a safety router before any provider integration.

The router should classify user intent into at least these outcomes:

- Explain: safe read-only explanation of current deterministic state or tax
  concepts.
- Guide: safe read-only next-step guidance based on exposed session state.
- Source: safe read-only citation, evidence, or verification lookup.
- Route to app action: request requires deterministic product control, such as
  editing data, applying a document detection, generating a package, or signing
  T183.
- Refuse: request asks TeeFoor to perform a prohibited action, invent a result,
  bypass user consent, bypass filing safeguards, or retain private context.

The router should make boundaries visible. A good TeeFoor answer can say what it
can explain, identify the app control that performs the real action, and tell the
user what verification signal to expect after the action completes.

## 7. TeeFoor Mirror privacy concept

TeeFoor Mirror is live privacy transparency for AI-assisted explanation.

The Mirror should show:

- whether TeeFoor is active for the current session;
- what return/session fields are visible to TeeFoor;
- what documents or artifacts are not visible;
- whether the response used deterministic tax output, source/evidence records,
  or general tax-process explanation;
- which requested actions TeeFoor cannot take;
- that TeeFoor does not retain private tax context after the session ends.

The Mirror is not a decorative feature. It is a trust and control surface. It
should keep the user aware that the app owns the filing workflow, TeeFoor is
read-only, and the user controls every mutation or submission.

## 8. Lightweight / older-device rule

Plan V3 should work for normal consumers on ordinary phones and older devices.

Core filing, review, explanation, confidence, and proof flows should avoid
unnecessary heavy client-side requirements. Prefer server-rendered or
progressively enhanced UI where it fits the current repo. Keep layouts
mobile-first, readable, low-bandwidth, and tolerant of slow devices.

AI explanation should not be required to complete the return. The deterministic
filing flow, CLI wizard, and evidence surfaces must remain usable when TeeFoor
is disabled, unavailable, or not appropriate for the user's request.

## 9. CLI wizard role

The CLI wizard is permanent, not temporary scaffolding.

The current CLI already provides guided prompts, help topics, profile loading,
profile saving, checklist generation, non-interactive smoke support, and a
deterministic T4 estimate flow. Plan V3 should preserve it as:

- a low-resource filing and estimate surface;
- a developer and tester workflow;
- an accessibility-friendly fallback;
- a stable place to expose explain and confidence primitives outside the web UI.

Future CLI explain mode should read deterministic outputs and explain them. It
must not become a separate tax engine or an unofficial TeeFoor mutation channel.

## 10. Future B2B layer

Plan V3 keeps the consumer product first, then creates a B2B layer from the same
deterministic foundation.

Future B2B capabilities include:

- public and partner APIs;
- white-label UI;
- embedded filing flows;
- compliance documentation;
- audit logs;
- data export;
- admin dashboards;
- webhooks;
- sandbox clients;
- partner support console.

B2B must not fork the tax engine. Partner experiences should call the same
deterministic calculation, validation, source/evidence, confidence, and filing
readiness contracts used by the consumer UI and CLI.

## 11. Phased roadmap

Plan V3 should land through small, reviewable PRs:

1. Plan V3 docs and repo audit.
2. Explanation models in `app/explain/`.
3. Deterministic explanation engine in `app/explain/`.
4. Read-only explanation API.
5. CLI explain mode.
6. Guided confidence primitives in `app/confidence/`.
7. Refund waterfall.
8. Source/proof ledger in `app/ledger/`.
9. TeeFoor contract and safety package in `app/teefoor/`.
10. TeeFoor Mirror lightweight skeleton.
11. Evidence pack MVP in `app/evidence/`.
12. AI provider router planning and stubs only.

Each phase should stop when its contract is deterministic, tested, and safe to
build on. Provider integrations come after safety, routing, privacy visibility,
and deterministic explanation contracts are in place.
