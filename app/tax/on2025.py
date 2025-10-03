from __future__ import annotations

from typing import Tuple

from app.tax.ca2025 import Bracket, tax_from_brackets as _tax_from_brackets
from app.tax.prov.on2025 import (
    ONTARIO_2025,
    ON_BPA_2025,
    ON_CREDIT_RATE,
    adapter,
    health_premium_2025,
    surtax_2025,
)


def tax_from_brackets(taxable: float, brackets: Tuple[Bracket, ...] = ONTARIO_2025) -> float:
    return _tax_from_brackets(taxable, brackets)


__all__ = [
    "ONTARIO_2025",
    "ON_BPA_2025",
    "ON_CREDIT_RATE",
    "adapter",
    "tax_from_brackets",
    "health_premium_2025",
    "surtax_2025",
]
