from __future__ import annotations

import base64
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class EncryptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _cipher() -> Optional[Fernet]:
    key = get_settings().t183_crypto_key
    if not key:
        return None
    try:
        raw = key.encode("utf-8")
        # Allow keys provided without padding
        missing = len(raw) % 4
        if missing:
            raw += b"=" * (4 - missing)
        decoded = base64.urlsafe_b64decode(raw)
        return Fernet(base64.urlsafe_b64encode(decoded))
    except Exception as exc:  # pragma: no cover - configuration errors caught early
        raise EncryptionError("Invalid T183 crypto key provided") from exc


def encrypt(data: bytes) -> bytes:
    cipher = _cipher()
    if cipher is None:
        return data
    return cipher.encrypt(data)


def decrypt(data: bytes) -> bytes:
    cipher = _cipher()
    if cipher is None:
        return data
    try:
        return cipher.decrypt(data)
    except InvalidToken as exc:  # pragma: no cover - indicates configuration drift
        raise EncryptionError("Failed to decrypt T183 record") from exc
