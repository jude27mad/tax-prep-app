import os
from fastapi.testclient import TestClient

from app.api.http import app as api_app
from app.config import get_settings
from tests.fixtures.min_client import make_min_input


def test_health_includes_build_meta():
    get_settings.cache_clear()
    os.environ["BUILD_VERSION"] = "1.2.3"
    os.environ["BUILD_SHA"] = "abc123"
    os.environ["FEATURE_EFILE_XML"] = "true"
    os.environ["FEATURE_LEGACY_EFILE"] = "true"
    api_app.state.last_sbmt_ref_id = "CERT0001"
    with TestClient(api_app) as client:
        resp = client.get("/health")
        body = resp.json()
    assert body["build"]["version"] == "1.2.3"
    assert body["build"]["sha"] == "abc123"
    assert body["build"]["feature_efile_xml"] is True
    assert body["build"]["feature_legacy_efile"] is True
    assert body["build"]["sbmt_ref_id_last"] == "CERT0001"
    get_settings.cache_clear()
    if hasattr(api_app.state, "last_sbmt_ref_id"):
        delattr(api_app.state, "last_sbmt_ref_id")
    for key in ("BUILD_VERSION", "BUILD_SHA", "FEATURE_EFILE_XML", "FEATURE_LEGACY_EFILE"):
        os.environ.pop(key, None)


def test_legacy_efile_disabled_returns_410(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("FEATURE_LEGACY_EFILE", "false")
    payload = make_min_input().model_dump(mode="json")
    with TestClient(api_app) as client:
        resp = client.post("/legacy/efile", json=payload)
        body = resp.json()

    assert resp.status_code == 410
    assert body == {"detail": "Legacy EFILE disabled"}
    get_settings.cache_clear()
