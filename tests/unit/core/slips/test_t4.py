from decimal import Decimal
from unittest.mock import Mock
from app.core.slips.t4 import sum_employment_income

def test_sum_employment_income_empty():
    result = sum_employment_income([])
    assert result == Decimal("0.00") or result == 0.0

def test_sum_employment_income_single_slip():
    slip = Mock()
    slip.employment_income = Decimal("50000.00")
    slip.box_14 = 50000.00
    result = sum_employment_income([slip])
    assert result == Decimal("50000.00") or result == 50000.00

def test_sum_employment_income_multiple_slips():
    slip1 = Mock()
    slip1.employment_income = Decimal("50000.50")
    slip1.box_14 = 50000.50
    slip2 = Mock()
    slip2.employment_income = Decimal("25000.25")
    slip2.box_14 = 25000.25
    slip3 = Mock()
    slip3.employment_income = Decimal("100.00")
    slip3.box_14 = 100.00

    slips = [slip1, slip2, slip3]
    result = sum_employment_income(slips)
    assert result == Decimal("75100.75") or result == 75100.75
