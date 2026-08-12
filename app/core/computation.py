"""The single deterministic tax computation result, shared by every surface.

Plan V3 (``docs/plan_v3.md`` §3) requires one authoritative calculation path.
This module holds the shape that path produces, so the arithmetic exists exactly
once and each surface only *adapts* it:

* :func:`app.core.tax_years.y2025.calc.compute_return` maps it to
  :class:`~app.core.models.ReturnCalc` for the filing flow.
* :func:`app.wizard.estimator.compute_tax_summary` maps it to the estimator's
  JSON-friendly dict for ``/tax/estimate``, ``/t4/estimate``, and the CLI
  preview.

Before this existed, the estimator re-assembled federal tax, provincial tax,
credits, and additions itself. The two implementations drifted: ``compute_return``
passed *total* income to the Basic Personal Amount phase-out while the estimator
passed *taxable* income, so they disagreed for anyone with deductions. Adapters
can differ; arithmetic cannot.

:class:`TaxComputation` carries the amounts a return produces *including* the
credit and after-credit figures. ``compute_return`` previously dropped those on
the floor — ``ReturnCalc`` exposed only pre-credit federal and provincial tax —
which is why the estimator had to recompute them and why nothing downstream could
reconcile net tax against its components.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from app.core.lines import IncomeLines

D = Decimal


@dataclass(frozen=True)
class TaxComputation:
    """Every deterministic amount a computed return yields.

    Field names are the contract surfaces adapt from. The pre-credit /
    after-credit distinction is explicit throughout because conflating them is
    how the previous duplication went unnoticed: ``line_items["federal_tax"]``
    has always been the *pre-credit* basic federal tax, which reads like net
    federal tax and is not.
    """

    tax_year: int
    province: str

    lines: IncomeLines

    # Federal. federal_tax is basic federal tax before credits (line 40400);
    # net_federal_tax is after credits (line 42000).
    federal_bpa: D
    federal_tax: D
    federal_credits: D
    net_federal_tax: D

    # Provincial. provincial_tax/provincial_credits are internals of the
    # provincial 428 form. net_provincial_tax is the amount that reaches the T1
    # (line 42800) and therefore includes provincial additions.
    provincial_bpa: D
    provincial_tax: D
    provincial_credits: D
    provincial_additions: Mapping[str, D]
    net_provincial_tax: D

    # Bottom line. net_tax is total payable (line 43500); withholding is tax
    # deducted at source (line 43700); balance is signed -- positive is balance
    # owing (line 48500), negative is a refund (line 48400).
    net_tax: D
    withholding: D
    balance: D

    @property
    def provincial_additions_total(self) -> D:
        return sum(self.provincial_additions.values(), D("0.00"))

    def as_line_items(self) -> dict[str, D]:
        """The T1/428 lines this computation produced.

        Feeds ``ReturnCalc.line_items``. Provincial additions are deliberately
        excluded — they live in their own ``ReturnCalc`` field so consumers never
        have to guess which keys are additions (see
        :class:`~app.core.models.ReturnCalc`).
        """
        return {
            **self.lines.as_line_items(),
            "federal_bpa": self.federal_bpa,
            "federal_tax": self.federal_tax,
            "federal_credits": self.federal_credits,
            "net_federal_tax": self.net_federal_tax,
            "prov_bpa": self.provincial_bpa,
            "prov_tax": self.provincial_tax,
            "prov_credits": self.provincial_credits,
            "net_prov_tax": self.net_provincial_tax,
        }

    def as_totals(self) -> dict[str, D]:
        """The bottom-line figures, for ``ReturnCalc.totals``."""
        return {
            "net_tax": self.net_tax,
            "withholding": self.withholding,
            "balance": self.balance,
        }

    def reconciles(self) -> bool:
        """Whether net tax equals the sum of its components.

        A deterministic self-check, not tax math: net federal tax plus net
        provincial tax (which already includes additions) must equal total
        payable. Surfaces and tests assert this so a future change that adds a
        component without folding it into ``net_tax`` fails loudly instead of
        producing a total that silently disagrees with its own breakdown.
        """
        return self.net_federal_tax + self.net_provincial_tax == self.net_tax


__all__ = ["TaxComputation"]
