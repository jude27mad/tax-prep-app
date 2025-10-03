import pytest

from app.tax.dispatch import UnknownProvinceError, get_provincial_adapter
from app.tax.on2025 import (
    ON_BPA_2025,
    ON_CREDIT_RATE,
    health_premium_2025,
    surtax_2025,
    tax_from_brackets as on_tax,
)


@pytest.mark.parametrize("taxable", [40_000, 75_000, 210_000])
def test_ontario_adapter_matches_legacy(taxable: float) -> None:
    adapter = get_provincial_adapter(2025, "ON")
    result = adapter.compute(taxable)

    expected_before = on_tax(taxable)
    expected_after = max(0.0, round(expected_before - ON_CREDIT_RATE * min(ON_BPA_2025, taxable), 2))
    expected_surtax = surtax_2025(expected_after)
    expected_premium = health_premium_2025(taxable)
    expected_net = round(expected_after + expected_surtax + expected_premium, 2)

    assert result.before_credits == expected_before
    assert result.after_credits == expected_after
    assert pytest.approx(result.additions["surtax"], rel=1e-4) == expected_surtax
    assert pytest.approx(result.additions["health_premium"], rel=1e-4) == expected_premium
    assert result.net_tax == expected_net


def test_adapters_registered_for_top_provinces() -> None:
    for code in ("ON", "BC", "AB", "MB"):
        adapter = get_provincial_adapter(2025, code)
        result = adapter.compute(60_000)
        assert result.net_tax >= 0
        assert result.province_code == code


def test_unknown_province_raises() -> None:
    with pytest.raises(UnknownProvinceError):
        get_provincial_adapter(2025, "ZZ")
