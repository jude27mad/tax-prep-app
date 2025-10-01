#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI

from app.api.http import _compute_for_year, app as preparer_app
from app.core.models import ReturnInput
from app.efile.error_map import explain_error
from app.efile.service import prepare_xml_submission
from app.efile.transmit import EfileClient


async def _run_case(app: FastAPI, case: ReturnInput, artifact_dir: Path) -> dict:
    calc = _compute_for_year(case)
    prepared = prepare_xml_submission(app, case, calc)

    suffix = case.taxpayer.sin[-4:] if case.taxpayer.sin else "anon"
    xml_path = artifact_dir / f"request_{suffix}.xml"
    xml_path.write_bytes(prepared.xml_bytes)

    client = EfileClient(prepared.endpoint)
    response = await client.send(prepared.xml_bytes, content_type="application/xml")

    response_path = artifact_dir / f"response_{suffix}.json"
    response_path.write_text(json.dumps(response, indent=2))

    raw_codes = response.get("codes") or response.get("reject_codes") or []
    mapped = [explain_error(code) for code in raw_codes]

    return {
        "digest": prepared.digest,
        "codes": raw_codes,
        "explanations": mapped,
        "files": {
            "request": str(xml_path),
            "response": str(response_path),
        },
    }


async def _run(app: FastAPI, cases: Iterable[ReturnInput], artifact_dir: Path) -> list[dict]:
    results: list[dict] = []
    async with app.router.lifespan_context(app):
        for case in cases:
            results.append(await _run_case(app, case, artifact_dir))
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CRA certification test submissions")
    parser.add_argument("--cases", required=True, help="Path to JSON array of ReturnInput payloads")
    parser.add_argument("--output", required=True, help="Directory to save artifacts")
    return parser.parse_args()


def load_cases(path: Path) -> list[ReturnInput]:
    data = json.loads(path.read_text())
    return [ReturnInput.model_validate(item) for item in data]


def main() -> None:
    args = parse_args()
    cases_path = Path(args.cases)
    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)
    artifact_dir = out_root / datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases(cases_path)
    results = asyncio.run(_run(preparer_app, cases, artifact_dir))

    summary_path = artifact_dir / "summary.json"
    summary_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"Saved CRA certification artifacts to {artifact_dir}")


if __name__ == "__main__":
    main()
