from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import Settings
from app.api.http import app as api_app

from tests.fixtures.min_client import make_min_input


def _configure_settings(tmp_path) -> Settings:
    artifacts = tmp_path / "artifacts"
    summaries = tmp_path / "summaries"
    settings = Settings(
        feature_efile_xml=True,
        feature_legacy_efile=True,
        efile_window_open=True,
        artifact_root=str(artifacts),
        daily_summary_root=str(summaries),
        endpoint_cert="http://127.0.0.1:9000",
        endpoint_prod="http://127.0.0.1:9000",
    )
    return settings


def test_prepare_print_and_efile_flow(tmp_path, monkeypatch):
    settings = _configure_settings(tmp_path)
    api_app.state.settings = settings
    api_app.state.artifact_root = Path(settings.artifact_root)
    api_app.state.daily_summary_root = Path(settings.daily_summary_root)
    api_app.state.submission_digests = set()
    api_app.state.summary_index = {}

    from app.api import http as api_http

    digest_value = "deadbeefcafebabe"
    sbmt_ref_id_value = "R1234567"

    def fake_prepare_xml_submission(app_obj, req, calc, endpoint_override=None):  # noqa: WPS430
        artifact_root = Path(app_obj.state.artifact_root)
        artifact_root.mkdir(parents=True, exist_ok=True)
        file_path = artifact_root / f"{sbmt_ref_id_value}_{digest_value}_envelope.xml"
        file_path.write_text("<xml />", encoding="utf-8")

        class DummyEnvelope:  # noqa: WPS430
            software_id = "TEST-SW"
            software_ver = "1.0.0"
            transmitter_id = "123456"
            environment = "CERT"

        return SimpleNamespace(
            envelope=DummyEnvelope(),
            package=SimpleNamespace(),
            digest=digest_value,
            sbmt_ref_id=sbmt_ref_id_value,
            xml_bytes=b"<xml />",
            endpoint=endpoint_override or settings.endpoint_cert,
        )

    monkeypatch.setattr(api_http, "prepare_xml_submission", fake_prepare_xml_submission)

    async def fake_send(self, data, content_type="application/xml"):  # noqa: WPS430
        return {"status": "ok"}

    monkeypatch.setattr(api_http.EfileClient, "send", fake_send)

    client = TestClient(api_app)

    payload = make_min_input().model_dump(mode="json")

    prepare_response = client.post("/prepare", json=payload)
    assert prepare_response.status_code == 200
    prepare_body = prepare_response.json()
    assert prepare_body["ok"] is True
    assert "calc" in prepare_body

    pdf_path = tmp_path / "return.pdf"
    print_payload = {**payload, "out_path": str(pdf_path)}
    print_response = client.post("/printout/t1", json=print_payload)
    assert print_response.status_code == 200
    assert pdf_path.exists()

    efile_response = client.post("/prepare/efile", json=payload)
    assert efile_response.status_code == 200
    efile_body = efile_response.json()
    assert efile_body["digest"] == digest_value
    assert efile_body["sbmt_ref_id"] == sbmt_ref_id_value
    assert efile_body["envelope"]["software_id"] == "TEST-SW"

    list_response = client.get("/ui/artifacts/list", params={"digest": digest_value})
    assert list_response.status_code == 200
    listed = list_response.json()["paths"]
    assert listed, "Expected artifact listing for digest"
    artifact_entry = listed[0]

    download_response = client.get("/ui/artifacts/download", params={"path": artifact_entry["path"]})
    assert download_response.status_code == 200
    assert download_response.content.startswith(b"<xml")


def test_prepare_efile_window_closed(tmp_path):
    settings = Settings(
        feature_efile_xml=True,
        feature_legacy_efile=False,
        efile_window_open=False,
        artifact_root=str(tmp_path / "artifacts"),
        daily_summary_root=str(tmp_path / "summaries"),
        endpoint_cert="http://127.0.0.1:9000",
        endpoint_prod="http://127.0.0.1:9000",
    )
    api_app.state.settings = settings
    api_app.state.artifact_root = Path(settings.artifact_root)
    api_app.state.daily_summary_root = Path(settings.daily_summary_root)
    api_app.state.submission_digests = set()
    api_app.state.summary_index = {}

    client = TestClient(api_app)
    payload = make_min_input().model_dump(mode="json")
    response = client.post("/prepare/efile", json=payload)
    assert response.status_code == 503
    assert response.json()["detail"] == "CRA EFILE window not yet open for 2025"


def test_prepare_efile_rejects_wrong_year(tmp_path):
    settings = _configure_settings(tmp_path)
    api_app.state.settings = settings
    api_app.state.artifact_root = Path(settings.artifact_root)
    api_app.state.daily_summary_root = Path(settings.daily_summary_root)
    api_app.state.submission_digests = set()
    api_app.state.summary_index = {}

    client = TestClient(api_app)
    payload = make_min_input(tax_year=2024).model_dump(mode="json")
    response = client.post("/prepare/efile", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "EFILE XML is only available for 2025 filings"
