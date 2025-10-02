import argparse
import csv
import json
import re
import sys
import textwrap
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, NotRequired, TypedDict

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parent.parent))


from fastapi import FastAPI

from app.config import get_settings
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError
from app.lifespan import build_application_lifespan

from app.tax.ca2025 import (
    FEDERAL_2025,
    FED_CREDIT_RATE,
    federal_bpa_2025,
    tax_from_brackets as fed_tax,
)
from app.tax.on2025 import (
    ON_BPA_2025,
    ON_CREDIT_RATE,
    health_premium_2025,
    surtax_2025,
    tax_from_brackets as on_tax,
)

app = FastAPI(
    title="Tax App",
    version="0.0.3",
    lifespan=build_application_lifespan("estimator"),
)

CPP_BASE_EXEMPTION = 3_500.0
CPP_YMPE_2025 = 71_300.0
CPP_YAMPE_2025 = 81_200.0
CPP_RATE_2025 = 0.0595
CPP2_RATE_2025 = 0.04
EI_MIE_2025 = 65_700.0
EI_RATE_2025 = 0.0164
_TOLERANCE = 0.05  # forgive minor payroll rounding
_CENT = Decimal("0.01")


def _to_decimal(value: float | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _round_cents(value: float | Decimal) -> float:
    return float(_to_decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP))




def _compute_tax_summary(income: float, rrsp: float, province: str) -> dict:
    taxable = max(0.0, income - max(rrsp, 0.0))

    federal_before = fed_tax(taxable, FEDERAL_2025)
    fed_bpa = federal_bpa_2025(taxable)
    federal_after = max(0.0, _round_cents(federal_before - FED_CREDIT_RATE * fed_bpa))

    ont_before = on_tax(taxable)
    ont_after_credits = max(0.0, _round_cents(ont_before - ON_CREDIT_RATE * ON_BPA_2025))
    on_surtax = surtax_2025(ont_after_credits)
    on_premium = health_premium_2025(taxable)
    ont_net = _round_cents(ont_after_credits + on_surtax + on_premium)

    total_net_tax = _round_cents(_to_decimal(federal_after) + _to_decimal(ont_net))

    return {
        "income": income,
        "rrsp": rrsp,
        "taxable_income": taxable,
        "federal": {
            "before_credits": federal_before,
            "bpa_used": fed_bpa,
            "after_credits": federal_after,
        },
        "ontario": {
            "before_credits": ont_before,
            "bpa_used": ON_BPA_2025,
            "after_credits": ont_after_credits,
            "surtax": on_surtax,
            "health_premium": on_premium,
            "net_provincial": ont_net,
        },
        "total_net_tax": total_net_tax,
    }


def _expected_cpp_contributions(income: float) -> tuple[float, float]:
    income_dec = _to_decimal(income)
    ympe = _to_decimal(CPP_YMPE_2025)
    base = _to_decimal(CPP_BASE_EXEMPTION)
    pensionable = max(Decimal("0"), min(income_dec, ympe) - base)
    cpp_regular = _round_cents(pensionable * _to_decimal(CPP_RATE_2025))

    yamp = _to_decimal(CPP_YAMPE_2025)
    additional_earnings = max(Decimal("0"), min(income_dec, yamp) - ympe)
    cpp_additional = _round_cents(additional_earnings * _to_decimal(CPP2_RATE_2025))

    return cpp_regular, cpp_additional


def _expected_ei_contribution(income: float) -> float:
    income_dec = _to_decimal(income)
    mie = _to_decimal(EI_MIE_2025)
    rate = _to_decimal(EI_RATE_2025)
    return _round_cents(min(income_dec, mie) * rate)


def _within_limit(actual: float, maximum: float) -> bool:
    return actual <= maximum + _TOLERANCE


def _contribution_status(actual: float, maximum: float) -> str:
    if actual > maximum + _TOLERANCE:
        return "over"
    if actual < max(0.0, maximum - _TOLERANCE):
        return "under"
    return "ok"


