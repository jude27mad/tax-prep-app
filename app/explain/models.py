"""Plan V3 Phase 2 — deterministic explanation contracts.

These models describe *what the deterministic tax engine already produced*:
a computed line/total, the source/evidence that supports it, and how the
user can verify it afterward. They are pure data contracts — assembling
them from a real :class:`~app.core.models.ReturnCalc` is the job of the
Phase 3 explanation engine, not this module.

Hard boundaries (Plan V3 docs §3/§5; execution roadmap §2):

* **No tax math here.** Nothing in this module computes a return. The
  models only *carry* numbers the engine emitted (``ReturnCalc.line_items``,
  ``totals``, ``cpp``, ``ei``). This guarantees there is never a second,
  divergent calculation path.
* **No AI-provider dependency.** Pure pydantic + stdlib, so the contract is
  fully usable when TeeFoor is disabled, unavailable, or inappropriate for
  the request.
* **Stable field names.** Every surface (web, mobile, CLI, API, TeeFoor) and
  the future source/proof ledger and evidence packs serialize against these
  names. Treat renames as breaking changes. ``extra="forbid"`` keeps the
  contract tight so a typo'd field is rejected rather than silently dropped.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# What kind of source backs an explained quantity. Kept symbolic (an
# identifier, not raw private data) so explanations can cite provenance
# without leaking SINs, slip amounts, or document contents. The ledger
# (roadmap §8) and evidence pack (§11) resolve these refs to richer,
# access-controlled records later.
EvidenceKind = Literal[
    "rule",  # a tax_rules/ citation or rule id from app.core.rules
    "input",  # a value the user supplied (ReturnInput field)
    "slip",  # a source slip (T4/T4A/T5/tuition/RRSP)
    "document",  # an uploaded/staged document, referenced by masked id
    "calculation",  # another deterministic line/total this one derives from
    "withholding",  # tax already deducted at source (refund/balance inputs)
]


class EvidenceRef(BaseModel):
    """A pointer to the source/evidence that supports an explanation.

    ``ref`` is a stable, symbolic identifier — a rule id, a line-item key,
    a slip kind, or a masked document handle — never a raw private value.
    """

    model_config = ConfigDict(extra="forbid")

    kind: EvidenceKind
    ref: str = Field(min_length=1)
    label: str | None = None
    detail: str | None = None


class VerificationStep(BaseModel):
    """How the user can confirm an explained outcome is what they expected.

    Plan V3's Guided Confidence doctrine (docs §4) says the product should
    answer "how do I verify this afterward?" with a concrete check, not
    vague homework. Each step names what to look at and, where useful, the
    surface to look on and the value to expect.
    """

    model_config = ConfigDict(extra="forbid")

    check: str = Field(min_length=1)
    surface: str | None = None  # e.g. "cli", "web", "printout", "cra_notice"
    expected: str | None = None


class ExplanationItem(BaseModel):
    """One explained quantity or step from the deterministic engine.

    ``id`` mirrors the engine's own key where one exists (``income_total``,
    ``taxable_income``, ``federal_tax``, ``net_tax``, …) so explanations,
    confidence primitives, and the refund waterfall all line up against the
    same stable names. ``depends_on`` records which other items feed this
    one — the seam the Phase 7 refund waterfall composes against.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    amount: Decimal | None = None
    depends_on: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    verification: list[VerificationStep] = Field(default_factory=list)


class ReturnExplanation(BaseModel):
    """A deterministic explanation of a single computed return.

    Holds the explained items in a stable, caller-defined order (income
    before taxable income before tax, etc.). This is the contract the
    Phase 3 engine populates from a :class:`~app.core.models.ReturnCalc`
    and that web/CLI/API/TeeFoor surfaces render.
    """

    model_config = ConfigDict(extra="forbid")

    tax_year: int
    province: str = Field(min_length=1)
    items: list[ExplanationItem] = Field(default_factory=list)

    def item_ids(self) -> list[str]:
        """Item ids in declaration order."""
        return [item.id for item in self.items]

    def get(self, item_id: str) -> ExplanationItem | None:
        """Return the item with ``item_id`` or ``None`` if absent."""
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def missing_dependencies(self) -> set[str]:
        """Ids referenced via ``depends_on`` that aren't present as items.

        A deterministic integrity check (no tax math): an empty set means
        every dependency resolves within this explanation, which the
        waterfall and ledger rely on. Surfacing the gap here keeps later
        phases from rendering dangling references.
        """
        present = set(self.item_ids())
        referenced: set[str] = set()
        for item in self.items:
            referenced.update(item.depends_on)
        return referenced - present


__all__ = [
    "EvidenceKind",
    "EvidenceRef",
    "ExplanationItem",
    "ReturnExplanation",
    "VerificationStep",
]
