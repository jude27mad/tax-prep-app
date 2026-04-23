"""Boundary coverage for the Ontario Health Premium schedule.

Each plateau and ramp in the OHP table is exercised so the cap behaviour
cannot regress (the canonical OHP table previously had no caps on the 25%
ramps, silently overcharging anyone earning > $48,600).
"""

import pytest
from decimal import Decimal as D

from app.core.provinces.on import on_health_premium_2024


@pytest.mark.parametrize(
    "income,expected",
    [
        # Below threshold
        ("0", "0.00"),
        ("19999", "0.00"),
        ("20000", "0.00"),
        # 6% phase-in toward $300
        ("22000", "120.00"),
        ("25000", "300.00"),
        # Plateau $300
        ("30000", "300.00"),
        ("36000", "300.00"),
        # 6% phase-in toward $450
        ("37000", "360.00"),
        ("38500", "450.00"),
        # Plateau $450
        ("42000", "450.00"),
        ("48000", "450.00"),
        # 25% phase-in toward $600 (narrow $600-wide ramp)
        ("48300", "525.00"),
        ("48600", "600.00"),
        # Plateau $600 — REGRESSION GUARD: previously over-charged here
        ("65000", "600.00"),
        ("72000", "600.00"),
        # 25% phase-in toward $750
        ("72300", "675.00"),
        ("72600", "750.00"),
        # Plateau $750
        ("100000", "750.00"),
        ("200000", "750.00"),
        # 25% phase-in toward $900
        ("200300", "825.00"),
        ("200600", "900.00"),
        # Top plateau
        ("220000", "900.00"),
        ("500000", "900.00"),
    ],
)
def test_ohp_table_boundaries(income: str, expected: str) -> None:
    assert on_health_premium_2024(D(income)) == D(expected)
