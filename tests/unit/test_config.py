from app.config import Settings, get_settings


def test_profile_defaults():
    settings = Settings()
    profile = settings.profile()
    assert profile.environment in {"CERT", "PROD"}
    assert profile.software_id
    assert profile.software_version


def test_feature_flag_parsing(monkeypatch):
    monkeypatch.setenv("FEATURE_EFILE_XML", "true")
    monkeypatch.setenv("EFILE_ENV", "prod")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.feature_efile_xml is True
    assert settings.efile_environment == "PROD"
    get_settings.cache_clear()
