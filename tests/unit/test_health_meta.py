import os
from fastapi.testclient import TestClient

from app.api.http import app as api_app
from app.config import get_settings


def test_health_includes_build_meta():
    get_settings.cache_clear()
    os.environ["BUILD_VERSION"] = "1.2.3"
    os.environ["BUILD_SHA"] = "abc123"
    os.environ["FEATURE_EFILE_XML"] = "true"
    api_app.state.last_sbmt_ref_id = "CERT0001"
    with TestClient(api_app) as client:
        resp = client.get("/health")
        body = resp.json()
    assert body["build"]["version"] == "1.2.3"
    assert body["build"]["sha"] == "abc123"
    assert body["build"]["feature_efile_xml"] is True
    assert body["build"]["sbmt_ref_id_last"] == "CERT0001"
    get_settings.cache_clear()
    if hasattr(api_app.state, "last_sbmt_ref_id"):
        delattr(api_app.state, "last_sbmt_ref_id")
    for key in ("BUILD_VERSION", "BUILD_SHA", "FEATURE_EFILE_XML"):
        os.environ.pop(key, None)
