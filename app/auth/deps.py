"""FastAPI dependencies for magic-link auth.

Three public deps:

* :func:`get_current_user` — reads ``request.session["user_id"]``, loads
  the :class:`UserRow`, returns it or ``None`` if no session. Never raises.
* :func:`require_user` — same as above but raises ``HTTPException(401)``
  if no session. Mount this on API/JSON routes.
* :func:`require_user_web` — same but raises a 303 redirect to
  ``/auth/login?next=<path>`` instead of 401. Mount this on HTML routes
  so unauthenticated browsers land on the login page instead of seeing
  a raw JSON error.

We also expose :func:`get_auth_service` which builds an :class:`AuthService`
on demand from app state (session factory + email backend + the request's
base URL). Rebuilding per-request is cheap and keeps the service stateless
between requests.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, status

from app.auth.email import EmailBackend
from app.auth.service import AuthService
from app.db import UserRow, session_scope


class AuthError(Exception):
    """Module-local alias so callers can import one symbol."""


async def get_current_user(request: Request) -> UserRow | None:
    # ``request.session`` is a property that raises when SessionMiddleware
    # isn't installed. Guard on the scope key instead so the dep degrades
    # gracefully in test harnesses / scripts that don't wire the middleware.
    if "session" not in request.scope:
        return None
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        return None
    async with session_scope(factory) as session:
        user = await session.get(UserRow, user_id)
    # Stash the user on request.state so templates can surface the signed-in
    # email in the nav bar without having to thread ``current_user_email``
    # through every TemplateResponse context.
    if user is not None:
        request.state.current_user = user
    return user


async def require_user(
    user: UserRow | None = Depends(get_current_user),
) -> UserRow:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user


async def require_user_web(
    request: Request,
    user: UserRow | None = Depends(get_current_user),
) -> UserRow:
    """HTML variant: on missing session, 303-redirect to ``/auth/login``.

    We preserve the requested path in ``?next=`` so the login handler can
    send the user back where they tried to go. Query strings are dropped
    (they're rarely worth preserving for a login round-trip and keeping
    them would require open-redirect hardening).
    """
    if user is None:
        next_path = request.url.path or "/"
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"location": f"/auth/login?next={quote(next_path)}"},
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