@app.get("/health")
def health():
    settings = getattr(app.state, "settings", get_settings())
    schema_versions = getattr(app.state, "schema_versions", {})
    last_sbmt_ref_id = getattr(app.state, "last_sbmt_ref_id", None)
    return {"ok": True, "build": {"version": settings.build_version, "sha": settings.build_sha, "feature_efile_xml": settings.feature_efile_xml, "sbmt_ref_id_last": last_sbmt_ref_id}, "schemas": schema_versions}


@app.get("/tax/estimate")
def estimate(income: float, rrsp: float = 0.0, province: str = "ON"):
    return _compute_tax_summary(income, rrsp, province)


class T4EstimateRequest(BaseModel):
    box14: float = Field(
        ...,
        ge=0,
        description="Employment income (T4 box 14)",
        validation_alias=AliasChoices("box14", "box14_employment_income"),
    )
    box22: float = Field(
        ...,
        ge=0,
        description="Income tax deducted (T4 box 22)",
        validation_alias=AliasChoices("box22", "box22_tax_withheld"),
    )
    box16: float = Field(
        ...,
        ge=0,
        description="CPP contributions (T4 box 16)",
        validation_alias=AliasChoices("box16", "box16_cpp"),
    )
    box16a: float = Field(
        0.0,
        ge=0,
        description="Second CPP contributions (T4 box 16A)",
        validation_alias=AliasChoices("box16a", "box16A", "box16A_cpp2", "box16_cpp2", "box16a_cpp2"),
    )
    box18: float = Field(
        ...,
        ge=0,
        description="EI premiums (T4 box 18)",
        validation_alias=AliasChoices("box18", "box18_ei"),
    )
    rrsp: float = Field(
        0.0,
        ge=0,
        description="RRSP deductions claimed",
        validation_alias=AliasChoices("rrsp", "rrsp_deduction"),
    )
    province: str = Field("ON", description="Province code, defaults to ON")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


@app.post("/tax/t4")
@app.post("/t4/estimate")
def estimate_from_t4(payload: T4EstimateRequest):
    tax_summary = _compute_tax_summary(payload.box14, payload.rrsp, payload.province)
    total_tax = tax_summary["total_net_tax"]
    total_tax_dec = _to_decimal(total_tax)
    withheld = _round_cents(payload.box22)
    balance = _round_cents(total_tax_dec - _to_decimal(withheld))

    cpp_max, cpp2_max = _expected_cpp_contributions(payload.box14)
    ei_max = _expected_ei_contribution(payload.box14)

    cpp_actual = _round_cents(payload.box16)
    cpp2_actual = _round_cents(payload.box16a)
    ei_actual = _round_cents(payload.box18)

    return {
        "inputs": {
            "box14": payload.box14,
            "box22": payload.box22,
            "box16": payload.box16,
            "box16A": payload.box16a,
            "box18": payload.box18,
            "rrsp": payload.rrsp,
            "province": payload.province,
        },
        "tax": tax_summary,
        "total_tax": total_tax,
        "withholding": withheld,
        "balance": balance,
        "balance_positive_is_amount_owing": balance > 0,
        "is_refund": balance < 0,
        "cpp": {
            "reported": cpp_actual,
            "maximum_allowed": cpp_max,
            "within_limit": _within_limit(cpp_actual, cpp_max),
            "status": _contribution_status(cpp_actual, cpp_max),
        },
        "cpp2": {
            "reported": cpp2_actual,
            "maximum_allowed": cpp2_max,
            "within_limit": _within_limit(cpp2_actual, cpp2_max),
            "status": _contribution_status(cpp2_actual, cpp2_max),
        },
        "ei": {
            "reported": ei_actual,
            "maximum_allowed": ei_max,
            "within_limit": _within_limit(ei_actual, ei_max),
            "status": _contribution_status(ei_actual, ei_max),
        },
    }

BASE_DIR = Path(__file__).resolve().parent.parent
INBOX_DIR = BASE_DIR / "inbox"

