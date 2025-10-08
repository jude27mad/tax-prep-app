from __future__ import annotations

from importlib import import_module

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.datastructures import FormData

import app.wizard as wizard
import app.wizard.profiles as profiles

ui_router_module = import_module("app.ui.router")


def _configure_profiles_dirs(monkeypatch, tmp_path):
    base = tmp_path / "app"
    profiles_dir = base / "profiles"
    history_dir = profiles_dir / "history"
    trash_dir = profiles_dir / ".trash"
    default_profile = profiles_dir / "active_profile.txt"

    monkeypatch.setattr(profiles, "BASE_DIR", base)
    monkeypatch.setattr(profiles, "PROFILES_DIR", profiles_dir)
    monkeypatch.setattr(profiles, "PROFILE_HISTORY_DIR", history_dir)
    monkeypatch.setattr(profiles, "PROFILE_TRASH_DIR", trash_dir)
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_FILE", default_profile)

    # The router keeps its own reference to BASE_DIR and the wizard package re-exports it.
    monkeypatch.setattr(ui_router_module, "BASE_DIR", base)
    monkeypatch.setattr(wizard, "BASE_DIR", base)

    # FastAPI's form parser requires python-multipart. Provide a simple stub so the
    # router can consume form data in tests without the extra dependency.
    from starlette import requests as starlette_requests

    if getattr(starlette_requests, "parse_options_header", None) is None:
        monkeypatch.setattr(
            starlette_requests,
            "parse_options_header",
            lambda value: ("application/x-www-form-urlencoded", {}),
        )

    return base


def _build_client():
    app = FastAPI()
    app.include_router(ui_router_module.router)
    return TestClient(app)


def _stub_form(monkeypatch, data: dict[str, str]):
    async def fake_form(self):
        return FormData(list(data.items()))

    monkeypatch.setattr(ui_router_module.Request, "form", fake_form)


def test_profiles_home_lists_profiles(tmp_path, monkeypatch):
    _configure_profiles_dirs(monkeypatch, tmp_path)
    profiles.save_profile_data("alice", {})

    client = _build_client()
    response = client.get("/ui/")

    assert response.status_code == 200
    assert "alice" in response.text


def test_preview_displays_summary(tmp_path, monkeypatch):
    _configure_profiles_dirs(monkeypatch, tmp_path)
    _stub_form(
        monkeypatch,
        {
            "box14": "50000",
            "box22": "7000",
            "box16": "2500",
            "box16a": "0",
            "box18": "890",
            "rrsp": "1000",
            "province": "ON",
        },
    )

    client = _build_client()
    response = client.post("/ui/profiles/tester/preview")

    assert response.status_code == 200
    body = response.text
    assert "Balance" in body
    assert "Contribution limits" in body


def test_preview_reports_field_errors(tmp_path, monkeypatch):
    _configure_profiles_dirs(monkeypatch, tmp_path)
    _stub_form(
        monkeypatch,
        {
            "box14": "oops",
            "box22": "7000",
            "box16": "2500",
            "box18": "890",
        },
    )

    client = _build_client()
    response = client.post("/ui/profiles/tester/preview")

    assert response.status_code == 200
    assert "Could not understand number" in response.text


def test_new_return_form_renders(monkeypatch, tmp_path):
    _configure_profiles_dirs(monkeypatch, tmp_path)
    client = _build_client()

    response = client.get("/ui/returns/new")

    assert response.status_code == 200
    body = response.text
    assert "Return input" in body
    assert "name=\"taxpayer_sin\"" in body
    assert "Compute return" in body


def test_prepare_return_handles_valid_form(monkeypatch, tmp_path):
    _configure_profiles_dirs(monkeypatch, tmp_path)
    _stub_form(
        monkeypatch,
        {
            "taxpayer_sin": "046454286",
            "taxpayer_first_name": "Test",
            "taxpayer_last_name": "User",
            "taxpayer_dob": "1990-01-01",
            "taxpayer_address_line1": "1 Main St",
            "taxpayer_city": "Toronto",
            "taxpayer_province": "ON",
            "taxpayer_postal_code": "M1M1M1",
            "taxpayer_residency_status": "resident",
            "household_marital_status": "single",
            "household_spouse_sin": "",
            "household_dependants_raw": "",
            "slips_t4-0-employment_income": "60000",
            "slips_t4-0-tax_deducted": "9000",
            "rrsp_contrib": "0",
            "province": "ON",
            "tax_year": "2025",
            "t183_signed_ts": "2025-02-15T09:00",
            "t183_ip_hash": "hash-ip",
            "t183_user_agent_hash": "hash-ua",
            "t183_pdf_path": "/tmp/t183.pdf",
            "out_path": "artifacts/printouts/t1.pdf",
        },
    )

    client = _build_client()
    response = client.post("/ui/returns/prepare")

    assert response.status_code == 200
    body = response.text
    assert "Return validated" in body or "Return validated." in body
    assert "Submitted payload" in body
