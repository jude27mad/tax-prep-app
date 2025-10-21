from __future__ import annotations

from importlib import import_module
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.wizard as wizard
import app.wizard.profiles as profiles
from app.config import get_settings
from app.efile import crypto

ui_router_module = import_module("app.ui.router")

TEST_KEY = "jLNo6J1iO5Y5P2bIC2T5T8DKS-p91Z9a7qV3-0iKqa4="


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

    return base


def _configure_crypto(monkeypatch):
    monkeypatch.setenv("T183_CRYPTO_KEY", TEST_KEY)
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def _build_client():
    app = FastAPI()
    app.include_router(ui_router_module.router)
    return TestClient(app)


def _seed_return_draft(slug: str, tax_year: int = 2025) -> None:
    state = ui_router_module._default_return_form_state()
    state["taxpayer"]["sin"] = "046454286"
    state["taxpayer"]["first_name"] = "Test"
    state["taxpayer"]["last_name"] = "User"
    state["tax_year"] = str(tax_year)
    ui_router_module._save_return_draft(slug, state, "transmit")


def test_profiles_home_lists_profiles(tmp_path, monkeypatch):
    _configure_profiles_dirs(monkeypatch, tmp_path)
    profiles.save_profile_data("alice", {})

    client = _build_client()
    response = client.get("/ui/")

    assert response.status_code == 200
    assert "alice" in response.text


def test_create_profile_accepts_multipart(tmp_path, monkeypatch):
    base = _configure_profiles_dirs(monkeypatch, tmp_path)

    client = _build_client()
    response = client.post(
        "/ui/profiles",
        data={"name": "Test User"},
        files={"__dummy_file": ("notes.txt", b"notes", "text/plain")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/ui/profiles/test-user?created=1")
    assert "multipart/form-data" in response.request.headers.get("Content-Type", "")
    assert (base / "profiles" / "test-user.toml").exists()


def test_preview_displays_summary(tmp_path, monkeypatch):
    _configure_profiles_dirs(monkeypatch, tmp_path)

    client = _build_client()
    response = client.post(
        "/ui/profiles/tester/preview",
        data={
            "box14": "50000",
            "box22": "7000",
            "box16": "2500",
            "box16a": "0",
            "box18": "890",
            "rrsp": "1000",
            "province": "ON",
        },
        files={"__dummy_file": ("notes.txt", b"notes", "text/plain")},
    )

    assert response.status_code == 200
    assert "multipart/form-data" in response.request.headers.get("Content-Type", "")
    body = response.text
    assert "Balance" in body
    assert "Contribution limits" in body


def test_preview_reports_field_errors(tmp_path, monkeypatch):
    _configure_profiles_dirs(monkeypatch, tmp_path)

    client = _build_client()
    response = client.post(
        "/ui/profiles/tester/preview",
        data={
            "box14": "oops",
            "box22": "7000",
            "box16": "2500",
            "box18": "890",
        },
        files={"__dummy_file": ("notes.txt", b"notes", "text/plain")},
    )

    assert response.status_code == 200
    assert "multipart/form-data" in response.request.headers.get("Content-Type", "")
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


def test_save_profile_accepts_multipart(tmp_path, monkeypatch):
    _configure_profiles_dirs(monkeypatch, tmp_path)
    profiles.save_profile_data("tester", {})

    client = _build_client()
    response = client.post(
        "/ui/profiles/tester",
        data={"box14": "55000", "province": "ON"},
        files={"__dummy_file": ("notes.txt", b"notes", "text/plain")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/ui/profiles/tester?saved=1")
    assert "multipart/form-data" in response.request.headers.get("Content-Type", "")
    saved_data, _, _ = profiles.load_profile("tester")
    assert saved_data.get("box14") == 55000


def test_prepare_return_handles_valid_form(monkeypatch, tmp_path):
    _configure_profiles_dirs(monkeypatch, tmp_path)

    client = _build_client()
    response = client.post(
        "/ui/returns/prepare",
        data={
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
            "out_path": "artifacts/printouts/t1.pdf",
        },
        files={"t183_pdf_path": ("t183.pdf", b"PDF", "application/pdf")},
    )

    assert response.status_code == 200
    assert "multipart/form-data" in response.request.headers.get("Content-Type", "")
    body = response.text
    assert "Return validated" in body or "Return validated." in body
    assert "Submitted payload" in body


def test_t183_consent_page_includes_masked_sin(tmp_path, monkeypatch):
    _configure_profiles_dirs(monkeypatch, tmp_path)
    _configure_crypto(monkeypatch)
    profiles.save_profile_data("tester", {})
    _seed_return_draft("tester")

    client = _build_client()
    client.app.state.artifact_root = tmp_path / "artifacts"

    response = client.get("/ui/profiles/tester/t183")

    assert response.status_code == 200
    body = response.text
    assert "***-***-4286" in body
    assert "retain them for 6 years" in body


def test_t183_consent_submission_stores_record(tmp_path, monkeypatch):
    _configure_profiles_dirs(monkeypatch, tmp_path)
    _configure_crypto(monkeypatch)
    profiles.save_profile_data("tester", {})
    _seed_return_draft("tester")

    client = _build_client()
    artifact_root = tmp_path / "artifacts"
    client.app.state.artifact_root = artifact_root

    response = client.post(
        "/ui/profiles/tester/t183",
        data={"signature": "Test User", "confirm": "on"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "t183_signed=1" in response.headers["location"]

    target_dir = artifact_root / ui_router_module.T183_RETENTION_DIRNAME / "2025" / "4286"
    assert target_dir.exists()
    encrypted_files = sorted(target_dir.glob("t183_*.enc"))
    metadata_files = sorted(target_dir.glob("t183_*.json"))
    summary_files = sorted(target_dir.glob("t183_*.txt"))
    assert encrypted_files and metadata_files and summary_files

    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert metadata["profile"] == "tester"
    assert metadata["masked_sin"] == "***-***-4286"
    assert metadata["encrypted_path"].endswith(encrypted_files[0].name)

    state, _, _, has_state = ui_router_module._load_return_draft("tester")
    assert has_state
    assert state["t183"]["record_path"].endswith(encrypted_files[0].name)
    assert state["t183"]["metadata_path"].endswith(metadata_files[0].name)

    download = client.get(
        f"/ui/profiles/tester/t183/{encrypted_files[0].stem}/download",
        follow_redirects=False,
    )
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/octet-stream"


def test_profile_page_lists_t183_records(tmp_path, monkeypatch):
    _configure_profiles_dirs(monkeypatch, tmp_path)
    _configure_crypto(monkeypatch)
    profiles.save_profile_data("tester", {})
    _seed_return_draft("tester")

    client = _build_client()
    artifact_root = tmp_path / "artifacts"
    client.app.state.artifact_root = artifact_root

    # Seed a stored record
    client.post(
        "/ui/profiles/tester/t183",
        data={"signature": "Test User", "confirm": "on"},
        follow_redirects=False,
    )

    response = client.get("/ui/profiles/tester")

    assert response.status_code == 200
    body = response.text
    assert "T183 authorizations" in body
    assert "Encrypted blob" in body
