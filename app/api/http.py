from decimal import Decimal
import logging

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

from ..core.models import ReturnCalc, ReturnInput
from ..core.tax_years._2024_alias import compute_full_2024, compute_return as compute_return_2024
from ..core.tax_years._2025_alias import compute_full_2025, compute_return as compute_return_2025
from ..core.validate.pre_submit import validate_return_input
from ..efile.records import EfileEnvelope, build_records
from ..efile.serialize import serialize
from ..efile.transmit import EfileClient
from ..printout.t1_render import render_t1_pdf

DEFAULT_TAX_YEAR = 2025
logger = logging.getLogger("tax_app")

app = FastAPI(
    title="Tax Preparer App",
    description="Default year: 2025. Use /tax/2025/compute for current filings; /tax/2024/compute remains available for backfiling.",
)
router = APIRouter()


class PrepareRequest(ReturnInput):
    pass


def _compute_for_year(req: ReturnInput) -> ReturnCalc:
    if req.tax_year == 2024:
        return compute_return_2024(req)
    if req.tax_year == 2025:
        return compute_return_2025(req)
    raise HTTPException(status_code=400, detail=f"Unsupported tax year {req.tax_year}")


@app.on_event("startup")
async def _log_startup_default_year() -> None:
    logger.info("Tax App startup complete; default tax_year=%s", DEFAULT_TAX_YEAR)


@app.get("/health")
def health():
    return {"status": "ok", "default_tax_year": DEFAULT_TAX_YEAR}


@app.post("/prepare")
def prepare(req: PrepareRequest):
    issues = validate_return_input(req)
    if issues:
        return {"ok": False, "issues": issues}
    calc = _compute_for_year(req)
    return {"ok": True, "calc": calc.model_dump()}


class TransmitRequest(ReturnInput):
    software_id: str
    software_ver: str
    transmitter_id: str
    endpoint: str


@app.post("/efile/transmit")
async def efile_transmit(req: TransmitRequest):
    issues = validate_return_input(req)
    if issues:
        raise HTTPException(status_code=400, detail=issues)
    calc = _compute_for_year(req)
    env = EfileEnvelope(req.software_id, req.software_ver, req.transmitter_id)
    payload = build_records(env, req, calc)
    data, digest = serialize(payload)
    client = EfileClient(req.endpoint)
    logger.info(
        "Sending EFILE payload for tax_year=%s software_id=%s transmitter=%s",
        calc.tax_year,
        req.software_id,
        req.transmitter_id,
    )
    resp = await client.send(data)
    return {"digest": digest, "response": resp}


class PrintRequest(ReturnInput):
    out_path: str


@app.post("/printout/t1")
def print_t1(req: PrintRequest):
    calc = _compute_for_year(req)
    path = render_t1_pdf(req.out_path, calc.model_dump())
    return {"pdf": path}


@router.post("/tax/2024/compute")
def compute_2024_tax(payload: dict):
    try:
        ti = Decimal(str(payload["taxable_income"]))
        ni = Decimal(str(payload.get("net_income", payload["taxable_income"])))
        credits = {
            k: Decimal(str(v))
            for (k, v) in (payload.get("personal_credit_amounts") or {}).items()
        }
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Missing field: {exc}") from exc

    result = compute_full_2024(ti, ni, credits)
    return {
        "federal_tax": str(result.federal_tax),
        "federal_credits": str(result.federal_credits),
        "ontario_tax": str(result.provincial_tax),
        "ontario_credits": str(result.provincial_credits),
        "ontario_surtax": str(result.ontario_surtax),
        "ontario_health_premium": str(result.ontario_health_premium),
        "total_payable": str(result.total_payable),
    }


@router.post("/tax/2025/compute")
def compute_2025_tax(payload: dict):
    try:
        ti = Decimal(str(payload["taxable_income"]))
        ni = Decimal(str(payload.get("net_income", payload["taxable_income"])))
        credits = {
            k: Decimal(str(v))
            for (k, v) in (payload.get("personal_credit_amounts") or {}).items()
        }
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Missing field: {exc}") from exc

    result = compute_full_2025(ti, ni, credits)
    return {
        "federal_tax": str(result.federal_tax),
        "federal_credits": str(result.federal_credits),
        "ontario_tax": str(result.provincial_tax),
        "ontario_credits": str(result.provincial_credits),
        "ontario_surtax": str(result.ontario_surtax),
        "ontario_health_premium": str(result.ontario_health_premium),
        "total_payable": str(result.total_payable),
    }


app.include_router(router)
