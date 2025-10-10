from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fastapi.testclient import TestClient
from PyPDF2 import PdfReader

from app import config as app_config
from app.api.http import app as api_app
from app.config import Settings
from app.printout import t1_render
from tests.fixtures.min_client import make_min_input


GOLDEN_DIGEST_PATH = Path(__file__).resolve().parent / "golden" / "t1_printout.sha256"


def _configure_settings(tmp_path: Path) -> Settings:
    artifacts = tmp_path / "artifacts"
    summaries = tmp_path / "summaries"
    return Settings(
        feature_efile_xml=True,
        artifact_root=str(artifacts),
        daily_summary_root=str(summaries),
        endpoint_cert="http://127.0.0.1:9000",
        endpoint_prod="http://127.0.0.1:9000",
    )


def _expected_filename(request) -> str:
    last_name = re.sub(r"[^A-Za-z0-9]+", "-", request.taxpayer.last_name.strip().lower()).strip("-")
    if not last_name:
        last_name = "taxpayer"
    sin_digits = "".join(ch for ch in request.taxpayer.sin if ch.isdigit())
    sin_suffix = sin_digits[-4:] if len(sin_digits) >= 4 else (sin_digits or "xxxx")
    return f"t1_{request.tax_year}_{last_name}_{sin_suffix}.pdf"


def test_printout_t1_endpoint_generates_artifact(tmp_path, monkeypatch):
    original_get_settings = app_config.get_settings
    original_get_settings.cache_clear()

    settings = _configure_settings(tmp_path)
    monkeypatch.setattr(app_config, "get_settings", lambda: settings)
    monkeypatch.setattr(t1_render, "get_settings", lambda: settings)
    monkeypatch.setattr("app.api.http.get_settings", lambda: settings)

    state_attrs = [
        "settings",
        "artifact_root",
        "daily_summary_root",
        "submission_digests",
        "summary_index",
    ]
    state_snapshot = {
        name: (hasattr(api_app.state, name), getattr(api_app.state, name, None)) for name in state_attrs
    }

    api_app.state.settings = settings
    api_app.state.artifact_root = Path(settings.artifact_root)
    api_app.state.daily_summary_root = Path(settings.daily_summary_root)
    api_app.state.submission_digests = set()
    api_app.state.summary_index = {}

    request_model = make_min_input(include_examples=True)
    payload = request_model.model_dump(mode="json")
    payload["out_path"] = "printouts"

    expected_name = _expected_filename(request_model)
    expected_path = Path(settings.artifact_root) / "printouts" / expected_name

    response = None
    try:
        with TestClient(api_app) as client:
            response = client.post("/printout/t1", json=payload)
    finally:
        original_get_settings.cache_clear()
        for name, (existed, value) in state_snapshot.items():
            if existed:
                setattr(api_app.state, name, value)
            elif hasattr(api_app.state, name):
                delattr(api_app.state, name)

    assert response is not None

    assert response.status_code == 200
    body = response.json()
    assert "pdf" in body

    pdf_path = Path(body["pdf"])
    assert pdf_path == expected_path
    assert pdf_path.exists()

    reader = PdfReader(str(pdf_path))
    metadata = reader.metadata or {}
    title = getattr(metadata, "title", None) or metadata.get("/Title")
    author = getattr(metadata, "author", None) or metadata.get("/Author")

    expected_title = f"T1 Summary - {request_model.taxpayer.last_name}, {request_model.taxpayer.first_name} ({request_model.tax_year})"
    expected_author = f"{request_model.taxpayer.first_name} {request_model.taxpayer.last_name}".strip()

    assert title == expected_title
    assert author == expected_author

    pages = reader.pages
    assert len(pages) == 1
    page_text = "\n".join(page.extract_text() or "" for page in pages)
    assert "Page 1 of 1" in page_text

    pdf_bytes = pdf_path.read_bytes()
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    expected_digest = GOLDEN_DIGEST_PATH.read_text().strip()
    assert digest == expected_digest
