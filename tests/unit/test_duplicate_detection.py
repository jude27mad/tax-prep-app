import pytest
from fastapi import HTTPException

from app.api.http import app as api_app
from app.config import get_settings
from app.core.tax_years._2025_alias import compute_return
from app.efile.service import prepare_xml_submission
from tests.fixtures.min_client import make_min_input


@pytest.mark.asyncio
async def test_duplicate_digest_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("DAILY_SUMMARY_ROOT", str(tmp_path / "summaries"))
    get_settings.cache_clear()

    async with api_app.router.lifespan_context(api_app):
        req = make_min_input()
        calc = compute_return(req)
        prepare_xml_submission(api_app, req, calc)
        with pytest.raises(HTTPException) as exc:
            prepare_xml_submission(api_app, req, calc)
        assert exc.value.status_code == 409

    get_settings.cache_clear()
