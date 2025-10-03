from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from app.tax.ca2025 import Bracket, tax_from_brackets


@dataclass(frozen=True)
class ProvincialResult:
    province_code: str
    province_name: str
    before_credits: float
    bpa_used: float
    credit_rate: float
    after_credits: float
    additions: Dict[str, float]
    net_tax: float


@dataclass(frozen=True)
class ProvincialAdapter:
    code: str
    name: str
    brackets: tuple[Bracket, ...]
    credit_rate: float
    bpa_fn: Callable[[float], float]
    additions_fn: Callable[[float, float], Dict[str, float]]

    def compute(self, taxable: float) -> ProvincialResult:
        before = tax_from_brackets(taxable, self.brackets)
        bpa_available = self.bpa_fn(taxable)
        bpa_used = min(bpa_available, taxable)
        after = max(0.0, round(before - self.credit_rate * bpa_used, 2))
        additions = self.additions_fn(taxable, after)
        net = round(after + sum(additions.values()), 2)
        return ProvincialResult(
            province_code=self.code,
            province_name=self.name,
            before_credits=before,
            bpa_used=bpa_used,
            credit_rate=self.credit_rate,
            after_credits=after,
            additions=additions,
            net_tax=net,
        )


def basic_personal_amount(value: float) -> Callable[[float], float]:
    return lambda _taxable: value


def no_additions(_: float, __: float) -> Dict[str, float]:
    return {}
