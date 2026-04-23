"""Locale-detection middleware.

Attaches ``request.state.locale`` on every request from (priority order):

  1. ``?lang=<code>`` query parameter (explicit per-request override).
  2. ``<LOCALE_COOKIE_NAME>`` cookie (sticky user preference).
  3. ``Accept-Language`` header (browser default).
  4. :data:`app.i18n.DEFAULT_LOCALE`.

The middleware itself is cheap — pure string inspection, no I/O. Template
code reads ``request.state.locale`` via the ``t`` Jinja global in
``app/ui/router.py``.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.i18n.catalog import DEFAULT_LOCALE, normalize_locale

LOCALE_COOKIE_NAME = "locale"


def _from_accept_language(header: str | None) -> str | None:
    """Pick the highest-priority supported locale from ``Accept-Language``.

    Parses the comma-separated list of ``tag;q=weight`` entries, normalizes
    each tag to a supported base locale, and returns the first one that
    matches. Ignores q-weights beyond ordering — a correct q-weighted
    preference sort can move in later if it starts mattering.
    """
    if not header:
        return None
    best: str | None = None
    best_weight = -1.0
    for i, part in enumerate(header.split(",")):
        piece, _, params = part.strip().partition(";")
        weight = 1.0
        for p in params.split(";"):
            p = p.strip()
            if p.startswith("q="):
                try:
                    weight = float(p[2:])
                except ValueError:
                    weight = 0.0
        # Preserve list order for equal weights by subtracting a tiny position cost.
        adjusted = weight - (i * 1e-6)
        normalized = normalize_locale(piece)
        if normalized is not None and adjusted > best_weight:
            best = normalized
            best_weight = adjusted
    return best


def resolve_locale(request: Request) -> str:
    """Determine the effective locale for ``request``. Pure function —
    tests can call this directly without invoking the middleware."""
    query_lang = normalize_locale(request.query_params.get("lang"))
    if query_lang is not None:
        return query_lang
    cookie_lang = normalize_locale(request.cookies.get(LOCALE_COOKIE_NAME))
    if cookie_lang is not None:
        return cookie_lang
    header_lang = _from_accept_language(request.headers.get("accept-language"))
    if header_lang is not None:
        return header_lang
    return DEFAULT_LOCALE


class LocaleMiddleware(BaseHTTPMiddleware):
    """Attach ``request.state.locale`` on every request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.locale = resolve_locale(request)
        return await call_next(request)


def get_request_locale(request: Request) -> str:
    """Read ``request.state.locale``, defaulting to the configured default if
    the middleware hasn't run (e.g. in a raw TestClient invocation)."""
    return getattr(request.state, "locale", DEFAULT_LOCALE)
