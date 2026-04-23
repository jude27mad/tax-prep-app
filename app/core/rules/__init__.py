"""Rules-as-data loader.

This package hydrates typed, citation-tagged rule objects (tax brackets,
credits, thresholds) from TOML files under the top-level ``tax_rules/``
directory. The goal per strategy D1.2 / E6 is to remove hardcoded Python
literals for tax rates and replace them with versioned data that carries
its own ITA / CRA guide citations.

Phase 1 scope: federal brackets, BPA (including phase-out), NRTC rate for
tax years 2024 and 2025. Provincial rules, payroll limits, and surtax/OHP
tables remain hardcoded pending the D2.3 migration pass.
"""

from app.core.rules.loader import (
    BasicPersonalAmount,
    BracketTier,
    Brackets,
    FederalRules,
    NrtcRate,
    RuleMeta,
    RuleSchemaError,
    load_federal_rules,
)

__all__ = [
    "BasicPersonalAmount",
    "BracketTier",
    "Brackets",
    "FederalRules",
    "NrtcRate",
    "RuleMeta",
    "RuleSchemaError",
    "load_federal_rules",
]