CLI_SUBMIT_FIELDS = {"box14", "box22", "box16", "box16a", "box18", "rrsp", "province"}
CLI_NUMERIC_FIELDS = {"box14", "box22", "box16", "box16a", "box18", "rrsp"}
CLI_INT_FIELDS = {"num_dependents"}
CLI_BOOL_FIELDS = {"dependents"}
CLI_SAVE_ORDER = [
    "full_name",
    "province",
    "box14",
    "box22",
    "box16",
    "box16a",
    "box18",
    "rrsp",
    "filing_status",
    "dependents",
    "num_dependents",
]


class PromptStep(TypedDict):
    field: str
    required: NotRequired[bool]

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "full_name": ("full name", "name", "legal name", "taxpayer name"),
    "province": ("province", "province code", "province of residence", "prov", "residence province"),
    "box14": ("box14", "box 14", "employment income", "wages", "salary", "income", "t4 box 14"),
    "box22": ("box22", "box 22", "tax deducted", "tax withheld", "withholding", "income tax deducted", "t4 box 22"),
    "box16": ("box16", "box 16", "cpp contributions", "cpp", "t4 box 16"),
    "box16a": ("box16a", "box 16a", "cpp2", "second cpp", "additional cpp", "additional cpp contributions", "t4 box 16a"),
    "box18": ("box18", "box 18", "ei premiums", "ei", "employment insurance"),
    "rrsp": ("rrsp", "rrsp deduction", "rrsp contributions", "rrsp claimed"),
    "filing_status": ("filing status", "status"),
    "dependents": ("dependents", "has dependents", "dependents?"),
    "num_dependents": ("dependents count", "dependents number", "number of dependents"),
}

_KEY_VALUE_RE = re.compile(r"^\s*([^#:=]+?)\s*(?:[:=]|->)\s*(.+)$")
_ALIAS_LOOKUP: dict[str, str] = {}
_ALIAS_MATCHERS: list[tuple[str, str]] = []

for canonical, aliases in _FIELD_ALIASES.items():
    all_aliases = (canonical, *aliases)
    for alias in all_aliases:
        normalized = re.sub(r"[^a-z0-9]", "", alias.lower())
        if normalized and normalized not in _ALIAS_LOOKUP:
            _ALIAS_LOOKUP[normalized] = canonical
        cleaned = " ".join(alias.lower().split())
        if cleaned:
            _ALIAS_MATCHERS.append((cleaned, canonical))

# Deduplicate while keeping longest aliases first so "box 16a" matches before "box 16"
_ALIAS_MATCHERS = sorted({alias: canonical for alias, canonical in _ALIAS_MATCHERS}.items(), key=lambda item: len(item[0]), reverse=True)

