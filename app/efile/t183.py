from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings

from .crypto import decrypt, encrypt

logger = logging.getLogger("tax_app")

RETENTION_YEARS = 6


@dataclass
class T183Record:
    taxpayer_sin_masked: str
    filed_at: datetime
    signed_at: datetime
    esign_accepted_at: Optional[datetime]
    expires_at: datetime
    ip_hash: Optional[str]
    user_agent_hash: Optional[str]
    pdf_path: str


def mask_sin(sin: str) -> str:
    return f"***-***-{sin[-4:]}" if sin and len(sin) == 9 else "***-***-****"


def retention_path(base: str, tax_year: int, sin: str) -> Path:
    p = Path(base) / f"{tax_year}" / sin[-4:]
    p.mkdir(parents=True, exist_ok=True)
    return p


def _compute_expiry(filed_at: datetime) -> datetime:
    try:
        return filed_at.replace(year=filed_at.year + RETENTION_YEARS)
    except ValueError:
        return filed_at + (
            datetime(filed_at.year + RETENTION_YEARS, 3, 1, tzinfo=filed_at.tzinfo)
            - datetime(filed_at.year, 3, 1, tzinfo=filed_at.tzinfo)
        )




def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def build_record(
    original_sin: str,
    signed_at: datetime,
    filed_at: datetime,
    pdf_path: str,
    ip_hash: Optional[str] = None,
    user_agent_hash: Optional[str] = None,
    esign_accepted_at: Optional[datetime] = None,
) -> T183Record:
    masked = mask_sin(original_sin)
    signed_at_utc = _ensure_utc(signed_at)
    filed_at_utc = _ensure_utc(filed_at)
    accepted_at_utc = _ensure_utc(esign_accepted_at) if esign_accepted_at else None
    expires = _compute_expiry(filed_at_utc)
    return T183Record(
        taxpayer_sin_masked=masked,
        filed_at=filed_at_utc,
        signed_at=signed_at_utc,
        esign_accepted_at=accepted_at_utc,
        expires_at=expires,
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
        pdf_path=pdf_path,
    )


def _store_authorization(record: T183Record, base_dir: str, tax_year: int, original_sin: str, prefix: str) -> str:
    target_dir = retention_path(base_dir, tax_year, original_sin)
    payload = asdict(record)
    serialized: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    serialized["retention_years"] = RETENTION_YEARS
    raw = json.dumps(serialized, separators=(",", ":")).encode("utf-8")
    encrypted = encrypt(raw)
    filename = f"{prefix}_{int(record.filed_at.timestamp())}.enc"
    path = target_dir / filename
    path.write_bytes(encrypted)
    return str(path)


def store_signed(record: T183Record, base_dir: str, tax_year: int, original_sin: str) -> str:
    return _store_authorization(record, base_dir, tax_year, original_sin, "t183")


def store_t2183(record: T183Record, base_dir: str, tax_year: int, original_sin: str) -> Optional[str]:
    if not get_settings().retention_t2183_enabled:
        logger.info("T2183 retention disabled; skipping store for %s", mask_sin(original_sin))
        return None
    return _store_authorization(record, base_dir, tax_year, original_sin, "t2183")


def _purge_authorizations(base_dir: str, prefix: str, as_of: Optional[datetime]) -> list[str]:
    base_path = Path(base_dir)
    if not base_path.exists():
        return []
    check_time = as_of or datetime.now(timezone.utc)
    if check_time.tzinfo is None:
        check_time = check_time.replace(tzinfo=timezone.utc)
    removed: list[str] = []
    for file in base_path.rglob(f"{prefix}_*"):
        if file.suffix not in {".json", ".enc"}:
            continue
        try:
            if file.suffix == ".enc":
                payload_bytes = decrypt(file.read_bytes())
            else:
                payload_bytes = file.read_bytes()
            data = json.loads(payload_bytes.decode("utf-8"))
            expires_at = datetime.fromisoformat(data["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= check_time:
                file.unlink()
                removed.append(str(file))
        except Exception:
            continue
    return removed


def purge_expired(base_dir: str, as_of: Optional[datetime] = None) -> list[str]:
    return _purge_authorizations(base_dir, "t183", as_of)


def purge_t2183(base_dir: str, as_of: Optional[datetime] = None) -> list[str]:
    if not get_settings().retention_t2183_enabled:
        logger.info("T2183 retention disabled; skipping purge")
        return []
    return _purge_authorizations(base_dir, "t2183", as_of)

