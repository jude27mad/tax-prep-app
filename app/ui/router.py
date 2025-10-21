from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.datastructures import UploadFile as StarletteUploadFile  # for type-narrowing form inputs

from app.config import Settings, get_settings
from app.core.models import ReturnInput
from app.core.validate.pre_submit import validate_return_input
from app.efile.gating import build_transmit_gate
from app.ui import slip_ingest
from app.wizard import (
    BASE_DIR,
    CLI_BOOL_FIELDS,
    CLI_NUMERIC_FIELDS,
    CLI_SAVE_ORDER,
    CLI_SUBMIT_FIELDS,
    T4EstimateRequest,
    coerce_for_field,
    delete_profile,
    estimate_from_t4,
    get_active_profile,
    list_profiles,
    list_trash,
    load_profile,
    rename_profile,
    restore_profile,
    save_profile_data,
    set_active_profile,
    slugify,
)

router = APIRouter(prefix="/ui", tags=["ui"])

UI_ROOT = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(UI_ROOT / "templates"))
STATIC_ROOT = UI_ROOT / "static"
PROFILE_DRAFTS_ROOT = BASE_DIR / "profiles"

FORM_STEPS: list[dict[str, str]] = [
    {"slug": "identity", "label": "Identity"},
    {"slug": "slips", "label": "Slips"},
    {"slug": "deductions", "label": "Deductions"},
    {"slug": "review", "label": "Review"},
    {"slug": "transmit", "label": "Print/Transmit"},
]
FORM_STEP_SLUGS = {step["slug"] for step in FORM_STEPS}
DEFAULT_FORM_STEP = FORM_STEPS[0]["slug"]
AUTOSAVE_INTERVAL_MS = 20000


@router.get("/static/{path:path}", name="ui_static")
async def serve_ui_static(path: str) -> FileResponse:
    target_path = (STATIC_ROOT / path).resolve()
    try:
        target_path.relative_to(STATIC_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Static asset not found") from exc
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail="Static asset not found")
    return FileResponse(target_path)


FIELD_METADATA: dict[str, dict[str, Any]] = {
    "full_name": {"label": "Full name", "optional": True, "placeholder": "Optional"},
    "province": {
        "label": "Province",
        "optional": True,
        "placeholder": "ON, BC, AB...",
    },
    "box14": {
        "label": "Employment income (T4 box 14)",
        "help": "Total employment income reported on the T4.",
        "inputmode": "decimal",
    },
    "box22": {
        "label": "Income tax deducted (T4 box 22)",
        "help": "Federal and provincial income tax withheld at source.",
        "inputmode": "decimal",
    },
    "box16": {
        "label": "CPP contributions (T4 box 16)",
        "inputmode": "decimal",
    },
    "box16a": {
        "label": "CPP2 contributions (T4 box 16A)",
        "optional": True,
        "inputmode": "decimal",
    },
    "box18": {
        "label": "EI premiums (T4 box 18)",
        "inputmode": "decimal",
    },
    "rrsp": {
        "label": "RRSP deductions claimed",
        "optional": True,
        "default": 0.0,
        "inputmode": "decimal",
    },
    "filing_status": {
        "label": "Filing status",
        "optional": True,
        "placeholder": "Single, married, etc.",
    },
    "dependents": {
        "label": "Have dependents?",
        "optional": True,
        "input_type": "checkbox",
    },
    "num_dependents": {
        "label": "Number of dependents",
        "optional": True,
        "inputmode": "numeric",
        "min": 0,
    },
}


def _format_currency(value: float | int) -> str:
    return f"${value:,.2f}"


def _resolve_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return get_settings()


def _transmit_gate_context(state: dict[str, Any], settings: Settings) -> dict[str, Any]:
    gate = build_transmit_gate(settings=settings)
    selected_year = str(state.get("tax_year", ""))
    entry = gate.get(selected_year, {"allowed": False, "message": ""})
    allowed = bool(entry.get("allowed"))
    message = str(entry.get("message", "")) if not allowed else ""
    years = sorted(int(year) for year in gate.keys())
    return {
        "supported_tax_years": years,
        "efile_transmit_gate": gate,
        "efile_selected_year_allowed": allowed,
        "efile_selected_year_message": message,
    }


def _friendly_profile_path(slug: str) -> str:
    profile_path = BASE_DIR / "profiles" / f"{slug}.toml"
    try:
        return str(profile_path.relative_to(BASE_DIR))
    except ValueError:
        return str(profile_path)


