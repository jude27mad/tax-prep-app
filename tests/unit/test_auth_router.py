"""D1.4 — /auth router smoke tests.

Wires the router against a FastAPI TestClient with:
  * In-memory SQLite (StaticPool so schema is visible across sessions).
  * :class:`RecordingEmailBackend` so we can pull the issued link out.
  * ``SessionMiddleware`` so the session cookie round-trips.

The TestClient is sync; inside FastAPI the async endpoints still run on
its internal event loop.
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
from app.db import Base, create_session_factory


@pytest.fixture
def client() -> tuple[TestClient, RecordingEmailBackend]:
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
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key-not-for-prod",
        session_cookie="taxapp_session",
    )
    app.include_router(auth_router)
    app.state.db_session_factory = factory
    app.state.email_backend = backend
    app.state.auth_token_ttl_minutes = 15

    with TestClient(app) as c:
        yield c, backend

    asyncio.run(engine.dispose())


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_request_returns_204_and_issues_link(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, backend = client
    resp = c.post("/auth/request", data={"email": "alice@example.com"})
    assert resp.status_code == 204
    assert len(backend.sent) == 1
    assert backend.sent[0].to == "alice@example.com"


def test_verify_sets_session_cookie_and_redirects(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, backend = client
    c.post("/auth/request", data={"email": "bob@example.com"})
    link = backend.sent[0].link
    token = link.split("token=", 1)[1]

    resp = c.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    # Cookie is set on the TestClient's cookie jar.
    assert c.cookies.get("taxapp_session")

    me = c.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "bob@example.com"


def test_logout_clears_session(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, backend = client
    c.post("/auth/request", data={"email": "claire@example.com"})
    token = backend.sent[0].link.split("token=", 1)[1]
    c.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert c.get("/auth/me").status_code == 200

    out = c.post("/auth/logout")
    assert out.status_code == 204

    me = c.get("/auth/me")
    assert me.status_code == 401


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_request_still_204_for_bad_email(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    """Malformed email must not leak via status code (oracle-prevention)."""
    c, backend = client
    resp = c.post("/auth/request", data={"email": "not-an-email"})
    assert resp.status_code == 204
    assert backend.sent == []


def test_verify_with_unknown_token_rejected(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, _ = client
    resp = c.get("/auth/verify?token=bogus", follow_redirects=False)
    assert resp.status_code == 400
    assert "Invalid" in resp.json()["detail"]


def test_verify_with_reused_token_rejected(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, backend = client
    c.post("/auth/request", data={"email": "dave@example.com"})
    token = backend.sent[0].link.split("token=", 1)[1]
    # First verify succeeds and sets a session on this TestClient.
    c.get(f"/auth/verify?token={token}", follow_redirects=False)
    # Drop the session so we can observe the raw 400 on reuse.
    c.cookies.clear()
    resp = c.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert resp.status_code == 400
    assert "already been used" in resp.json()["detail"]


def test_me_returns_401_without_session(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, _ = client
    resp = c.get("/auth/me")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# D1.6 — HTML login flow
# ---------------------------------------------------------------------------


def test_login_page_renders_form(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, _ = client
    resp = c.get("/auth/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    body = resp.text
    assert 'name="email"' in body
    assert 'action="/auth/request"' in body


def test_login_page_preserves_next_param(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    """The hidden ``next`` input must round-trip through the form."""
    c, _ = client
    resp = c.get("/auth/login?next=/ui/profiles")
    assert resp.status_code == 200
    # Rendered form must carry the next path as a hidden field.
    assert 'name="next"' in resp.text
    assert "/ui/profiles" in resp.text


def test_login_page_rejects_unsafe_next(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    """Absolute URLs and protocol-relative paths must be neutralized."""
    c, _ = client
    # Open-redirect attempt should collapse to "/" — we never echo the bad value.
    resp = c.get("/auth/login?next=//evil.example/hax")
    assert resp.status_code == 200
    assert "evil.example" not in resp.text


def test_form_post_request_redirects_to_sent(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    """Browser form POSTs get a 303 to /auth/sent; API callers still get 204."""
    c, backend = client
    resp = c.post(
        "/auth/request",
        data={"email": "eve@example.com", "next": "/ui/profiles"},
        headers={"accept": "text/html"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/sent"
    assert len(backend.sent) == 1
    # Next path must be baked into the magic link so verify can redirect back.
    assert "next=%2Fui%2Fprofiles" in backend.sent[0].link or "next=/ui/profiles" in backend.sent[0].link


def test_form_post_request_renders_error_on_bad_email(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, _ = client
    resp = c.post(
        "/auth/request",
        data={"email": "not-an-email"},
        headers={"accept": "text/html"},
    )
    assert resp.status_code == 400
    assert 'name="email"' in resp.text  # form is re-rendered
    assert "not-an-email" in resp.text  # value is preserved


def test_sent_page_renders(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, _ = client
    resp = c.get("/auth/sent")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_verify_redirects_to_next_when_provided(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, backend = client
    c.post(
        "/auth/request",
        data={"email": "frank@example.com", "next": "/ui/profiles"},
        headers={"accept": "text/html"},
        follow_redirects=False,
    )
    # The emailed link now carries ?next=/ui/profiles
    link = backend.sent[0].link
    assert "next=" in link
    # Follow the verify step manually so we can inspect the Location header.
    resp = c.get(link.replace("http://testserver", ""), follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/ui/profiles"


def test_verify_drops_unsafe_next(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    """Even if an attacker crafts a verify URL with an open-redirect next,
    the server must collapse it to ``/`` before redirecting."""
    c, backend = client
    c.post("/auth/request", data={"email": "grace@example.com"})
    token = backend.sent[0].link.split("token=", 1)[1]
    resp = c.get(
        f"/auth/verify?token={token}&next=https://evil.example/",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_form_post_logout_redirects_to_login(
    client: tuple[TestClient, RecordingEmailBackend],
) -> None:
    c, backend = client
    c.post("/auth/request", data={"email": "henri@example.com"})
    token = backend.sent[0].link.split("token=", 1)[1]
    c.get(f"/auth/verify?token={token}", follow_redirects=False)

    resp = c.post("/auth/logout", headers={"accept": "text/html"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"
    assert c.get("/auth/me").status_code == 401
