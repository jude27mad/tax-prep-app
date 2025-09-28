from decimal import Decimal as D

from app.core.tax_years.y2025.federal import federal_tax_2025
from app.core.provinces.on import on_tax_on_taxable_income_2025


def test_federal_bracket_edges_2025():
    assert federal_tax_2025(D("57375")) == D("8319.38")
    slight = federal_tax_2025(D("57376"))
    assert slight > D("8319.38")

    assert federal_tax_2025(D("114750")) > federal_tax_2025(D("114749"))
    assert federal_tax_2025(D("177882")) > federal_tax_2025(D("177881"))
    assert federal_tax_2025(D("253414")) > federal_tax_2025(D("253413"))


def test_ontario_bracket_edges_2025():
    first = on_tax_on_taxable_income_2025(D("52886"))
    assert first == (D("52886") * D("0.0505")).quantize(D("0.01"))
    assert on_tax_on_taxable_income_2025(D("52887")) > first

    assert on_tax_on_taxable_income_2025(D("105775")) > on_tax_on_taxable_income_2025(D("105774"))
    assert on_tax_on_taxable_income_2025(D("150000")) > on_tax_on_taxable_income_2025(D("149999"))
    assert on_tax_on_taxable_income_2025(D("220000")) > on_tax_on_taxable_income_2025(D("219999"))
