"""Browser-facing web hardening: CSRF protection + security headers.

This module adds two pure-ASGI middlewares plus the Jinja helpers that wire
the synchronizer CSRF token into server-rendered forms.

Design notes
------------
*CSRF* uses the **synchronizer-token** pattern: a random token is minted once
per session and stashed in the signed session cookie (so it inherits the
cookie's tamper-evidence). Every state-changing **browser** request must echo
that token back via a hidden ``csrf_token`` form field (or, for same-origin
JS, the ``X-CSRF-Token`` header). The token is compared in constant time.

Who is enforced, and why JSON callers are exempt
    The app's routers already distinguish browser callers from programmatic
    API clients by the ``Accept`` header (``_wants_html``); the form variants
    of ``/auth/request`` and ``/auth/logout`` use ``application/x-www-form-
    urlencoded`` *bodies* for both browser and API callers, so content-type
    alone can't tell them apart — only ``Accept`` can. We therefore enforce
    CSRF exactly on requests that "want HTML" (real browser form posts, which
    always carry ``Accept: text/html``) and leave JSON/API callers — the ones
    that receive ``204`` — untouched. This is layered defense-in-depth on top
    of the ``SameSite=Lax`` session cookie, which already prevents the session
    cookie from riding along on cross-site POSTs at all.

*Security headers* are emitted on every response: a baseline CSP that tolerates
the templates' inline ``<style>``/``<script>`` blocks while still locking down
framing/base-uri/form-action, ``X-Frame-Options: DENY``,
``X-Content-Type-Options: nosniff``, a ``Referrer-Policy``, and (when the
deployment is HTTPS/secure) HSTS.
"""

from __future__ import annotations

import secrets
from typing import Any, Final
from urllib.parse import parse_qs

from jinja2 import pass_context
from markupsafe import Markup
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Session key, form-field name, and header name all share one literal so the
# template helpers and the middleware can never drift apart.
CSRF_SESSION_KEY: Final = "csrf_token"
CSRF_FIELD_NAME: Final = "csrf_token"
CSRF_HEADER_NAME: Final = "x-csrf-token"

# Methods that never mutate state and so never require a token.
SAFE_METHODS: Final[frozenset[str]] = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

_TOKEN_BYTES: Final = 32

DEFAULT_CSP: Final = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "form-action 'self'"
)
DEFAULT_REFERRER_POLICY: Final = "strict-origin-when-cross-origin"
DEFAULT_FRAME_OPTIONS: Final = "DENY"
DEFAULT_HSTS_MAX_AGE: Final = 63072000  # two years, in seconds


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def get_csrf_token(request: Request) -> str:
    """Read the session's CSRF token, or ``""`` when unavailable.

    Degrades gracefully when ``SessionMiddleware`` isn't installed (e.g. the
    router unit tests build a bare app) so templates can still render a hidden
    field — it just carries an empty value there.
    """
    if "session" not in request.scope:
        return ""
    token = request.session.get(CSRF_SESSION_KEY)
    return token if isinstance(token, str) else ""


def wants_html(request: Request) -> bool:
    """True for browser-form callers (``Accept`` advertises HTML).

    Mirrors :func:`app.auth.router._wants_html`; kept local to avoid an import
    cycle between this module and the routers.
    """
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "application/xhtml+xml" in accept


# ---------------------------------------------------------------------------
# Jinja globals
# ---------------------------------------------------------------------------


@pass_context
def csrf_token_global(context: Any) -> str:
    """Jinja global ``{{ csrf_token() }}`` — the raw token string."""
    request = context.get("request")
    return get_csrf_token(request) if request is not None else ""


@pass_context
def csrf_input_global(context: Any) -> Markup:
    """Jinja global ``{{ csrf_input() }}`` — a ready-to-drop hidden field."""
    request = context.get("request")
    token = get_csrf_token(request) if request is not None else ""
    return Markup('<input type="hidden" name="{name}" value="{value}">').format(
        name=CSRF_FIELD_NAME, value=token
    )


# ---------------------------------------------------------------------------
# ASGI body helpers (so the middleware can read the form and replay it)
# ---------------------------------------------------------------------------


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] == "http.request":
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        elif message["type"] == "http.disconnect":
            break
    return b"".join(chunks)


def _replay_receive(body: bytes) -> Receive:
    """Hand the buffered body back to the downstream app exactly once."""
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


async def _submitted_token(request: Request, body: bytes) -> str | None:
    """Pull the caller's token from the ``X-CSRF-Token`` header or the body."""
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if header_token:
        return header_token

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/x-www-form-urlencoded"):
        parsed = parse_qs(body.decode("utf-8", "ignore"))
        values = parsed.get(CSRF_FIELD_NAME)
        return values[0] if values else None
    if content_type.startswith("multipart/form-data"):
        # Re-parse via Starlette so multipart boundaries are handled correctly;
        # the throwaway request reads from a private replay of the same body.
        form_request = Request(request.scope, _replay_receive(body))
        form = await form_request.form()
        value = form.get(CSRF_FIELD_NAME)
        return value if isinstance(value, str) else None
    return None


# ---------------------------------------------------------------------------
# Middlewares
# ---------------------------------------------------------------------------


class CSRFMiddleware:
    """Synchronizer-token CSRF guard for browser form posts.

    Requires :class:`starlette.middleware.sessions.SessionMiddleware` to be
    installed *outside* it (added later in ``main.py``) so the session dict is
    already on the scope when this runs and any newly minted token gets
    persisted on the way out.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        session_key: str = CSRF_SESSION_KEY,
    ) -> None:
        self.app = app
        self.session_key = session_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        session = scope.get("session")

        # Mint a token on first sight so any form rendered this request can
        # echo it. No session -> no synchronizer token possible; degrade open
        # (only reachable if installed without SessionMiddleware).
        token: str | None = None
        if session is not None:
            token = session.get(self.session_key)
            if not isinstance(token, str) or not token:
                token = generate_csrf_token()
                session[self.session_key] = token

        if scope["method"] in SAFE_METHODS or session is None or not wants_html(request):
            await self.app(scope, receive, send)
            return

        body = await _read_body(receive)
        submitted = await _submitted_token(request, body)
        if (
            not token
            or not submitted
            or not secrets.compare_digest(submitted, token)
        ):
            response = PlainTextResponse(
                "CSRF token missing or invalid.",
                status_code=403,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, _replay_receive(body), send)


class SecurityHeadersMiddleware:
    """Attach baseline security headers to every HTTP response."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enable_hsts: bool = False,
        csp: str = DEFAULT_CSP,
        referrer_policy: str = DEFAULT_REFERRER_POLICY,
        frame_options: str = DEFAULT_FRAME_OPTIONS,
        hsts_max_age: int = DEFAULT_HSTS_MAX_AGE,
    ) -> None:
        self.app = app
        self.enable_hsts = enable_hsts
        self.csp = csp
        self.referrer_policy = referrer_policy
        self.frame_options = frame_options
        self.hsts_value = f"max-age={hsts_max_age}; includeSubDomains"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", self.frame_options)
                headers.setdefault("Referrer-Policy", self.referrer_policy)
                headers.setdefault("Content-Security-Policy", self.csp)
                if self.enable_hsts:
                    headers.setdefault("Strict-Transport-Security", self.hsts_value)
            await send(message)

        await self.app(scope, receive, send_with_headers)
