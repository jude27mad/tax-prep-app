from app.core.tax_years._2024_alias import compute_return
from tests.fixtures.min_client import make_min_input


def test_compute_return_smoke():
  calc = compute_return(make_min_input(tax_year=2024))
  assert calc.tax_year == 2024
  assert "net_tax" in calc.totals
