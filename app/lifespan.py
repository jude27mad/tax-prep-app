from __future__ import annotations

import hashlib
import importlib
import inspect
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncContextManager
import httpx
from fastapi import FastAPI

from app.auth.email import SmtpConfig, make_email_backend
from app.auth.rate_limit import AuthRequestRateLimiter, RateLimiter
from app.config import Settings, get_settings
from app.db import (
    build_database_url,
    create_engine as create_db_engine,
    create_session_factory,
    dispose_engine,
)

_SCHEMA_CACHE: dict[str, str] | None = None
_REGISTERED_FONTS: set[str] = set()

Hook = Callable[[FastAPI], Awaitable[None] | None]


def _load_cra_schema_cache(logger: logging.Logger) -> dict[str, str]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        cache: dict[str, str] = {}
        schema_root = Path(__file__).resolve().parent / "schemas"
        if schema_root.is_dir():
            for path in schema_root.rglob("*.xsd"):
                try:
                    cache[path.name] = path.read_text(encoding="utf-8")
                except OSError as exc:
                    logger.warning("Failed to load CRA schema %s: %s", path, exc)
            logger.info("CRA XSD cache initialized from %s", schema_root)
        else:
            logger.debug("CRA schema directory %s not found; continuing without cache", schema_root)
        _SCHEMA_CACHE = cache
    return dict(_SCHEMA_CACHE)


def _register_reportlab_fonts(logger: logging.Logger) -> list[str]:
    registered_now: list[str] = []
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception as exc:  # pragma: no cover
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
        except Exception as exc:  # pragma: no cover
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


def _build_smtp_config(settings: Settings) -> SmtpConfig | None:
    """Materialize an SMTP config when the SMTP backend is selected.

    Returns ``None`` for the console backend so :func:`make_email_backend`
    follows its zero-config path. Settings validation already enforces
    that host + from are present when ``auth_email_backend == "smtp"``,
    so we can rely on that here.
    """
    if settings.auth_email_backend != "smtp":
        return None
    assert settings.auth_smtp_host is not None  # validated by Settings
    assert settings.auth_smtp_from is not None
    return SmtpConfig(
        host=settings.auth_smtp_host,
        port=settings.auth_smtp_port,
        username=settings.auth_smtp_username,
        password=settings.auth_smtp_password,
        use_tls=settings.auth_smtp_use_tls,
        use_ssl=settings.auth_smtp_use_ssl,
        timeout=settings.auth_smtp_timeout,
        from_address=settings.auth_smtp_from,
        subject=settings.auth_smtp_subject,
    )


async def _invoke_hook(hook: Hook | None, app: FastAPI) -> None:
    if hook is None:
        return
    try:
        result = hook(app)
        if inspect.isawaitable(result):
            await result  # type: ignore[func-returns-value]
    except Exception:  # pragma: no cover
        logging.getLogger("tax_app").exception("Application lifecycle hook failed")


def build_application_lifespan(
    app_label: str,
    *,
    startup_hook: Hook | None = None,
    shutdown_hook: Hook | None = None,
    http_timeout: float = 15.0,
) -> Callable[[FastAPI], AsyncContextManager[None]]:
    base_logger = logging.getLogger("tax_app")

    # Hard-require python-multipart for form parsing (unit test asserts RuntimeError)
    try:
        importlib.import_module("python_multipart")
    except ImportError as exc:  # pragma: no cover - covered by dedicated unit test
        raise RuntimeError(
            "python-multipart is required for form submissions. Install it with 'pip install python-multipart'."
        ) from exc

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        logger = base_logger.getChild(app_label)
        http_client = httpx.AsyncClient(timeout=http_timeout)
        schema_cache = _load_cra_schema_cache(logger)
        schema_versions = {name: hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12] for name, payload in schema_cache.items()}
        registered_fonts = _register_reportlab_fonts(logger)
        telemetry_handler = _open_telemetry_sink(logger, app_label)

        database_url = build_database_url(settings)
        db_engine = create_db_engine(database_url)
        db_session_factory = create_session_factory(db_engine)
        email_backend = make_email_backend(
            settings.auth_email_backend,
            smtp_config=_build_smtp_config(settings),
        )
        request_rate_limiter = AuthRequestRateLimiter(
            per_email=RateLimiter(
                limit=settings.auth_request_rate_per_email,
                window_seconds=settings.auth_request_rate_window_seconds,
            ),
            per_ip=RateLimiter(
                limit=settings.auth_request_rate_per_ip,
                window_seconds=settings.auth_request_rate_window_seconds,
            ),
        )

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
        app.state.db_engine = db_engine
        app.state.db_session_factory = db_session_factory
        app.state.database_url = database_url
        app.state.email_backend = email_backend
        app.state.auth_token_ttl_minutes = settings.auth_token_ttl_minutes
        app.state.auth_request_rate_limiter = request_rate_limiter

        logger.info(
            "Startup complete: schemas=%s fonts_registered=%s feature_efile_xml=%s "
            "feature_legacy_efile=%s database_url=%s",
            len(schema_cache),
            len(registered_fonts),
            settings.feature_efile_xml,
            settings.feature_legacy_efile,
            database_url,
        )

        try:
            await _invoke_hook(startup_hook, app)
            yield
        finally:
            await _invoke_hook(shutdown_hook, app)
            try:
                await http_client.aclose()
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to close shared httpx client: %s", exc)
            try:
                await dispose_engine(db_engine)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to dispose DB engine: %s", exc)
            if telemetry_handler is not None:
                logger.removeHandler(telemetry_handler)
                telemetry_handler.close()
            for attr in (
                "settings",
                "http_client",
                "cra_schema_cache",
                "schema_versions",
                "reportlab_fonts",
                "telemetry_handler",
                "artifact_root",
                "daily_summary_root",
                "submission_digests",
                "summary_index",
                "last_sbmt_ref_id",
                "app_label",
                "db_engine",
                "db_session_factory",
                "database_url",
                "email_backend",
                "auth_token_ttl_minutes",
                "auth_request_rate_limiter",
            ):
                if hasattr(app.state, attr):
                    delattr(app.state, attr)
            logger.info("Shutdown complete")

    return _lifespan
