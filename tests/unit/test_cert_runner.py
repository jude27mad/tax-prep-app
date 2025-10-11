from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.http import app as preparer_app
from app.config import get_settings
from scripts import run_cert_tests
from tests.fixtures.min_client import make_min_input


@pytest.mark.asyncio
async def test_cert_runner_saves_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("DAILY_SUMMARY_ROOT", str(tmp_path / "summaries"))
    monkeypatch.setenv("EFILE_ENDPOINT_CERT", "http://localhost:8000")
    get_settings.cache_clear()
    case = make_min_input()

    def fake_prepare(app, req, calc, endpoint_override=None):
        return SimpleNamespace(
            xml_bytes=b"<xml />",
            endpoint="http://localhost:8000",
            digest="deadbeef",
            sbmt_ref_id="CERT0001",
            package=SimpleNamespace(
                envelope_xml=(
                    "<T619Transmission xmlns=\"http://www.cra-arc.gc.ca/xmlns/efile/t619/1.0\">"
                    "<sbmt_ref_id>CERT0001</sbmt_ref_id>"
                    "<Environment>CERT</Environment>"
                    "<SoftwareId>SW</SoftwareId>"
                    "<SoftwareVersion>1.0</SoftwareVersion>"
                    "<TransmitterId>TRN</TransmitterId>"
                    "<RepID>RP1234567</RepID>"
                    "<Payload>DATA</Payload>"
                    "</T619Transmission>"
                )
            ),
        )

    with patch.object(run_cert_tests, "prepare_xml_submission", new=fake_prepare):
        with patch("app.efile.transmit.EfileClient.send", new=AsyncMock(return_value={"codes": ["E000"]})):
            results = await run_cert_tests._run(preparer_app, [case], tmp_path)

    assert len(results) == 1
    assert results[0]["sbmt_ref_id"] == "CERT0001"
    saved_files = list(Path(tmp_path).glob("**/*"))
    assert any("CERT0001" in p.name for p in saved_files)
    get_settings.cache_clear()


