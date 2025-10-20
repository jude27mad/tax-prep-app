from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import io
from pathlib import Path
import re
from typing import Iterable, Sequence

from starlette.datastructures import UploadFile

MAX_BYTES = 2 * 1024 * 1024  # 2 MiB cap for inline processing

FIELD_PATTERNS: dict[str, Sequence[str]] = {
    "employment_income": (
        r"box\s*14[^0-9]*([\d][\d,\. ]*)",
        r"employment income[^0-9]*([\d][\d,\. ]*)",
    ),
    "tax_deducted": (
        r"box\s*22[^0-9]*([\d][\d,\. ]*)",
        r"income tax deducted[^0-9]*([\d][\d,\. ]*)",
    ),
    "cpp_contrib": (
        r"box\s*16[^0-9]*([\d][\d,\. ]*)",
        r"cpp contributions[^0-9]*([\d][\d,\. ]*)",
    ),
    "ei_premiums": (
        r"box\s*18[^0-9]*([\d][\d,\. ]*)",
        r"employment insurance premiums[^0-9]*([\d][\d,\. ]*)",
    ),
    "pensionable_earnings": (
        r"box\s*26[^0-9]*([\d][\d,\. ]*)",
        r"pensionable earnings[^0-9]*([\d][\d,\. ]*)",
    ),
    "insurable_earnings": (
        r"box\s*24[^0-9]*([\d][\d,\. ]*)",
        r"insurable earnings[^0-9]*([\d][\d,\. ]*)",
    ),
}


@dataclass
class SlipDetection:
    source: str
    fields: dict[str, str]
    warnings: list[str]
    applied: bool = False
    applied_index: int | None = None
    preview: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "fields": self.fields,
            "warnings": self.warnings,
            "applied": self.applied,
            "applied_index": self.applied_index,
            "preview": self.preview,
        }


def _normalize_amount(raw: str) -> str | None:
    cleaned = raw.strip().replace(",", "").replace("$", "").replace(" ", "")
    cleaned = cleaned.replace("O", "0")  # common OCR quirk
    if cleaned.endswith("."):
        cleaned = cleaned[:-1]
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return f"{value.quantize(Decimal('0.01'))}"


def _extract_text_from_pdf(data: bytes) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        from PyPDF2 import PdfReader  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - import failure handled in warning
        warnings.append(f"Unable to import PyPDF2 for PDF parsing: {exc}")
        return "", warnings

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # pragma: no cover - invalid PDFs
        warnings.append(f"Failed to open PDF: {exc}")
        return "", warnings

    text_parts: list[str] = []
    for page in reader.pages:
        try:
            extracted = page.extract_text() or ""
        except Exception as exc:  # pragma: no cover - PyPDF2 fallback
            warnings.append(f"Failed to extract PDF page text: {exc}")
            continue
        text_parts.append(extracted)
    return "\n".join(text_parts), warnings


def _decode_bytes(data: bytes, filename: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        return _extract_text_from_pdf(data)

    if ext in {".txt", ".csv"}:
        try:
            return data.decode("utf-8"), warnings
        except UnicodeDecodeError:
            warnings.append("Unable to decode text file as UTF-8; using latin-1 fallback.")
            return data.decode("latin-1", errors="ignore"), warnings

    # Attempt a generic UTF-8 decode
    try:
        return data.decode("utf-8"), warnings
    except UnicodeDecodeError:
        warnings.append("Unsupported file format for slip auto-detection.")
        return "", warnings


def _detect_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    if not text:
        return fields
    for key, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = _normalize_amount(match.group(1))
                if value:
                    fields[key] = value
                    break
        # continue searching other patterns only until first match
    return fields


async def ingest_slip_uploads(files: Iterable[UploadFile]) -> tuple[list[SlipDetection], list[str]]:
    detections: list[SlipDetection] = []
    errors: list[str] = []

    for upload in files:
        if not isinstance(upload, UploadFile):
            continue
        if not upload.filename:
            continue

        try:
            content = await upload.read()
        finally:
            await upload.close()

        if not content:
            errors.append(f"{upload.filename}: file was empty.")
            continue
        if len(content) > MAX_BYTES:
            errors.append(f"{upload.filename}: file exceeds {MAX_BYTES // (1024 * 1024)} MiB limit.")
            continue

        text, warnings = _decode_bytes(content, upload.filename)
        fields = _detect_fields(text)
        preview = text.strip().splitlines()
        summary = "\n".join(preview[:6]) if preview else None
        detections.append(
            SlipDetection(
                source=upload.filename,
                fields=fields,
                warnings=list(warnings),
                preview=summary,
            )
        )

    return detections, errors


__all__ = ["SlipDetection", "ingest_slip_uploads"]
