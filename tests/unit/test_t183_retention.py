from datetime import datetime, timedelta
from pathlib import Path

from app.efile import t183


def test_mask_sin():
    assert t183.mask_sin("123456789") == "***-***-6789"
    assert t183.mask_sin("123") == "***-***-****"


def test_store_signed_and_purge(tmp_path):
    now = datetime(2025, 9, 30)
    record = t183.build_record("123456789", now, pdf_path="/tmp/t183.pdf", ip_hash="ip", user_agent_hash="ua")
    stored_path = t183.store_signed(record, tmp_path.as_posix(), tax_year=2025, original_sin="123456789")
    stored_file = Path(stored_path)
    assert stored_file.exists()

    data = stored_file.read_text(encoding="utf-8")
    assert "***-***-6789" in data
    assert str(t183.RETENTION_YEARS) in data

    purge_time = record.expires_at + timedelta(days=1)
    removed = t183.purge_expired(tmp_path.as_posix(), as_of=purge_time)
    assert stored_path in removed
