from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from fastapi import FastAPI, HTTPException

from app.config import Settings, get_settings
from app.core.models import ReturnCalc, ReturnInput
from app.core.validate.pre_submit import Identity, ValidationIssue, validate_before_efile
from app.efile.records import EfileEnvelope
from app.efile.t183 import mask_sin
from app.efile.t619 import T619Package, build_t619_package


@dataclass
class PreparedEfile:
    envelope: EfileEnvelope
    package: T619Package
    digest: str
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
            "t183_signed_ts": req.t183_signed_ts.isoformat() if req.t183_signed_ts else "",
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

    package = build_t619_package(req, calc, profile_dict, schema_cache)
    xml_bytes = package.envelope_xml.encode("utf-8")
    digest = sha256(xml_bytes).hexdigest()

    envelope = EfileEnvelope(
        software_id=profile.software_id,
        software_ver=profile.software_version,
        transmitter_id=profile.transmitter_id,
        environment=profile.environment,
    )

    endpoint = _resolve_endpoint(settings, endpoint_override)

    return PreparedEfile(
        envelope=envelope,
        package=package,
        digest=digest,
        xml_bytes=xml_bytes,
        endpoint=endpoint,
    )


def pii_safe_context(req: ReturnInput) -> dict[str, Any]:
    return {
        "tax_year": req.tax_year,
        "province": req.province,
        "taxpayer_sin_masked": mask_sin(req.taxpayer.sin),
    }
