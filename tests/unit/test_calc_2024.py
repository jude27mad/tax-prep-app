from decimal import Decimal as D

import pytest

from app.core.provinces import get_provincial_calculator, supported_provinces
from app.core.provinces.nb import nb_credits_2024, nb_tax_on_taxable_income_2024
from app.core.provinces.nl import nl_credits_2024, nl_tax_on_taxable_income_2024
from app.core.provinces.ns import ns_credits_2024, ns_tax_on_taxable_income_2024
from app.core.provinces.nt import nt_credits_2024, nt_tax_on_taxable_income_2024
from app.core.provinces.nu import nu_credits_2024, nu_tax_on_taxable_income_2024
from app.core.provinces.on import on_credits_2024, on_surtax_2024, on_tax_on_taxable_income_2024
from app.core.provinces.pe import pe_credits_2024, pe_tax_on_taxable_income_2024
from app.core.provinces.sk import sk_credits_2024, sk_tax_on_taxable_income_2024
from app.core.provinces.yt import yt_credits_2024, yt_tax_on_taxable_income_2024
from app.core.tax_years.y2024.calc import compute_full_2024


def test_federal_bpa_phase():
    # Low income: full BPA should yield non-zero federal credits
    r = compute_full_2024(D("40000"), D("40000"))
    assert r.federal_credits > D("0")


def test_on_surtax_thresholds():
    assert on_surtax_2024(D("5554")) == D("0.00")
    assert on_surtax_2024(D("5554.10")) > D("0.00")
    assert on_surtax_2024(D("7108.10")) > on_surtax_2024(D("7108.00"))


def test_end_to_end_sample():
    r = compute_full_2024(D("120000"), D("120000"))
    assert r.total_payable > D("0")


def test_supported_province_listing_for_2024():
    provinces = supported_provinces(2024)
    assert set(provinces.keys()) == {
        "ON",
        "SK",
        "NS",
        "NB",
        "NL",
        "PE",
        "YT",
        "NT",
        "NU",
    }


@pytest.mark.parametrize(
    "province,tax_fn,credit_fn",
    [
        ("ON", on_tax_on_taxable_income_2024, on_credits_2024),
        ("SK", sk_tax_on_taxable_income_2024, sk_credits_2024),
        ("NS", ns_tax_on_taxable_income_2024, ns_credits_2024),
        ("NB", nb_tax_on_taxable_income_2024, nb_credits_2024),
        ("NL", nl_tax_on_taxable_income_2024, nl_credits_2024),
        ("PE", pe_tax_on_taxable_income_2024, pe_credits_2024),
        ("YT", yt_tax_on_taxable_income_2024, yt_credits_2024),
        ("NT", nt_tax_on_taxable_income_2024, nt_credits_2024),
        ("NU", nu_tax_on_taxable_income_2024, nu_credits_2024),
    ],
)
def test_get_provincial_calculator_routes_to_specific_province(province, tax_fn, credit_fn):
    taxable = D("85000.00")
    calculator = get_provincial_calculator(2024, province)
    assert calculator.tax(taxable) == tax_fn(taxable)
    assert calculator.credits() == credit_fn()


def test_get_provincial_calculator_defaults_to_on_when_missing():
    taxable = D("42000.00")
    calculator = get_provincial_calculator(2024, None)
    assert calculator.tax(taxable) == on_tax_on_taxable_income_2024(taxable)
    additions = calculator.additions(taxable, calculator.tax(taxable), calculator.credits())
    assert set(additions.keys()) == {"ontario_surtax", "ontario_health_premium"}


def test_get_provincial_calculator_raises_for_unknown_province():
    with pytest.raises(KeyError):
        get_provincial_calculator(2024, "ZZ")
