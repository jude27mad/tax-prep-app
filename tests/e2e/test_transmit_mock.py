import json
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from app.api.http import app
from tests.fixtures.min_client import make_min_input

@pytest.mark.asyncio
async def test_transmit_path():
  req = json.loads(make_min_input().model_dump_json())
  req.update({"software_id":"X","software_ver":"0.1.0","transmitter_id":"T","endpoint":"http://localhost:9999"})
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as ac:
    with patch("app.efile.transmit.EfileClient.send", new=AsyncMock(return_value={"status":"mocked"})):
      r = await ac.post("/efile/transmit", json=req)
  assert r.status_code == 200
  body = r.json()
  assert body["response"] == {"status": "mocked"}
