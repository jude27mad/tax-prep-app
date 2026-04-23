"""Tests for the rules-as-data loader.

Covers:
  * Happy-path load for both supported tax years.
  * Citation metadata presence on every section.
  * Module-level constants in ``app.core.tax_years.y{2024,2025}.federal``
    match the loader output (no drift after refactor).
  * Schema validation: missing required fields, tax-year mismatch, missing
    file, non-string numeric literals, and bracket tier structure.
  * Numeric precision preservation through the string -> Decimal boundary.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.core.rules import (
    RuleSchemaError,
    load_federal_rules,
)
from app.core.tax_years.y2024.federal import (
    BPA_FLOOR_2024,
    BPA_FULL_2024,
    BPA_PHASE_END,
    BPA_PHASE_START,
    BRACKETS_2024,
    NRTC_RATE,
)
from app.core.tax_years.y2025.federal import (
    BPA_FLOOR_2025,
    BPA_FULL_2025,
    BPA_PHASE_END_2025,
    BPA_PHASE_START_2025,
    BRACKETS_2025,
    NRTC_RATE_2025,
)

D = Decimal


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_load_federal_rules_2025_shape():
    rules = load_federal_rules(2025)
    assert rules.tax_year == 2025
    assert len(rules.brackets.tiers) == 5
    assert rules.brackets.tiers[0].lower == D("0")
    assert rules.brackets.tiers[0].upper == D("57375")
    assert rules.brackets.tiers[0].rate == D("0.145")
    assert rules.brackets.tiers[-1].upper is None  # open-ended top tier
    assert rules.brackets.tiers[-1].rate == D("0.33")
    assert rules.bpa.full == D("16129")
    assert rules.bpa.floor == D("14538")
    assert rules.bpa.phase_start == D("177882")
    assert rules.bpa.phase_end == D("253414")
    assert rules.nrtc.rate == D("0.145")


def test_load_federal_rules_2024_shape():
    rules = load_federal_rules(2024)
    assert rules.tax_year == 2024
    assert len(rules.brackets.tiers) == 5
    assert rules.brackets.tiers[0].rate == D("0.15")
    assert rules.brackets.tiers[-1].upper is None
    assert rules.bpa.full == D("15705")
    assert rules.bpa.floor == D("14156")
    assert rules.bpa.phase_start == D("173205")
    assert rules.bpa.phase_end == D("246752")
    assert rules.nrtc.rate == D("0.15")


# ---------------------------------------------------------------------------
# Citation metadata — every section must carry the three required fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("year", [2024, 2025])
def test_citation_metadata_present(year):
    rules = load_federal_rules(year)
    for meta in (rules.brackets.meta, rules.bpa.meta, rules.nrtc.meta):
        assert meta.ita_section, f"missing ita_section for {year}"
        assert meta.cra_guide_ref, f"missing cra_guide_ref for {year}"
        assert meta.effective_date, f"missing effective_date for {year}"
    # 2025 specifically references ITA s.117(2) for brackets, s.118(1)(c) for BPA
    if year == 2025:
        assert "117" in rules.brackets.meta.ita_section
        assert "118" in rules.bpa.meta.ita_section


# ---------------------------------------------------------------------------
# No drift between loader output and the year modules that call it
# ---------------------------------------------------------------------------


def test_year_module_constants_match_loader_2025():
    rules = load_federal_rules(2025)
    assert BRACKETS_2025 == [(t.lower, t.upper, t.rate) for t in rules.brackets.tiers]
    assert BPA_FULL_2025 == rules.bpa.full
    assert BPA_FLOOR_2025 == rules.bpa.floor
    assert BPA_PHASE_START_2025 == rules.bpa.phase_start
    assert BPA_PHASE_END_2025 == rules.bpa.phase_end
    assert NRTC_RATE_2025 == rules.nrtc.rate


def test_year_module_constants_match_loader_2024():
    rules = load_federal_rules(2024)
    assert BRACKETS_2024 == [(t.lower, t.upper, t.rate) for t in rules.brackets.tiers]
    assert BPA_FULL_2024 == rules.bpa.full
    assert BPA_FLOOR_2024 == rules.bpa.floor
    assert BPA_PHASE_START == rules.bpa.phase_start
    assert BPA_PHASE_END == rules.bpa.phase_end
    assert NRTC_RATE == rules.nrtc.rate


# ---------------------------------------------------------------------------
# Precision — the string -> Decimal boundary must not lose digits
# ---------------------------------------------------------------------------


_VALID_TEMPLATE = """
[meta]
tax_year = {year}

[brackets]
ita_section = "s.117(2)"
cra_guide_ref = "Test"
effective_date = "{year}-01-01"

[[brackets.tiers]]
lower = "0"
upper = "50000"
rate = "0.12345"

[[brackets.tiers]]
lower = "50000"
rate = "0.98765"

[bpa]
ita_section = "s.118(1)(c)"
cra_guide_ref = "Test"
effective_date = "{year}-01-01"
full = "10000.00"
floor = "5000.00"
phase_start = "100000"
phase_end = "200000"

