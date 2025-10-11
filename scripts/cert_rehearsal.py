#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import zipfile
from datetime import datetime
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import xmlschema  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from app.api.http import _compute_for_year, app as preparer_app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.core.models import ReturnInput  # noqa: E402
from app.efile.service import PrefileValidationError, prepare_xml_submission  # noqa: E402
from app.efile.t619 import SCHEMA_T1, SCHEMA_T619  # noqa: E402
from app.printout.t1_render import render_t1_pdf  # noqa: E402

CANONICAL_CASES = Path(__file__).with_name("cert_cases.json")
LOGGER = logging.getLogger("cert_rehearsal")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CRA CERT rehearsal against canonical cases")
    parser.add_argument(
        "--cases",
        type=Path,
        default=CANONICAL_CASES,
        help="Path to JSON array of ReturnInput payloads (default: scripts/cert_cases.json)",
    )
    parser.add_argument(
        "--bundle-root",
        type=Path,
        default=Path("cert_bundle"),
        help="Directory to store rehearsal artifacts",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices={"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"},
        help="Logging verbosity",
    )
    return parser.parse_args()


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _load_cases(path: Path) -> list[ReturnInput]:
    if not path.exists():
        raise FileNotFoundError(f"Canonical case bundle not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Expected JSON array of ReturnInput payloads")
    return [ReturnInput.model_validate(item) for item in data]


def _ensure_single_return_type(cases: Iterable[ReturnInput]) -> None:
    tax_years = {case.tax_year for case in cases}
    if not tax_years:
        raise ValueError("No canonical cases provided")
    if len(tax_years) > 1:
        raise ValueError(f"Mixed tax years detected: {sorted(tax_years)}")


def _sanitize_segment(value: str | None) -> str:
    if not value:
        return "taxpayer"
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-")
    return cleaned or "taxpayer"


def _case_directory_name(case: ReturnInput, index: int) -> str:
    sin_digits = ''.join(ch for ch in (case.taxpayer.sin or "") if ch.isdigit())
    suffix = sin_digits[-4:] if len(sin_digits) >= 4 else (sin_digits or f"{index:02d}")
    last_name = _sanitize_segment(case.taxpayer.last_name)
    province = _sanitize_segment(case.province)
    return f"{index:02d}_{province}_{last_name}_{suffix}"


def _ensure_environment(artifact_dir: Path, summary_dir: Path) -> None:
    os.environ.setdefault("EFILE_ENV", "CERT")
    os.environ.setdefault("FEATURE_EFILE_XML", "1")
    os.environ.setdefault("EFILE_WINDOW_OPEN", "1")
    os.environ.setdefault("ARTIFACT_ROOT", str(artifact_dir))
    os.environ.setdefault("DAILY_SUMMARY_ROOT", str(summary_dir))
    get_settings.cache_clear()


@lru_cache(maxsize=None)
def _compiled_schema(name: str, schema_cache: tuple[tuple[str, str], ...]) -> xmlschema.XMLSchemaBase:
    cache_map = dict(schema_cache)
    if name not in cache_map:
        raise ValueError(f"Schema {name} not available in CRA cache")
    return xmlschema.XMLSchema(StringIO(cache_map[name]))


def _validate_xml(payload: str, name: str, schema_cache: dict[str, str]) -> None:
    schema = _compiled_schema(name, tuple(sorted(schema_cache.items())))
    schema.validate(payload)


def _enforce_ift_constraints(package) -> None:
    documents = package.payload_documents
    if not documents:
        raise ValueError("CRA payload did not include any documents")
    return_docs = [name for name in documents if name.endswith("Return")]
    if not return_docs:
        raise ValueError("CRA payload missing return document")
    primary = return_docs[0]
    for name in return_docs[1:]:
        if name != primary:
            raise ValueError(f"Mixed return documents detected: {sorted(return_docs)}")
    if "<T619Transmission" not in package.envelope_xml:
        raise ValueError("CRA payload missing T619 envelope")


