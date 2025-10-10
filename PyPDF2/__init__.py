"""Minimal PdfReader implementation for tests."""

from __future__ import annotations

import base64
import re
import zlib
from pathlib import Path
from typing import Iterable

__all__ = ["PdfReader"]


_STREAM_PATTERN = re.compile(rb"stream\r?\n(.*?)endstream", re.DOTALL)


class _PdfMetadata(dict):
    def __init__(self, raw_text: str) -> None:
        super().__init__()
        for key in ("Title", "Author", "Subject", "Creator"):
            value = _extract_metadata_value(raw_text, key)
            if value is not None:
                self[f"/{key}"] = value

    def __getattr__(self, item: str):  # pragma: no cover - convenience proxy
        key = f"/{item.capitalize()}"
        if key in self:
            return self[key]
        raise AttributeError(item)


class _PdfPage:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def extract_text(self) -> str:
        data = self._payload.strip()
        if not data:
            return ""
        try:
            decoded = base64.a85decode(data, adobe=True)
            inflated = zlib.decompress(decoded)
        except Exception:  # pragma: no cover - defensive
            return ""
        return inflated.decode("latin-1", errors="ignore")


class PdfReader:
    """Very small subset of PyPDF2's PdfReader API used in tests."""

    def __init__(self, path: str | Path) -> None:
        pdf_path = Path(path)
        self._data = pdf_path.read_bytes()
        text_repr = self._data.decode("latin-1", errors="ignore")
        self.metadata = _PdfMetadata(text_repr)
        streams = _extract_streams(self._data)
        if not streams:
            streams = [b""]
        self.pages = [_PdfPage(chunk) for chunk in streams]


def _extract_streams(data: bytes) -> list[bytes]:
    return [match.group(1) for match in _STREAM_PATTERN.finditer(data)]


def _extract_metadata_value(pdf_text: str, key: str) -> str | None:
    marker = f"/{key}"
    start = pdf_text.find(marker)
    if start == -1:
        return None
    start = pdf_text.find("(", start)
    if start == -1:
        return None
    start += 1
    result: list[str] = []
    escaped = False
    for ch in pdf_text[start:]:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == ")":
            break
        result.append(ch)
    if not result and not escaped:
        return ""
    return _unescape_pdf_string("".join(result))


def _unescape_pdf_string(value: str) -> str:
    replacements: Iterable[tuple[str, str]] = (
        (r"\\(", "("),
        (r"\\)", ")"),
        (r"\\\\", "\\"),
    )
    for src, dest in replacements:
        value = value.replace(src, dest)
    return value
