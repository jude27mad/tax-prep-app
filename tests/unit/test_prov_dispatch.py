import pytest

from app.tax.dispatch import (
    NEXT_TAX_YEAR,
    UnknownProvinceError,
    get_provincial_adapter,
    list_provincial_adapters,
    list_supported_provinces,
)
from app.tax.on2025 import (
    ON_BPA_2025,
    ON_CREDIT_RATE,
    health_premium_2025,
    surtax_2025,
    tax_from_brackets as on_tax,
)
from tests.fixtures.min_client import make_provincial_examples


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
    provinces = list_supported_provinces(2025)
    assert provinces
    for code in provinces:
        adapter = get_provincial_adapter(2025, code)
        result = adapter.compute(60_000)
        assert result.net_tax >= 0
        assert result.province_code == code


def test_list_provincial_adapters_includes_registered_codes() -> None:
    adapters = list_provincial_adapters(2025)
    codes = [a.code for a in adapters]
    expected = ["ON","BC","AB","MB","SK","NS","NB","NL","PE","YT","NT","NU"]
    assert sorted(codes) == sorted(expected)
    assert list_supported_provinces(2025) == sorted(expected)


def test_registered_adapters_are_progressive() -> None:
    provinces = list_supported_provinces(2025)
    assert provinces
    for code in provinces:
        adapter = get_provincial_adapter(2025, code)
        zero = adapter.compute(0.0)
        mid = adapter.compute(45_000.0)
        high = adapter.compute(180_000.0)
        assert zero.net_tax >= 0
        assert mid.net_tax >= zero.net_tax
        assert high.net_tax >= mid.net_tax


def test_registered_adapters_align_with_fixture_income() -> None:
    examples = make_provincial_examples()
    for code, example in examples.items():
        taxable = sum(float(s.employment_income) for s in example.slips_t4)
        adapter = get_provincial_adapter(2025, code)
        result = adapter.compute(taxable)
        assert result.province_code == code
        assert result.after_credits <= result.before_credits


def test_unknown_province_raises() -> None:
    with pytest.raises(UnknownProvinceError):
        get_provincial_adapter(2025, "ZZ")


def test_next_year_not_registered_yet() -> None:
    provinces = list_supported_provinces(2025)
    assert provinces
    for code in provinces:
        with pytest.raises(UnknownProvinceError):
            get_provincial_adapter(NEXT_TAX_YEAR, code)
