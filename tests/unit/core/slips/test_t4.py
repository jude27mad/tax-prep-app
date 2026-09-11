from decimal import Decimal

from app.core.models import T4Slip
from app.core.slips.t4 import sum_employment_income


def test_sum_employment_income_empty():
    assert sum_employment_income([]) == Decimal("0.00")


def test_sum_employment_income_single_slip():
    slip = T4Slip(employment_income=Decimal("50000.00"))

    assert sum_employment_income([slip]) == Decimal("50000.00")


def test_sum_employment_income_multiple_slips():
    slips = [
        T4Slip(employment_income=Decimal("50000.50")),
        T4Slip(employment_income=Decimal("25000.25")),
        T4Slip(employment_income=Decimal("100.00")),
    ]

    assert sum_employment_income(slips) == Decimal("75100.75")
