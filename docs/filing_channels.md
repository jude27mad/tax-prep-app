# Filing Channels: NETFILE (consumer) vs EFILE (preparer)

Tax_App is a **consumer-first** Canadian personal tax product. The consumer filing
path is **NETFILE**. EFILE is the professional/preparer channel.

This distinction is load-bearing. The repository's existing filing stack was built
EFILE-shaped — the string `NETFILE` did not appear anywhere in `app/`, `docs/`, or
`scripts/` before this document — so parts of it are on the wrong channel for the
consumer product. Read this before touching anything under `app/efile/`,
`app/schemas/`, or the transmission path.

---

## 0. Governing rule: NO CRA PROTOCOL ASSUMPTIONS

**Anything concerning NETFILE transmission format, authentication fields,
certification test procedure, developer credentials, controlled-access artifacts, or
service limits that is not established by current official CRA material must remain
behind an interface and be marked "pending official CRA developer specification."**

**Do not reverse-engineer or infer the NETFILE protocol from the existing EFILE
code.** The EFILE XML machinery in this repo carries no evidential weight about
NETFILE.

Items marked **[PENDING CRA]** below are placeholders for official material, not
design decisions. When official material is obtained, update this document *from that
source* rather than patching around it.

---

## 1. The two channels

| | **NETFILE** (consumer — our path) | **EFILE** (preparer — future B2B) |
|---|---|---|
| Who transmits | The individual, filing their own return | A registered electronic filer, on behalf of clients |
| Identity / authorization | The individual authenticates as themselves; no third-party authorization form. A **NETFILE Access Code** (8-char, from the prior NOA) is publicly documented as *optional* — without it, prior-year information cannot be used to confirm identity. Developer-facing auth fields are **[PENDING CRA]** | **EFILE number + password** from CRA, plus **Form T183** signed by the client before transmission |
| Transmission format | **[PENDING CRA] — unknown.** Not assumed to be XML/XSD | XML per CRA EFILE specifications |
| Return volume limit | **[PENDING CRA] — do not build.** See §3 | No cap |
| T183 | **Not part of the flow** — there is no electronic filer to authorize | Required for every initial and amended T1; retained 6 years |
| Auto-fill My Return | Yes — individual signs into their CRA account; **requires NETFILE-certified software** | Yes — via Represent a Client authorization |
| ReFILE | Yes (rolling ~4-year window) | Yes |
| Express NOA in software | **Discontinued.** Effective 2026-02-09 notices are viewable only in CRA portals; the T183 Part E checkbox for it was removed | Same — discontinued |

## 2. What is confirmed vs pending

**Confirmed shared** (build once, protocol-independent): T1 return calculation and
field/form coverage, tax-year rules, validation rules, golden fixtures, CERT/PROD
environment separation as an engineering practice.

**Confirmed NETFILE-relevant:** Auto-fill My Return is gated on NETFILE-certified
software for the consumer flow — so the import-ledger/reconciliation feature depends
on the NETFILE path specifically. ReFILE and the NETFILE exclusion list also apply.

**Confirmed EFILE-only:** EFILE number/password registration, T183 generation and
6-year retention, Represent a Client authorization, unlimited volume,
preparer-specific error validities, and CRA's software-specific EFILE account
controls.

**[PENDING CRA] — confirm, do not infer:**

- The NETFILE developer onboarding and certification procedure end to end. The
  confidentiality agreement → controlled-access draft forms → mid-November test
  returns → transmit → evaluate → confirmation-letter cycle is documented publicly
  **for EFILE**. **Do not assume NETFILE is identical.**
- The NETFILE transmission format/schema/specification, and whether a
  schema-validation step exists at all.
- Developer credentials, software identifiers, controlled-access artifacts.
- Acknowledgement/rejection semantics and their error-code vocabulary.
- Service limits (see §3).

## 3. The 20-return limit — do not build it yet

Current public CRA wording ties the 20-return limit to individuals preparing multiple
returns for family and friends while registered for Represent a Client. It is **not**
self-evidently a blanket per-account cap that certified software must enforce for our
delivery model.

**Do not implement a 20-return product or account limit unless the NETFILE developer
specification explicitly requires it.**

## 4. What is on the wrong channel in this repo

Three pieces of otherwise-good work are EFILE-shaped and must not be treated as the
consumer implementation:

