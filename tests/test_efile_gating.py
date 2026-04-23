from unittest.mock import patch
from app.config import Settings
from app.efile.gating import build_transmit_gate, can_transmit, transmit_restriction


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


def test_build_transmit_gate_without_feature_flag():
    settings = _settings(feature_2025_transmit=False)
    gate = build_transmit_gate(settings=settings)

    # 2024 should be allowed
    assert "2024" in gate
    assert gate["2024"]["allowed"] is True
    assert gate["2024"]["message"] == ""

    # 2025 should be blocked
    assert "2025" in gate
    assert gate["2025"]["allowed"] is False
    assert "not yet available" in str(gate["2025"]["message"])


def test_build_transmit_gate_with_feature_flag():
    settings = _settings(feature_2025_transmit=True)
    gate = build_transmit_gate(settings=settings)

    # Both 2024 and 2025 should be allowed
    assert "2024" in gate
    assert gate["2024"]["allowed"] is True
    assert gate["2024"]["message"] == ""

    assert "2025" in gate
    assert gate["2025"]["allowed"] is True
    assert gate["2025"]["message"] == ""


@patch("app.efile.gating.get_settings")
def test_build_transmit_gate_default_settings(mock_get_settings):
    mock_get_settings.return_value = _settings(feature_2025_transmit=False)
    gate = build_transmit_gate()
    assert gate["2025"]["allowed"] is False
    mock_get_settings.assert_called_once()


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
