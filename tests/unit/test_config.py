import pytest

from app.config import Settings, get_settings


def test_profile_defaults():
    settings = Settings()
    profile = settings.profile()
    assert profile.environment in {"CERT", "PROD"}
    assert profile.software_id
    assert profile.software_version


def test_feature_flag_parsing(monkeypatch):
    monkeypatch.setenv("FEATURE_EFILE_XML", "true")
    monkeypatch.setenv("FEATURE_LEGACY_EFILE", "true")
    monkeypatch.setenv("EFILE_ENV", "prod")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-prod-session-secret")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.feature_efile_xml is True
    assert settings.feature_legacy_efile is True
    assert settings.efile_environment == "PROD"
    get_settings.cache_clear()


def test_session_secret_prod_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("EFILE_ENV", "prod")
    monkeypatch.delenv("AUTH_SESSION_SECRET", raising=False)
    monkeypatch.setenv("AUTH_SESSION_SECRET_FILE", str(tmp_path / "session-secret"))
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="AUTH_SESSION_SECRET must be explicitly set in PROD"):
        Settings()
    get_settings.cache_clear()


def test_session_secret_prod_insecure_default_raises(monkeypatch):
    monkeypatch.setenv("EFILE_ENV", "prod")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "dev-only-change-me-do-not-use-in-prod")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="AUTH_SESSION_SECRET must be explicitly set in PROD"):
        Settings()
    get_settings.cache_clear()


def test_session_secret_prod_valid_succeeds(monkeypatch):
    monkeypatch.setenv("EFILE_ENV", "prod")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "my-secure-prod-secret-1234567890")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.session_secret == "my-secure-prod-secret-1234567890"
    get_settings.cache_clear()


def test_session_secret_prod_valid_constructor_value_succeeds(monkeypatch):
    monkeypatch.setenv("EFILE_ENV", "prod")
    monkeypatch.delenv("AUTH_SESSION_SECRET", raising=False)
    settings = Settings(session_secret="constructor-provided-secure-secret")
    assert settings.session_secret == "constructor-provided-secure-secret"


def test_session_secret_prod_valid_env_does_not_mask_insecure_constructor(monkeypatch):
    monkeypatch.setenv("EFILE_ENV", "prod")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "secure-environment-secret")
    with pytest.raises(ValueError, match="AUTH_SESSION_SECRET must be explicitly set in PROD"):
        Settings(session_secret="dev-only-change-me-do-not-use-in-prod")


def test_session_secret_cert_default_is_persisted(monkeypatch, tmp_path):
    monkeypatch.setenv("EFILE_ENV", "cert")
    monkeypatch.delenv("AUTH_SESSION_SECRET", raising=False)
    secret_path = tmp_path / "session-secret"
    monkeypatch.setenv("AUTH_SESSION_SECRET_FILE", str(secret_path))
    get_settings.cache_clear()
    settings1 = Settings()
    get_settings.cache_clear()
    settings2 = Settings()
    assert settings1.session_secret
    assert settings2.session_secret == settings1.session_secret
    assert secret_path.read_text(encoding="utf-8").strip() == settings1.session_secret
    assert len(settings1.session_secret) >= 16
    get_settings.cache_clear()


def test_session_secret_cert_override(monkeypatch):
    monkeypatch.setenv("EFILE_ENV", "cert")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "explicit-cert-secret")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.session_secret == "explicit-cert-secret"
    get_settings.cache_clear()
