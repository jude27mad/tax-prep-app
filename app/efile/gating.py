from __future__ import annotations

from typing import Mapping

from app.config import Settings, get_settings
from app.core.tax_years import SUPPORTED_YEARS

CRA_EFILE_INITIAL_YEARS: frozenset[int] = frozenset(range(2017, 2025))
CRA_REFILING_YEARS: frozenset[int] = frozenset(range(2021, 2025))


def _cra_active_years() -> set[int]:
    return set(CRA_EFILE_INITIAL_YEARS) | set(CRA_REFILING_YEARS)


def transmit_restriction(
    year: int,
    *,
    settings: Settings | None = None,
) -> str | None:
    if year not in SUPPORTED_YEARS:
        return f"Tax year {year} is not supported for this deployment."
    resolved = settings or get_settings()
    if year == 2025 and not resolved.feature_2025_transmit:
        return (
            f"EFILE transmission for tax year {year} is not yet available. "
            "Prepare estimates only."
        )
    if year not in _cra_active_years():
        return (
            f"EFILE transmission for tax year {year} is outside the CRA window. "
            "Prepare estimates only."
        )
    return None


def can_transmit(year: int, *, settings: Settings | None = None) -> bool:
    return transmit_restriction(year, settings=settings) is None


def build_transmit_gate(*, settings: Settings | None = None) -> Mapping[str, dict[str, object]]:
    resolved = settings or get_settings()
    gate: dict[str, dict[str, object]] = {}
    for year in SUPPORTED_YEARS:
        reason = transmit_restriction(year, settings=resolved)
        gate[str(year)] = {
            "allowed": reason is None,
            "message": reason or "",
        }
    return gate


__all__ = [
    "CRA_EFILE_INITIAL_YEARS",
    "CRA_REFILING_YEARS",
    "build_transmit_gate",
    "can_transmit",
    "transmit_restriction",
]
