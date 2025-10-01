from datetime import datetime, timedelta

from app.config import get_settings
from app.efile import t183


def _make_record():
    now = datetime(2025, 2, 15, 9, 0, 0)
    return t183.build_record("046454286", now, pdf_path="/tmp/t2183.pdf", ip_hash="ip", user_agent_hash="ua")


def test_t2183_retention_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("RETENTION_T2183_ENABLED", "false")
    get_settings.cache_clear()
    record = _make_record()
    assert t183.store_t2183(record, tmp_path.as_posix(), 2025, "046454286") is None
    assert t183.purge_t2183(tmp_path.as_posix()) == []
    get_settings.cache_clear()


def test_t2183_retention_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("RETENTION_T2183_ENABLED", "true")
    get_settings.cache_clear()
    record = _make_record()
    stored = t183.store_t2183(record, tmp_path.as_posix(), 2025, "046454286")
    assert stored is not None
    purge_time = record.expires_at + timedelta(days=1)
    removed = t183.purge_t2183(tmp_path.as_posix(), as_of=purge_time)
    assert stored in removed
    get_settings.cache_clear()
