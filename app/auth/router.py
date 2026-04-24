"""Magic-link auth router.

Routes:

* ``GET /auth/login``
    Renders the sign-in form (HTML). Accepts ``?next=<path>`` so the form
    can round-trip the caller's intended destination through the magic
    link. Unauthenticated /ui/* routes 303-redirect here via
    :func:`app.auth.deps.require_user_web`.

* ``POST /auth/request``
    Body (form or JSON): ``email`` (plus optional ``next`` for form-POSTs).
    JSON callers get ``204``; HTML form callers get a 303 redirect to
    ``/auth/sent`` on success or a re-render of ``/auth/login`` with an
    inline error on bad input. Either way we don't leak account existence
    through timing or status codes — send failures land in logs.

* ``GET /auth/sent``
    "Check your email" landing page shown after a successful form POST
    to /auth/request. Static page — it doesn't need to know the email.

* ``GET /auth/verify?token=<raw>&next=<path>``
    Resolves the token, stamps ``consumed_at``, populates the session
    cookie with ``user_id``. On success redirects to ``next`` (if safe)
    or ``/``. On failure (invalid / expired / reused) returns a 400
    JSON error.

* ``POST /auth/logout``
    Clears the session. HTML form callers get a 303 redirect to
    ``/auth/login``; programmatic callers get ``204``.

* ``GET /auth/me``
    Returns the current user as JSON or ``401`` if not signed in. Small
    convenience surface for the UI and tests.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

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

# Reuse the UI templates directory so /auth pages inherit base.html (nav,
# locale switcher, shared CSS). Building a second Jinja2Templates keeps
# this module loosely coupled from app.ui.router and avoids an import
# cycle (ui.router also imports auth deps). The ``t()`` / ``current_locale()``
# / ``current_user_email()`` globals that base.html expects are registered
# on this env too so /auth pages render identically to /ui pages.
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "ui" / "templates"
TEMPLATES = Jinja2Templates(directory=str(_TEMPLATES_DIR))


from jinja2 import pass_context  # noqa: E402 — keep auth-template-env wiring co-located

from app.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, get_request_locale, translate  # noqa: E402


@pass_context
def _auth_jinja_t(ctx, key, **params):  # type: ignore[no-untyped-def]
    request = ctx.get("request")
    locale = get_request_locale(request) if request is not None else DEFAULT_LOCALE
    return translate(key, locale, **params)


@pass_context
def _auth_jinja_current_locale(ctx):  # type: ignore[no-untyped-def]
    request = ctx.get("request")
    return get_request_locale(request) if request is not None else DEFAULT_LOCALE


@pass_context
def _auth_jinja_current_user_email(ctx):  # type: ignore[no-untyped-def]
    request = ctx.get("request")
    if request is None:
        return None
    user = getattr(request.state, "current_user", None)
    return getattr(user, "email", None) if user is not None else None


TEMPLATES.env.globals["t"] = _auth_jinja_t
TEMPLATES.env.globals["current_locale"] = _auth_jinja_current_locale
TEMPLATES.env.globals["supported_locales"] = SUPPORTED_LOCALES
TEMPLATES.env.globals["current_user_email"] = _auth_jinja_current_user_email


def _safe_next_path(value: str | None) -> str:
    """Accept only absolute-path redirect targets on this origin.

    Guards against open-redirect by rejecting anything that isn't a
    leading-slash path (so ``//evil.example`` or ``https://...`` are
    both dropped). Empty / invalid values fall back to ``/``.
    """
    if not value:
        return "/"
    if not value.startswith("/"):
        return "/"
    if value.startswith("//"):
        return "/"
    return value


def _wants_html(request: Request) -> bool:
    """Detect browser-form callers vs JSON API clients.

    Browsers submitting a <form> always send ``text/html`` (or
    ``application/xhtml+xml``) in their Accept header. API callers that
    happen to POST form-urlencoded still send ``*/*`` or
    ``application/json``, so we don't over-match on content-type alone.
    When in doubt, default to the legacy 204 to preserve the pre-D1.6
    contract that existing API callers relied on.
    """
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "application/xhtml+xml" in accept


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: str = "",  # noqa: A002 — shadowing builtin is fine here as query arg
) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        "auth_login.html",
        {
            "request": request,
            "next_path": _safe_next_path(next),
            "email_value": "",
            "error": None,
        },
    )


@router.get("/sent", response_class=HTMLResponse)
async def sent_page(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        "auth_sent.html",
        {"request": request},
    )


@router.post("/request")
async def request_link(
    request: Request,
    email: str = Form(...),
    next: str = Form(""),  # noqa: A002
    service: AuthService = Depends(get_auth_service),
) -> Response:
    sent = True
    safe_next = _safe_next_path(next)
    try:
        await service.request_magic_link(email, next_path=safe_next)
    except ValueError as exc:
        # Invalid email shape. For HTML callers we re-render the form
        # with an inline error so they can fix it; for JSON we still
        # return 204 to avoid oracle behavior.
        _LOGGER.warning("Rejected malformed email in /auth/request: %s", exc)
        sent = False
    except Exception:  # noqa: BLE001 — we never want to leak send-failures
        _LOGGER.exception("Failed to issue magic link")
        # Fall through as if it succeeded. Operators see the failure in logs.

    if _wants_html(request):
        if not sent:
            return TEMPLATES.TemplateResponse(
                "auth_login.html",
                {
                    "request": request,
                    "next_path": _safe_next_path(next),
                    "email_value": email,
                    "error": "That doesn't look like a valid email address.",
                },
                status_code=400,
            )
        return RedirectResponse(url="/auth/sent", status_code=status.HTTP_303_SEE_OTHER)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/verify")
async def verify_link(
    request: Request,
    token: str = "",
    next: str = "",  # noqa: A002
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
    return RedirectResponse(
        url=_safe_next_path(next),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/logout")
async def logout(request: Request) -> Response:
    request.session.clear()
    if _wants_html(request):
        return RedirectResponse(
            url="/auth/login", status_code=status.HTTP_303_SEE_OTHER
        )
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
