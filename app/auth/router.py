"""Magic-link auth router.

Routes:

* ``POST /auth/request``
    Body (form or JSON): ``email``.
    Always responds ``204`` regardless of whether the email exists or the
    send succeeded — we don't leak account existence through timing or
    status codes. Actual send errors land in logs.

* ``GET /auth/verify?token=<raw>``
    Resolves the token, stamps ``consumed_at``, populates the session
    cookie with ``user_id``. On success redirects to ``/``. On failure
    (invalid / expired / reused) returns a 400 JSON error.

* ``POST /auth/logout``
    Clears the session. Always 204.

* ``GET /auth/me``
    Returns the current user as JSON or ``401`` if not signed in. Small
    convenience surface for the UI and tests.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth.deps import get_auth_service, require_user
from app.auth.service import (
    AuthService,
    TokenExpiredError,
    TokenInvalidError,
    TokenReusedError,
)
from app.db import UserRow

router = APIRouter(prefix="/auth", tags=["auth"])

_LOGGER = logging.getLogger("tax_app.auth.router")


@router.post("/request", status_code=status.HTTP_204_NO_CONTENT)
async def request_link(
    email: str = Form(...),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    try:
        await service.request_magic_link(email)
    except ValueError as exc:
        # Invalid email shape. Still return 204 to avoid oracle behavior —
        # but log at warning so operators can spot misuse.
        _LOGGER.warning("Rejected malformed email in /auth/request: %s", exc)
    except Exception:  # noqa: BLE001 — we never want to leak send-failures
        _LOGGER.exception("Failed to issue magic link")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/verify")
async def verify_link(
    request: Request,
    token: str = "",
    service: AuthService = Depends(get_auth_service),
) -> Response:
    try:
        user = await service.verify_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link has expired. Request a new one.",
        ) from None
    except TokenReusedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link has already been used. Request a new one.",
        ) from None
    except TokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid login link.",
        ) from None

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
async def me(user: UserRow = Depends(require_user)) -> JSONResponse:
    return JSONResponse(
        {
            "id": user.id,
            "email": user.email,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": (
                user.last_login_at.isoformat() if user.last_login_at else None
            ),
        }
    )
