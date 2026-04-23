"""JSON-backed translation catalogs.

Catalogs live at ``app/i18n/catalogs/{code}.json``. They are loaded lazily
on first access and cached in-process. Tests can invalidate the cache via
:func:`reload_catalogs` or by pointing :func:`translate` at a fresh root
with the ``catalogs_root`` argument.

Lookup semantics:

* ``translate(key, "fr")`` returns the FR value for ``key``.
* If the FR catalog is missing the key, fall back to the EN catalog.
* If EN is also missing, return the key itself (debug visibility — never
  crash a template render on a missing translation).
* Parameters are substituted with ``str.format_map`` over a ``SafeDict``
  so missing params pass through as ``{name}`` rather than raising.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES: tuple[str, ...] = ("en", "fr")

_DEFAULT_CATALOGS_ROOT = Path(__file__).resolve().parent / "catalogs"

# Keyed by (catalogs_root_str, locale). Clearing by reload_catalogs() wipes all.
_CACHE: dict[tuple[str, str], dict[str, str]] = {}


def is_supported(code: str | None) -> bool:
    if code is None:
        return False
    return code.lower() in SUPPORTED_LOCALES


def normalize_locale(code: str | None) -> str | None:
    """Map a header tag or raw string onto a supported locale.

    Accepts case variants, region tags (``fr-CA`` -> ``fr``), and whitespace.
    Returns ``None`` if the result isn't in :data:`SUPPORTED_LOCALES`.
    """
    if not code:
        return None
    head = code.strip().split(",")[0].split(";")[0].strip().lower()
    if not head:
        return None
    # "fr-ca", "fr_ca" -> "fr"
    base = head.replace("_", "-").split("-")[0]
    return base if base in SUPPORTED_LOCALES else None


def catalog_for(locale: str, catalogs_root: Path | None = None) -> dict[str, str]:
    """Return the parsed JSON catalog for ``locale``. Caches per root+locale.

    Raises FileNotFoundError if the catalog file does not exist. Callers
    that want soft-fallback to default should use :func:`translate`.
    """
    root = catalogs_root or _DEFAULT_CATALOGS_ROOT
    key = (str(root), locale)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    path = root / f"{locale}.json"
    if not path.exists():
        raise FileNotFoundError(f"i18n catalog for locale '{locale}' not found at {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Catalog at {path} must be a JSON object, got {type(data).__name__}")
    # Force str values — keeps template output predictable and catches accidents early.
    normalized: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            raise ValueError(f"Catalog at {path} has a non-string key: {k!r}")
        if not isinstance(v, str):
            raise ValueError(
                f"Catalog at {path} has a non-string value for {k!r}: {type(v).__name__}"
            )
        normalized[k] = v
    _CACHE[key] = normalized
    return normalized


def reload_catalogs() -> None:
    """Drop the in-memory cache. Intended for tests and dev reload."""
    _CACHE.clear()


class _SafeDict(dict[str, Any]):
    """Dict subclass that returns ``{key}`` for missing lookups so
    ``str.format_map`` never raises on a missing param."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def translate(
    key: str,
    locale: str | None = None,
    *,
    catalogs_root: Path | None = None,
    **params: Any,
) -> str:
    """Return the translation of ``key`` for ``locale``.

    Resolution order:

    1. Catalog for ``locale`` (if supported).
    2. Catalog for :data:`DEFAULT_LOCALE` (if ``locale`` differs and the
       key is missing).
    3. ``key`` itself, so missing translations are visible in rendered
       output rather than crashing a page.

    String values are substituted with ``params`` via
    ``str.format_map``. Missing placeholders pass through literally.
    """
    requested = normalize_locale(locale) or DEFAULT_LOCALE

    try:
        primary = catalog_for(requested, catalogs_root=catalogs_root)
    except FileNotFoundError:
        primary = {}

    raw = primary.get(key)
    if raw is None and requested != DEFAULT_LOCALE:
        try:
            fallback = catalog_for(DEFAULT_LOCALE, catalogs_root=catalogs_root)
        except FileNotFoundError:
            fallback = {}
        raw = fallback.get(key)

    if raw is None:
        logger.warning("Missing translation for key %r (locale: %r)", key, requested)
        return key

    if not params:
        return raw
    return raw.format_map(_SafeDict(params))
