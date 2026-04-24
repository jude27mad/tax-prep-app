"""D1.4 — AuthService unit tests.

Covers the service layer directly (no FastAPI) against an in-memory SQLite
built with StaticPool so the schema created via ``Base.metadata.create_all``
stays visible to subsequent sessions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import select

from app.auth.email import RecordingEmailBackend
from app.auth.service import (
    AuthService,
    TokenExpiredError,
    TokenInvalidError,
    TokenReusedError,
)
from app.db import (
    Base,
    LoginTokenRow,
    UserRow,
    create_session_factory,
    session_scope,
)


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def service(engine: AsyncEngine) -> tuple[AuthService, RecordingEmailBackend]:
    backend = RecordingEmailBackend()
    svc = AuthService(
        session_factory=create_session_factory(engine),
        email_backend=backend,
        verify_base_url="http://testserver",
        token_ttl=timedelta(minutes=15),
    )
    return svc, backend


# ---------------------------------------------------------------------------
# request_magic_link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_creates_user_and_emails_link(
    service: tuple[AuthService, RecordingEmailBackend], engine: AsyncEngine
) -> None:
    svc, backend = service
    magic = await svc.request_magic_link("  Alice@Example.COM ")

    assert magic.email == "alice@example.com"
    assert len(backend.sent) == 1
    msg = backend.sent[0]
    assert msg.to == "alice@example.com"
    assert msg.link.startswith("http://testserver/auth/verify?token=")
    assert magic.raw_token in msg.link

    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        users = (await session.execute(select(UserRow))).scalars().all()
        tokens = (await session.execute(select(LoginTokenRow))).scalars().all()
    assert len(users) == 1
    assert users[0].email == "alice@example.com"
    assert len(tokens) == 1
    assert tokens[0].user_id == users[0].id
    # Raw token is NOT what's in the DB — only the hash.
    assert tokens[0].token_hash != magic.raw_token


@pytest.mark.asyncio
async def test_request_reuses_existing_user(
    service: tuple[AuthService, RecordingEmailBackend], engine: AsyncEngine
) -> None:
    svc, _ = service
    first = await svc.request_magic_link("bob@example.com")
    second = await svc.request_magic_link("BOB@example.com")

    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        users = (await session.execute(select(UserRow))).scalars().all()
        tokens = (await session.execute(select(LoginTokenRow))).scalars().all()

    assert len(users) == 1
    assert len(tokens) == 2
    # Each request mints a distinct token.
    assert first.raw_token != second.raw_token


@pytest.mark.asyncio
async def test_request_rejects_malformed_email(
    service: tuple[AuthService, RecordingEmailBackend],
) -> None:
    svc, backend = service
    with pytest.raises(ValueError):
        await svc.request_magic_link("not-an-email")
    assert backend.sent == []


# ---------------------------------------------------------------------------
# verify_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_valid_token_marks_consumed_and_sets_last_login(
    service: tuple[AuthService, RecordingEmailBackend], engine: AsyncEngine
) -> None:
    svc, _ = service
    magic = await svc.request_magic_link("claire@example.com")

    before = datetime.now(timezone.utc)
    user = await svc.verify_token(magic.raw_token)
    after = datetime.now(timezone.utc)

    assert user.email == "claire@example.com"
    assert user.last_login_at is not None
    # Normalize for sqlite tz round-trip.
    last_login = user.last_login_at
    if last_login.tzinfo is None:
        last_login = last_login.replace(tzinfo=timezone.utc)
    assert before - timedelta(seconds=5) <= last_login <= after + timedelta(seconds=5)

    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        tokens = (await session.execute(select(LoginTokenRow))).scalars().all()
    assert len(tokens) == 1
    assert tokens[0].consumed_at is not None


@pytest.mark.asyncio
async def test_verify_expired_token_raises(engine: AsyncEngine) -> None:
    backend = RecordingEmailBackend()
    svc = AuthService(
        session_factory=create_session_factory(engine),
        email_backend=backend,
        verify_base_url="http://testserver",
        token_ttl=timedelta(seconds=-1),  # already expired at birth
    )
    magic = await svc.request_magic_link("dave@example.com")

    with pytest.raises(TokenExpiredError):
        await svc.verify_token(magic.raw_token)


@pytest.mark.asyncio
async def test_verify_reused_token_raises(
    service: tuple[AuthService, RecordingEmailBackend],
) -> None:
    svc, _ = service
    magic = await svc.request_magic_link("erin@example.com")

    user = await svc.verify_token(magic.raw_token)
    assert user.email == "erin@example.com"

    with pytest.raises(TokenReusedError):
        await svc.verify_token(magic.raw_token)


@pytest.mark.asyncio
async def test_verify_unknown_token_raises(
    service: tuple[AuthService, RecordingEmailBackend],
) -> None:
    svc, _ = service
    with pytest.raises(TokenInvalidError):
        await svc.verify_token("definitely-not-a-real-token")


@pytest.mark.asyncio
async def test_verify_empty_token_raises(
    service: tuple[AuthService, RecordingEmailBackend],
) -> None:
    svc, _ = service
    with pytest.raises(TokenInvalidError):
        await svc.verify_token("")
