from __future__ import annotations

from importlib import import_module
from pathlib import Path
import re
from functools import lru_cache
from typing import Callable, Mapping, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from app.core.models import ReturnCalc, ReturnInput


_ALIAS_PATTERN = re.compile(r"_(\d{4})_alias\.py$")


def _package_path() -> Path:
    return Path(__file__).resolve().parent


def _load_compute_functions() -> Mapping[int, Callable[["ReturnInput"], "ReturnCalc"]]:
    mapping: dict[int, Callable[["ReturnInput"], "ReturnCalc"]] = {}
    base = _package_path()
    for module_path in base.glob("_20??_alias.py"):
        match = _ALIAS_PATTERN.match(module_path.name)
        if not match:
            continue
        year = int(match.group(1))
        module = import_module(f"{__name__}.{module_path.stem}")
        compute = getattr(module, "compute_return", None)
        if compute is None:
            continue
        mapping[year] = compute
    return mapping


@lru_cache(maxsize=1)
def _compute_map() -> Mapping[int, Callable[["ReturnInput"], "ReturnCalc"]]:
    return _load_compute_functions()


SUPPORTED_YEARS: tuple[int, ...] = tuple(sorted(_compute_map().keys()))


def get_compute_handler(year: int) -> Callable[["ReturnInput"], "ReturnCalc"]:
    try:
        return _compute_map()[year]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported tax year {year}") from exc


def compute_for_year(req: "ReturnInput") -> "ReturnCalc":
    handler = get_compute_handler(req.tax_year)
    return handler(req)


__all__ = ["SUPPORTED_YEARS", "get_compute_handler", "compute_for_year"]
