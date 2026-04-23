"""TOML-backed loader for federal tax rules.

Design notes:

* All monetary and rate fields are accepted only as quoted strings. Bare TOML
  floats lose precision (``0.145`` does not round-trip through IEEE 754), and
  this module is the boundary that protects Decimal precision end-to-end.

* Each rule section must carry ``ita_section``, ``cra_guide_ref``, and
  ``effective_date``. Missing citations raise :class:`RuleSchemaError` at
  load time rather than silently producing an un-auditable rule.

* The top (open-ended) tax bracket is encoded by omitting ``upper``. The
  loader enforces that exactly the last tier is open-ended; all other tiers
  must carry an ``upper`` bound.

* The loader is pure: it reads a TOML file, validates structure, and returns
  frozen dataclasses. No I/O side effects, no caching. Callers that want
  module-level singletons should invoke ``load_federal_rules`` at import
  time (see ``app/core/tax_years/y2025/federal.py``).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


class RuleSchemaError(ValueError):
    """A TOML rule file is missing required fields, has the wrong shape, or uses
    an unsupported numeric form."""


@dataclass(frozen=True)
class RuleMeta:
    """Citation metadata attached to every rule section."""

    ita_section: str
    cra_guide_ref: str
    effective_date: str
    description: str = ""
    prior_year_value: str = ""


@dataclass(frozen=True)
class BracketTier:
    """One tier in a progressive bracket table. ``upper`` is ``None`` for the
    open-ended top tier."""

    lower: Decimal
    upper: Decimal | None
    rate: Decimal


@dataclass(frozen=True)
class Brackets:
    meta: RuleMeta
    tiers: tuple[BracketTier, ...]


@dataclass(frozen=True)
class BasicPersonalAmount:
    """Federal Basic Personal Amount with a linear phase-out from ``full`` at
    ``phase_start`` down to ``floor`` at ``phase_end``."""

    meta: RuleMeta
    full: Decimal
    floor: Decimal
    phase_start: Decimal
    phase_end: Decimal


@dataclass(frozen=True)
class NrtcRate:
    """Rate applied to the sum of non-refundable tax credit amounts."""

    meta: RuleMeta
    rate: Decimal


@dataclass(frozen=True)
class FederalRules:
    tax_year: int
    brackets: Brackets
    bpa: BasicPersonalAmount
    nrtc: NrtcRate


# ---------------------------------------------------------------------------
# Low-level accessors
# ---------------------------------------------------------------------------


def _require(section: dict[str, Any], key: str, path: str) -> Any:
    if key not in section:
        where = f"{path}.{key}" if path else key
        raise RuleSchemaError(f"Missing required key '{where}'")
    return section[key]


def _dec(section: dict[str, Any], key: str, path: str) -> Decimal:
    raw = _require(section, key, path)
    if not isinstance(raw, str):
        raise RuleSchemaError(
            f"Field '{path}.{key}' must be a quoted string to preserve precision, "
            f"got {type(raw).__name__}"
        )
    try:
        return Decimal(raw)
    except Exception as exc:  # noqa: BLE001 — re-raise as our own error
        raise RuleSchemaError(
            f"Field '{path}.{key}' is not a valid decimal: {raw!r}"
        ) from exc


def _opt_dec(section: dict[str, Any], key: str, path: str) -> Decimal | None:
    if key not in section:
        return None
    return _dec(section, key, path)


def _build_meta(section: dict[str, Any], path: str) -> RuleMeta:
    return RuleMeta(
        ita_section=_require(section, "ita_section", path),
        cra_guide_ref=_require(section, "cra_guide_ref", path),
        effective_date=_require(section, "effective_date", path),
        description=section.get("description", ""),
        prior_year_value=section.get("prior_year_value", ""),
    )


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_brackets(section: dict[str, Any]) -> Brackets:
    path = "brackets"
    meta = _build_meta(section, path)
    tiers_raw = _require(section, "tiers", path)
    if not isinstance(tiers_raw, list) or not tiers_raw:
        raise RuleSchemaError(f"'{path}.tiers' must be a non-empty array of tables")

    tiers: list[BracketTier] = []
    for i, tier in enumerate(tiers_raw):
        tier_path = f"{path}.tiers[{i}]"
        if not isinstance(tier, dict):
            raise RuleSchemaError(f"'{tier_path}' must be a table")
        tiers.append(
            BracketTier(
                lower=_dec(tier, "lower", tier_path),
                upper=_opt_dec(tier, "upper", tier_path),
                rate=_dec(tier, "rate", tier_path),
            )
        )

    # Structural invariants: only the last tier is open-ended; all others bounded.
    if tiers[-1].upper is not None:
        raise RuleSchemaError(
            f"Last bracket tier must be open-ended (omit 'upper'); "
            f"got upper={tiers[-1].upper}"
        )
    for i, t in enumerate(tiers[:-1]):
        if t.upper is None:
            raise RuleSchemaError(
                f"Non-final bracket tier at index {i} must specify 'upper'"
            )

    return Brackets(meta=meta, tiers=tuple(tiers))


def _build_bpa(section: dict[str, Any]) -> BasicPersonalAmount:
    path = "bpa"
    meta = _build_meta(section, path)
    return BasicPersonalAmount(
        meta=meta,
        full=_dec(section, "full", path),
        floor=_dec(section, "floor", path),
        phase_start=_dec(section, "phase_start", path),
        phase_end=_dec(section, "phase_end", path),
    )


def _build_nrtc(section: dict[str, Any]) -> NrtcRate:
    path = "nrtc"
    meta = _build_meta(section, path)
    return NrtcRate(meta=meta, rate=_dec(section, "rate", path))


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


# Repo root is four parents up from this file:
#   .../tax_rules
#   .../app/core/rules/loader.py  ->  parents[3] = repo root
DEFAULT_RULES_ROOT = Path(__file__).resolve().parents[3] / "tax_rules"


def load_federal_rules(tax_year: int, root: Path | None = None) -> FederalRules:
    """Load federal rules for ``tax_year`` from TOML.

    Args:
        tax_year: Tax year (e.g. ``2025``). Maps to ``tax_rules/y{tax_year}/federal.toml``.
        root: Optional override of the ``tax_rules/`` root. Defaults to the
            directory at the repo root. Useful for tests.

    Returns:
        A fully populated :class:`FederalRules` dataclass.

    Raises:
        FileNotFoundError: When the TOML file for the year does not exist.
        RuleSchemaError: When the TOML file is missing required fields, has
            a malformed structure, or uses a non-string numeric literal.
    """
    if root is None:
        root = DEFAULT_RULES_ROOT
    path = root / f"y{tax_year}" / "federal.toml"
    if not path.exists():
        raise FileNotFoundError(
            f"Federal rules for tax year {tax_year} not found at {path}"
        )
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    meta_section = data.get("meta", {})
    declared_year = meta_section.get("tax_year")
    if declared_year != tax_year:
        raise RuleSchemaError(
            f"TOML meta.tax_year = {declared_year!r} does not match requested {tax_year}"
        )

    brackets_section = _require(data, "brackets", "")
    bpa_section = _require(data, "bpa", "")
    nrtc_section = _require(data, "nrtc", "")

    return FederalRules(
        tax_year=tax_year,
        brackets=_build_brackets(brackets_section),
        bpa=_build_bpa(bpa_section),
        nrtc=_build_nrtc(nrtc_section),
    )
