from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping

from app.core.provinces import ab, bc, mb, nb, nl, ns, nt, nu, on, pe, sk, yt

D = Decimal

TaxFunction = Callable[[D], D]
CreditFunction = Callable[[], D]
AdditionFunction = Callable[[D, D, D], Mapping[str, D]]


@dataclass(frozen=True)
class ProvincialCalculator:
    tax: TaxFunction
    credits: CreditFunction
    additions: AdditionFunction


_DEFAULT_PROVINCE = "ON"

_PROVINCE_CALCULATORS_BY_YEAR: dict[int, dict[str, ProvincialCalculator]] = {
    2024: {
        "ON": ProvincialCalculator(
            tax=on.on_tax_on_taxable_income_2024,
            credits=on.on_credits_2024,
            additions=on.on_additions_2024,
        )
    },
    2025: {
        "ON": ProvincialCalculator(
            tax=on.on_tax_on_taxable_income_2025,
            credits=on.on_credits_2025,
            additions=on.on_additions_2025,
        ),
        "BC": ProvincialCalculator(
            tax=bc.bc_tax_on_taxable_income_2025,
            credits=bc.bc_credits_2025,
            additions=bc.bc_additions_2025,
        ),
        "AB": ProvincialCalculator(
            tax=ab.ab_tax_on_taxable_income_2025,
            credits=ab.ab_credits_2025,
            additions=ab.ab_additions_2025,
        ),
        "MB": ProvincialCalculator(
            tax=mb.mb_tax_on_taxable_income_2025,
            credits=mb.mb_credits_2025,
            additions=mb.mb_additions_2025,
        ),
        "SK": ProvincialCalculator(
            tax=sk.sk_tax_on_taxable_income_2025,
            credits=sk.sk_credits_2025,
            additions=sk.sk_additions_2025,
        ),
        "NS": ProvincialCalculator(
            tax=ns.ns_tax_on_taxable_income_2025,
            credits=ns.ns_credits_2025,
            additions=ns.ns_additions_2025,
        ),
        "NB": ProvincialCalculator(
            tax=nb.nb_tax_on_taxable_income_2025,
            credits=nb.nb_credits_2025,
            additions=nb.nb_additions_2025,
        ),
        "NL": ProvincialCalculator(
            tax=nl.nl_tax_on_taxable_income_2025,
            credits=nl.nl_credits_2025,
            additions=nl.nl_additions_2025,
        ),
        "PE": ProvincialCalculator(
            tax=pe.pe_tax_on_taxable_income_2025,
            credits=pe.pe_credits_2025,
            additions=pe.pe_additions_2025,
        ),
        "YT": ProvincialCalculator(
            tax=yt.yt_tax_on_taxable_income_2025,
            credits=yt.yt_credits_2025,
            additions=yt.yt_additions_2025,
        ),
        "NT": ProvincialCalculator(
            tax=nt.nt_tax_on_taxable_income_2025,
            credits=nt.nt_credits_2025,
            additions=nt.nt_additions_2025,
        ),
        "NU": ProvincialCalculator(
            tax=nu.nu_tax_on_taxable_income_2025,
            credits=nu.nu_credits_2025,
            additions=nu.nu_additions_2025,
        ),
    },
}


def get_provincial_calculator(tax_year: int, province: str | None) -> ProvincialCalculator:
    province_code = (province or _DEFAULT_PROVINCE).upper()
    year_map = _PROVINCE_CALCULATORS_BY_YEAR.get(tax_year)
    if year_map is None:
        year_map = _PROVINCE_CALCULATORS_BY_YEAR.get(2025, {})
    calculator = year_map.get(province_code)
    if calculator is None:
        calculator = year_map.get(_DEFAULT_PROVINCE)
    if calculator is None:
        calculator = _PROVINCE_CALCULATORS_BY_YEAR[2025][_DEFAULT_PROVINCE]
    return calculator


def supported_provinces(tax_year: int) -> Mapping[str, ProvincialCalculator]:
    year_map = _PROVINCE_CALCULATORS_BY_YEAR.get(tax_year)
    if not year_map:
        return {}
    return dict(year_map)
