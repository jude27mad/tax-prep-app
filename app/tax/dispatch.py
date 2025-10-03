from __future__ import annotations

from typing import Dict, Tuple

from app.tax.prov.ab2025 import adapter as ab_2025
from app.tax.prov.bc2025 import adapter as bc_2025
from app.tax.prov.mb2025 import adapter as mb_2025
from app.tax.prov.on2025 import adapter as on_2025
from app.tax.prov.base import ProvincialAdapter

_YEAR = "2025"
_REGISTRY: Dict[Tuple[str, str], ProvincialAdapter] = {
    (_YEAR, "ON"): on_2025,
    (_YEAR, "BC"): bc_2025,
    (_YEAR, "AB"): ab_2025,
    (_YEAR, "MB"): mb_2025,
}


class UnknownProvinceError(KeyError):
    pass


def get_provincial_adapter(year: int | str, province: str) -> ProvincialAdapter:
    key = (str(year), province.upper())
    try:
        return _REGISTRY[key]
    except KeyError as exc:  # pragma: no cover - surfaced to caller
        raise UnknownProvinceError(f"No provincial adapter registered for {key[1]} in {key[0]}") from exc
