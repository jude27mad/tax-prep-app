from __future__ import annotations

import asyncio
import hashlib
import io
import mimetypes
import re
import secrets
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Literal

from fastapi import UploadFile
from pydantic import BaseModel, Field
from PyPDF2 import PdfReader

from app.config import Settings
from app.wizard import BASE_DIR, slugify

__all__ = [
    "ingest_slip_uploads",
    "slip_job_status",
    "apply_staged_detections",
    "SlipUploadError",
    "SlipJobNotFoundError",
    "SlipApplyError",
    "SlipDetection",
    "SlipJobStatus",
    "SlipStagingStore",
    "resolve_store",
]

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    ".webp",
}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}

MAX_UPLOAD_SIZE = 8 * 1024 * 1024  # 8 MiB cap per upload
PREVIEW_LIMIT = 2_000
_CENT = Decimal("0.01")


class SlipUploadError(Exception):
    pass


class SlipJobNotFoundError(Exception):
    pass


class SlipApplyError(Exception):
    pass


class SlipDetection(BaseModel):
    id: str
    slip_type: str
    original_filename: str
    stored_filename: str
    stored_path: str
    size: int
    preview: str = Field(default="")
    fields: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SlipJobStatus(BaseModel):
    job_id: str
    status: Literal["processing", "complete", "error"]
    detection: SlipDetection | None = None
    error: str | None = None


@dataclass
class _SlipJobRecord:
    job_id: str
    bucket: str
    original_filename: str
    status: Literal["processing", "complete", "error"] = "processing"
    detection: SlipDetection | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_status(self) -> SlipJobStatus:
        return SlipJobStatus(
            job_id=self.job_id,
            status=self.status,
            detection=self.detection,
            error=self.error,
        )


class ApplyDetectionsRequest(BaseModel):
    detection_ids: list[str] | None = None


