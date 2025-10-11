import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import get_settings
from app.efile import t183, crypto
from app.efile.crypto import EncryptionError, decrypt, encrypt


TEST_KEY = "jLNo6J1iO5Y5P2bIC2T5T8DKS-p91Z9a7qV3-0iKqa4="


def _clear_caches() -> None:
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def _set_crypto_key(monkeypatch) -> None:
    monkeypatch.setenv("T183_CRYPTO_KEY", TEST_KEY)
    _clear_caches()


def test_mask_sin():
    assert t183.mask_sin("123456789") == "***-***-6789"
    assert t183.mask_sin("123") == "***-***-****"


def test_store_signed_and_purge(tmp_path, monkeypatch):
    _set_crypto_key(monkeypatch)
    signed_at = datetime(2025, 9, 30, 12, 0, 0)
    filed_at = datetime(2025, 10, 1, 10, 30, 0, tzinfo=timezone.utc)
    accepted_at = datetime(2025, 9, 30, 12, 5, 0)
    record = t183.build_record(
        "123456789",
        signed_at,
        filed_at,
        pdf_path="/tmp/t183.pdf",
        ip_hash="ip",
        user_agent_hash="ua",
        esign_accepted_at=accepted_at,
    )
    stored_path = t183.store_signed(record, tmp_path.as_posix(), tax_year=2025, original_sin="123456789")
    stored_file = Path(stored_path)
    assert stored_file.exists()

    payload_bytes = stored_file.read_bytes()
    assert stored_file.suffix == ".enc"
    assert b"***-***-6789" not in payload_bytes
    plaintext = decrypt(payload_bytes)
    payload = json.loads(plaintext.decode("utf-8"))
    assert payload["taxpayer_sin_masked"] == "***-***-6789"
    assert payload["retention_years"] == t183.RETENTION_YEARS
    assert payload["filed_at"] == record.filed_at.isoformat()
    assert payload["esign_accepted_at"] == record.esign_accepted_at.isoformat()

    purge_time = record.expires_at + timedelta(days=1)
    removed = t183.purge_expired(tmp_path.as_posix(), as_of=purge_time)
    assert stored_path in removed
    _clear_caches()


def test_expiry_from_filed_at(monkeypatch):
    _set_crypto_key(monkeypatch)
    filed_at = datetime(2024, 2, 29, 8, 0, 0, tzinfo=timezone.utc)
    record = t183.build_record(
        "987654321",
        signed_at=datetime(2024, 2, 28, 23, 45, 0),
        filed_at=filed_at,
        pdf_path="/tmp/t183.pdf",
    )
    assert record.filed_at == filed_at
    expected_expiry = filed_at + (
        datetime(2030, 3, 1, tzinfo=timezone.utc) - datetime(2024, 3, 1, tzinfo=timezone.utc)
    )
    assert record.expires_at == expected_expiry
    _clear_caches()


def test_encrypt_requires_key(monkeypatch):
    monkeypatch.delenv("T183_CRYPTO_KEY", raising=False)
    _clear_caches()
    with pytest.raises(EncryptionError):
        encrypt(b"payload")
    with pytest.raises(EncryptionError):
        decrypt(b"payload")
