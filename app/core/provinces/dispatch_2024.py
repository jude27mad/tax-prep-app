from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Dict, Tuple

_PROVINCE_MODULES: Tuple[Tuple[str, str], ...] = (
    ("ON", "on"),
    ("SK", "sk"),
    ("NS", "ns"),
    ("NB", "nb"),
    ("NL", "nl"),
    ("PE", "pe"),
    ("YT", "yt"),
    ("NT", "nt"),
    ("NU", "nu"),
)

CALC_2024: Dict[str, ModuleType] = {
    code: import_module(f"app.core.provinces.{module}") for code, module in _PROVINCE_MODULES
}

__all__ = ["CALC_2024"]
