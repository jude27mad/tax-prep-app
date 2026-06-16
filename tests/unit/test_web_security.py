"""Tests for CSRF protection and security-header middleware (web hardening).

Mirrors the repo's router-test style: each test builds a small FastAPI app
wiring only the middleware under test, plus one end-to-end pass through the
real ``/auth`` router with the full Session + CSRF + headers stack to prove the
synchronizer token round-trips through a rendered Jinja form while the
programmatic ``204`` contract stays intact.
"""

from __future__ import annotations

import asyncio
import re

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.auth.email import RecordingEmailBackend
from app.db import Base, create_session_factory
from app.i18n import LocaleMiddleware
from app.web_security import (
    CSRFMiddleware,
    SecurityHeadersMiddleware,
    get_csrf_token,
)

_CSRF_INPUT_RE = re.compile(r'name="csrf_token"\s+value="([^"]*)"')


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


def _headers_app(*, enable_hsts: bool) -> TestClient:
    app = FastAPI()

    @app.get("/probe")
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=enable_hsts)
    return TestClient(app)


def test_security_headers_present_on_response() -> None:
    client = _headers_app(enable_hsts=False)
    resp = client.get("/probe")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    csp = resp.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp


def test_hsts_emitted_only_when_enabled() -> None:
    off = _headers_app(enable_hsts=False).get("/probe")
    assert "strict-transport-security" not in off.headers

    on = _headers_app(enable_hsts=True).get("/probe")
    assert on.headers["strict-transport-security"].startswith("max-age=")
    assert "includeSubDomains" in on.headers["strict-transport-security"]


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------


def _csrf_client() -> TestClient:
    app = FastAPI()

    @app.get("/token")
    async def token(request: Request) -> dict[str, str]:
        return {"csrf": get_csrf_token(request)}

    @app.post("/submit")
    async def submit(request: Request) -> dict[str, object]:
        # Touch the body so a swallowed/unreplayed body would surface here.
        form = await request.form()
        return {"ok": True, "value": form.get("value", "")}

    # Mirror production's stack order so the body-replay path is exercised
    # through LocaleMiddleware (a BaseHTTPMiddleware) too: run order ends up
    # Session -> CSRF -> Locale -> route.
    app.add_middleware(LocaleMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key-not-for-prod",
        session_cookie="taxapp_session",
        same_site="lax",
    )
    return TestClient(app)


def _mint_token(client: TestClient) -> str:
    token = client.get("/token").json()["csrf"]
    assert token  # middleware mints one on the safe GET
    return token


def test_csrf_allows_safe_get() -> None:
    client = _csrf_client()
    assert client.get("/token").status_code == 200


def test_csrf_rejects_forged_post() -> None:
    client = _csrf_client()
    _mint_token(client)  # establish session cookie + token

    missing = client.post(
        "/submit",
        data={"value": "hello"},
        headers={"accept": "text/html"},
    )
    assert missing.status_code == 403

    forged = client.post(
        "/submit",
        data={"value": "hello", "csrf_token": "not-the-real-token"},
        headers={"accept": "text/html"},
    )
    assert forged.status_code == 403


def test_csrf_accepts_valid_token_in_form_field() -> None:
    client = _csrf_client()
    token = _mint_token(client)

    resp = client.post(
        "/submit",
        data={"value": "hello", "csrf_token": token},
        headers={"accept": "text/html"},
    )
    assert resp.status_code == 200
    # Proves the buffered body was replayed to the handler intact.
    assert resp.json() == {"ok": True, "value": "hello"}


def test_csrf_accepts_valid_token_in_header() -> None:
    client = _csrf_client()
    token = _mint_token(client)

    resp = client.post(
        "/submit",
        data={"value": "hi"},
        headers={"accept": "text/html", "x-csrf-token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == "hi"


def test_csrf_exempts_json_api_caller() -> None:
    """Non-HTML (API) callers bypass CSRF so the ``204`` contract is intact."""
    client = _csrf_client()
    # No prior GET, no token, JSON Accept -> must reach the handler, not 403.
    resp = client.post(
        "/submit",
        data={"value": "api"},
        headers={"accept": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == "api"


# ---------------------------------------------------------------------------
# End-to-end: real /auth router behind the full stack
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_client() -> tuple[TestClient, RecordingEmailBackend]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _init_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init_db())

    factory = create_session_factory(engine)
    backend = RecordingEmailBackend()

    app = FastAPI()
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key-not-for-prod",
        session_cookie="taxapp_session",
        same_site="lax",
    )
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True)
    app.include_router(auth_router)
    app.state.db_session_factory = factory
    app.state.email_backend = backend
    app.state.auth_token_ttl_minutes = 15

    with TestClient(app) as c:
        yield c, backend

    asyncio.run(engine.dispose())


def test_login_form_carries_csrf_token_and_headers(
    auth_client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, _ = auth_client
    resp = c.get("/auth/login")
    assert resp.status_code == 200
    assert resp.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in resp.headers
    match = _CSRF_INPUT_RE.search(resp.text)
    assert match and match.group(1), "login form must embed a CSRF token"


def test_auth_request_requires_csrf_for_browser(
    auth_client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, backend = auth_client
    token = _CSRF_INPUT_RE.search(c.get("/auth/login").text).group(1)  # type: ignore[union-attr]

    # Forged browser POST (no token) is rejected before any mail is sent.
    forged = c.post(
        "/auth/request",
        data={"email": "mallory@example.com"},
        headers={"accept": "text/html"},
        follow_redirects=False,
    )
    assert forged.status_code == 403
    assert backend.sent == []

    # Valid token -> normal 303 redirect to /auth/sent.
    ok = c.post(
        "/auth/request",
        data={"email": "alice@example.com", "csrf_token": token},
        headers={"accept": "text/html"},
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert ok.headers["location"] == "/auth/sent"
    assert len(backend.sent) == 1


def test_auth_request_json_caller_still_204(
    auth_client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    """Programmatic form-encoded callers (default Accept) keep their 204."""
    c, backend = auth_client
    resp = c.post("/auth/request", data={"email": "bob@example.com"})
    assert resp.status_code == 204
    assert len(backend.sent) == 1
