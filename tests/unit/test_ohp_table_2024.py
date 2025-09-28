from decimal import Decimal as D

from app.core.provinces.on import on_health_premium_2024


def test_ohp_zero_under_20k():
    assert on_health_premium_2024(D("19999")) == D("0.00")
