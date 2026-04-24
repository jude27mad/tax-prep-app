"""Magic-link auth service.

Contract:

* :meth:`AuthService.request_magic_link(email)` — find-or-create a user,
  mint a random token, persist its sha-256 hash with a TTL, and hand the
  raw token to the configured email backend. Returns :class:`MagicLink`
  so callers in tests or scripts can inspect what was sent; the HTTP
  layer ignores it.
* :meth:`AuthService.verify_token(raw_token)` — resolve the token hash,
  reject expired or previously-consumed tokens, stamp ``consumed_at`` and
  refresh ``last_login_at``. Returns the :class:`UserRow` on success.

Design notes:

* We always generate a user if the email is new. This leaks nothing
  (attacker can already verify existence by requesting a link) and keeps
  the flow simple. If we ever need "account-required" semantics we can
  add a flag on UserRow.
* Tokens are 256-bit URL-safe strings from :func:`secrets.token_urlsafe`.
  We never log or return the raw value from verify — it's been consumed.
* Hashing is plain sha-256; brute-forcing 256 bits of entropy in 15
  minutes is not meaningfully easier with a stronger KDF, and the DB row
  only exists for the TTL window.
* Email is always lowercased before write/lookup. The unique index on
  ``users.email`` assumes this normalization happens at the app layer.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.auth.email import EmailBackend
from app.db import LoginTokenRow, UserRow, session_scope


class AuthError(Exception):
    """Base class for auth service errors surfaced over HTTP."""


class TokenInvalidError(AuthError):
    """Token does not match any row (unknown / tampered)."""


class TokenExpiredError(AuthError):
    """Token matched but its expires_at is in the past."""


class TokenReusedError(AuthError):
    """Token matched but consumed_at is already set."""


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass
class MagicLink:
    """What request_magic_link returns so tests/diagnostics can inspect it."""

    email: str
    raw_token: str
    url: str
    expires_at: datetime


class AuthService:
    """Issue and verify magic-link login tokens.

    Args:
        session_factory: SQLAlchemy async session factory (from
            :func:`app.db.create_session_factory`).
        email_backend: Pluggable transport. See :mod:`app.auth.email`.
        verify_base_url: Public origin where /auth/verify is reachable
            (e.g. ``"http://localhost:8000"``). We build the link by
            joining this with ``/auth/verify?token=<raw>``.
        token_ttl: How long a new token stays valid.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        email_backend: EmailBackend,
        verify_base_url: str,
        token_ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        self._session_factory = session_factory
        self._email_backend = email_backend
        self._verify_base_url = verify_base_url.rstrip("/")
        self._token_ttl = token_ttl

    async def request_magic_link(
        self, email: str, *, next_path: str | None = None
    ) -> MagicLink:
        normalized = _normalize_email(email)
        if not normalized or "@" not in normalized:
            raise ValueError("Invalid email address.")

        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw_token)
        expires_at = _utcnow() + self._token_ttl

        async with session_scope(self._session_factory) as session:
            user = await self._find_or_create_user(session, normalized)
            session.add(
                LoginTokenRow(
                    user_id=user.id,
                    token_hash=token_hash,
                    expires_at=expires_at,
                )
            )

        # Preserve ``next`` through the email round-trip so clicking the
        # link lands the user where they originally tried to go. The
        # verify handler re-validates the path before redirecting.
        params: dict[str, str] = {"token": raw_token}
        if next_path and next_path.startswith("/") and not next_path.startswith("//"):
            params["next"] = next_path
        link = f"{self._verify_base_url}/auth/verify?{urlencode(params)}"
        await self._email_backend.send_magic_link(to=normalized, link=link)

        return MagicLink(
            email=normalized,
            raw_token=raw_token,
            url=link,
            expires_at=expires_at,
        )

    async def verify_token(self, raw_token: str) -> UserRow:
        if not raw_token:
            raise TokenInvalidError("Empty token.")
        token_hash = _hash_token(raw_token)

        async with session_scope(self._session_factory) as session:
            stmt = select(LoginTokenRow).where(LoginTokenRow.token_hash == token_hash)
            result = await session.execute(stmt)
            token = result.scalars().first()
            if token is None:
                raise TokenInvalidError("Unknown token.")

            now = _utcnow()
            if token.consumed_at is not None:
                raise TokenReusedError("Token already used.")
            # expires_at stored as timezone-aware UTC; sqlite round-trips it
            # as naive datetimes in some driver paths, so coerce before compare.
            expires = token.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now:
                raise TokenExpiredError("Token expired.")

            user = await session.get(UserRow, token.user_id)
            if user is None:
                # DB in a weird state — token references a missing user.
                raise TokenInvalidError("Token references a missing user.")

            token.consumed_at = now
            user.last_login_at = now
            session.add(token)
            session.add(user)
            # session_scope commits on exit.

        return user

    async def _find_or_create_user(
        self, session: AsyncSession, email: str
    ) -> UserRow:
        stmt = select(UserRow).where(UserRow.email == email)
        existing = (await session.execute(stmt)).scalars().first()
        if existing is not None:
            return existing
        user = UserRow(email=email)
        session.add(user)
        await session.flush()  # populate user.id
        return user
