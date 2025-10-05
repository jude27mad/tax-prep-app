from __future__ import annotations

from typing import Dict, List, Tuple

from app.tax.prov.base import ProvincialAdapter
from app.tax.prov.ab2025 import adapter as ab_2025
from app.tax.prov.bc2025 import adapter as bc_2025
from app.tax.prov.mb2025 import adapter as mb_2025
from app.tax.prov.nb2025 import adapter as nb_2025
from app.tax.prov.nl2025 import adapter as nl_2025
from app.tax.prov.ns2025 import adapter as ns_2025
from app.tax.prov.nt2025 import adapter as nt_2025
from app.tax.prov.nu2025 import adapter as nu_2025
from app.tax.prov.on2025 import adapter as on_2025
from app.tax.prov.pe2025 import adapter as pe_2025
from app.tax.prov.sk2025 import adapter as sk_2025
from app.tax.prov.yt2025 import adapter as yt_2025

_REGISTRY: Dict[Tuple[str, str], ProvincialAdapter] = {}


def register_provincial_adapters(year: int | str, adapters: Iterable[ProvincialAdapter]) -> None:
    year_key = str(year)
    for adapter in adapters:
        key = (year_key, adapter.code)
        _REGISTRY[key] = adapter


# 2025 production adapters (default year)
register_provincial_adapters(
    2025,
    (
        on_2025,
        bc_2025,
        ab_2025,
        mb_2025,
        sk_2025,
        ns_2025,
        nb_2025,
        nl_2025,
        pe_2025,
        yt_2025,
        nt_2025,
        nu_2025,
    ),
)


# Placeholder for next filing season; populate once 2026 adapters land.
NEXT_TAX_YEAR = 2026


class UnknownProvinceError(KeyError):
    pass


def get_provincial_adapter(year: int | str, province: str) -> ProvincialAdapter:
    key = (str(year), province.upper())
    try:
        return _REGISTRY[key]
    except KeyError as exc:  # pragma: no cover - surfaced to caller
        raise UnknownProvinceError(f"No provincial adapter registered for {key[1]} in {key[0]}") from exc


def list_provincial_adapters(year: int | str | None = None) -> List[ProvincialAdapter]:
    target_year = str(year) if year is not None else _YEAR
    seen: set[str] = set()
    adapters: List[ProvincialAdapter] = []
    for (registered_year, code), adapter in _REGISTRY.items():
        if registered_year != target_year:
            continue
        if code in seen:
            continue
        adapters.append(adapter)
        seen.add(code)
    return adapters

def list_supported_provinces(year: int | str | None = None) -> list[str]:
    # reuse the adapters list to keep de-dupe logic consistent
    return sorted(a.code for a in list_provincial_adapters(year))
  