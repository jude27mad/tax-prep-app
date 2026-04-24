"""Tests for the i18n scaffolding (catalog lookup, middleware, UI wiring).

Covers:
  * Catalog resolution: primary locale, fallback to default, missing-key
    sentinel, parameter interpolation with safe-dict pass-through.
  * Locale normalization from header-tag forms (``fr-CA``, ``FR``,
    ``en-US,fr;q=0.9``).
  * Middleware priority order: query param > cookie > Accept-Language > default.
  * Parity: EN and FR catalogs share the same key set (no drift).
  * HTTP integration: the landing page renders FR when the cookie is set,
    and ``POST /ui/locale/fr`` persists the cookie.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.i18n import (
    DEFAULT_LOCALE,
    LOCALE_COOKIE_NAME,
    SUPPORTED_LOCALES,
    LocaleMiddleware,
    is_supported,
    normalize_locale,
    reload_catalogs,
    translate,
)
from app.i18n.middleware import _from_accept_language, resolve_locale


# ---------------------------------------------------------------------------
# Catalog resolution
# ---------------------------------------------------------------------------


def test_translate_returns_locale_value():
    assert translate("profiles.heading", "en") == "Profiles"
    assert translate("profiles.heading", "fr") == "Profils"


def test_translate_falls_back_to_default_when_key_missing_in_locale(tmp_path):
    root = tmp_path / "catalogs"
    root.mkdir()
    (root / "en.json").write_text(json.dumps({"greeting": "Hello"}), encoding="utf-8")
    (root / "fr.json").write_text(json.dumps({}), encoding="utf-8")
    reload_catalogs()
    try:
        # FR lacks the key → falls back to EN.
        assert translate("greeting", "fr", catalogs_root=root) == "Hello"
    finally:
        reload_catalogs()


def test_translate_returns_key_when_missing_everywhere(tmp_path):
    root = tmp_path / "catalogs"
    root.mkdir()
    (root / "en.json").write_text(json.dumps({}), encoding="utf-8")
    (root / "fr.json").write_text(json.dumps({}), encoding="utf-8")
    reload_catalogs()
    try:
        assert translate("missing.key", "en", catalogs_root=root) == "missing.key"
    finally:
        reload_catalogs()


def test_translate_unsupported_locale_uses_default():
    # "de" isn't in SUPPORTED_LOCALES → normalize to None → DEFAULT_LOCALE.
    assert translate("profiles.heading", "de") == "Profiles"


def test_translate_none_locale_uses_default():
    assert translate("profiles.heading", None) == "Profiles"


def test_translate_interpolates_params(tmp_path):
    root = tmp_path / "catalogs"
    root.mkdir()
    (root / "en.json").write_text(
        json.dumps({"greeting": "Hello, {name}!"}), encoding="utf-8"
    )
    reload_catalogs()
    try:
        assert (
            translate("greeting", "en", catalogs_root=root, name="Alice")
            == "Hello, Alice!"
        )
    finally:
        reload_catalogs()


def test_translate_missing_param_passes_through_literally(tmp_path):
    root = tmp_path / "catalogs"
    root.mkdir()
    (root / "en.json").write_text(
        json.dumps({"greeting": "Hello, {name}!"}), encoding="utf-8"
    )
    reload_catalogs()
    try:
        # No `name` kwarg → the placeholder survives so a missing var
        # never crashes a template render.
        assert translate("greeting", "en", catalogs_root=root) == "Hello, {name}!"
    finally:
        reload_catalogs()


def test_catalog_rejects_non_string_values(tmp_path):
    root = tmp_path / "catalogs"
    root.mkdir()
    (root / "en.json").write_text(
        json.dumps({"count": 42}), encoding="utf-8"
    )
    reload_catalogs()
    try:
        with pytest.raises(ValueError, match="non-string value"):
            translate("count", "en", catalogs_root=root)
    finally:
        reload_catalogs()


# ---------------------------------------------------------------------------
# EN/FR parity — any key added to EN must also be present in FR, and vice
# versa. This guards the D3.10 translation pass from silent drift.
# ---------------------------------------------------------------------------


def _project_catalog(code: str) -> dict[str, str]:
    path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "i18n"
        / "catalogs"
        / f"{code}.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_catalog_key_parity_between_en_and_fr():
    en = _project_catalog("en")
    fr = _project_catalog("fr")
    assert set(en.keys()) == set(fr.keys())


def test_catalog_has_every_supported_locale():
    for code in SUPPORTED_LOCALES:
        assert _project_catalog(code), f"empty catalog for {code}"


# ---------------------------------------------------------------------------
# Locale normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("en", "en"),
        ("EN", "en"),
        ("fr", "fr"),
        ("fr-CA", "fr"),
        ("fr_CA", "fr"),
        ("  fr-ca  ", "fr"),
        ("de", None),
        ("", None),
        (None, None),
        ("fr-CA,en;q=0.8", "fr"),
    ],
)
def test_normalize_locale(raw, expected):
    assert normalize_locale(raw) == expected


def test_is_supported():
    assert is_supported("en")
    assert is_supported("fr")
    assert not is_supported("de")
    assert not is_supported(None)


# ---------------------------------------------------------------------------
# Accept-Language parsing
# ---------------------------------------------------------------------------


def test_accept_language_prefers_highest_weight():
    assert _from_accept_language("fr;q=0.3, en;q=0.9") == "en"
    assert _from_accept_language("en;q=0.4, fr;q=0.8") == "fr"


def test_accept_language_uses_position_as_tiebreaker():
    # Equal weights → first listed wins.
    assert _from_accept_language("fr, en") == "fr"
    assert _from_accept_language("en, fr") == "en"


def test_accept_language_ignores_unsupported():
    assert _from_accept_language("de, it, fr") == "fr"
    assert _from_accept_language("de, it") is None


def test_accept_language_handles_region_tags():
    assert _from_accept_language("en-US") == "en"
    assert _from_accept_language("fr-CA") == "fr"


def test_accept_language_none_or_empty_returns_none():
    assert _from_accept_language(None) is None
    assert _from_accept_language("") is None


# ---------------------------------------------------------------------------
# Middleware integration — priority order
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(LocaleMiddleware)

    @app.get("/echo")
    async def echo(request: Request) -> JSONResponse:
        return JSONResponse({"locale": request.state.locale})

    return app


def test_middleware_defaults_to_en_when_no_signals():
    client = TestClient(_make_app())
    resp = client.get("/echo")
    assert resp.json() == {"locale": "en"}


def test_middleware_picks_up_accept_language_header():
    client = TestClient(_make_app())
    resp = client.get("/echo", headers={"accept-language": "fr-CA,en;q=0.5"})
    assert resp.json() == {"locale": "fr"}


def test_middleware_cookie_beats_accept_language():
    client = TestClient(_make_app())
    resp = client.get(
        "/echo",
        headers={"accept-language": "en"},
        cookies={LOCALE_COOKIE_NAME: "fr"},
    )
    assert resp.json() == {"locale": "fr"}


def test_middleware_query_param_beats_cookie():
    client = TestClient(_make_app())
    resp = client.get(
        "/echo?lang=en",
        cookies={LOCALE_COOKIE_NAME: "fr"},
    )
    assert resp.json() == {"locale": "en"}


def test_middleware_ignores_unsupported_query_param():
    client = TestClient(_make_app())
    resp = client.get("/echo?lang=de", headers={"accept-language": "fr"})
    # Unsupported query param → falls through to Accept-Language.
    assert resp.json() == {"locale": "fr"}


def test_resolve_locale_default_when_state_unset():
    # resolve_locale is a pure function on Request; exercise the default path
    # directly through the middleware on a bare app.
    client = TestClient(_make_app())
    resp = client.get("/echo")
    assert resp.json()["locale"] == DEFAULT_LOCALE


# ---------------------------------------------------------------------------
# Resolve_locale unit (no TestClient)
# ---------------------------------------------------------------------------


def test_resolve_locale_prefers_query_then_cookie_then_header():
    from starlette.requests import Request

    # Craft a minimal ASGI scope with a known query/cookie/header set.
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"lang=fr",
        "headers": [
            (b"cookie", b"locale=en"),
            (b"accept-language", b"en"),
        ],
    }
    request = Request(scope)
    assert resolve_locale(request) == "fr"  # query wins

    scope["query_string"] = b""
    request = Request(scope)
    assert resolve_locale(request) == "en"  # cookie wins over header


# ---------------------------------------------------------------------------
# HTTP integration against the real UI app — /ui/ and /ui/locale/{code}
# ---------------------------------------------------------------------------


@pytest.fixture
def ui_client(tmp_path, monkeypatch):
    """Isolated TestClient against the real FastAPI app with a scratch
    profile root so we don't touch the developer's ``profiles/`` folder.

    Since D1.6 every /ui/* route is gated behind ``require_user_web``, we
    install a dependency override that pretends a test user is signed in
    so locale-rendering assertions aren't shadowed by a 303-redirect
    to /auth/login.
    """
    from dataclasses import dataclass

    from app import main as main_module
    from app.auth.deps import require_user_web
    from app.ui import router as ui_router_module
    from app.wizard import profiles as profile_store

    monkeypatch.setattr(profile_store, "BASE_DIR", tmp_path)
    monkeypatch.setattr(ui_router_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        ui_router_module, "PROFILE_DRAFTS_ROOT", tmp_path / "profiles"
    )
    (tmp_path / "profiles").mkdir(exist_ok=True)

    @dataclass
    class _I18nFakeUser:
        id: str = "11111111-1111-1111-1111-111111111111"
        email: str = "tester@example.com"

    main_module.app.dependency_overrides[require_user_web] = lambda: _I18nFakeUser()
    try:
        yield TestClient(main_module.app)
    finally:
        main_module.app.dependency_overrides.pop(require_user_web, None)


def test_ui_home_renders_english_by_default(ui_client):
    resp = ui_client.get("/ui/")
    assert resp.status_code == 200
    body = resp.text
    assert "<h2>Profiles</h2>" in body
    assert 'lang="en"' in body
    # The EN header string is present.
    assert "Tax App – Guided UI" in body


def test_ui_home_renders_french_when_cookie_set(ui_client):
    ui_client.cookies.set(LOCALE_COOKIE_NAME, "fr")
    resp = ui_client.get("/ui/")
    assert resp.status_code == 200
    body = resp.text
    assert "<h2>Profils</h2>" in body
    assert 'lang="fr"' in body
    assert "Application fiscale" in body


def test_ui_home_query_param_overrides_cookie(ui_client):
    ui_client.cookies.set(LOCALE_COOKIE_NAME, "fr")
    resp = ui_client.get("/ui/?lang=en")
    assert resp.status_code == 200
    assert "<h2>Profiles</h2>" in resp.text


def test_ui_set_locale_persists_cookie(ui_client):
    resp = ui_client.post("/ui/locale/fr", follow_redirects=False)
    assert resp.status_code == 303
    set_cookie = resp.headers.get("set-cookie", "")
    assert f"{LOCALE_COOKIE_NAME}=fr" in set_cookie


def test_ui_set_locale_rejects_unsupported(ui_client):
    resp = ui_client.post("/ui/locale/de", follow_redirects=False)
    assert resp.status_code == 400