[nrtc]
ita_section = "s.117.1"
cra_guide_ref = "Test"
effective_date = "{year}-01-01"
rate = "0.1234567890"
"""


def _write_rules(tmp_path: Path, year: int, body: str) -> Path:
    root = tmp_path / "tax_rules"
    (root / f"y{year}").mkdir(parents=True)
    (root / f"y{year}" / "federal.toml").write_text(body)
    return root


def test_decimal_precision_preserved(tmp_path):
    root = _write_rules(tmp_path, 9999, _VALID_TEMPLATE.format(year=9999))
    rules = load_federal_rules(9999, root=root)
    assert rules.brackets.tiers[0].rate == D("0.12345")
    assert rules.brackets.tiers[1].rate == D("0.98765")
    assert rules.nrtc.rate == D("0.1234567890")
    # Trailing zeros survive — proves we never round-tripped through float.
    assert str(rules.bpa.full) == "10000.00"


# ---------------------------------------------------------------------------
# Schema errors
# ---------------------------------------------------------------------------


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_federal_rules(1900, root=tmp_path / "tax_rules")


def test_tax_year_mismatch_raises(tmp_path):
    root = _write_rules(tmp_path, 2000, _VALID_TEMPLATE.format(year=2001))
    with pytest.raises(RuleSchemaError, match="tax_year"):
        load_federal_rules(2000, root=root)


def test_missing_required_citation_field_raises(tmp_path):
    body = _VALID_TEMPLATE.format(year=2000).replace(
        'ita_section = "s.117(2)"', "", 1
    )
    root = _write_rules(tmp_path, 2000, body)
    with pytest.raises(RuleSchemaError, match="ita_section"):
        load_federal_rules(2000, root=root)


def test_bare_float_rate_rejected(tmp_path):
    # TOML `rate = 0.15` is parsed as a Python float and loses precision.
    # The loader must reject it in favour of quoted strings.
    body = _VALID_TEMPLATE.format(year=2000).replace('rate = "0.12345"', "rate = 0.12345")
    root = _write_rules(tmp_path, 2000, body)
    with pytest.raises(RuleSchemaError, match="quoted string"):
        load_federal_rules(2000, root=root)


def test_bare_int_dollar_rejected(tmp_path):
    body = _VALID_TEMPLATE.format(year=2000).replace('full = "10000.00"', "full = 10000")
    root = _write_rules(tmp_path, 2000, body)
    with pytest.raises(RuleSchemaError, match="quoted string"):
        load_federal_rules(2000, root=root)


def test_last_tier_must_be_open_ended(tmp_path):
    body = _VALID_TEMPLATE.format(year=2000).replace(
        'lower = "50000"\nrate = "0.98765"',
        'lower = "50000"\nupper = "100000"\nrate = "0.98765"',
    )
    root = _write_rules(tmp_path, 2000, body)
    with pytest.raises(RuleSchemaError, match="open-ended"):
        load_federal_rules(2000, root=root)


def test_non_final_tier_missing_upper_rejected(tmp_path):
    body = _VALID_TEMPLATE.format(year=2000).replace(
        'lower = "0"\nupper = "50000"\nrate = "0.12345"',
        'lower = "0"\nrate = "0.12345"',
    )
    root = _write_rules(tmp_path, 2000, body)
    with pytest.raises(RuleSchemaError, match="must specify 'upper'"):
        load_federal_rules(2000, root=root)


def test_empty_tiers_rejected(tmp_path):
    # Drop both tiers and leave the rest intact.
    body = _VALID_TEMPLATE.format(year=2000)
    # Blank out the entire tiers block by replacing the [[brackets.tiers]] section.
    lines = body.splitlines()
    filtered = []
    skip = False
    for line in lines:
        if line.startswith("[[brackets.tiers]]"):
            skip = True
            continue
        if skip and line.startswith("[") and not line.startswith("[["):
            skip = False
        if not skip:
            filtered.append(line)
    root = _write_rules(tmp_path, 2000, "\n".join(filtered))
    with pytest.raises(RuleSchemaError, match="tiers"):
        load_federal_rules(2000, root=root)


def test_invalid_decimal_string_rejected(tmp_path):
    body = _VALID_TEMPLATE.format(year=2000).replace(
        'rate = "0.12345"', 'rate = "not-a-number"'
    )
    root = _write_rules(tmp_path, 2000, body)
    with pytest.raises(RuleSchemaError, match="valid decimal"):
        load_federal_rules(2000, root=root)


# ---------------------------------------------------------------------------
# Computed behavior — the loader-backed federal functions produce the same
# numbers as the prior hardcoded path (regression lock).
# ---------------------------------------------------------------------------


def test_federal_tax_2025_known_boundary():
    from app.core.tax_years.y2025.federal import federal_tax_2025

    # 57,375 is the first-bracket edge; 57,375 * 0.145 = 8319.375 -> 8319.38
    assert federal_tax_2025(D("57375")) == D("8319.38")


def test_federal_tax_2024_known_boundary():
    from app.core.tax_years.y2024.federal import federal_tax_2024

    # 55,867 is the first-bracket edge; 55,867 * 0.15 = 8380.05
    assert federal_tax_2024(D("55867")) == D("8380.05")
