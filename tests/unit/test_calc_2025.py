from decimal import Decimal as D

from app.core.provinces.on import on_surtax_2025
from app.core.tax_years.y2025.calc import compute_full_2025


def test_federal_first_bracket_math_blended():
    r = compute_full_2025(D("57000"), D("57000"))
    assert r.federal_tax > D("0")
    assert r.federal_credits > D("0")


def test_on_surtax_thresholds_2025():
    assert on_surtax_2025(D("5710")) == D("0.00")
    assert on_surtax_2025(D("5710.10")) > D("0.00")
    assert on_surtax_2025(D("7307.10")) > on_surtax_2025(D("7307.00"))


def test_end_to_end_sample_2025():
    r = compute_full_2025(D("120000"), D("120000"))
    assert r.total_payable > D("0")
