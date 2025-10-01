import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.http import app as preparer_app
from scripts import run_cert_tests
from tests.fixtures.min_client import make_min_input


@pytest.mark.asyncio
async def test_cert_runner_saves_artifacts(tmp_path):
    case = make_min_input()

    def fake_prepare(app, req, calc, endpoint_override=None):
        return SimpleNamespace(
            xml_bytes=b"<xml />",
            endpoint="http://localhost:8000",
            digest="deadbeef",
        )

    with patch.object(run_cert_tests, "prepare_xml_submission", new=fake_prepare):
        with patch("app.efile.transmit.EfileClient.send", new=AsyncMock(return_value={"codes": ["E000"]})):
            results = await run_cert_tests._run(preparer_app, [case], tmp_path)

    assert len(results) == 1
    saved_files = list(Path(tmp_path).glob("*"))
    assert saved_files
