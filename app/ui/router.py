from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.datastructures import UploadFile  # for type-narrowing form inputs

from app.config import Settings, get_settings
from app.core.models import ReturnInput
from app.core.validate.pre_submit import validate_return_input
from app.efile.gating import build_transmit_gate
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
    """Return a safe text value from a form field which might be UploadFile | str | None."""
    if isinstance(val, UploadFile):
        # For text fields, treat file inputs as empty string; or use filename if you prefer.
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
            # If UploadFile, treat as empty too
            if isinstance(raw_value, UploadFile):
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
    except HTTPException as exc:  # pragma: no cover - should not occur with validated payload
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
    # Ensure we only pass a valid str/PathLike to Path(), never Any|None.
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
    # Safely coerce text (mypy fix for UploadFile | str)
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
    # Safely coerce text (mypy fix for UploadFile | str)
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
        # Display field-level errors at the top of the preview
        pe = cast(list[str], context.setdefault("preview_errors", []))
        pe.extend(list(errors.values()))
    return TEMPLATES.TemplateResponse("preview.html", context)


@router.get("/returns/new", response_class=HTMLResponse)
def new_return(request: Request) -> HTMLResponse:
    settings = _resolve_settings(request)
    context: dict[str, Any] = {
        "request": request,
        "form_state": _default_return_form_state(),
        "field_errors": {},
        "issues": [],
        "calc": None,
        "calc_json": None,
        "payload_json": None,
        "prepare_ok": False,
        "artifact_paths": [],
        "format_currency": _format_currency,
        "messages": [],
    }
    context.update(_transmit_gate_context(context["form_state"], settings))
    return TEMPLATES.TemplateResponse("return_form.html", context)


@router.post("/returns/prepare", response_class=HTMLResponse)
async def prepare_return(request: Request) -> HTMLResponse:
    form = await request.form()
    form_dict = {key: form.get(key) for key in form.keys()}
    payload, field_errors, state = _parse_return_form(form_dict)

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
    }
    messages: list[str] = []
    if payload is None:
        messages.append("Please review the highlighted fields before continuing.")
    context["messages"] = messages
    context.update(_transmit_gate_context(state, settings))
    return TEMPLATES.TemplateResponse("return_form.html", context, status_code=status_code)


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

