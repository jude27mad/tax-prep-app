from __future__ import annotations

from typing import Dict, Tuple

from app.tax.prov.ab2025 import adapter as ab_2025
from app.tax.prov.bc2025 import adapter as bc_2025
from app.tax.prov.mb2025 import adapter as mb_2025
from app.tax.prov.on2025 import adapter as on_2025
from app.tax.prov.sk2025 import adapter as sk_2025
from app.tax.prov.ns2025 import adapter as ns_2025
from app.tax.prov.nb2025 import adapter as nb_2025
from app.tax.prov.nl2025 import adapter as nl_2025
from app.tax.prov.pe2025 import adapter as pe_2025
from app.tax.prov.yt2025 import adapter as yt_2025
from app.tax.prov.nt2025 import adapter as nt_2025
from app.tax.prov.nu2025 import adapter as nu_2025
from app.tax.prov.base import ProvincialAdapter

_YEAR = "2025"
_REGISTRY: Dict[Tuple[str, str], ProvincialAdapter] = {
    (_YEAR, "ON"): on_2025,
    (_YEAR, "BC"): bc_2025,
    (_YEAR, "AB"): ab_2025,
    (_YEAR, "MB"): mb_2025,
    (_YEAR, "SK"): sk_2025,
    (_YEAR, "NS"): ns_2025,
    (_YEAR, "NB"): nb_2025,
    (_YEAR, "NL"): nl_2025,
    (_YEAR, "PE"): pe_2025,
    (_YEAR, "YT"): yt_2025,
    (_YEAR, "NT"): nt_2025,
    (_YEAR, "NU"): nu_2025,
}


class UnknownProvinceError(KeyError):
    pass


def get_provincial_adapter(year: int | str, province: str) -> ProvincialAdapter:
    key = (str(year), province.upper())
    try:
        return _REGISTRY[key]
    except KeyError as exc:  # pragma: no cover - surfaced to caller
        raise UnknownProvinceError(f"No provincial adapter registered for {key[1]} in {key[0]}") from exc