class SlipStagingStore:
    def __init__(self) -> None:
        self._jobs: dict[str, _SlipJobRecord] = {}
        self._staged: dict[str, dict[str, SlipDetection]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _bucket(profile: str, year: int) -> str:
        return f"{profile}:{year}"

    async def process_upload(
        self,
        profile: str,
        year: int,
        upload: UploadFile,
        *,
        settings: Settings,
    ) -> SlipJobStatus:
        safe_profile = slugify(profile) or "default"
        bucket = self._bucket(safe_profile, year)
        job_id = secrets.token_hex(8)
        record = _SlipJobRecord(
            job_id=job_id,
            bucket=bucket,
            original_filename=upload.filename or "",
        )
        async with self._lock:
            self._jobs[job_id] = record
        try:
            detection = await _ingest_upload(
                job_id, safe_profile, year, upload, settings=settings
            )
        except SlipUploadError as exc:
            record.status = "error"
            record.error = str(exc)
            async with self._lock:
                self._jobs[job_id] = record
            raise
        except Exception as exc:  # pragma: no cover
            record.status = "error"
            record.error = "Unable to process slip"
            async with self._lock:
                self._jobs[job_id] = record
            raise SlipUploadError("Unable to process slip") from exc
        else:
            record.status = "complete"
            record.detection = detection
            async with self._lock:
                self._jobs[job_id] = record
                staged = self._staged.setdefault(bucket, {})
                staged[detection.id] = detection
            return record.to_status()
        finally:
            await upload.close()

    async def job_status(self, profile: str, year: int, job_id: str) -> SlipJobStatus:
        safe_profile = slugify(profile) or "default"
        bucket = self._bucket(safe_profile, year)
        async with self._lock:
            record = self._jobs.get(job_id)
        if record is None or record.bucket != bucket:
            raise SlipJobNotFoundError("Upload job not found")
        return record.to_status()

    async def apply(
        self,
        profile: str,
        year: int,
        detection_ids: Iterable[str] | None = None,
    ) -> list[SlipDetection]:
        safe_profile = slugify(profile) or "default"
        bucket = self._bucket(safe_profile, year)
        async with self._lock:
            staged = self._staged.get(bucket)
            if not staged:
                return []

            if detection_ids is None:
                results = list(staged.values())
                self._staged.pop(bucket, None)
                return results

            results: list[SlipDetection] = []
            for detection_id in detection_ids:
                detection = staged.pop(detection_id, None)
                if detection is None:
                    raise SlipApplyError(f"Detection {detection_id} not found for profile")
                results.append(detection)

            if not staged:
                self._staged.pop(bucket, None)
            return results

    async def clear(self, profile: str, year: int) -> None:
        safe_profile = slugify(profile) or "default"
        bucket = self._bucket(safe_profile, year)
        async with self._lock:
            self._staged.pop(bucket, None)


_DEFAULT_STORE = SlipStagingStore()


def resolve_store(app: Any | None = None) -> SlipStagingStore:
    if app is None:
        return _DEFAULT_STORE
    store = getattr(app.state, "slip_staging_store", None)
    if isinstance(store, SlipStagingStore):
        return store
    store = SlipStagingStore()
    setattr(app.state, "slip_staging_store", store)
    return store


async def _ingest_upload(
    detection_id: str,
    profile: str,
    year: int,
    upload: UploadFile,
    *,
    settings: Settings,
) -> SlipDetection:
    filename = upload.filename or "upload"
    data = await upload.read()
    if not data:
        raise SlipUploadError("Uploaded file was empty")
    size = len(data)
    extension = _resolve_extension(filename, upload.content_type)
    _validate_upload(extension, size)
    text = _extract_text(extension, data)
    if not text.strip():
        raise SlipUploadError("Unable to extract text from upload")
    slip_type = _classify_slip(text)
    stored_path, stored_filename = _persist_upload(
        settings, profile, year, slip_type, extension, data
    )
    fields = _build_detection_fields(slip_type, text)
    preview = text[:PREVIEW_LIMIT]
    return SlipDetection(
        id=detection_id,
        slip_type=slip_type,
        original_filename=filename,
        stored_filename=stored_filename,
        stored_path=stored_path,
        size=size,
        preview=preview,
        fields=fields,
        created_at=datetime.now(timezone.utc),
    )


def _resolve_extension(filename: str, content_type: str | None) -> str:
    extension = Path(filename).suffix.lower()
    if extension:
        return extension
    if content_type:
        guessed = mimetypes.guess_extension(content_type)
        if guessed:
            return guessed.lower()
    return ""


def _validate_upload(extension: str, size: int) -> None:
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise SlipUploadError(f"Unsupported file type. Allowed extensions: {allowed}")
    if size > MAX_UPLOAD_SIZE:
        raise SlipUploadError("File exceeds maximum allowed size of 8 MiB")


def _extract_text(extension: str, data: bytes) -> str:
    if extension == ".pdf":
        return _extract_text_from_pdf(data)
    if extension in IMAGE_EXTENSIONS:
        return _extract_text_from_image(data)
    raise SlipUploadError("Unsupported file type for text extraction")


def _extract_text_from_pdf(data: bytes) -> str:
    try:
        tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    except OSError as exc:  # pragma: no cover
        raise SlipUploadError("Unable to stage PDF upload for processing") from exc
    try:
        with tmp_file:
            tmp_file.write(data)
            tmp_path = Path(tmp_file.name)
        reader = PdfReader(tmp_path)
        pages: list[str] = []
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # pragma: no cover
                raise SlipUploadError("Unable to extract text from PDF page") from exc
            pages.append(text)
        return "\n".join(pages)
    except SlipUploadError:
        raise
    except Exception as exc:  # pragma: no cover
        raise SlipUploadError("Unable to read PDF upload") from exc
    finally:
        try:
            Path(tmp_file.name).unlink()
        except OSError:  # pragma: no cover
            pass


def _extract_text_from_image(data: bytes) -> str:
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover
        raise SlipUploadError("Image OCR requires Pillow to be installed") from exc
    try:
        import pytesseract  # type: ignore
    except Exception as exc:  # noqa: F841
        raise SlipUploadError("Image OCR requires the pytesseract package to be installed") from exc
    with Image.open(io.BytesIO(data)) as image:
        try:
            return pytesseract.image_to_string(image)
        except Exception as exc:  # pragma: no cover
            raise SlipUploadError("Unable to extract text from image upload") from exc


def _classify_slip(text: str) -> str:
    lowered = text.lower()
    if "t4a" in lowered or "t4-a" in lowered:
        return "t4a"
    if "t5" in lowered and "t4" not in lowered:
        return "t5"
    if "t4 slip" in lowered or "statement of remuneration" in lowered:
        return "t4"
    if "t5" in lowered:
        return "t5"
    return "t4"


def _persist_upload(
    settings: Settings,
    profile: str,
    year: int,
    slip_type: str,
    extension: str,
    data: bytes,
) -> tuple[str, str]:
    root = Path(settings.artifact_root)
    if not root.is_absolute():
        root = (BASE_DIR / root).resolve()
    upload_dir = root / "returns" / profile / str(year) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()[:16]
    safe_type = slip_type or "unknown"
    stored_filename = f"{digest}-{safe_type}{extension}"
    path = upload_dir / stored_filename
    path.write_bytes(data)
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    return str(relative), stored_filename


def _build_detection_fields(slip_type: str, text: str) -> dict[str, str]:
    mapping: dict[str, list[str]]
    if slip_type == "t4":
        mapping = {
            "employment_income": ["box 14", "employment income"],
            "tax_deducted": ["box 22", "income tax deducted"],
            "cpp_contrib": ["box 16", "cpp contributions"],
            "ei_premiums": ["box 18", "ei premiums"],
            "pensionable_earnings": ["box 26", "pensionable earnings"],
            "insurable_earnings": ["box 24", "insurable earnings"],
        }
    elif slip_type == "t4a":
        mapping = {
            "pension_income": ["box 16", "pension income"],
            "other_income": ["box 18", "other income"],
            "self_employment_commissions": ["box 20", "self-employed commissions"],
            "research_grants": ["box 48", "research grants"],
            "tax_deducted": ["box 22", "income tax deducted"],
        }
    elif slip_type == "t5":
        mapping = {
            "interest_income": ["box 13", "interest income"],
            "eligible_dividends": ["box 25", "eligible dividends"],
            "other_dividends": ["box 23", "other dividends"],
            "capital_gains": ["box 18", "capital gains"],
            "foreign_income": ["box 15", "foreign income"],
            "foreign_tax_withheld": ["box 16", "foreign tax"],
        }
    else:
        return {}

    fields: dict[str, str] = {}
    for field_name, keywords in mapping.items():
        value = _extract_numeric_value(text, keywords)
        if value is not None:
            fields[field_name] = value
    return fields


def _keyword_pattern(keyword: str) -> str:
    escaped = re.escape(keyword)
    return escaped.replace("\\ ", r"\s+")


def _extract_numeric_value(text: str, keywords: Iterable[str]) -> str | None:
    normalized = text.replace("\r", " ")
    for keyword in keywords:
        pattern = _keyword_pattern(keyword)
        regex = re.compile(rf"{pattern}[^0-9\-]*(-?[\d,\s]*\.?\d+)", re.IGNORECASE)
        match = regex.search(normalized)
        if not match:
            continue
        raw_value = match.group(1)
        cleaned = raw_value.replace(",", "").replace(" ", "")
        try:
            amount = Decimal(cleaned)
        except (InvalidOperation, ValueError):
            continue
        return format(amount.quantize(_CENT), "f")
    return None


async def ingest_slip_uploads(
    profile: str,
    year: int,
    uploads: Iterable[UploadFile],
    *,
    settings: Settings,
    app: Any | None = None,
) -> list[SlipJobStatus]:
    store = resolve_store(app)
    statuses: list[SlipJobStatus] = []
    for upload in uploads:
        statuses.append(await store.process_upload(profile, year, upload, settings=settings))
    return statuses


async def slip_job_status(
    profile: str,
    year: int,
    job_id: str,
    *,
    app: Any | None = None,
) -> SlipJobStatus:
    store = resolve_store(app)
    return await store.job_status(profile, year, job_id)


async def apply_staged_detections(
    profile: str,
    year: int,
    detection_ids: Iterable[str] | None = None,
    *,
    app: Any | None = None,
) -> list[SlipDetection]:
    store = resolve_store(app)
    return await store.apply(profile, year, detection_ids)
