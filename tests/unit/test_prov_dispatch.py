"""Coverage for the canonical provincial calculator registry.

This file used to test the float-based ``app/tax`` adapter system. That parallel
implementation has been retired in favour of the Decimal-only canonical
calculators in ``app/core/provinces``. Tests now exercise the Decimal API
directly.
"""

from decimal import Decimal as D

import pytest

from app.core.provinces import (
    NEXT_TAX_YEAR,
    UnknownProvinceError,
    get_provincial_calculator,
    list_provincial_calculators,
    list_supported_provinces,
)
from app.core.provinces.on import (
    ON_BPA_2025,
    ON_NRTC_RATE_2025,
    on_health_premium_2024,
    on_surtax_2025,
    on_tax_on_taxable_income_2025,
)
from tests.fixtures.min_client import make_provincial_examples


@pytest.mark.parametrize("taxable", [D("40000"), D("75000"), D("210000")])
def test_ontario_calculator_matches_canonical_pieces(taxable: D) -> None:
    calc = get_provincial_calculator(2025, "ON")
    expected_before = on_tax_on_taxable_income_2025(taxable)
    expected_credits = (ON_BPA_2025 * ON_NRTC_RATE_2025).quantize(D("0.01"))
    expected_after = max(D("0"), expected_before - expected_credits)
    expected_surtax = on_surtax_2025(expected_after)
    expected_premium = on_health_premium_2024(taxable)

    before = calc.tax(taxable)
    credits = calc.credits()
    after = max(D("0"), before - credits)
    additions = dict(calc.additions(taxable, before, credits))

    assert before == expected_before
    assert credits == expected_credits
    assert after == expected_after
    assert additions["ontario_surtax"] == expected_surtax
    assert additions["ontario_health_premium"] == expected_premium
    assert calc.code == "ON"
    assert calc.name == "Ontario"
    assert calc.bpa == ON_BPA_2025
    assert calc.nrtc_rate == ON_NRTC_RATE_2025


def test_calculators_registered_for_all_provinces() -> None:
    provinces = list_supported_provinces(2025)
    assert provinces
    for code in provinces:
        calc = get_provincial_calculator(2025, code)
        before = calc.tax(D("60000"))
        after = max(D("0"), before - calc.credits())
        assert before >= 0
        assert after >= 0
        assert calc.code == code


def test_list_provincial_calculators_includes_registered_codes() -> None:
    calcs = list_provincial_calculators(2025)
    codes = [c.code for c in calcs]
    expected = ["ON", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE", "YT", "NT", "NU"]
    assert sorted(codes) == sorted(expected)
    assert list_supported_provinces(2025) == sorted(expected)


def test_registered_calculators_are_progressive() -> None:
    provinces = list_supported_provinces(2025)
    assert provinces
    for code in provinces:
        calc = get_provincial_calculator(2025, code)
        zero = calc.tax(D("0"))
        mid = calc.tax(D("45000"))
        high = calc.tax(D("180000"))
        assert zero >= 0
        assert mid >= zero
        assert high >= mid


def test_registered_calculators_align_with_fixture_income() -> None:
    examples = make_provincial_examples()
    for code, example in examples.items():
        taxable = sum((s.employment_income for s in example.slips_t4), D("0"))
        calc = get_provincial_calculator(2025, code)
        before = calc.tax(taxable)
        after = max(D("0"), before - calc.credits())
        assert calc.code == code
        assert after <= before


def test_unknown_province_raises() -> None:
    with pytest.raises(UnknownProvinceError):
        get_provincial_calculator(2025, "ZZ")


def test_next_year_falls_back_to_2025_for_known_province() -> None:
    # 2026 calculators are not yet registered; the registry falls back to the
    # current default year so the wizard does not blow up on a forward-dated
    # query. Unknown provinces still raise.
    fallback = get_provincial_calculator(NEXT_TAX_YEAR, "ON")
    assert fallback.code == "ON"
    with pytest.raises(UnknownProvinceError):
        get_provincial_calculator(NEXT_TAX_YEAR, "ZZ")
