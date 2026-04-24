from decimal import Decimal
from ..models import T4Slip

def sum_employment_income(slips: list[T4Slip]) -> Decimal:
  return sum((slip.employment_income for slip in slips), Decimal("0.00"))

def compute_cpp_2024(slips: list[T4Slip]) -> dict[str, Decimal]:
  emp = Decimal("0.00")
  for slip in slips:
    if slip.cpp_contrib:
      emp += slip.cpp_contrib
  return {"employee": emp}

def compute_ei_2024(slips: list[T4Slip]) -> dict[str, Decimal]:
  emp = Decimal("0.00")
  for slip in slips:
    if slip.ei_premiums:
      emp += slip.ei_premiums
  return {"employee": emp}
