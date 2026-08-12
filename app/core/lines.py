"""T1 line architecture — the structure of a return, shared across tax years.

The *structure* of a T1 is stable across years and provinces:

    total income (15000)
      − deductions                → net income (23600)
      − further deductions        → taxable income (26000)
      → tax, credits, withholding → refund or balance owing

Only the rates and thresholds are year-specific, and those live in ``tax_rules/``
and the per-year modules under :mod:`app.core.tax_years`. Keeping the structure
here is what stops tax years from drifting apart on what a "line" *means* — the
2024 and 2025 handlers previously duplicated this arithmetic and made the same
mistake in both places (see :func:`compute_income_lines`).

Two distinctions this module exists to enforce:

**Net income is not total income.** Net income (23600) is total income minus
Division B deductions such as RRSP contributions. It drives income-tested
amounts — the Basic Personal Amount phase-out, credit thresholds, clawbacks — so
passing total income where net income is expected silently overstates tax for
anyone with deductions. Both year handlers did exactly that.

**Net income is not taxable income either.** Taxable income (26000) is net income
minus Division C deductions. With only RRSP deductions modelled the two are
numerically equal today, but they are different lines with different consumers,
and they diverge as soon as a Division C deduction lands (for example the line
25000 social-assistance offset). Collapsing them now would mean reworking every
downstream consumer later.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

D = Decimal

# Canonical ``ReturnCalc.line_items`` keys mapped to their CRA T1 line numbers.
# The explanation engine cites these, so the mapping belongs with the structure
# rather than in a presentation layer. Keys are stable contract names: the two
# legacy spellings (``income_total`` rather than ``total_income``, ``prov_tax``
# rather than ``provincial_tax``) are kept deliberately because the printout,
# EFILE serializer, and existing fixtures already serialize against them.
CRA_LINE_NUMBERS: dict[str, str] = {
    "income_total": "15000",
    "total_deductions": "23300",
    "net_income": "23600",
    # Line 25000, "Other payments deduction": today the sole Division C
    # deduction this field carries is the T5007 workers' compensation/social
    # assistance offset (see app.core.slips.sum_t5007_offset). If a second
    # Division C deduction is ever modelled, this single field/line pairing
    # will need to split.
    "division_c_deductions": "25000",
    "taxable_income": "26000",
    "federal_tax": "42000",
    "prov_tax": "42800",
    # Total income tax deducted at source (T4/T4A box 22). Single line
    # regardless of sign, unlike the refund/balance-owing pair below.
    "withholding": "43700",
}

# Refund vs. balance owing aren't a single CRA line: which one applies depends
# on the sign of ``ReturnCalc.totals["balance"]`` (positive = balance owing,
# line 48500; negative = refund, line 48400). That duality doesn't fit
# CRA_LINE_NUMBERS's one-key-one-line shape, so it's recorded here instead.
BALANCE_OWING_LINE_NUMBER = "48500"
REFUND_LINE_NUMBER = "48400"


@dataclass(frozen=True)
class IncomeLines:
    """The income section of a return, with each line kept distinct.

    ``total_deductions`` covers the Division B deductions that bridge total
    income to net income. ``division_c_deductions`` bridges net income to
    taxable income; it is zero until such a deduction is modelled, but it is
    represented explicitly so the bridge is visible rather than implied.
    """

    total_income: D
    total_deductions: D
    net_income: D
    division_c_deductions: D
    taxable_income: D

    def as_line_items(self) -> dict[str, D]:
        """The income lines as ``ReturnCalc.line_items`` entries."""
        return {
            "income_total": self.total_income,
            "total_deductions": self.total_deductions,
            "net_income": self.net_income,
            "division_c_deductions": self.division_c_deductions,
            "taxable_income": self.taxable_income,
        }


def compute_income_lines(
    total_income: D,
    division_b_deductions: D,
    division_c_deductions: D = D("0.00"),
) -> IncomeLines:
    """Bridge total income to taxable income through net income.

    Both intermediate lines are floored at zero: a deduction larger than income
    cannot produce negative net or taxable income, and letting it do so would
    feed a negative figure into the bracket and phase-out arithmetic.

    No tax math happens here — this is the structural bridge only. Callers pass
    :attr:`IncomeLines.net_income` to income-tested calculations and
    :attr:`IncomeLines.taxable_income` to the bracket calculation. Passing the
    wrong one is the bug this module exists to prevent.
    """
    net_income = max(D("0.00"), total_income - division_b_deductions)
    taxable_income = max(D("0.00"), net_income - division_c_deductions)
    return IncomeLines(
        total_income=total_income,
        total_deductions=division_b_deductions,
        net_income=net_income,
        division_c_deductions=division_c_deductions,
        taxable_income=taxable_income,
    )


__all__ = [
    "BALANCE_OWING_LINE_NUMBER",
    "CRA_LINE_NUMBERS",
    "IncomeLines",
    "REFUND_LINE_NUMBER",
    "compute_income_lines",
]
