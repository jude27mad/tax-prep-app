"""Playwright smoke coverage for the upload → apply → preview UI workflow."""

from __future__ import annotations

import importlib
import os
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from playwright.sync_api import expect

import app.wizard as wizard
from app.config import get_settings
from app.ui import slip_ingest
from app.wizard import profiles

ui_router_module = importlib.import_module("app.ui.router")


TEST_T183_KEY = "jLNo6J1iO5Y5P2bIC2T5T8DKS-p91Z9a7qV3-0iKqa4="


def _reserve_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def sample_t4_slip_path() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "sample_t4_slip.txt"


@pytest.fixture()
def duplicate_t4_slip_path(
    tmp_path_factory: pytest.TempPathFactory, sample_t4_slip_path: Path
) -> Path:
    duplicate_dir = tmp_path_factory.mktemp("duplicate-slip")
    duplicate_path = duplicate_dir / "sample_t4_duplicate.txt"
    shutil.copyfile(sample_t4_slip_path, duplicate_path)
    return duplicate_path


@pytest.fixture(scope="session")
def ui_server_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    base_dir = tmp_path_factory.mktemp("ui-playwright")
    artifact_root = base_dir / "artifacts"
    summary_root = artifact_root / "summaries"
    artifact_root.mkdir(parents=True, exist_ok=True)
    summary_root.mkdir(parents=True, exist_ok=True)

    original_env = {key: os.environ.get(key) for key in ("ARTIFACT_ROOT", "DAILY_SUMMARY_ROOT", "T183_CRYPTO_KEY")}

    original_profiles = {
        "BASE_DIR": profiles.BASE_DIR,
        "INBOX_DIR": profiles.INBOX_DIR,
        "PROFILES_DIR": profiles.PROFILES_DIR,
        "PROFILE_HISTORY_DIR": profiles.PROFILE_HISTORY_DIR,
        "PROFILE_TRASH_DIR": profiles.PROFILE_TRASH_DIR,
        "DEFAULT_PROFILE_FILE": profiles.DEFAULT_PROFILE_FILE,
    }
    original_wizard_base = wizard.BASE_DIR
    original_router_base = ui_router_module.BASE_DIR
    original_router_drafts = ui_router_module.PROFILE_DRAFTS_ROOT
    original_slip_ingest_base = slip_ingest.BASE_DIR
    original_default_store = slip_ingest._DEFAULT_STORE  # type: ignore[attr-defined]
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None

    try:
        os.environ["ARTIFACT_ROOT"] = str(artifact_root)
        os.environ["DAILY_SUMMARY_ROOT"] = str(summary_root)
        os.environ.setdefault("T183_CRYPTO_KEY", TEST_T183_KEY)
        get_settings.cache_clear()
        settings = get_settings()

        wizard.BASE_DIR = base_dir
        profiles.BASE_DIR = base_dir
        profiles.INBOX_DIR = base_dir / "inbox"
        profiles.PROFILES_DIR = base_dir / "profiles"
        profiles.PROFILE_HISTORY_DIR = profiles.PROFILES_DIR / "history"
        profiles.PROFILE_TRASH_DIR = profiles.PROFILES_DIR / ".trash"
        profiles.DEFAULT_PROFILE_FILE = profiles.PROFILES_DIR / "active_profile.txt"
        ui_router_module.BASE_DIR = base_dir
        ui_router_module.PROFILE_DRAFTS_ROOT = profiles.PROFILES_DIR
        slip_ingest.BASE_DIR = base_dir
        slip_ingest._DEFAULT_STORE = slip_ingest.SlipStagingStore()  # type: ignore[attr-defined]

        profiles.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        profiles.PROFILE_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        profiles.PROFILE_TRASH_DIR.mkdir(parents=True, exist_ok=True)
        (base_dir / "inbox").mkdir(parents=True, exist_ok=True)

        profiles.save_profile_data("playwright-smoke", {"province": "ON", "tax_year": 2025})

        app = FastAPI()
        app.include_router(ui_router_module.router)
        app.state.slip_staging_store = slip_ingest.SlipStagingStore()
        app.state.settings = settings

        host = "127.0.0.1"
        port = _reserve_port(host)
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config=config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("UI server failed to start")
            time.sleep(0.05)

        yield f"http://{host}:{port}"
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError("UI server did not shut down")
        get_settings.cache_clear()
        if original_env["ARTIFACT_ROOT"] is not None:
            os.environ["ARTIFACT_ROOT"] = original_env["ARTIFACT_ROOT"]
        else:
            os.environ.pop("ARTIFACT_ROOT", None)
        if original_env["DAILY_SUMMARY_ROOT"] is not None:
            os.environ["DAILY_SUMMARY_ROOT"] = original_env["DAILY_SUMMARY_ROOT"]
        else:
            os.environ.pop("DAILY_SUMMARY_ROOT", None)
        if original_env["T183_CRYPTO_KEY"] is not None:
            os.environ["T183_CRYPTO_KEY"] = original_env["T183_CRYPTO_KEY"]
        else:
            os.environ.pop("T183_CRYPTO_KEY", None)
        wizard.BASE_DIR = original_wizard_base
        profiles.BASE_DIR = original_profiles["BASE_DIR"]
        profiles.INBOX_DIR = original_profiles["INBOX_DIR"]
        profiles.PROFILES_DIR = original_profiles["PROFILES_DIR"]
        profiles.PROFILE_HISTORY_DIR = original_profiles["PROFILE_HISTORY_DIR"]
        profiles.PROFILE_TRASH_DIR = original_profiles["PROFILE_TRASH_DIR"]
        profiles.DEFAULT_PROFILE_FILE = original_profiles["DEFAULT_PROFILE_FILE"]
        ui_router_module.BASE_DIR = original_router_base
        ui_router_module.PROFILE_DRAFTS_ROOT = original_router_drafts
        slip_ingest.BASE_DIR = original_slip_ingest_base
        slip_ingest._DEFAULT_STORE = original_default_store  # type: ignore[attr-defined]
        get_settings.cache_clear()


