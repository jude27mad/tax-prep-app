from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import ModuleType
from typing import Callable, Mapping

from app.core.provinces import ab, bc, mb, nb, nl, ns, nt, nu, on, pe, sk, yt
from app.core.provinces.dispatch_2024 import CALC_2024 as MODULES_2024

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

def _calculator_from_module(module: ModuleType, year: int) -> ProvincialCalculator:
    name = module.__name__.rsplit(".", 1)[-1]
    prefix = name.lower()
    return ProvincialCalculator(
        tax=getattr(module, f"{prefix}_tax_on_taxable_income_{year}"),
        credits=getattr(module, f"{prefix}_credits_{year}"),
        additions=getattr(module, f"{prefix}_additions_{year}"),
    )


_PROVINCE_CALCULATORS_BY_YEAR: dict[int, dict[str, ProvincialCalculator]] = {
    2024: {
        code: _calculator_from_module(module, 2024)
        for code, module in MODULES_2024.items()
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
    year_map = _PROVINCE_CALCULATORS_BY_YEAR.get(tax_year)
    resolved_year = tax_year
    if not year_map:
        resolved_year = 2025
        year_map = _PROVINCE_CALCULATORS_BY_YEAR.get(2025, {})
    if not year_map:
        raise KeyError(f"No provincial calculators available for tax year {tax_year}")

    if province:
        province_code = province.upper()
    else:
        province_code = _DEFAULT_PROVINCE

    try:
        return year_map[province_code]
    except KeyError as exc:
        if not province:
            raise KeyError(
                f"Default province '{_DEFAULT_PROVINCE}' missing for tax year {resolved_year}"
            ) from exc
        raise KeyError(
            f"Unsupported province code '{province_code}' for tax year {resolved_year}"
        ) from exc


def supported_provinces(tax_year: int) -> Mapping[str, ProvincialCalculator]:
    year_map = _PROVINCE_CALCULATORS_BY_YEAR.get(tax_year)
    if not year_map:
        return {}
    return dict(year_map)
