from unittest.mock import patch
from app.config import Settings
from app.efile.gating import can_transmit, transmit_restriction


def _settings(*, feature_2025_transmit: bool = False) -> Settings:
    return Settings(
        feature_efile_xml=True,
        feature_legacy_efile=True,
        feature_2025_transmit=feature_2025_transmit,
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


def test_can_transmit_allows_2025_with_feature_flag():
    settings = _settings(feature_2025_transmit=True)
    assert can_transmit(2025, settings=settings) is True


def test_transmit_restriction_unsupported_year():
    settings = _settings()
    reason = transmit_restriction(2010, settings=settings)
    assert reason is not None
    assert "not supported" in reason


def test_transmit_restriction_outside_cra_window():
    settings = _settings()
    # 2016 is not in CRA_EFILE_INITIAL_YEARS or CRA_REFILING_YEARS
    # But it also might not be in SUPPORTED_YEARS. We mock SUPPORTED_YEARS to test this branch.
    with patch("app.efile.gating.SUPPORTED_YEARS", (2016, 2024, 2025)):
        reason = transmit_restriction(2016, settings=settings)
        assert reason is not None
        assert "outside the CRA window" in reason
