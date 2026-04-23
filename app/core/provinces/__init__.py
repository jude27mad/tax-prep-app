from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import ModuleType
from typing import Callable, Iterable, Mapping

from app.core.provinces import ab, bc, mb, nb, nl, ns, nt, nu, on, pe, sk, yt
from app.core.provinces.dispatch_2024 import CALC_2024 as MODULES_2024

D = Decimal

TaxFunction = Callable[[D], D]
CreditFunction = Callable[[], D]
AdditionFunction = Callable[[D, D, D], Mapping[str, D]]


# Filing-season constants. Kept here so callers can import a single canonical
# year value without reaching into year-specific calc modules.
DEFAULT_TAX_YEAR = 2025
NEXT_TAX_YEAR = 2026


class UnknownProvinceError(KeyError):
    """Raised when a (year, province) pair has no registered calculator."""


@dataclass(frozen=True)
class ProvincialCalculator:
    tax: TaxFunction
    credits: CreditFunction
    additions: AdditionFunction
    code: str = ""
    name: str = ""
    bpa: D = D("0")
    nrtc_rate: D = D("0")


_DEFAULT_PROVINCE = "ON"

# Canonical English province/territory names. Matches the metadata previously
# carried on the float-path ProvincialAdapter dataclasses in app/tax/prov/*.
_PROVINCE_NAMES: dict[str, str] = {
    "ON": "Ontario",
    "BC": "British Columbia",
    "AB": "Alberta",
    "MB": "Manitoba",
    "SK": "Saskatchewan",
    "NS": "Nova Scotia",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "PE": "Prince Edward Island",
    "YT": "Yukon",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
}


def _calculator_from_module(module: ModuleType, year: int) -> ProvincialCalculator:
    name = module.__name__.rsplit(".", 1)[-1]
    prefix = name.lower()
    code = prefix.upper()
    bpa = getattr(module, f"{code}_BPA_{year}", D("0"))
    nrtc_rate = getattr(module, f"{code}_NRTC_RATE_{year}", D("0"))
    return ProvincialCalculator(
        tax=getattr(module, f"{prefix}_tax_on_taxable_income_{year}"),
        credits=getattr(module, f"{prefix}_credits_{year}"),
        additions=getattr(module, f"{prefix}_additions_{year}"),
        code=code,
        name=_PROVINCE_NAMES.get(code, code),
        bpa=bpa,
        nrtc_rate=nrtc_rate,
    )


def _build_2025_calculators() -> dict[str, ProvincialCalculator]:
    modules: tuple[ModuleType, ...] = (on, bc, ab, mb, sk, ns, nb, nl, pe, yt, nt, nu)
    return {
        module.__name__.rsplit(".", 1)[-1].upper(): _calculator_from_module(module, 2025)
        for module in modules
    }


_PROVINCE_CALCULATORS_BY_YEAR: dict[int, dict[str, ProvincialCalculator]] = {
    2024: {
        code: _calculator_from_module(module, 2024)
        for code, module in MODULES_2024.items()
    },
    2025: _build_2025_calculators(),
}


def get_provincial_calculator(tax_year: int, province: str | None) -> ProvincialCalculator:
    """Return the calculator for (year, province). Raises UnknownProvinceError on miss.

    Backwards compatibility note: previously this function silently fell back to
    2025 when an unknown year was requested. We preserve that fallback for the
    inputs path but still raise for genuinely unknown provinces, so the new
    UnknownProvinceError is a strict subclass of KeyError.
    """
    year_map = _PROVINCE_CALCULATORS_BY_YEAR.get(tax_year)
    resolved_year = tax_year
    if not year_map:
        resolved_year = 2025
        year_map = _PROVINCE_CALCULATORS_BY_YEAR.get(2025, {})
    if not year_map:
        raise UnknownProvinceError(
            f"No provincial calculators available for tax year {tax_year}"
        )

    if province:
        province_code = province.upper()
    else:
        province_code = _DEFAULT_PROVINCE

    try:
        return year_map[province_code]
    except KeyError as exc:
        if not province:
            raise UnknownProvinceError(
                f"Default province '{_DEFAULT_PROVINCE}' missing for tax year {resolved_year}"
            ) from exc
        raise UnknownProvinceError(
            f"Unsupported province code '{province_code}' for tax year {resolved_year}"
        ) from exc


def supported_provinces(tax_year: int) -> Mapping[str, ProvincialCalculator]:
    year_map = _PROVINCE_CALCULATORS_BY_YEAR.get(tax_year)
    if not year_map:
        return {}
    return dict(year_map)


def list_provincial_calculators(
    tax_year: int | None = None,
) -> list[ProvincialCalculator]:
    """Return the registered calculators for ``tax_year`` (defaults to current).

    Order matches insertion order in _PROVINCE_CALCULATORS_BY_YEAR for the year,
    which gives ON first to match prior behaviour expected by the wizard UI.
    """
    target = tax_year if tax_year is not None else DEFAULT_TAX_YEAR
    year_map = _PROVINCE_CALCULATORS_BY_YEAR.get(target)
    if not year_map:
        return []
    return list(year_map.values())


def list_supported_provinces(tax_year: int | None = None) -> list[str]:
    return sorted(c.code for c in list_provincial_calculators(tax_year))


def register_provincial_calculators(
    tax_year: int, calculators: Iterable[ProvincialCalculator]
) -> None:
    """Register additional calculators for a tax year (used by tests/extensions)."""
    bucket = _PROVINCE_CALCULATORS_BY_YEAR.setdefault(tax_year, {})
    for calc in calculators:
        if not calc.code:
            raise ValueError("ProvincialCalculator must have a code to register")
        bucket[calc.code] = calc
