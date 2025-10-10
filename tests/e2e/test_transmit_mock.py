import json
from unittest.mock import AsyncMock, patch
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

from app.api.http import app
from app.config import Settings
from tests.fixtures.min_client import make_min_input


def _prime_state():
    app.state.settings = Settings(
        feature_efile_xml=True,
        feature_legacy_efile=False,
        efile_environment="CERT",
        endpoint_cert="http://localhost:9999",
        software_id_cert="X",
        software_version="0.1.0",
        transmitter_id_cert="T",
        artifact_root=str(Path('tests/.tmp_artifacts')),
        daily_summary_root=str(Path('tests/.tmp_summaries')),
    )
    schema_cache = {
        schema_path.name: schema_path.read_text()
        for schema_path in Path("app/schemas").glob("*.xsd")
    }
    app.state.cra_schema_cache = schema_cache


@pytest.mark.asyncio
async def test_transmit_path():
    _prime_state()
    req = json.loads(make_min_input().model_dump_json())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("app.efile.transmit.EfileClient.send", new=AsyncMock(return_value={"codes": ["E000"]})):
            r = await ac.post("/prepare/efile", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["envelope"]["software_id"] == "X"
    assert body["response"] == {"codes": ["E000"]}
    assert body["digest"]
    assert body["sbmt_ref_id"]
    assert len(body["sbmt_ref_id"]) == 8
    assert body["sbmt_ref_id"].isalnum()