_HELP_TOPICS: dict[str, str] = {
    "overview": textwrap.dedent(
        """
        Guided mode walks you through the T4 estimator without typing Python syntax.
        The flow is simple: we load any saved answers, ask for anything missing,
        compute the result, and save a fresh copy for next time. Type `?` during a prompt
        to open the matching help topic.
        """
    ).strip(),
    "wizard": textwrap.dedent(
        """
        The wizard asks for: your name (optional), province, and the T4 boxes (14, 22, 16, 16A, 18),
        plus RRSP deductions if you have them. Press Enter to keep the current value, or enter a new one.
        You can type amounts like 57k, $12,345.67, or 12345. The app cleans them automatically.
        """
    ).strip(),
    "box14": textwrap.dedent(
        """
        Box 14 is the employment income on your T4. Enter the number printed in box 14.
        You can paste it directly, or type shorthand such as 85k or $42,100.
        """
    ).strip(),
    "box22": textwrap.dedent(
        """
        Box 22 is the total income tax deducted at source. It is used to determine your refund or balance due.
        Enter the full amount from the slip, including cents if available.
        """
    ).strip(),
    "box16": textwrap.dedent(
        """
        Box 16 is your CPP contributions. Enter the value exactly as it appears.
        We compare it to the annual maximum to flag under- or over-contributions.
        """
    ).strip(),
    "box16a": textwrap.dedent(
        """
        Box 16A is the additional CPP (CPP2) amount. Only some employees have this.
        If your slip does not show a figure, press Enter to skip it.
        """
    ).strip(),
    "box18": textwrap.dedent(
        """
        Box 18 is Employment Insurance (EI) premiums. Enter the value from your T4 so the
        app can compare it to the EI maximum.
        """
    ).strip(),
    "rrsp": textwrap.dedent(
        """
        RRSP deductions reduce taxable income. Use the total from your official receipts (March to
        December plus the first 60 days of the next year) and stay within the deduction limit on your
        latest Notice of Assessment. You can always claim less than you contributed and carry the rest
        forward.
        """
    ).strip(),
    "province": textwrap.dedent(
        """
        Enter the two-letter province or territory code for where you live on December 31 (example: ON, BC, QC).
        It affects the provincial tax and credits that are applied in the calculation.
        """
    ).strip(),
    "full_name": textwrap.dedent(
        """
        Your name only appears on the PDF or summary output. It is optional but handy if you keep multiple runs.
        """
    ).strip(),
    "dependents": textwrap.dedent(
        """
        Dependents are family members (children, parents, others) you support. This assistant notes the count for
        checklist purposes but does not yet calculate dependent credits. Future releases can use it.
        """
    ).strip(),
    "checklist": textwrap.dedent(
        """
        The checklist lists documents that are commonly needed before filing: personal info, T4 slips, RRSP receipts,
        prior assessments, and anything related to dependents or deductions you plan to claim.
        """
    ).strip(),
    "t4_slip": textwrap.dedent(
        """
        T4 slips report employment income and payroll deductions for each employer. Collect every slip
        you received. The wizard needs boxes 14 (income), 22 (tax withheld), 16/16A (CPP amounts), and
        18 (EI premiums). Note any other boxes (union dues, taxable benefits, RPP contributions) for the
        full return even if the quick estimator ignores them today.
        """
    ).strip(),
    "t4a_slip": textwrap.dedent(
        """
        T4A slips cover other income such as pensions, self-employed commissions, scholarships, or
        research grants. Record the boxes that apply to you (commonly 020, 048, 105, 107). The estimator
        focuses on employment income now, but keep these figures ready for the complete filing or future
        updates.
        """
    ).strip(),
    "t5_slip": textwrap.dedent(
        """
        T5 slips summarize investment income from banks and brokerages. Box 10 holds interest, boxes 12 and
        13 cover eligible and other dividends, and boxes 15-18 show foreign income and taxes paid. Track
        currency codes and withholding because they matter for the foreign tax credit.
        """
    ).strip(),
    "tuition_credit": textwrap.dedent(
        """
        Tuition credits come from the T2202 or TL11 slips. Capture the eligible tuition amount, number of
        months of full-time or part-time study, and any unused credits you are carrying forward. The wizard
        does not deduct tuition yet, but the checklist will remind you to apply the credit when you file.
        """
    ).strip(),
    "canada_workers_benefit": textwrap.dedent(
        """
        The Canada Workers Benefit (CWB) is a refundable credit for low-income workers. Eligibility depends
        on earned income, family status, and residency. Keep your net income estimate, marital status, and
        spouse or partner income nearby so you can check the CRA tables or schedule when you complete the
        full return.
        """
    ).strip(),
    "topics": textwrap.dedent(
        """
        Available help topics include: overview, wizard, box14, box22, box16, box16a, box18, rrsp, province,
        full_name, dependents, checklist. Run `python -m app.main help <topic>` to open one of them.
        """
    ).strip(),
}

_HELP_TOPIC_ALIASES: dict[str, str] = {}
for key in _HELP_TOPICS:
    _HELP_TOPIC_ALIASES[re.sub(r"[^a-z0-9]", "", key.lower())] = key
_HELP_TOPIC_ALIASES[""] = "overview"
_HELP_TOPIC_ALIASES["start"] = "overview"
_HELP_TOPIC_ALIASES["help"] = "overview"
_HELP_TOPIC_ALIASES["list"] = "topics"
_HELP_TOPIC_ALIASES["topic"] = "topics"
for canonical, aliases in _FIELD_ALIASES.items():
    if canonical in _HELP_TOPICS:
        _HELP_TOPIC_ALIASES.setdefault(re.sub(r"[^a-z0-9]", "", canonical.lower()), canonical)
        for alias in aliases:
            normalized = re.sub(r"[^a-z0-9]", "", alias.lower())
            _HELP_TOPIC_ALIASES.setdefault(normalized, canonical)