@pytest.mark.smoke
@pytest.mark.playwright_smoke
def test_upload_apply_preview_flow(
    page,
    ui_server_url: str,
    sample_t4_slip_path: Path,
    duplicate_t4_slip_path: Path,
) -> None:
    page.goto(f"{ui_server_url}/ui/returns/new?step=slips")

    dropzone = page.locator("#t4-slip-dropzone")
    queue = page.locator("#t4-file-queue")
    apply_button = page.get_by_role("button", name="Apply detections")

    expect(apply_button).to_be_disabled()
    expect(queue).to_have_attribute("data-empty", "true")

    page.set_input_files("#t4-slip-file-input", str(sample_t4_slip_path))

    queue_items = page.locator("#t4-file-queue li")
    first_item = queue_items.first
    first_status = first_item.locator(".file-status")

    expect(first_item).to_be_visible()
    expect(apply_button).to_be_disabled()

    expect(first_status).to_have_text("Ready to apply", timeout=5000)
    expect(apply_button).not_to_be_disabled()

    apply_button.click()

    expect(first_status).to_have_text("Applied to form", timeout=5000)

    expect(page.locator("input[name='slips_t4-0-employment_income']")).to_have_value("55123.45")
    expect(page.locator("input[name='slips_t4-0-tax_deducted']")).to_have_value("8765.43")
    expect(page.locator("input[name='slips_t4-0-cpp_contrib']")).to_have_value("3000.99")
    expect(page.locator("input[name='slips_t4-0-ei_premiums']")).to_have_value("890.12")

    expect(apply_button).to_be_disabled()

    page.set_input_files("#t4-slip-file-input", str(duplicate_t4_slip_path))

    expect(queue_items).to_have_count(2)
    expect(apply_button).to_be_disabled()

    first_item.locator(".file-remove").click()
    expect(queue_items).to_have_count(1)
    expect(queue_items.first.locator(".file-remove")).to_be_focused()

    queue_items.first.locator(".file-remove").click()
    expect(queue).to_have_attribute("data-empty", "true")
    expect(dropzone).to_be_focused()
