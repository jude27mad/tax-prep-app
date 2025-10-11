from app.config import Settings
from app.efile.gating import can_transmit


def _settings() -> Settings:
    return Settings(
        feature_efile_xml=True,
        feature_legacy_efile=True,
        feature_2025_transmit=False,
        efile_window_open=True,
        endpoint_cert="http://127.0.0.1:9000",
        endpoint_prod="http://127.0.0.1:9000",
    )


def test_can_transmit_allows_2024():
    settings = _settings()
    assert can_transmit(2024, settings=settings) is True


def test_can_transmit_blocks_2025_without_feature_flag():
    settings = _settings()
    assert can_transmit(2025, settings=settings) is False
