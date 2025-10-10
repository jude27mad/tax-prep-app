from __future__ import annotations

from unittest.mock import AsyncMock, patch
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.http import app as api_app
from app.config import Settings
from tests.fixtures.min_client import make_min_input


def _settings_for_test(tmp_path: Path, **overrides) -> Settings:
    base_kwargs = {
        "artifact_root": str(tmp_path / "artifacts"),
        "daily_summary_root": str(tmp_path / "summaries"),
        "endpoint_cert": "http://127.0.0.1:9000",
        "endpoint_prod": "http://127.0.0.1:9000",
    }
    base_kwargs.update(overrides)
    return Settings(**base_kwargs)


def test_legacy_efile_disabled_returns_410(tmp_path):
    settings = _settings_for_test(tmp_path, feature_legacy_efile=False)
    previous = getattr(api_app.state, "settings", None)
    api_app.state.settings = settings
    try:
        client = TestClient(api_app)
        payload = make_min_input().model_dump(mode="json")
        response = client.post("/legacy/efile", json=payload)
    finally:
        if previous is None:
            if hasattr(api_app.state, "settings"):
                delattr(api_app.state, "settings")
        else:
            api_app.state.settings = previous
    assert response.status_code == 410
    assert response.json() == {"detail": "Legacy efile endpoint has been retired"}


def test_legacy_efile_enabled_returns_success(tmp_path):
    settings = _settings_for_test(tmp_path, feature_legacy_efile=True)
    previous = getattr(api_app.state, "settings", None)
    api_app.state.settings = settings
    try:
        client = TestClient(api_app)
        payload = make_min_input().model_dump(mode="json")
        with patch("app.api.http.EfileClient.send", new=AsyncMock(return_value={"codes": ["E000"]})):
            response = client.post("/legacy/efile", json=payload)
    finally:
        if previous is None:
            if hasattr(api_app.state, "settings"):
                delattr(api_app.state, "settings")
        else:
            api_app.state.settings = previous
    assert response.status_code == 200
    body = response.json()
    assert body["response"] == {"codes": ["E000"]}
    assert body["digest"]
