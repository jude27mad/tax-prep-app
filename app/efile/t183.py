from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

RETENTION_YEARS = 6


@dataclass
class T183Record:
    taxpayer_sin_masked: str
    signed_at: datetime
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


def _compute_expiry(signed_at: datetime) -> datetime:
    try:
        return signed_at.replace(year=signed_at.year + RETENTION_YEARS)
    except ValueError:
        # handle Feb 29, etc.
        return signed_at + (datetime(signed_at.year + RETENTION_YEARS, 3, 1) - datetime(signed_at.year, 3, 1))


def build_record(original_sin: str, signed_at: datetime, pdf_path: str, ip_hash: Optional[str] = None, user_agent_hash: Optional[str] = None) -> T183Record:
    masked = mask_sin(original_sin)
    expires = _compute_expiry(signed_at)
    return T183Record(
        taxpayer_sin_masked=masked,
        signed_at=signed_at,
        expires_at=expires,
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
        pdf_path=pdf_path,
    )


def store_signed(record: T183Record, base_dir: str, tax_year: int, original_sin: str) -> str:
    target_dir = retention_path(base_dir, tax_year, original_sin)
    filename = f"t183_{int(record.signed_at.timestamp())}.json"
    path = target_dir / filename
    payload = asdict(record)
    payload["retention_years"] = RETENTION_YEARS
    path.write_text(json.dumps(payload, default=str, separators=(",", ":")), encoding="utf-8")
    return str(path)


def purge_expired(base_dir: str, as_of: Optional[datetime] = None) -> list[str]:
    base_path = Path(base_dir)
    if not base_path.exists():
        return []
    removed: list[str] = []
    check_time = as_of or datetime.utcnow()
    for file in base_path.rglob("t183_*.json"):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            expires_at = datetime.fromisoformat(data["expires_at"])
            if expires_at <= check_time:
                file.unlink()
                removed.append(str(file))
        except Exception:
            continue
    return removed