def _form_text(val: Any) -> str:
    if isinstance(val, StarletteUploadFile):
        return val.filename or ""
    if val is None:
        return ""
    return str(val)


def _extract_form_data(form: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    data: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for field in CLI_SAVE_ORDER:
        if field in CLI_BOOL_FIELDS:
            data[field] = bool(form.get(field))
            continue
        raw_value = form.get(field)
        if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
            if isinstance(raw_value, StarletteUploadFile):
                data[field] = None
                continue
            data[field] = None
            continue
        try:
            data[field] = coerce_for_field(field, raw_value)
        except ValueError as exc:
            errors[field] = str(exc)
    return data, errors


def _build_preview(data: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    payload = {key: data.get(key) for key in CLI_SUBMIT_FIELDS if data.get(key) is not None}
    if not payload:
        return None, []
    try:
        model = T4EstimateRequest.model_validate(payload)
    except ValidationError as exc:
        messages = [
            " -> ".join(str(part) for part in err.get("loc", ("value",))) + ": " + err.get("msg", "invalid")
            for err in exc.errors()
        ]
        return None, messages
    try:
        result = estimate_from_t4(model)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return None, [detail]
    return result, []


def _profile_messages(request: Request) -> list[str]:
    messages: list[str] = []
    params = request.query_params
    if params.get("saved") == "1":
        messages.append("Profile saved successfully.")
    if params.get("created") == "1":
        messages.append("Profile created; fill in the form to get a preview.")
    if params.get("restored") == "1":
        messages.append("Profile restored from trash.")
    if params.get("renamed") == "1":
        messages.append("Profile renamed.")
    return messages


def _profile_context(slug: str, data: dict[str, Any], errors: dict[str, str] | None = None) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    error_map = errors or {}
    for name in CLI_SAVE_ORDER:
        meta = FIELD_METADATA.get(name, {})
        value = data.get(name)
        if value is None and "default" in meta:
            value = meta["default"]
        fields.append(
            {
                "name": name,
                "label": meta.get("label", name.replace("_", " ").title()),
                "value": value,
                "optional": meta.get("optional", False),
                "input_type": meta.get("input_type", "number" if name in CLI_NUMERIC_FIELDS else "text"),
                "inputmode": meta.get("inputmode"),
                "placeholder": meta.get("placeholder"),
                "min": meta.get("min"),
                "error": error_map.get(name),
                "help": meta.get("help"),
            }
        )
    preview, preview_errors = _build_preview(data)
    trash_entries = [path for path in list_trash(slug)]
    trash_entries.sort()
    return {
        "profile_slug": slug,
        "profile_path": _friendly_profile_path(slug),
        "fields": fields,
        "preview": preview,
        "preview_errors": preview_errors,
        "format_currency": _format_currency,
        "trash_count": len(trash_entries),
    }


def _blank_slip_state(index: int = 0) -> dict[str, Any]:
    return {
        "index": index,
        "employment_income": "",
        "tax_deducted": "",
        "cpp_contrib": "",
        "ei_premiums": "",
        "pensionable_earnings": "",
        "insurable_earnings": "",
    }


def _default_return_form_state() -> dict[str, Any]:
    return {
        "taxpayer": {
            "sin": "",
            "first_name": "",
            "last_name": "",
            "dob": "",
            "address_line1": "",
            "city": "",
            "province": "ON",
            "postal_code": "",
            "residency_status": "resident",
        },
        "household": {
            "marital_status": "single",
            "spouse_sin": "",
            "dependants_raw": "",
        },
        "slips_t4": [_blank_slip_state()],
        "rrsp_contrib": "0.00",
        "province": "ON",
        "tax_year": "2025",
        "t183": {
            "signed_ts": "",
            "ip_hash": "",
            "user_agent_hash": "",
            "pdf_path": "",
        },
        "outputs": {
            "out_path": "artifacts/printouts/t1.pdf",
        },
        "efile": {
            "endpoint": "",
            "software_id": "",
            "software_ver": "",
            "transmitter_id": "",
        },
    }


def _normalize_step(step: str | None) -> str:
    if not step:
        return DEFAULT_FORM_STEP
    candidate = str(step).strip().lower()
    if candidate in FORM_STEP_SLUGS:
        return candidate
    return DEFAULT_FORM_STEP


def _profile_draft_dir(slug: str) -> Path:
    return (PROFILE_DRAFTS_ROOT / slug).resolve()


def _profile_draft_path(slug: str) -> Path:
    return _profile_draft_dir(slug) / "draft.json"


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _coerce_slip_state(entry: dict[str, Any], fallback_index: int) -> dict[str, Any]:
    slip = _blank_slip_state(fallback_index)
    index_value = entry.get("index", fallback_index)
    try:
        slip_index = int(index_value)
    except (TypeError, ValueError):
        slip_index = fallback_index
    slip["index"] = slip_index
    for key in (
        "employment_income",
        "tax_deducted",
        "cpp_contrib",
        "ei_premiums",
        "pensionable_earnings",
        "insurable_earnings",
    ):
        slip[key] = _coerce_text(entry.get(key))
    return slip


def _merge_return_form_state(base: dict[str, Any], saved: dict[str, Any]) -> dict[str, Any]:
    state = base
    taxpayer_saved = saved.get("taxpayer")
    if isinstance(taxpayer_saved, dict):
        for key in state["taxpayer"].keys():
            state["taxpayer"][key] = _coerce_text(taxpayer_saved.get(key))
    household_saved = saved.get("household")
    if isinstance(household_saved, dict):
        state["household"]["marital_status"] = _coerce_text(household_saved.get("marital_status"))
        state["household"]["spouse_sin"] = _coerce_text(household_saved.get("spouse_sin"))
        state["household"]["dependants_raw"] = _coerce_text(household_saved.get("dependants_raw"))
    slips_saved = saved.get("slips_t4")
    if isinstance(slips_saved, list):
        slips: list[dict[str, Any]] = []
        for position, entry in enumerate(slips_saved):
            if isinstance(entry, dict):
                slips.append(_coerce_slip_state(entry, position))
        if slips:
            state["slips_t4"] = slips
    if "rrsp_contrib" in saved:
        state["rrsp_contrib"] = _coerce_text(saved.get("rrsp_contrib"))
    if "province" in saved:
        state["province"] = _coerce_text(saved.get("province"))
    if "tax_year" in saved:
        state["tax_year"] = _coerce_text(saved.get("tax_year"))
    t183_saved = saved.get("t183")
    if isinstance(t183_saved, dict):
        for key in state["t183"].keys():
            state["t183"][key] = _coerce_text(t183_saved.get(key))
    outputs_saved = saved.get("outputs")
    if isinstance(outputs_saved, dict) and "out_path" in outputs_saved:
        state["outputs"]["out_path"] = _coerce_text(outputs_saved.get("out_path"))
    efile_saved = saved.get("efile")
    if isinstance(efile_saved, dict):
        for key in state["efile"].keys():
            state["efile"][key] = _coerce_text(efile_saved.get(key))
    return state


def _load_return_draft(slug: str) -> tuple[dict[str, Any], str | None, str | None, bool]:
    path = _profile_draft_path(slug)
    if not path.exists():
        return {}, None, None, False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, None, None, False
    state_data = raw.get("state") or raw.get("form_state")
    state: dict[str, Any] = {}
    has_state = isinstance(state_data, dict)
    if has_state:
        state = _merge_return_form_state(_default_return_form_state(), state_data)
    step_value = raw.get("step") if isinstance(raw.get("step"), str) else None
    normalized_step = _normalize_step(step_value) if step_value else None
    updated_at_raw = raw.get("updated_at")
    timestamp = str(updated_at_raw) if isinstance(updated_at_raw, str) else None
    return state, normalized_step, timestamp, has_state


def _save_return_draft(slug: str, state: dict[str, Any], step: str) -> None:
    directory = _profile_draft_dir(slug)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "step": step,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    path = _profile_draft_path(slug)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class ReturnAutosavePayload(BaseModel):
    profile: str = Field(..., min_length=1)
    step: str = Field(..., min_length=1)
    state: dict[str, Any] = Field(default_factory=dict)

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, value: str) -> str:
        slug = slugify(value)
        if not slug:
            raise ValueError("Invalid profile identifier")
        return slug

    @field_validator("step")
    @classmethod
    def validate_step(cls, value: str) -> str:
        candidate = str(value).strip().lower()
        if candidate not in FORM_STEP_SLUGS:
            raise ValueError("Invalid step")
        return candidate

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("State must be an object")
        return value


def _normalize_datetime_field(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return cleaned
    if parsed.tzinfo:
        return parsed.isoformat()
    return parsed.replace(microsecond=0).isoformat()


def _dependants_from_text(raw: str) -> list[str]:
    entries: list[str] = []
    for segment in raw.replace(",", "\n").splitlines():
        item = segment.strip()
        if item:
            entries.append(item)
    return entries


def _resolve_field_name(location: tuple[Any, ...]) -> str:
    if not location:
        return "return"
    first = location[0]
    rest = location[1:]
    if first == "taxpayer":
        return "taxpayer_" + "_".join(str(part) for part in rest)
    if first == "household":
        if rest and rest[0] == "dependants":
            return "household_dependants_raw"
        return "household_" + "_".join(str(part) for part in rest)
    if first == "slips_t4" and len(location) >= 3 and isinstance(location[1], int):
        return f"slips_t4-{location[1]}-{location[2]}"
    return "_".join(str(part) for part in location)


def _parse_return_form(form: dict[str, Any]) -> tuple[ReturnInput | None, dict[str, str], dict[str, Any]]:
    state = _default_return_form_state()
    taxpayer_state = state["taxpayer"]
    household_state = state["household"]
    for field in list(taxpayer_state.keys()):
        if field == "province":
            taxpayer_state[field] = _form_text(form.get(f"taxpayer_{field}")) or taxpayer_state[field]
        else:
            taxpayer_state[field] = _form_text(form.get(f"taxpayer_{field}"))
    household_state["marital_status"] = _form_text(form.get("household_marital_status")) or household_state["marital_status"]
    household_state["spouse_sin"] = _form_text(form.get("household_spouse_sin"))
    household_state["dependants_raw"] = _form_text(form.get("household_dependants_raw"))

    state["province"] = _form_text(form.get("province")) or state["province"]
    state["tax_year"] = _form_text(form.get("tax_year")) or state["tax_year"]
    state["rrsp_contrib"] = _form_text(form.get("rrsp_contrib")) or state["rrsp_contrib"]

    t183_state = state["t183"]
    t183_state["signed_ts"] = _form_text(form.get("t183_signed_ts"))
    t183_state["ip_hash"] = _form_text(form.get("t183_ip_hash"))
    t183_state["user_agent_hash"] = _form_text(form.get("t183_user_agent_hash"))
    t183_state["pdf_path"] = _form_text(form.get("t183_pdf_path"))

    outputs_state = state["outputs"]
    outputs_state["out_path"] = _form_text(form.get("out_path")) or outputs_state["out_path"]

    efile_state = state["efile"]
    efile_state["endpoint"] = _form_text(form.get("endpoint"))
    efile_state["software_id"] = _form_text(form.get("software_id"))
    efile_state["software_ver"] = _form_text(form.get("software_ver"))
    efile_state["transmitter_id"] = _form_text(form.get("transmitter_id"))

    slip_indices: set[int] = set()
    for key in form.keys():
        if not key.startswith("slips_t4-"):
            continue
        _, maybe_index, *_ = key.split("-", 2)
        if maybe_index.isdigit():
            slip_indices.add(int(maybe_index))
    state["slips_t4"] = []
    for index in sorted(slip_indices) or [0]:
        slip_state = _blank_slip_state(index)
        for field in [
            "employment_income",
            "tax_deducted",
            "cpp_contrib",
            "ei_premiums",
            "pensionable_earnings",
            "insurable_earnings",
        ]:
            key = f"slips_t4-{index}-{field}"
            slip_state[field] = _form_text(form.get(key))
        state["slips_t4"].append(slip_state)

    taxpayer_payload = taxpayer_state.copy()
    if not taxpayer_payload.get("province"):
        taxpayer_payload["province"] = state["province"]
    if not taxpayer_payload.get("residency_status"):
        taxpayer_payload["residency_status"] = "resident"

    household_payload = {
        "marital_status": household_state["marital_status"] or "single",
        "spouse_sin": household_state["spouse_sin"] or None,
        "dependants": _dependants_from_text(household_state["dependants_raw"]),
    }

    slips_payload: list[dict[str, Any]] = []
    for slip_state in state["slips_t4"]:
        slip_payload: dict[str, Any] = {}
        for field in [
            "employment_income",
            "tax_deducted",
            "cpp_contrib",
            "ei_premiums",
            "pensionable_earnings",
            "insurable_earnings",
        ]:
            value = slip_state.get(field, "").strip()
            if value:
                slip_payload[field] = value
        if slip_payload:
            slips_payload.append(slip_payload)

    payload = {
        "taxpayer": taxpayer_payload,
        "household": household_payload,
        "slips_t4": slips_payload,
        "rrsp_contrib": state["rrsp_contrib"],
        "province": state["province"],
        "tax_year": state["tax_year"],
        "t183_signed_ts": _normalize_datetime_field(t183_state["signed_ts"]) or None,
        "t183_ip_hash": t183_state["ip_hash"] or None,
        "t183_user_agent_hash": t183_state["user_agent_hash"] or None,
        "t183_pdf_path": t183_state["pdf_path"] or None,
    }

    field_errors: dict[str, str] = {}
    try:
        request_model = ReturnInput.model_validate(payload)
    except ValidationError as exc:
        for error in exc.errors():
            loc = tuple(error.get("loc", ()))
            field_errors[_resolve_field_name(loc)] = error.get("msg", "Invalid value")
        return None, field_errors, state

    return request_model, field_errors, state


def _compute_return(req: ReturnInput):
    from app.api import http as api_http

    return api_http._compute_for_year(req)


def _resolve_artifact_root(request: Request) -> Path:
    raw = getattr(request.app.state, "artifact_root", None)
    if raw is None:
        settings = getattr(request.app.state, "settings", None)
        raw = getattr(settings, "artifact_root", None) if settings is not None else None
    if isinstance(raw, (str, Path)):
        root_path = Path(raw)
    else:
        root_path = Path("artifacts")
    if not root_path.is_absolute():
        root_path = (BASE_DIR / root_path).resolve()
    return root_path


def _relative_artifact_label(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


@router.get("/", response_class=HTMLResponse)
def profiles_home(request: Request) -> HTMLResponse:
    profiles = list_profiles()
    active = get_active_profile()
    trashed_items: list[dict[str, Any]] = []
    for path in list_trash():
        name = path.stem
        if "-" in name:
            slug, timestamp = name.split("-", 1)
        else:
            slug, timestamp = name, ""
        restored_at = None
        if timestamp:
            try:
                restored_at = datetime.strptime(timestamp, "%Y%m%d-%H%M%S")
            except ValueError:
                restored_at = None
        trashed_items.append({
            "slug": slug,
            "path": path,
            "timestamp": restored_at,
        })
    trashed_items.sort(key=lambda item: item["timestamp"] or datetime.min, reverse=True)
    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            "request": request,
            "profiles": profiles,
            "active": active,
            "trashed": trashed_items,
        },
    )


@router.post("/profiles", response_class=RedirectResponse)
async def create_profile(request: Request) -> RedirectResponse:
    form = await request.form()
    name = _form_text(form.get("name")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile name is required")
    slug = slugify(name)
    data, _, load_errors = load_profile(slug)
    if load_errors:
        raise HTTPException(status_code=400, detail="Unable to load existing profile state.")
    if data:
        return RedirectResponse(url=f"/ui/profiles/{slug}", status_code=303)
    save_profile_data(slug, {})
    return RedirectResponse(url=f"/ui/profiles/{slug}?created=1", status_code=303)


@router.post("/profiles/{slug}/set-active", response_class=RedirectResponse)
def set_active(slug: str) -> RedirectResponse:
    set_active_profile(slugify(slug))
    return RedirectResponse(url="/ui/", status_code=303)


@router.post("/profiles/{slug}/delete", response_class=RedirectResponse)
def delete(slug: str) -> RedirectResponse:
    removed = delete_profile(slugify(slug))
    if removed is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return RedirectResponse(url="/ui/", status_code=303)


@router.post("/profiles/{slug}/restore", response_class=RedirectResponse)
def restore(slug: str) -> RedirectResponse:
    restored = restore_profile(slugify(slug))
    if not restored:
        raise HTTPException(status_code=404, detail="No trashed profile found")
    return RedirectResponse(url=f"/ui/profiles/{slug}?restored=1", status_code=303)


@router.post("/profiles/{slug}/rename", response_class=RedirectResponse)
async def rename(slug: str, request: Request) -> RedirectResponse:
    form = await request.form()
    new_name = _form_text(form.get("new_name")).strip()
    old_slug = slugify(slug)
    new_slug = slugify(new_name)
    if not new_slug:
        raise HTTPException(status_code=400, detail="New profile name cannot be empty")
    try:
        rename_profile(old_slug, new_slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/ui/profiles/{new_slug}?renamed=1", status_code=303)


@router.get("/profiles/{slug}", response_class=HTMLResponse)
def edit_profile(request: Request, slug: str) -> HTMLResponse:
    normalized = slugify(slug)
    data, path, load_errors = load_profile(normalized)
    errors: dict[str, str] = {}
    messages = _profile_messages(request)
    if load_errors:
        messages.extend(load_errors)
    context: dict[str, Any] = _profile_context(normalized, data, errors)
    context.update(
        {
            "request": request,
            "messages": messages,
        }
    )
    return TEMPLATES.TemplateResponse("edit.html", context)


@router.post("/profiles/{slug}", response_class=HTMLResponse)
async def save_profile(request: Request, slug: str):
    normalized = slugify(slug)
    form = await request.form()
    form_dict = {key: form.get(key) for key in form.keys()}
    data, field_errors = _extract_form_data(form_dict)
    if field_errors:
        context: dict[str, Any] = _profile_context(normalized, data, field_errors)
        context.update({"request": request, "messages": ["Please fix the highlighted fields."]})
        return TEMPLATES.TemplateResponse("edit.html", context, status_code=400)
    save_profile_data(normalized, data)
    return RedirectResponse(url=f"/ui/profiles/{normalized}?saved=1", status_code=303)


@router.post("/profiles/{slug}/preview", response_class=HTMLResponse)
async def preview_profile(request: Request, slug: str) -> HTMLResponse:
    form = await request.form()
    form_dict = {key: form.get(key) for key in form.keys()}
    data, errors = _extract_form_data(form_dict)
    preview, preview_errors = _build_preview(data)
    context: dict[str, Any] = {
        "request": request,
        "preview": preview,
        "preview_errors": preview_errors,
        "format_currency": _format_currency,
    }
    if errors:
        pe = cast(list[str], context.setdefault("preview_errors", []))
        pe.extend(list(errors.values()))
    return TEMPLATES.TemplateResponse("preview.html", context)


def _render_return_form(request: Request, step: str | None) -> HTMLResponse:
    settings = _resolve_settings(request)
    form_state = _default_return_form_state()
    current_step = _normalize_step(step)
    messages: list[str] = []
    autosave_profile = get_active_profile()
    autosave_url = ""
    if autosave_profile:
        saved_state, saved_step, saved_timestamp, has_state = _load_return_draft(autosave_profile)
        if has_state:
            form_state = saved_state
        if saved_step:
            current_step = saved_step
        if saved_timestamp:
            messages.append(f"Loaded draft saved at {saved_timestamp}.")
        autosave_url = str(request.url_for("ui_autosave_return"))
    context: dict[str, Any] = {
        "request": request,
        "form_state": form_state,
        "field_errors": {},
        "issues": [],
        "calc": None,
        "calc_json": None,
        "payload_json": None,
        "prepare_ok": False,
        "artifact_paths": [],
        "format_currency": _format_currency,
        "messages": messages,
        "form_steps": FORM_STEPS,
        "current_step": current_step,
        "autosave_profile": autosave_profile,
        "autosave_url": autosave_url,
        "autosave_interval": AUTOSAVE_INTERVAL_MS,
    }
    context.update(_transmit_gate_context(form_state, settings))
    return TEMPLATES.TemplateResponse("return_form.html", context)


@router.get("/returns/new", response_class=HTMLResponse)
def new_return(request: Request, step: str | None = Query(None)) -> HTMLResponse:
    return _render_return_form(request, step)


@router.get("/returns/new/{step_slug}", response_class=HTMLResponse)
def new_return_step(request: Request, step_slug: str) -> HTMLResponse:
    return _render_return_form(request, step_slug)


@router.post("/returns/prepare", response_class=HTMLResponse)
async def prepare_return(request: Request) -> HTMLResponse:
    form = await request.form()
    form_dict = {key: form.get(key) for key in form.keys()}
    payload, field_errors, state = _parse_return_form(form_dict)

    current_step = _normalize_step(_form_text(form.get("current_step")))

    issues: list[str] = []
    calc_dump: dict[str, Any] | None = None
    calc_json: str | None = None
    payload_json: str | None = None
    status_code = 200

    if payload is None:
        status_code = 400
    else:
        payload_json = json.dumps(payload.model_dump(mode="json"), indent=2)
        issues = validate_return_input(payload)
        if not issues:
            calc = _compute_return(payload)
            calc_dump = calc.model_dump(mode="json")
            calc_json = json.dumps(calc_dump, indent=2)

    settings = _resolve_settings(request)
    autosave_profile = get_active_profile()
    autosave_url = str(request.url_for("ui_autosave_return")) if autosave_profile else ""

    messages: list[str] = []
    if payload is None:
        messages.append("Please review the highlighted fields before continuing.")
    context: dict[str, Any] = {
        "request": request,
        "form_state": state,
        "field_errors": field_errors,
        "issues": issues,
        "calc": calc_dump,
        "calc_json": calc_json,
        "payload_json": payload_json,
        "prepare_ok": payload is not None and not issues,
        "artifact_paths": [],
        "format_currency": _format_currency,
        "messages": messages,
        "form_steps": FORM_STEPS,
        "current_step": current_step,
        "autosave_profile": autosave_profile,
        "autosave_url": autosave_url,
        "autosave_interval": AUTOSAVE_INTERVAL_MS,
    }
    context.update(_transmit_gate_context(state, settings))
    return TEMPLATES.TemplateResponse("return_form.html", context, status_code=status_code)


@router.post("/returns/autosave", response_class=JSONResponse, name="ui_autosave_return")
async def autosave_return(request: Request, payload: ReturnAutosavePayload) -> JSONResponse:
    active_profile = get_active_profile()
    if not active_profile:
        raise HTTPException(status_code=400, detail="No active profile selected for autosave")
    if payload.profile != active_profile:
        raise HTTPException(status_code=400, detail="Autosave profile mismatch")
    sanitized_state = _merge_return_form_state(_default_return_form_state(), payload.state)
    _save_return_draft(payload.profile, sanitized_state, payload.step)
    return JSONResponse({"saved": True, "step": payload.step})


@router.post("/returns/{profile}/{year}/slips/upload", response_class=JSONResponse)
async def upload_slip(
    request: Request,
    profile: str,
    year: int,
    upload: UploadFile = File(...),
) -> JSONResponse:
    settings = _resolve_settings(request)
    store = slip_ingest.resolve_store(request.app)
    try:
        status = await store.process_upload(profile, year, upload, settings=settings)
    except slip_ingest.SlipUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(status.model_dump(mode="json"))


@router.get("/returns/{profile}/{year}/slips/status", response_class=JSONResponse)
async def slip_status(request: Request, profile: str, year: int, job_id: str) -> JSONResponse:
    store = slip_ingest.resolve_store(request.app)
    try:
        status = await store.job_status(profile, year, job_id)
    except slip_ingest.SlipJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(status.model_dump(mode="json"))


@router.post("/returns/{profile}/{year}/slips/apply", response_class=JSONResponse)
async def apply_slip_detections(
    request: Request,
    profile: str,
    year: int,
    payload: slip_ingest.ApplyDetectionsRequest,
) -> JSONResponse:
    store = slip_ingest.resolve_store(request.app)
    try:
        detections = await store.apply(profile, year, payload.detection_ids)
    except slip_ingest.SlipApplyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(
        {"detections": [detection.model_dump(mode="json") for detection in detections]}
    )


@router.post("/returns/{profile}/{year}/slips/clear", response_class=JSONResponse)
async def clear_slip_detections(request: Request, profile: str, year: int) -> JSONResponse:
    store = slip_ingest.resolve_store(request.app)
    await store.clear(profile, year)
    return JSONResponse({"cleared": True})


@router.get("/artifacts/list", response_class=JSONResponse)
def list_artifacts(request: Request, digest: str) -> JSONResponse:
    root = _resolve_artifact_root(request)
    paths: list[dict[str, str]] = []
    if root.exists():
        for path in sorted(root.rglob(f"*{digest}*.xml")):
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(root)
            except ValueError:
                relative = path
            paths.append({
                "path": str(relative),
                "label": _relative_artifact_label(path),
            })
    return JSONResponse({"paths": paths})


@router.get("/artifacts/download")
def download_artifact(request: Request, path: str) -> FileResponse:
    if not path:
        raise HTTPException(status_code=400, detail="Missing artifact path")
    root = _resolve_artifact_root(request)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(candidate)

