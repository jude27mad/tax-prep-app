from __future__ import annotations

import asyncio
import hashlib
import io
import mimetypes
import re
import secrets
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Literal

from fastapi import UploadFile
from pydantic import BaseModel, Field, ConfigDict
from PyPDF2 import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import select

from app.config import Settings
from app.db import (
    Base,
    DocumentRow,
    DocumentSource,
    DocumentStatus,
    create_session_factory,
    session_scope,
)
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
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf", ".txt"}

MAX_UPLOAD_SIZE = 8 * 1024 * 1024
PREVIEW_LIMIT = 2_000
_CENT = Decimal("0.01")


class SlipUploadError(Exception):
    pass


class SlipJobNotFoundError(Exception):
    pass


class SlipApplyError(Exception):
    pass


class SlipDetection(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    slip_type: str
    original_filename: str
    stored_filename: str
    stored_path: str
    size: int
    preview: str = Field(default="")
    fields: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SlipJobStatus(BaseModel):
    job_id: str
    status: Literal["processing", "complete", "error"]
    detection: SlipDetection | None = None
    error: str | None = None


class ApplyDetectionsRequest(BaseModel):
    detection_ids: list[str] | None = None


def _detection_from_row(row: DocumentRow) -> SlipDetection:
    fields_raw: dict[str, Any] = row.raw_fields or {}
    return SlipDetection(
        id=row.id,
        slip_type=row.slip_type,
        original_filename=row.original_filename,
        stored_filename=row.stored_filename or "",
        stored_path=row.stored_path or "",
        size=row.size_bytes,
        preview=row.preview_text or "",
        fields={str(k): str(v) for k, v in fields_raw.items()},
        warnings=list(row.warnings or []),
        created_at=row.created_at,
    )


def _status_from_row(row: DocumentRow) -> SlipJobStatus:
    if row.status == DocumentStatus.ERROR.value:
        return SlipJobStatus(job_id=row.id, status="error", error=row.error_message)
    if row.status == DocumentStatus.PROCESSING.value:
        return SlipJobStatus(job_id=row.id, status="processing")
    # COMPLETE and APPLIED both expose the detection to the caller; APPLIED
    # is treated as terminal "complete" from the UI's perspective because
    # the detection already landed on the return.
    return SlipJobStatus(
        job_id=row.id, status="complete", detection=_detection_from_row(row)
    )


class SlipStagingStore:
    """DB-backed staging store. Writes through to the ``documents`` table
    (see :class:`app.db.models.DocumentRow`). A PROCESSING row is inserted
    on upload receipt, then updated to COMPLETE (with detection fields) or
    ERROR (with message) as extraction finishes. ``apply()`` flips rows
    COMPLETE → APPLIED; ``clear()`` deletes COMPLETE rows but preserves
    APPLIED rows as an audit trail.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def process_upload(
        self,
        profile: str,
        year: int,
        upload: UploadFile,
        *,
        settings: Settings,
    ) -> SlipJobStatus:
        safe_profile = slugify(profile) or "default"
        filename = upload.filename or ""
        doc_id = str(uuid.uuid4())

        async with session_scope(self._factory) as session:
            session.add(
                DocumentRow(
                    id=doc_id,
                    profile_slug=safe_profile,
                    tax_year=int(year),
                    source_type=DocumentSource.UPLOAD.value,
                    slip_type="unknown",
                    status=DocumentStatus.PROCESSING.value,
                    original_filename=filename,
                    raw_fields={},
                    warnings=[],
                )
            )

        try:
            detection = await _ingest_upload(
                doc_id, safe_profile, int(year), upload, settings=settings
            )
        except SlipUploadError as exc:
            await self._mark_error(doc_id, str(exc))
            raise
        except Exception as exc:
            await self._mark_error(doc_id, "Unable to process slip")
            raise SlipUploadError("Unable to process slip") from exc
        else:
            await self._mark_complete(doc_id, detection)
            return SlipJobStatus(
                job_id=doc_id, status="complete", detection=detection
            )
        finally:
            await upload.close()

    async def _mark_error(self, doc_id: str, message: str) -> None:
        async with session_scope(self._factory) as session:
            row = await session.get(DocumentRow, doc_id)
            if row is None:
                return
            row.status = DocumentStatus.ERROR.value
            row.error_message = message[:2048]

    async def _mark_complete(self, doc_id: str, detection: SlipDetection) -> None:
        async with session_scope(self._factory) as session:
            row = await session.get(DocumentRow, doc_id)
            if row is None:
                return
            row.slip_type = detection.slip_type
            row.status = DocumentStatus.COMPLETE.value
            row.stored_filename = detection.stored_filename or None
            row.stored_path = detection.stored_path or None
            row.size_bytes = detection.size
            row.preview_text = detection.preview or None
            row.raw_fields = dict(detection.fields)
            row.warnings = list(detection.warnings)

    async def job_status(self, profile: str, year: int, job_id: str) -> SlipJobStatus:
        safe_profile = slugify(profile) or "default"
        async with session_scope(self._factory) as session:
            row = await session.get(DocumentRow, job_id)
            if (
                row is None
                or row.profile_slug != safe_profile
                or row.tax_year != int(year)
            ):
                raise SlipJobNotFoundError("Upload job not found")
            return _status_from_row(row)

    async def apply(
        self,
        profile: str,
        year: int,
        detection_ids: Iterable[str] | None = None,
    ) -> list[SlipDetection]:
        safe_profile = slugify(profile) or "default"
        async with session_scope(self._factory) as session:
            stmt = (
                select(DocumentRow)
                .where(DocumentRow.profile_slug == safe_profile)
                .where(DocumentRow.tax_year == int(year))
                .where(DocumentRow.status == DocumentStatus.COMPLETE.value)
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            by_id = {row.id: row for row in rows}

            if detection_ids is None:
                selected = list(rows)
            else:
                requested = list(detection_ids)
                selected = []
                for detection_id in requested:
                    row = by_id.get(detection_id)
                    if row is None:
                        raise SlipApplyError(
                            f"Detection {detection_id} not found for profile"
                        )
                    selected.append(row)

            applied: list[SlipDetection] = []
            for row in selected:
                applied.append(_detection_from_row(row))
                row.status = DocumentStatus.APPLIED.value

            return applied

    async def clear(self, profile: str, year: int) -> None:
        safe_profile = slugify(profile) or "default"
        async with session_scope(self._factory) as session:
            stmt = (
                select(DocumentRow)
                .where(DocumentRow.profile_slug == safe_profile)
                .where(DocumentRow.tax_year == int(year))
                .where(DocumentRow.status == DocumentStatus.COMPLETE.value)
            )
            result = await session.execute(stmt)
            for row in result.scalars().all():
                await session.delete(row)


_DEFAULT_STORE: SlipStagingStore | None = None
_DEFAULT_STORE_LOCK = asyncio.Lock()


async def _get_default_store() -> SlipStagingStore:
    """Lazily build an in-memory SlipStagingStore for callers that don't
    supply a FastAPI app (e.g. the ``ingest_slip_uploads`` helper invoked
    outside the lifespan). Uses a StaticPool single-connection sqlite so
    the schema and rows stay visible across sessions in one process.
    """
    global _DEFAULT_STORE
    async with _DEFAULT_STORE_LOCK:
        if _DEFAULT_STORE is None:
            engine = create_async_engine(
                "sqlite+aiosqlite:///:memory:",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = create_session_factory(engine)
            _DEFAULT_STORE = SlipStagingStore(factory)
        return _DEFAULT_STORE


async def resolve_store(app: Any | None = None) -> SlipStagingStore:
    """Return the SlipStagingStore bound to the given FastAPI app, or the
    lazy module-level default if ``app`` is None. When ``app.state`` has a
    pre-wired ``slip_staging_store`` we honor it (used by tests); otherwise
    we build one from ``app.state.db_session_factory`` and cache it.
    """
    if app is None:
        return await _get_default_store()
    existing = getattr(app.state, "slip_staging_store", None)
    if isinstance(existing, SlipStagingStore):
        return existing
    factory = getattr(app.state, "db_session_factory", None)
    if factory is None:
        raise RuntimeError(
            "db_session_factory not wired on app.state; "
            "ensure app.lifespan is running or set app.state.slip_staging_store manually."
        )
    store = SlipStagingStore(factory)
    app.state.slip_staging_store = store
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
    loop = asyncio.get_running_loop()
    text = await loop.run_in_executor(None, _extract_text, extension, data)
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
        warnings=[],
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
        return _clean_extracted_text(_extract_text_from_image(data))
    if extension == ".txt":
        return _clean_extracted_text(data.decode("utf-8", errors="ignore"))
    raise SlipUploadError("Unsupported file type for text extraction")


def _extract_text_from_pdf(data: bytes) -> str:
    tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_path = Path(tmp_file.name)
    try:
        with tmp_file:
            tmp_file.write(data)
        reader = PdfReader(tmp_path)
        pages: list[str] = []
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                raise SlipUploadError("Unable to extract text from PDF page") from exc
            pages.append(text)
        extracted = _clean_extracted_text("\n".join(pages))
        if extracted:
            return extracted
        images = _rasterize_pdf(data)
        ocr_text = _perform_pdf_ocr(images)
        return _clean_extracted_text("\n".join(ocr_text))
    except SlipUploadError:
        raise
    except Exception as exc:
        raise SlipUploadError("Unable to read PDF upload") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


def _extract_text_from_image(data: bytes) -> str:
    try:
        from PIL import Image
    except Exception as exc:
        raise SlipUploadError("Image OCR requires Pillow to be installed") from exc
    try:
        import pytesseract  # type: ignore
    except Exception as exc:
        raise SlipUploadError("Image OCR requires the pytesseract package to be installed") from exc
    with Image.open(io.BytesIO(data)) as image:
        try:
            return pytesseract.image_to_string(image)
        except Exception as exc:
            raise SlipUploadError("Unable to extract text from image upload") from exc


def _clean_extracted_text(text: str) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", text)
    return cleaned.strip()


def _rasterize_pdf(data: bytes) -> list[Any]:
    try:
        from pdf2image import convert_from_bytes
    except Exception as exc:
        raise SlipUploadError("PDF OCR requires the pdf2image package to be installed") from exc
    try:
        return convert_from_bytes(
            data,
            dpi=200,
            size=(2048, None),
            fmt="png",
            thread_count=1,
            use_cropbox=True,
        )
    except Exception as exc:
        raise SlipUploadError("Unable to rasterize PDF for OCR") from exc


def _perform_pdf_ocr(images: Iterable[Any]) -> list[str]:
    try:
        import pytesseract  # type: ignore
    except Exception as exc:
        raise SlipUploadError("PDF OCR requires the pytesseract package to be installed") from exc

    texts: list[str] = []
    for index, image in enumerate(images, start=1):
        try:
            texts.append(pytesseract.image_to_string(image))
        except Exception as exc:
            raise SlipUploadError(
                f"Unable to OCR rasterized PDF page {index}"
            ) from exc
        finally:
            closer = getattr(image, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass
    return texts


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
    uploads: Iterable[UploadFile],
    profile: str = "default",
    year: int | None = None,
    *,
    settings: Settings | None = None,
    app: Any | None = None,
) -> tuple[list[SlipDetection], list[str]]:
    year_val = year if year is not None else datetime.now(timezone.utc).year
    cfg = settings or Settings()
    store = await resolve_store(app)
    detections: list[SlipDetection] = []
    errors: list[str] = []
    for upload in uploads:
        filename = upload.filename or ""
        ext = Path(filename).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            slip_guess = "t4a" if "t4a" in filename.lower() else ("t5" if "t5" in filename.lower() else "t4")
            det = SlipDetection(
                id=secrets.token_hex(8),
                slip_type=slip_guess,
                original_filename=filename,
                stored_filename="",
                stored_path="",
                size=0,
                preview="",
                fields={},
                warnings=["Unsupported image format for text extraction; OCR skipped"],
                created_at=datetime.now(timezone.utc),
            )
            detections.append(det)
            try:
                await upload.close()
            except Exception:
                pass
            continue
        try:
            status = await store.process_upload(profile, int(year_val), upload, settings=cfg)
            if status.status == "complete" and status.detection is not None:
                detections.append(status.detection)
        except Exception:
            pass
    return detections, errors


async def slip_job_status(
    profile: str,
    year: int,
    job_id: str,
    *,
    app: Any | None = None,
) -> SlipJobStatus:
    store = await resolve_store(app)
    return await store.job_status(profile, year, job_id)


async def apply_staged_detections(
    profile: str,
    year: int,
    detection_ids: Iterable[str] | None = None,
    *,
    app: Any | None = None,
) -> list[SlipDetection]:
    store = await resolve_store(app)
    return await store.apply(profile, year, detection_ids)
