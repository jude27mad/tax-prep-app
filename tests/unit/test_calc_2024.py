from decimal import Decimal as D

from app.core.provinces.on import on_surtax_2024
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