async def _process_case(
    app: FastAPI,
    case: ReturnInput,
    case_dir: Path,
    schema_cache: dict[str, str],
) -> dict:
    LOGGER.info("Running CERT rehearsal case", extra={"province": case.province, "tax_year": case.tax_year})

    calc = _compute_for_year(case)
    (case_dir / "input.json").write_text(json.dumps(case.model_dump(mode="json"), indent=2), encoding="utf-8")
    (case_dir / "calc.json").write_text(json.dumps(calc.model_dump(mode="json"), indent=2), encoding="utf-8")

    try:
        prepared = prepare_xml_submission(app, case, calc)
    except PrefileValidationError as exc:
        LOGGER.error("Prefile validation failed", extra={"province": case.province, "errors": exc.detail})
        raise

    package = prepared.package
    _enforce_ift_constraints(package)
    _validate_xml(package.t1_xml, SCHEMA_T1, schema_cache)
    _validate_xml(package.envelope_xml, SCHEMA_T619, schema_cache)

    envelope_path = case_dir / f"{prepared.sbmt_ref_id}_t619_envelope.xml"
    t1_path = case_dir / f"{prepared.sbmt_ref_id}_t1_return.xml"
    t183_path = case_dir / f"{prepared.sbmt_ref_id}_t183_authorization.xml"
    envelope_path.write_text(package.envelope_xml, encoding="utf-8")
    t1_path.write_text(package.t1_xml, encoding="utf-8")
    t183_path.write_text(package.t183_xml, encoding="utf-8")

    payload_zip = case_dir / f"{prepared.sbmt_ref_id}_payload.zip"

    with zipfile.ZipFile(payload_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, xml_body in sorted(package.payload_documents.items()):
            archive.writestr(f"{name}.xml", xml_body)

    pdf_path = Path(render_t1_pdf(str((case_dir / "t1_return.pdf").resolve()), case, calc))

    summary = {
        "province": case.province,
        "tax_year": case.tax_year,
        "sbmt_ref_id": prepared.sbmt_ref_id,
        "digest": prepared.digest,
        "artifact_paths": {
            "envelope": str(envelope_path),
            "t1": str(t1_path),
            "t183": str(t183_path),
            "payload_zip": str(payload_zip),
            "pdf": str(pdf_path),
        },
    }
    LOGGER.info("Completed case", extra={"province": case.province, "sbmt_ref_id": prepared.sbmt_ref_id})
    return summary


async def _run_rehearsal(app: FastAPI, cases: list[ReturnInput], run_dir: Path) -> list[dict]:
    results: list[dict] = []
    async with app.router.lifespan_context(app):
        settings = get_settings()
        if settings.profile().environment != "CERT":
            raise RuntimeError(f"CERT rehearsal must run in CERT environment (got {settings.profile().environment})")
        schema_cache = getattr(app.state, "cra_schema_cache", {})
        for idx, case in enumerate(cases, start=1):
            case_dir = run_dir / _case_directory_name(case, idx)
            case_dir.mkdir(parents=True, exist_ok=True)
            results.append(await _process_case(app, case, case_dir, schema_cache))
    return results


def _copy_logs(run_dir: Path) -> None:
    log_path = Path("logs") / "preparer.log"
    if log_path.exists():
        dest = run_dir / log_path.name
        dest.write_bytes(log_path.read_bytes())


def main() -> None:
    args = _parse_args()
    _configure_logging(args.log_level)

    cases = _load_cases(args.cases)
    _ensure_single_return_type(cases)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    bundle_root = args.bundle_root.resolve()
    run_dir = bundle_root / timestamp
    artifacts_dir = run_dir / "artifacts"
    summaries_dir = run_dir / "summaries"
    run_dir.mkdir(parents=True, exist_ok=True)

    _ensure_environment(artifacts_dir, summaries_dir)

    try:
        results = asyncio.run(_run_rehearsal(preparer_app, cases, run_dir))
    except Exception as exc:  # pragma: no cover - surfaced in CLI
        LOGGER.exception("CERT rehearsal failed")
        raise SystemExit(str(exc)) from exc

    summary = {
        "run_dir": str(run_dir),
        "case_count": len(results),
        "cases": results,
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _copy_logs(run_dir)

    LOGGER.info("CERT rehearsal artifacts saved", extra={"directory": str(run_dir)})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
