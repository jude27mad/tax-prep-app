from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.datastructures import UploadFile  # for type-narrowing form inputs

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

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


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
    context = _profile_context(normalized, data, errors)
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
        context = _profile_context(normalized, data, field_errors)
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
