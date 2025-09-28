import json
from decimal import Decimal
from hashlib import sha256
from typing import Any

def _json_default(value: Any) -> str:
  if isinstance(value, Decimal):
    return format(value, 'f')
  raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

def serialize(payload: dict) -> tuple[bytes, str]:
  data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=_json_default).encode("utf-8")
  digest = sha256(data).hexdigest()
  return data, digest
