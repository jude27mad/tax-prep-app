"""FastAPI dependencies for magic-link auth.

Two public deps:

* :func:`get_current_user` — reads ``request.session["user_id"]``, loads
  the :class:`UserRow`, returns it or ``None`` if no session. Never raises.
* :func:`require_user` — same as above but raises ``HTTPException(401)``
  if no session. Mount this on routes that must be signed in.

We also expose :func:`get_auth_service` which builds an :class:`AuthService`
on demand from app state (session factory + email backend + the request's
base URL). Rebuilding per-request is cheap and keeps the service stateless
between requests.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status

from app.auth.email import EmailBackend
from app.auth.service import AuthService
from app.db import UserRow, session_scope


class AuthError(Exception):
    """Module-local alias so callers can import one symbol."""


async def get_current_user(request: Request) -> UserRow | None:
    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        return None
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        return None
    async with session_scope(factory) as session:
        return await session.get(UserRow, user_id)


async def require_user(
    user: UserRow | None = Depends(get_current_user),
) -> UserRow:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user


def get_auth_service(request: Request) -> AuthService:
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        raise RuntimeError(
            "DB session factory missing from app.state; is the lifespan running?"
        )
    email_backend: EmailBackend | None = getattr(
        request.app.state, "email_backend", None
    )
    if email_backend is None:
        raise RuntimeError(
            "Email backend missing from app.state; is the lifespan running?"
        )
    ttl_minutes = getattr(request.app.state, "auth_token_ttl_minutes", 15)
    # Prefer the request's own origin so links point back where the user
    # came from (localhost in dev, the public host in prod).
    base_url = str(request.base_url).rstrip("/")
    return AuthService(
        session_factory=factory,
        email_backend=email_backend,
        verify_base_url=base_url,
        token_ttl=timedelta(minutes=ttl_minutes),
    )
