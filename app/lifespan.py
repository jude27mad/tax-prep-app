from __future__ import annotations

import hashlib
import inspect
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncContextManager

import httpx
from fastapi import FastAPI

from app.config import get_settings

_SCHEMA_CACHE: dict[str, str] | None = None
_REGISTERED_FONTS: set[str] = set()

Hook = Callable[[FastAPI], Awaitable[None] | None]


def _load_cra_schema_cache(logger: logging.Logger) -> dict[str, str]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        cache: dict[str, str] = {}
        schema_root = Path(__file__).resolve().parent / "schemas"
        if schema_root.exists():
            for path in schema_root.rglob("*.xsd"):
                try:
                    cache[path.name] = path.read_text(encoding="utf-8")
                except OSError as exc:
                    logger.warning("Failed to load CRA schema %s: %s", path, exc)
        else:
            logger.debug("CRA schema directory %s not found; continuing without cache", schema_root)
        _SCHEMA_CACHE = cache
    return dict(_SCHEMA_CACHE)


def _register_reportlab_fonts(logger: logging.Logger) -> list[str]:
    registered_now: list[str] = []
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception as exc:  # pragma: no cover - reportlab should be present but guard regardless
        logger.warning("ReportLab unavailable, cannot register fonts: %s", exc)
        return registered_now

    fonts_dir = Path(__file__).resolve().parent / "printout" / "fonts"
    if not fonts_dir.exists():
        logger.debug("No ReportLab font directory found at %s", fonts_dir)
        return registered_now

    for font_path in fonts_dir.glob("*.ttf"):
        font_name = font_path.stem
        if font_name in _REGISTERED_FONTS:
            continue
        try:
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
            _REGISTERED_FONTS.add(font_name)
            registered_now.append(font_name)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to register ReportLab font %s: %s", font_path, exc)
    return registered_now


def _open_telemetry_sink(logger: logging.Logger, app_label: str) -> logging.Handler | None:
    logs_dir = Path("logs")
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Unable to create logs directory %s: %s", logs_dir, exc)
        return None
    handler = logging.FileHandler(logs_dir / f"{app_label}.log", encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    logger.addHandler(handler)
    return handler


async def _invoke_hook(hook: Hook | None, app: FastAPI) -> None:
    if hook is None:
        return
    try:
        result = hook(app)
        if inspect.isawaitable(result):
            await result  # type: ignore[func-returns-value]
    except Exception:  # pragma: no cover - hooks are user provided
        logging.getLogger("tax_app").exception("Application lifecycle hook failed")


def build_application_lifespan(
    app_label: str,
    *,
    startup_hook: Hook | None = None,
    shutdown_hook: Hook | None = None,
    http_timeout: float = 15.0,
) -> Callable[[FastAPI], AsyncContextManager[None]]:
    base_logger = logging.getLogger("tax_app")

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        logger = base_logger.getChild(app_label)
        http_client = httpx.AsyncClient(timeout=http_timeout)
        schema_cache = _load_cra_schema_cache(logger)
        schema_versions = {name: hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12] for name, payload in schema_cache.items()}
        registered_fonts = _register_reportlab_fonts(logger)
        telemetry_handler = _open_telemetry_sink(logger, app_label)

        app.state.settings = settings
        app.state.http_client = http_client
        app.state.cra_schema_cache = schema_cache
        app.state.schema_versions = schema_versions
        app.state.reportlab_fonts = registered_fonts
        app.state.artifact_root = settings.artifact_root
        app.state.daily_summary_root = settings.daily_summary_root
        app.state.submission_digests = set()
        app.state.summary_index = {}
        app.state.telemetry_handler = telemetry_handler
        app.state.app_label = app_label

        logger.info(
            "Startup complete: schemas=%s fonts_registered=%s", len(schema_cache), len(registered_fonts)
        )

        try:
            await _invoke_hook(startup_hook, app)
            yield
        finally:
            await _invoke_hook(shutdown_hook, app)
            try:
                await http_client.aclose()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to close shared httpx client: %s", exc)
            if telemetry_handler is not None:
                logger.removeHandler(telemetry_handler)
                telemetry_handler.close()
            for attr in ("settings", "http_client", "cra_schema_cache", "schema_versions", "reportlab_fonts", "telemetry_handler", "artifact_root", "daily_summary_root", "submission_digests", "summary_index", "last_sbmt_ref_id", "app_label"):
                if hasattr(app.state, attr):
                    delattr(app.state, attr)
            logger.info("Shutdown complete")

    return _lifespan