1. **`app/efile/t619.py`** wraps the T1 + T183 payload in a `T619Transmission`
   envelope. **T619 is the Electronic Transmittal record for *information returns*** —
   the T4/T5/T3 slips an *issuer* files via Internet File Transfer — not the T1
   transmission envelope. Its mandatory fields (Transmitter CRA Account Number,
   Transmitter Rep ID) are how `ReturnInput.transmitter_account_mm` and
   `ReturnInput.rep_id` leaked into the consumer return contract.
2. **The T183 stack** (`app/efile/t183.py`, the consent UI, encryption, retention,
   purge scheduling). Correct work on the preparer channel; a consumer NETFILE return
   needs none of it.
3. **All four `app/schemas/*.xsd`** are self-described placeholders modelling an
   EFILE-shaped XML flow. They are evidence of nothing about NETFILE and must not be
   "upgraded" into an assumed NETFILE shape.

## 5. Disposition

**Preserve, quarantined off the consumer path** (feature-flagged; retained for the
future preparer/B2B product): `app/efile/t183.py`, the T183/T2183 consent UI and
retention/purge, `transmitter_account_mm` / `rep_id`, `feature_legacy_efile`, the
XML/XSD machinery.

**Preserve and reuse** (protocol-agnostic): `app/efile/crypto.py` and `storage.py`
envelope encryption and retention; `app/efile/transmit.py` transport hardening
(duplicate-digest detection, backoff, circuit breaker, masked logging).

**Generalize:** `app/efile/gating.py` into a filing-channel gate whose transmission
implementation sits behind an interface, so CRA's eventual NETFILE format drops in
without disturbing the engine, trust layer, or UX above it. **Assume nothing about
payload format at that boundary** — the interface takes a computed return and returns
a channel-specific submission result.

## 6. Exclusions must be attributed accurately

An exclusion is either a CRA requirement or **our own product-scope decision**. Never
present an invented rule as CRA's, and never state a suspected CRA rule as confirmed.

- **CRA-required, confirmed:** non-residents and deemed non-residents; emigrants
  filing with T1243/T1244/T1161; self-employment reported on T2203 (multiple
  jurisdictions); returns under ITA section 116; Seasonal Agricultural Worker Program
  filers who are non-residents or deemed non-residents.
- **[PENDING CRA]:** bankruptcy-year returns (public wording describes these as
  *EFILE* exclusions — confirm NETFILE treatment); first-year newcomers; deceased
  taxpayers. Until confirmed, gate these as product-scope exclusions and describe them
  to users as unsupported by Tax_App, **not** as prohibited by CRA.
- **Product-scope, ours:** whatever is outside the current supported-case envelope.

## 7. Sources

Public CRA pages. **No NETFILE software-developer specification, onboarding document,
or certification procedure has been obtained** — every claim touching that material is
marked [PENDING CRA] above.

- [Find certified tax software (NETFILE program)](https://www.canada.ca/en/revenue-agency/services/e-services/digital-services-individuals/netfile-overview/certified-software-netfile-program.html)
- [EFILE certified software for the 2026 EFILE program](https://www.canada.ca/en/revenue-agency/services/e-services/digital-services-individuals/efile-electronic-filers/efile-certified-software-efile-program.html)
- [NETFILE — sending a tax return](https://www.canada.ca/en/services/taxes/income-tax/personal-income-tax/how-file/tax-software/send-return/netfile.html)
- [File returns — EFILE exclusions and restrictions](https://www.canada.ca/en/revenue-agency/services/e-services/digital-services-individuals/efile-electronic-filers/file-returns.html)
- [Form T183 and authorizing a representative](https://www.canada.ca/en/revenue-agency/services/e-services/digital-services-individuals/efile-electronic-filers/forms-t183-t1013.html)
- [Auto-fill My Return (individuals)](https://www.canada.ca/en/services/taxes/income-tax/personal-income-tax/how-file/tax-software/complete-return/auto-fill.html)
- [Express NOA / NOA in tax software — no longer available](https://www.canada.ca/en/revenue-agency/services/e-services/about-express-noa.html)
- [T619, Electronic Transmittal (information returns)](https://www.canada.ca/en/revenue-agency/services/e-services/filing-information-returns-electronically-t4-t5-other-types-returns-overview/t619.html)
