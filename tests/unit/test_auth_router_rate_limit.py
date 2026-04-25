"""D1.7 — /auth/request rate-limit integration tests.

Mirrors the harness in :mod:`tests.unit.test_auth_router` but configures
a tight rate limit so we can observe the 429 path without sending
hundreds of requests.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.auth.email import RecordingEmailBackend
from app.auth.rate_limit import AuthRequestRateLimiter, RateLimiter
from app.db import Base, create_session_factory


@pytest.fixture
def client_factory():
    """Build a TestClient with configurable rate-limit ceilings."""

    def _factory(*, per_email: int, per_ip: int, window: int = 60):
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
        limiter = AuthRequestRateLimiter(
            per_email=RateLimiter(limit=per_email, window_seconds=window),
            per_ip=RateLimiter(limit=per_ip, window_seconds=window),
        )

        app = FastAPI()
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-secret-key-not-for-prod",
            session_cookie="taxapp_session",
        )
        app.include_router(auth_router)
        app.state.db_session_factory = factory
        app.state.email_backend = backend
        app.state.auth_token_ttl_minutes = 15
        app.state.auth_request_rate_limiter = limiter

        return TestClient(app), backend, engine

    yield _factory


def test_per_email_cap_returns_429_with_retry_after(client_factory):
    c, backend, engine = client_factory(per_email=2, per_ip=10)
    try:
        for _ in range(2):
            assert c.post("/auth/request", data={"email": "alice@example.com"}).status_code == 204
        blocked = c.post("/auth/request", data={"email": "alice@example.com"})
        assert blocked.status_code == 429
        retry = blocked.headers.get("retry-after")
        assert retry is not None and int(retry) > 0
        # The blocked request must NOT have generated a new email.
        assert len(backend.sent) == 2
    finally:
        asyncio.run(engine.dispose())


def test_per_ip_cap_blocks_email_rotation(client_factory):
    """A single IP cycling through unique emails must still be capped."""
    c, backend, engine = client_factory(per_email=10, per_ip=2)
    try:
        assert c.post("/auth/request", data={"email": "a@example.com"}).status_code == 204
        assert c.post("/auth/request", data={"email": "b@example.com"}).status_code == 204
        blocked = c.post("/auth/request", data={"email": "c@example.com"})
        assert blocked.status_code == 429
        assert len(backend.sent) == 2
    finally:
        asyncio.run(engine.dispose())


def test_rate_limited_html_caller_gets_login_page_with_error(client_factory):
    """Browser callers see the form re-rendered with an inline error, not raw 429 JSON."""
    c, _, engine = client_factory(per_email=1, per_ip=10)
    try:
        c.post(
            "/auth/request",
            data={"email": "alice@example.com"},
            headers={"accept": "text/html"},
        )
        blocked = c.post(
            "/auth/request",
            data={"email": "alice@example.com"},
            headers={"accept": "text/html"},
        )
        assert blocked.status_code == 429
        assert "text/html" in blocked.headers.get("content-type", "")
        assert "Too many sign-in attempts" in blocked.text
        # Hidden form value preserved so the user can resubmit.
        assert "alice@example.com" in blocked.text
        assert blocked.headers.get("retry-after") is not None
    finally:
        asyncio.run(engine.dispose())


def test_rate_limit_honors_x_forwarded_for(client_factory):
    """When X-Forwarded-For is present, per-IP buckets follow the spoofable header.

    This documents the intended behavior — operators must put a trusted
    proxy in front of the app for the per-IP cap to be meaningful. The
    test asserts the bucketing logic, not the trust boundary.
    """
    c, _, engine = client_factory(per_email=10, per_ip=2)
    try:
        # Two requests from "client A" via proxy.
        c.post(
            "/auth/request",
            data={"email": "a@example.com"},
            headers={"x-forwarded-for": "203.0.113.1"},
        )
        c.post(
            "/auth/request",
            data={"email": "b@example.com"},
            headers={"x-forwarded-for": "203.0.113.1"},
        )
        # Third request from "client A" should be blocked.
        blocked = c.post(
            "/auth/request",
            data={"email": "c@example.com"},
            headers={"x-forwarded-for": "203.0.113.1"},
        )
        assert blocked.status_code == 429
        # But "client B" via same proxy still gets through.
        ok = c.post(
            "/auth/request",
            data={"email": "d@example.com"},
            headers={"x-forwarded-for": "198.51.100.7"},
        )
        assert ok.status_code == 204
    finally:
        asyncio.run(engine.dispose())
