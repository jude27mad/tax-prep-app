import logging

from fastapi import APIRouter, FastAPI, HTTPException

from app.lifespan import build_application_lifespan
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.efile.service import (
    PrefileValidationError,
    pii_safe_context,
    prepare_xml_submission,
    record_transmit_outcome,
)
from app.efile.transmit import CircuitOpenError, EfileClient
from ..efile.records import EfileEnvelope, build_records
from ..core.models import ReturnCalc, ReturnInput
from ..core.tax_years._2024_alias import compute_return as compute_return_2024
from ..core.tax_years._2025_alias import compute_return as compute_return_2025
from ..core.validate.pre_submit import validate_return_input
from ..efile.serialize import serialize
from ..printout.t1_render import render_t1_pdf
from ..ui import router as ui_router

DEFAULT_TAX_YEAR = 2025
logger = logging.getLogger("tax_app")


async def _announce_default_tax_year(_: FastAPI) -> None:
    settings = get_settings()
    logger.info(
        "Tax App startup complete; default_tax_year=%s env=%s feature_efile_xml=%s feature_legacy_efile=%s",
        DEFAULT_TAX_YEAR,
        settings.efile_environment,
        settings.feature_efile_xml,
        settings.feature_legacy_efile,
    )


app = FastAPI(
    title="Tax Preparer App",
    description="Default year: 2025. Use /tax/2025/compute for current filings; /tax/2024/compute remains available for backfiling.",
    lifespan=build_application_lifespan("preparer", startup_hook=_announce_default_tax_year),
)
app.include_router(ui_router)
router = APIRouter()


class PrepareRequest(ReturnInput):
    pass


class PrintRequest(ReturnInput):
    out_path: str


class TransmitRequest(ReturnInput):
    endpoint: str | None = Field(default=None, alias="endpoint")
    software_id: str | None = None
    software_ver: str | None = None
    transmitter_id: str | None = None

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CertRunnerRequest(BaseModel):
    cases: list[ReturnInput]
    save_path: str


class CertRunnerResponse(BaseModel):
    saved_dir: str
    results: list[dict]


def _compute_for_year(req: ReturnInput) -> ReturnCalc:
    if req.tax_year == 2024:
        return compute_return_2024(req)
    if req.tax_year == 2025:
        return compute_return_2025(req)
    raise HTTPException(status_code=400, detail=f"Unsupported tax year {req.tax_year}")


@app.get("/health")
def health():
    settings = getattr(app.state, "settings", get_settings())
    schema_versions = getattr(app.state, "schema_versions", {})
    last_sbmt_ref_id = getattr(app.state, "last_sbmt_ref_id", None)
    return {
        "status": "ok",
        "default_tax_year": DEFAULT_TAX_YEAR,
        "build": {
            "version": settings.build_version,
            "sha": settings.build_sha,
            "efile_env": settings.efile_environment,
            "feature_efile_xml": settings.feature_efile_xml,
            "feature_legacy_efile": settings.feature_legacy_efile,
            "sbmt_ref_id_last": last_sbmt_ref_id,
        },
        "schemas": schema_versions,
    }


@app.post("/prepare")
def prepare(req: PrepareRequest):
    issues = validate_return_input(req)
    if issues:
        return {"ok": False, "issues": issues}
    calc = _compute_for_year(req)
    return {"ok": True, "calc": calc.model_dump()}


@app.post("/printout/t1")
def print_t1(req: PrintRequest):
    calc = _compute_for_year(req)
    path = render_t1_pdf(req.out_path, req, calc)
    return {"pdf": path}


@app.post("/prepare/efile")
@app.post("/efile/transmit")
async def prepare_efile(req: TransmitRequest):
    settings = getattr(app.state, "settings", get_settings())
    if not settings.feature_efile_xml:
        raise HTTPException(status_code=503, detail="EFILE XML feature flag disabled")

    if req.tax_year != 2025:
        raise HTTPException(status_code=400, detail="EFILE XML is only available for 2025 filings")
    if not settings.efile_window_open:
        raise HTTPException(status_code=503, detail="CRA EFILE window not yet open for 2025")

    issues = validate_return_input(req)
    if issues:
        raise HTTPException(status_code=400, detail=issues)

    calc = _compute_for_year(req)

    try:
        prepared = prepare_xml_submission(app, req, calc, endpoint_override=req.endpoint)
    except PrefileValidationError as exc:
        raise exc

    context = pii_safe_context(req)
    context["sbmt_ref_id"] = prepared.sbmt_ref_id
    logger.info("Prepared EFILE XML payload", extra={"submission": context})

    client = EfileClient(prepared.endpoint)
    try:
        response = await client.send(prepared.xml_bytes, content_type="application/xml")
    except CircuitOpenError as exc:
        logger.error("EFILE circuit open", extra={"submission": context, "error": str(exc)})
        raise HTTPException(status_code=503, detail="EFILE transmission circuit open") from exc
    except RuntimeError as exc:
        logger.error("EFILE transmission failed", extra={"submission": context, "error": str(exc)})
        raise HTTPException(status_code=502, detail="EFILE transmission failed") from exc

    logger.info(
        "Transmitted EFILE XML payload", extra={"submission": context, "digest": prepared.digest, "sbmt_ref_id": prepared.sbmt_ref_id}
    )
    record_transmit_outcome(app, prepared.digest, response)

    return {
        "digest": prepared.digest,
        "sbmt_ref_id": prepared.sbmt_ref_id,
        "envelope": {
            "software_id": prepared.envelope.software_id,
            "software_version": prepared.envelope.software_ver,
            "transmitter_id": prepared.envelope.transmitter_id,
            "environment": prepared.envelope.environment,
        },
        "response": response,
    }


@app.post("/legacy/efile")
async def legacy_efile(req: TransmitRequest):
    """Handle the legacy JSON-based EFILE transport.

    This path predates the XML/T619 submission flow implemented via
    :func:`prepare_efile`/``prepare_xml_submission`` and should only be exposed
    when the ``FEATURE_LEGACY_EFILE`` flag is enabled. Production integrations
    are expected to migrate to the XML pathway defined in ``app.efile.service``
    and ``app.efile.t619``.
    """
    settings = getattr(app.state, "settings", get_settings())
    if not settings.feature_legacy_efile:
        raise HTTPException(status_code=410, detail="Legacy EFILE disabled")

    issues = validate_return_input(req)
    if issues:
        raise HTTPException(status_code=400, detail=issues)
    calc = _compute_for_year(req)
    settings = getattr(app.state, "settings", get_settings())
    # The legacy JSON transport is normally disabled unless FEATURE_LEGACY_EFILE
    # is true. Prefer the XML/T619 workflow handled by prepare_efile.
    profile = settings.profile()
    envelope = EfileEnvelope(
        req.software_id or profile.software_id,
        req.software_ver or profile.software_version,
        req.transmitter_id or profile.transmitter_id,
        profile.environment,
    )
    payload = build_records(envelope, req, calc)
    data, digest = serialize(payload)
    endpoint = req.endpoint or profile.endpoint or "http://localhost:8000"
    client = EfileClient(endpoint)
    response = await client.send(data)
    return {"digest": digest, "response": response}


app.include_router(router)




