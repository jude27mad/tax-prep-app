from decimal import Decimal as D

import pytest

from app.core.models import RRSPReceipt
from app.core.provinces import get_provincial_calculator
from app.core.provinces.ab import ab_credits_2025, ab_tax_on_taxable_income_2025
from app.core.provinces.bc import bc_credits_2025, bc_tax_on_taxable_income_2025
from app.core.provinces.mb import mb_credits_2025, mb_tax_on_taxable_income_2025
from app.core.provinces.nb import nb_credits_2025, nb_tax_on_taxable_income_2025
from app.core.provinces.nl import nl_credits_2025, nl_tax_on_taxable_income_2025
from app.core.provinces.ns import ns_credits_2025, ns_tax_on_taxable_income_2025
from app.core.provinces.nt import nt_credits_2025, nt_tax_on_taxable_income_2025
from app.core.provinces.nu import nu_credits_2025, nu_tax_on_taxable_income_2025
from app.core.provinces.on import on_surtax_2025
from app.core.provinces.pe import pe_credits_2025, pe_tax_on_taxable_income_2025
from app.core.provinces.sk import sk_credits_2025, sk_tax_on_taxable_income_2025
from app.core.provinces.yt import yt_credits_2025, yt_tax_on_taxable_income_2025
from app.core.slips import sum_rrsp_contributions, sum_t4a_income, sum_t5_income
from app.core.tax_years.y2025.calc import compute_full_2025
from tests.fixtures.min_client import make_min_input, make_provincial_examples


def test_federal_first_bracket_math_blended():
    r = compute_full_2025(D("57000"), D("57000"))
    assert r.federal_tax > D("0")
    assert r.federal_credits > D("0")


def test_on_surtax_thresholds_2025():
    assert on_surtax_2025(D("5710")) == D("0.00")
    assert on_surtax_2025(D("5710.10")) > D("0.00")
    assert on_surtax_2025(D("7307.10")) > on_surtax_2025(D("7307.00"))


def test_end_to_end_sample_2025():
    r = compute_full_2025(D("120000"), D("120000"))
    assert r.total_payable > D("0")


@pytest.mark.parametrize(
    "province,tax_fn,credit_fn",
    [
        ("AB", ab_tax_on_taxable_income_2025, ab_credits_2025),
        ("BC", bc_tax_on_taxable_income_2025, bc_credits_2025),
        ("MB", mb_tax_on_taxable_income_2025, mb_credits_2025),
        ("SK", sk_tax_on_taxable_income_2025, sk_credits_2025),
        ("NS", ns_tax_on_taxable_income_2025, ns_credits_2025),
        ("NB", nb_tax_on_taxable_income_2025, nb_credits_2025),
        ("NL", nl_tax_on_taxable_income_2025, nl_credits_2025),
        ("PE", pe_tax_on_taxable_income_2025, pe_credits_2025),
        ("YT", yt_tax_on_taxable_income_2025, yt_credits_2025),
        ("NT", nt_tax_on_taxable_income_2025, nt_credits_2025),
        ("NU", nu_tax_on_taxable_income_2025, nu_credits_2025),
    ],
)
def test_core_provincial_calculators_align_with_exports(province, tax_fn, credit_fn):
    taxable = D("95000.00")
    breakdown = compute_full_2025(taxable, taxable, province=province)
    assert breakdown.provincial_tax == tax_fn(taxable)
    assert breakdown.provincial_credits == credit_fn()


def test_supported_provincial_calculators_handle_fixture_examples():
    examples = make_provincial_examples()
    for province, req in examples.items():
        calculator = get_provincial_calculator(req.tax_year, province)
        employment_income = sum(slip.employment_income for slip in req.slips_t4)
        t4a_income = sum_t4a_income(req.slips_t4a)
        t5_income = sum_t5_income(req.slips_t5)
        total_income = employment_income + t4a_income + t5_income
        rrsp_total = req.rrsp_contrib + sum_rrsp_contributions(req.rrsp_receipts)
        breakdown = compute_full_2025(total_income - rrsp_total, total_income, province=province)
        assert breakdown.provincial_tax == calculator.tax(total_income - rrsp_total)
        assert breakdown.total_payable >= D("0.00")


def test_slip_aggregation_helpers_cover_all_fields():
    req = make_min_input(include_examples=True)
    req.slips_t4a.append(
        req.slips_t4a[0].model_copy(update={
            "pension_income": D("500.00"),
            "other_income": D("125.00"),
            "self_employment_commissions": D("75.00"),
            "research_grants": D("60.00"),
            "tax_deducted": D("0.00"),
        })
    )
    req.slips_t5.append(
        req.slips_t5[0].model_copy(update={
            "interest_income": D("15.00"),
            "eligible_dividends": D("10.00"),
            "other_dividends": D("5.00"),
            "capital_gains": D("20.00"),
            "foreign_income": D("30.00"),
            "foreign_tax_withheld": D("4.00"),
        })
    )
    req.rrsp_receipts.extend(
        [
            RRSPReceipt(contribution_amount=D("250.00"), issuer="Extra Bank"),
            RRSPReceipt(contribution_amount=D("125.00"), issuer="Extra Bank"),
        ]
    )

    expected_t4a = sum(
        sum(
            getattr(slip, field) or D("0.00")
            for field in ("pension_income", "other_income", "self_employment_commissions", "research_grants")
        )
        for slip in req.slips_t4a
    )
    expected_t5 = sum(
        sum(
            getattr(slip, field) or D("0.00")
            for field in ("interest_income", "eligible_dividends", "other_dividends", "capital_gains", "foreign_income")
        )
        for slip in req.slips_t5
    )
    expected_rrsp = sum(receipt.contribution_amount for receipt in req.rrsp_receipts)

    assert sum_t4a_income(req.slips_t4a) == expected_t4a
    assert sum_t5_income(req.slips_t5) == expected_t5
    assert sum_rrsp_contributions(req.rrsp_receipts) == expected_rrsp