for alias, canonical in {
    "t4": "t4_slip",
    "t4slip": "t4_slip",
    "employmentincome": "t4_slip",
    "t4a": "t4a_slip",
    "t4aslip": "t4a_slip",
    "pensionincome": "t4a_slip",
    "t5": "t5_slip",
    "t5slip": "t5_slip",
    "investmentincome": "t5_slip",
    "tuition": "tuition_credit",
    "education": "tuition_credit",
    "cwb": "canada_workers_benefit",
    "workersbenefit": "canada_workers_benefit",
}.items():
    _HELP_TOPIC_ALIASES.setdefault(alias, canonical)

_CHECKLIST_BASE = [
    "Government-issued photo ID and your Social Insurance Number.",
    "Current address and contact information.",
    "T4 slips for each employer.",
    "Notices of Assessment from previous years (for RRSP room reference).",
]

_WIZARD_SEQUENCE: list[PromptStep] = [
    {"field": "full_name", "required": False},
    {"field": "province", "required": False},
    {"field": "box14", "required": True},
    {"field": "box22", "required": True},
    {"field": "box16", "required": True},
    {"field": "box16a", "required": False},
    {"field": "box18", "required": True},
    {"field": "rrsp", "required": False},
]

_FIELD_METADATA: dict[str, dict[str, Any]] = {
    "full_name": {
        "label": "Your full legal name",
        "hint": "Optional, used for the summary header.",
        "help_topic": "full_name",
    },
    "province": {
        "label": "Province or territory (two-letter code)",
        "hint": "Example: ON, BC, AB, QC.",
        "default": "ON",
        "help_topic": "province",
    },
    "box14": {
        "label": "Employment income — T4 box 14",
        "hint": "Type the value from the slip. Use numbers like 57000 or 57k.",
        "help_topic": "box14",
    },
    "box22": {
        "label": "Income tax deducted — T4 box 22",
        "hint": "This is the tax withheld at source.",
        "help_topic": "box22",
    },
    "box16": {
        "label": "CPP contributions — T4 box 16",
        "hint": "Used to check against the annual CPP maximum.",
        "help_topic": "box16",
    },
    "box16a": {
        "label": "Additional CPP (CPP2) — T4 box 16A",
        "hint": "Only present for some employees. Press Enter to skip if blank.",
        "default": 0.0,
        "help_topic": "box16a",
    },
    "box18": {
        "label": "EI premiums — T4 box 18",
        "hint": "Used to compare against the EI maximum.",
        "help_topic": "box18",
    },
    "rrsp": {
        "label": "RRSP deductions you plan to claim",
        "hint": "Enter zero if you are not claiming RRSP deductions.",
        "default": 0.0,
        "help_topic": "rrsp",
    },
}

NUM_SUFFIXES = {
    "k": 1_000.0,
    "m": 1_000_000.0,
    "b": 1_000_000_000.0,
}


def _normalize_key(raw: str) -> str:
    return re.sub(r"[^a-z0-9]", "", raw.lower())


