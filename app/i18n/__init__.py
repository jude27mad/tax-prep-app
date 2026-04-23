"""Internationalization scaffolding (EN + FR).

Phase 1 infrastructure for strategy plan **D1.5**. Delivers a minimal,
dependency-free i18n surface: JSON catalogs per locale, a ``translate``
function with parameter interpolation, and a Starlette middleware that
attaches ``request.state.locale`` based on (in priority order) a
``?lang=`` query parameter, a ``locale`` cookie, and the
``Accept-Language`` header.

The catalog format (JSON flat key -> value) is intentionally lighter than
Babel/gettext. When plural forms, CLDR-aware number formatting, or
extraction tooling become necessary, migration to Babel is straightforward
because all lookups go through :func:`translate`.

Public API:

* :func:`translate` — key -> localized string, with ``{param}`` interpolation.
* :data:`SUPPORTED_LOCALES` / :data:`DEFAULT_LOCALE` — canonical locale set.
* :func:`normalize_locale` — map header tags (``fr-CA``, ``FR``) onto
  supported codes, or ``None`` if unsupported.
* :func:`get_request_locale` — extract the locale attached by the middleware.
* :class:`LocaleMiddleware` — wires locale detection into every request.
"""

from app.i18n.catalog import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    catalog_for,
    is_supported,
    normalize_locale,
    reload_catalogs,
    translate,
)
from app.i18n.middleware import LOCALE_COOKIE_NAME, LocaleMiddleware, get_request_locale

__all__ = [
    "DEFAULT_LOCALE",
    "LOCALE_COOKIE_NAME",
    "LocaleMiddleware",
    "SUPPORTED_LOCALES",
    "catalog_for",
    "get_request_locale",
    "is_supported",
    "normalize_locale",
    "reload_catalogs",
    "translate",
]
