from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import secrets
import string
from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException

from app.config import Settings, get_settings
from app.core.models import ReturnCalc, ReturnInput
from app.core.validate.pre_submit import Identity, ValidationIssue, validate_before_efile
from app.efile.records import EfileEnvelope
from app.efile.t183 import mask_sin
from app.efile.t619 import T619Package, build_t619_package




def _generate_sbmt_ref_id() -> str:
    now = datetime.now(timezone.utc).strftime("%y%j%H")  # year+day-of-year+hour
    alphabet = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(8 - len(now)))
    return (now + random_part)[:8]

def _ensure_submission_cache(app: FastAPI) -> set[str]:
    cache = getattr(app.state, "submission_digests", None)
    if cache is None:
        cache = set()
        app.state.submission_digests = cache
    return cache




def _summary_index(app: FastAPI) -> dict[str, Path]:
    index = getattr(app.state, "summary_index", None)
    if index is None:
        index = {}
        app.state.summary_index = index
    return index

def _artifact_directories(app: FastAPI) -> tuple[Path, Path]:
    artifact_root = Path(getattr(app.state, "artifact_root", "artifacts"))
    summary_root = Path(getattr(app.state, "daily_summary_root", artifact_root / "summaries"))
    artifact_root.mkdir(parents=True, exist_ok=True)
    summary_root.mkdir(parents=True, exist_ok=True)
    return artifact_root, summary_root


def _persist_artifacts(app: FastAPI, digest: str, package: T619Package) -> None:
    artifact_root, summary_root = _artifact_directories(app)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    day_dir = artifact_root / today
    day_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{package.sbmt_ref_id}_{digest}"
    (day_dir / f"{prefix}_envelope.xml").write_text(package.envelope_xml, encoding="utf-8")
    (day_dir / f"{prefix}_t1.xml").write_text(package.t1_xml, encoding="utf-8")
    (day_dir / f"{prefix}_t183.xml").write_text(package.t183_xml, encoding="utf-8")
    summary_path = summary_root / f"{today}.json"
    entry = {"digest": digest, "sbmt_ref_id": package.sbmt_ref_id, "time_utc": datetime.now(timezone.utc).isoformat(), "documents": list(package.payload_documents.keys())}
    if summary_path.exists():
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"submissions": []}
    else:
        data = {"submissions": []}
    submissions = data.setdefault("submissions", [])
    submissions.append(entry)
    summary_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _summary_index(app)[digest] = summary_path


@dataclass
class PreparedEfile:
    envelope: EfileEnvelope
    package: T619Package
    digest: str
    sbmt_ref_id: str
    xml_bytes: bytes
    endpoint: str


class PrefileValidationError(HTTPException):
    def __init__(self, issues: list[ValidationIssue]):
        super().__init__(status_code=400, detail=[issue.__dict__ for issue in issues])
        self.issues = issues


def _build_identity(req: ReturnInput) -> Identity:
    taxpayer = req.taxpayer
    return Identity(
        sin=taxpayer.sin,
        first_name=taxpayer.first_name,
        last_name=taxpayer.last_name,
        dob_yyyy_mm_dd=taxpayer.dob.isoformat(),
        address_line1=taxpayer.address_line1,
        city=taxpayer.city,
        province=taxpayer.province,
        postal_code=taxpayer.postal_code,
    )


def enforce_prefile_gates(req: ReturnInput, calc: ReturnCalc) -> None:
    issues = validate_before_efile(
        _build_identity(req),
        {
            "taxable_income": str(calc.line_items.get("taxable_income", "0")),
            "province": req.province,
            "tax_year": req.tax_year,
            "t183_signed_ts": req.t183_signed_ts.isoformat() if req.t183_signed_ts else "",
            "t183_ip_hash": req.t183_ip_hash,
            "t183_user_agent_hash": req.t183_user_agent_hash,
        },
    )
    if issues:
        raise PrefileValidationError(issues)


def _resolve_endpoint(settings: Settings, endpoint_override: str | None) -> str:
    if endpoint_override:
        return endpoint_override
    profile = settings.profile()
    if profile.endpoint:
        return profile.endpoint
    raise HTTPException(status_code=400, detail="No EFILE endpoint configured for current environment")


def prepare_xml_submission(
    app: FastAPI,
    req: ReturnInput,
    calc: ReturnCalc,
    *,
    endpoint_override: str | None = None,
) -> PreparedEfile:
    enforce_prefile_gates(req, calc)

    settings = getattr(app.state, "settings", get_settings())
    profile = settings.profile()
    schema_cache = getattr(app.state, "cra_schema_cache", {})
    profile_dict = {
        "Environment": profile.environment,
        "SoftwareId": profile.software_id,
        "SoftwareVersion": profile.software_version,
        "TransmitterId": profile.transmitter_id,
    }

    sbmt_ref_id = _generate_sbmt_ref_id()
    package = build_t619_package(req, calc, profile_dict, schema_cache, sbmt_ref_id)
    canonical_source = (package.t1_xml + package.t183_xml + profile.environment + profile.software_id + profile.software_version + profile.transmitter_id).encode("utf-8")
    digest = sha256(canonical_source).hexdigest()

    xml_bytes = package.envelope_xml.encode("utf-8")

    cache = _ensure_submission_cache(app)
    if digest in cache:
        raise HTTPException(status_code=409, detail="Duplicate submission digest detected")

    envelope = EfileEnvelope(
        software_id=profile.software_id,
        software_ver=profile.software_version,
        transmitter_id=profile.transmitter_id,
        environment=profile.environment,
    )

    endpoint = _resolve_endpoint(settings, endpoint_override)

    _persist_artifacts(app, digest, package)
    cache.add(digest)
    app.state.last_sbmt_ref_id = sbmt_ref_id

    return PreparedEfile(
        envelope=envelope,
        package=package,
        digest=digest,
        sbmt_ref_id=sbmt_ref_id,
        xml_bytes=xml_bytes,
        endpoint=endpoint,
    )


def pii_safe_context(req: ReturnInput) -> dict[str, Any]:
    return {
        "tax_year": req.tax_year,
        "province": req.province,
        "taxpayer_sin_masked": mask_sin(req.taxpayer.sin),
    }


def record_transmit_outcome(app: FastAPI, digest: str, response: dict[str, Any]) -> None:
    summary_path = _summary_index(app).get(digest)
    if not summary_path or not summary_path.exists():
        return
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    submissions = data.get("submissions", [])
    for entry in submissions[::-1]:
        if entry.get("digest") == digest:
            entry.setdefault("sbmt_ref_id", getattr(app.state, "last_sbmt_ref_id", None))
            entry["response"] = response
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            break
    summary_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