def _friendly_path(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _display_value(field: str, value: Any) -> str:
    if value is None:
        return ""
    if field in CLI_NUMERIC_FIELDS:
        return _format_currency(float(value))
    if field in CLI_BOOL_FIELDS:
        return "yes" if bool(value) else "no"
    return str(value)


def _parse_number(text: str) -> float:
    cleaned = text.strip().lower()
    if not cleaned:
        raise ValueError("Please enter a number.")
    multiplier = 1.0
    suffix = cleaned[-1]
    if suffix in NUM_SUFFIXES:
        multiplier = NUM_SUFFIXES[suffix]
        cleaned = cleaned[:-1]
    cleaned = cleaned.replace("$", "").replace(",", "").replace(" ", "").replace("_", "")
    cleaned = cleaned.replace("−", "-").replace("–", "-")
    if cleaned in {"", "-", "."}:
        raise ValueError("Please enter a number.")
    try:
        return float(cleaned) * multiplier
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Could not understand number '{text}'.") from exc


def _parse_bool(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in {"y", "yes", "true", "1", "ok", "sure"}:
        return True
    if lowered in {"n", "no", "false", "0"}:
        return False
    raise ValueError("Enter yes or no.")


def _coerce_for_field(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in CLI_NUMERIC_FIELDS:
        if isinstance(value, (int, float)):
            return _round_cents(float(value))
        if isinstance(value, Decimal):
            return _round_cents(float(value))
        return _round_cents(_parse_number(str(value)))
    if field in CLI_INT_FIELDS:
        if isinstance(value, (int, float)):
            return int(round(float(value)))
        return int(round(_parse_number(str(value))))
    if field in CLI_BOOL_FIELDS:
        if isinstance(value, bool):
            return value
        return _parse_bool(str(value))
    if field == "province":
        return str(value).strip().upper()
    return str(value).strip()


def _canonical_key(raw: str) -> str | None:
    normalized = _normalize_key(raw)
    return _ALIAS_LOOKUP.get(normalized)


def _canonicalize_data(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    flattened = dict(raw)
    # Common pattern: {"t4": {...}}
    t4_block = flattened.get("t4")
    if isinstance(t4_block, dict):
        flattened = {**flattened, **t4_block}
    result: dict[str, Any] = {}
    for key, value in flattened.items():
        canonical = _canonical_key(str(key))
        if not canonical:
            continue
        try:
            coerced = _coerce_for_field(canonical, value)
        except ValueError as exc:
            raise ValueError(f"Field '{key}': {exc}") from exc
        if coerced is not None:
            result[canonical] = coerced
    return result


def _parse_freeform_text(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _KEY_VALUE_RE.match(line)
        if match:
            raw_key, raw_value = match.groups()
            canonical = _canonical_key(raw_key)
            if canonical:
                result[canonical] = _coerce_for_field(canonical, raw_value.strip())
            continue
        lowered = " ".join(line.lower().split())
        for alias, canonical in _ALIAS_MATCHERS:
            if lowered.startswith(alias):
                remainder = line[len(alias):].lstrip(" :=-")
                if not remainder:
                    continue
                result[canonical] = _coerce_for_field(canonical, remainder.strip())
                break
    return result


def _read_data_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".toml":
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
            return _canonicalize_data(raw)
        if suffix == ".json":
            with path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
            return _canonicalize_data(raw)
        if suffix == ".txt":
            text = path.read_text(encoding="utf-8")
            return _parse_freeform_text(text)
        if suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                try:
                    row = next(reader)
                except StopIteration:
                    return {}
            return _canonicalize_data(row)
    except ValueError as exc:
        raise ValueError(f"{path.name}: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive catch for file decoding issues
        raise ValueError(f"{path.name}: {exc}") from exc
    return {}


def _default_candidate_paths() -> tuple[list[Path], list[Path]]:
    supported: list[Path] = []
    for name in ("user_data.toml", "user_data.json", "user_data.txt"):
        candidate = BASE_DIR / name
        if candidate.exists():
            supported.append(candidate)
    unsupported: list[Path] = []
    if INBOX_DIR.exists() and INBOX_DIR.is_dir():
        for item in sorted(INBOX_DIR.iterdir()):
            if not item.is_file():
                continue
            suffix = item.suffix.lower()
            if suffix in {".toml", ".json", ".txt", ".csv"}:
                supported.append(item)
            elif suffix in {".xlsx", ".pdf"}:
                unsupported.append(item)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_supported: list[Path] = []
    for path in supported:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique_supported.append(path)
    return unique_supported, unsupported


def _load_inputs(path_value: str | None) -> tuple[dict[str, Any], Path | None, list[Path], list[str]]:
    errors: list[str] = []
    unsupported: list[Path] = []
    candidates: list[Path] = []
    if path_value:
        candidate = Path(path_value).expanduser()
        if candidate.exists():
            candidates.append(candidate)
        else:
            errors.append(f"Could not find {candidate}.")
    else:
        candidates, unsupported = _default_candidate_paths()
    for candidate in candidates:
        try:
            data = _read_data_file(candidate)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if data:
            return data, candidate, unsupported, errors
    return {}, None, unsupported, errors


def _prompt_for_missing_fields(data: dict[str, Any]) -> dict[str, Any]:
    working = {key: _coerce_for_field(key, value) for key, value in data.items()}
    required_steps = [meta for meta in _WIZARD_SEQUENCE if meta["field"] in _FIELD_METADATA]
    steps_to_run = [
        meta
        for meta in required_steps
        if bool(meta.get("required", False)) or not _has_value(working.get(meta["field"]))
    ]
    total = len(steps_to_run)
    if total == 0:
        return working
    for index, meta in enumerate(steps_to_run, start=1):
        field = meta["field"]
        required = bool(meta.get("required", False))
        current = working.get(field)
        value = _ask_field(field, current, index, total, required)
        if value is None and required:
            continue
        working[field] = value
    return working


def _ask_field(field: str, current: Any, step: int, total: int, required: bool) -> Any:
    meta = _FIELD_METADATA[field]
    label = meta["label"]
    hint = meta.get("hint")
    default = meta.get("default")
    print(f"\n[{step}/{total}] {label}")
    if hint:
        print(f"  {hint}")
    if _has_value(current):
        print(f"  Current value: {_display_value(field, current)}")
    if default is not None and not _has_value(current):
        print(f"  Default: {_display_value(field, default)}")
    prompt = "  -> "
    while True:
        raw = input(prompt).strip()
        if raw == "?":
            _print_help_topic(meta.get("help_topic", field))
            continue
        if not raw:
            if _has_value(current):
                return current
            if default is not None:
                return _coerce_for_field(field, default)
            if not required:
                return None
            print("  This field is required. Please enter a value or type ? for help.")
            continue
        try:
            return _coerce_for_field(field, raw)
        except ValueError as exc:
            print(f"  {exc}")


def _print_help_topic(topic: str | None) -> None:
    key = _normalize_key(topic or "")
    resolved = _HELP_TOPIC_ALIASES.get(key)
    if resolved is None:
        print("\nNo help topic found. Try one of:")
        _print_help_index()
        return
    if resolved == "topics":
        _print_help_index()
        return
    message = _HELP_TOPICS.get(resolved)
    if not message:
        print("\nHelp topic not available yet.")
        return
    print("\n" + message + "\n")


def _print_help_index() -> None:
    print("\nAvailable help topics:")
    for key in sorted(_HELP_TOPICS):
        if key == "topics":
            continue
        print(f"  - {key}")
    print("Use `python -m app.main help <topic>` to open one.\n")


def _print_checklist(data: dict[str, Any] | None = None) -> None:
    data = data or {}
    items = list(_CHECKLIST_BASE)
    if _has_value(data.get("rrsp")) and float(data.get("rrsp", 0.0)) > 0.0:
        items.append("RRSP contribution receipts.")
    if _has_value(data.get("dependents")) or int(data.get("num_dependents") or 0) > 0:
        items.append("Information for dependents (birthdates, childcare or disability receipts).")
    items.append("A folder to store the generated PDF/summary for your records.")
    print("\nFiling checklist:")
    for item in items:
        print(f"  - {item}")
    print()


def _format_currency(value: float | Decimal) -> str:
    return f"${_round_cents(value):,.2f}"


def _summarize_changes(before: dict[str, Any], after: dict[str, Any]) -> None:
    keys = [key for key in CLI_SAVE_ORDER if key in before or key in after]
    changes = []
    for key in keys:
        if before.get(key) != after.get(key):
            changes.append((key, before.get(key), after.get(key)))
    if not changes:
        if before:
            print("\nNo changes from the saved answers.")
        return
    print("\nUpdated answers:")
    for key, old, new in changes:
        before_text = _display_value(key, old) or "<empty>"
        after_text = _display_value(key, new) or "<empty>"
        print(f"  - {key}: {before_text} -> {after_text}")


def _save_user_data(data: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    for key in CLI_SAVE_ORDER:
        value = data.get(key)
        if value is None:
            continue
        if key in CLI_NUMERIC_FIELDS:
            lines.append(f"{key} = {_round_cents(float(value)):.2f}")
        elif key in CLI_BOOL_FIELDS:
            lines.append(f"{key} = {'true' if bool(value) else 'false'}")
        elif key in CLI_INT_FIELDS:
            lines.append(f"{key} = {int(value)}")
        else:
            escaped = str(value).replace("\"", "\\\"")
            lines.append(f"{key} = \"{escaped}\"")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nSaved your answers to {_friendly_path(path)}")


def _print_summary(payload: T4EstimateRequest, outcome: dict[str, Any]) -> None:
    print("\nSummary:")
    print("--------")
    print(f"Employment income (box 14): {_format_currency(payload.box14)}")
    print(f"Tax withheld (box 22): {_format_currency(payload.box22)}")
    print(f"CPP reported (box 16): {_format_currency(payload.box16)} — status: {outcome['cpp']['status']}")
    print(f"CPP2 reported (box 16A): {_format_currency(payload.box16a)} — status: {outcome['cpp2']['status']}")
    print(f"EI premiums (box 18): {_format_currency(payload.box18)} — status: {outcome['ei']['status']}")
    print(f"RRSP deduction: {_format_currency(payload.rrsp)}")
    print(f"Province: {payload.province}")
    print(
        f"Federal tax after credits: {_format_currency(outcome['tax']['federal']['after_credits'])}"
    )
    print(
        f"Ontario tax (after surtax/premium): {_format_currency(outcome['tax']['ontario']['net_provincial'])}"
    )
    print(f"Total tax owing: {_format_currency(outcome['total_tax'])}")
    print(f"Withholding applied: {_format_currency(outcome['withholding'])}")
    balance = outcome["balance"]
    if outcome.get("is_refund"):
        print(f"Expected refund: {_format_currency(abs(balance))}")
    elif balance > 0:
        print(f"Balance owing: {_format_currency(balance)}")
    else:
        print("No balance owing or refund detected.")


def _run_wizard(data_path: str | None, allow_save: bool) -> None:
    original, source, unsupported, errors = _load_inputs(data_path)
    print("\nTax App guided mode")
    print("===================")
    if errors:
        for message in errors:
            print(f"NOTE: {message}")
    if source:
        print(f"Loaded saved answers from {_friendly_path(source)}")
    else:
        print("No saved answers found; we will collect everything now.")
    if unsupported:
        print("Files in inbox/ that could not be imported automatically (open them and type the values):")
        for item in unsupported:
            print(f"  - {_friendly_path(item)}")
    answers = _prompt_for_missing_fields(original)
    payload_data = {key: value for key, value in answers.items() if key in CLI_SUBMIT_FIELDS and value is not None}
    try:
        payload = T4EstimateRequest.model_validate(payload_data)
    except ValidationError as exc:
        print("\nThere was a problem with the answers provided:")
        for error in exc.errors():
            location = " -> ".join(str(part) for part in error.get("loc", ("value",)))
            print(f"  - {location}: {error.get('msg')}")
        sys.exit(1)
    result = estimate_from_t4(payload)
    _print_summary(payload, result)
    _summarize_changes(original, answers)
    if allow_save:
        _save_user_data(answers, BASE_DIR / "user_data.toml")
    else:
        print("\nSkipped saving because --no-save was used.")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tax-app",
        description="Guided assistant for the Tax App T4 estimator.",
    )
    parser.add_argument("command", nargs="?", default="wizard", choices=["wizard", "help", "checklist"], help="Action to perform.")
    parser.add_argument("topic", nargs="?", help="Help topic or (for checklist) focus area.")
    parser.add_argument("--data", help="Path to a TOML/JSON/CSV/TXT file with answers.")
    parser.add_argument("--no-save", action="store_true", help="Do not update user_data.toml after running.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.command == "help":
        _print_help_topic(args.topic)
        return
    if args.command == "checklist":
        data, _, _, _ = _load_inputs(args.data)
        _print_checklist(data)
        return
    _run_wizard(args.data, allow_save=not args.no_save)


if __name__ == "__main__":
    main()
