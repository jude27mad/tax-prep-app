# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Added

- Declared `python-multipart` as an explicit dependency so FastAPI's form parsing works in the UI routes without relying on transitive installs.

### Fixed

- Hardened application startup with a guard around the ReportLab font registration to surface actionable guidance when PDF tooling is missing.
- Updated CI and test fixtures to exercise the guarded startup path and stub multipart handling when the dependency is intentionally absent.

### Operator guidance

- Install the new dependency on every application host: `pip install python-multipart` (or re-run `pip install -r requirements.txt`).
- After redeploying, start the service (for example, `uvicorn app.api.http:app --reload`) and confirm the startup guard logs a successful ReportLab check instead of a missing dependency warning.
- Review the deployment notes in the [Running the APIs guide](README.md#running-the-apis) for additional rollout details.
