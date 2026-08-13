from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import base64
import re
import zlib

import pytest

from app.config import get_settings
from app.printout.t1_render import render_t1_pdf
from app.core.models import (
    ReturnCalc,
    ReturnInput,
    Taxpayer,
    Household,
    RRSPReceipt,
    DeductionCreditInputs,
)


def _make_input() -> ReturnInput:
    taxpayer = Taxpayer(
        sin="123456789",
        first_name="Ada",
        last_name="Lovelace",
        dob=date(1990, 12, 10),
        address_line1="123 Example St",
        city="Toronto",
        province="ON",
        postal_code="M5V1E3",
        residency_status="Resident",
    )
    household = Household(marital_status="single")
    receipt = RRSPReceipt(contribution_amount=Decimal("500.00"))
    return ReturnInput(
        taxpayer=taxpayer,
        household=household,
        rrsp_receipts=[receipt],
        rrsp_contrib=Decimal("250.00"),
        deductions=DeductionCreditInputs(),
        province="ON",
        tax_year=2025,
    )


def _make_calc() -> ReturnCalc:
    return ReturnCalc(
        tax_year=2025,
        province="ON",
        line_items={
            "income_total": Decimal("75000.00"),
            "total_deductions": Decimal("5000.00"),
            "net_income": Decimal("70000.00"),
            "taxable_income": Decimal("70000.00"),
            "federal_tax": Decimal("15000.00"),
            "prov_tax": Decimal("6000.00"),
        },
        totals={"net_tax": Decimal("21000.00")},
        cpp={"employee": Decimal("2898.00")},
        ei={"employee": Decimal("889.54")},
        # Declared, not inferred from leftover line_items keys.
        provincial_additions={"ontario_surtax": Decimal("500.00")},
    )


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_render_t1_pdf_generates_named_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path))
    request = _make_input()
    calc = _make_calc()

    pdf_path = Path(render_t1_pdf(".", request, calc))

    assert pdf_path.exists()
    expected_name = "t1_2025_lovelace_6789.pdf"
    assert pdf_path.name == expected_name
    assert pdf_path.parent == tmp_path

    payload = pdf_path.read_bytes()
    assert b"T1 Summary - Lovelace, Ada \\(2025\\)" in payload
    assert b"CRA T1 return for tax year 2025" in payload
    assert b"/Author (Ada Lovelace)" in payload

    stream_marker = b"stream\r\n"
    if stream_marker not in payload:
        stream_marker = b"stream\n"
    start = payload.index(stream_marker) + len(stream_marker)
    end = payload.index(b"endstream", start)
    decoded = zlib.decompress(base64.a85decode(payload[start:end], adobe=True)).decode("latin-1")
    assert "Page 1 of 1" in decoded
    assert "Net tax payable" in decoded


def _make_calc_full_ontario() -> ReturnCalc:
    """An Ontario return with every summary row and both provincial additions.

    This is the layout stress case: LINE_ITEM_ROWS fully populated *and* both
    ontario_surtax and ontario_health_premium present pushes the income summary
    section to its tallest, which is exactly the condition that used to make it
    collide with the fixed-position CPP/EI and RRSP sections below it.
    """
    return ReturnCalc(
        tax_year=2025,
        province="ON",
        line_items={
            "income_total": Decimal("150000.00"),
            "total_deductions": Decimal("10000.00"),
            "net_income": Decimal("140000.00"),
            "taxable_income": Decimal("140000.00"),
            "federal_tax": Decimal("30000.00"),
            "prov_tax": Decimal("12000.00"),
        },
        totals={"net_tax": Decimal("45000.00")},
        cpp={"employee": Decimal("4034.10")},
        ei={"employee": Decimal("1077.48")},
        provincial_additions={
            "ontario_surtax": Decimal("600.00"),
            "ontario_health_premium": Decimal("900.00"),
        },
    )


_TM_TJ_PATTERN = re.compile(r"1 0 0 1 [\-\d.]+ ([\-\d.]+) Tm \((.*?)\) Tj")


def _decode_content_stream(pdf_bytes: bytes) -> str:
    stream_marker = b"stream\r\n"
    if stream_marker not in pdf_bytes:
        stream_marker = b"stream\n"
    start = pdf_bytes.index(stream_marker) + len(stream_marker)
    end = pdf_bytes.index(b"endstream", start)
    return zlib.decompress(base64.a85decode(pdf_bytes[start:end], adobe=True)).decode(
        "latin-1"
    )


def _first_y_for_text(decoded: str, text: str) -> float:
    for y, drawn in _TM_TJ_PATTERN.findall(decoded):
        if drawn == text:
            return float(y)
    raise AssertionError(f"text {text!r} not found in rendered PDF content stream")


def test_summary_sections_do_not_overlap_with_full_ontario_additions(tmp_path):
    """CPP/EI and RRSP must not overlap a fully expanded income summary.

    _draw_cpp_ei previously started at a page-relative fixed Y regardless of how
    much the income summary above it had drawn. With both Ontario additions
    present plus the "Net tax payable" total row, the summary section grew tall
    enough to run into the CPP/EI header, and RRSP in turn overlapped CPP/EI.
    Each section's start position must now derive from the previous section's
    actual consumed height.
    """
    request = _make_input()
    calc = _make_calc_full_ontario()
    pdf_path = tmp_path / "t1.pdf"

    render_t1_pdf(str(pdf_path), request, calc)
    decoded = _decode_content_stream(pdf_path.read_bytes())

    # PDF y increases upward, so "does not overlap" means each later section's
    # header sits at a strictly smaller y than the previous section's last
    # drawn row, with at least a full line of clearance between them.
    y_net_tax = _first_y_for_text(decoded, "Net tax payable")
    y_cpp_header = _first_y_for_text(decoded, "CPP and EI")
    y_ei_row = _first_y_for_text(decoded, "EI premiums")
    y_rrsp_header = _first_y_for_text(decoded, "RRSP contributions")
    y_rrsp_last_row = _first_y_for_text(decoded, "Total RRSP contributions")

    min_clearance = 16  # LINE_HEIGHT in app.printout.t1_render

    assert y_net_tax - y_cpp_header >= min_clearance, (
        "CPP and EI header overlaps the income summary's net tax row"
    )
    assert y_ei_row - y_rrsp_header >= min_clearance, (
        "RRSP contributions header overlaps the CPP/EI section"
    )
    # Sanity: the whole stack still fits comfortably on the page above the
    # page-number footer drawn at y=36.
    assert y_rrsp_last_row > 36 + min_clearance


def _make_calc_with_t5007_offset() -> ReturnCalc:
    """A return where the line 25000 deduction is actually non-zero."""
    return ReturnCalc(
        tax_year=2025,
        province="ON",
        line_items={
            "income_total": Decimal("53000.00"),
            "total_deductions": Decimal("0.00"),
            "net_income": Decimal("53000.00"),
            "division_c_deductions": Decimal("3000.00"),
            "taxable_income": Decimal("50000.00"),
            "federal_tax": Decimal("7500.00"),
            "prov_tax": Decimal("3000.00"),
        },
        totals={"net_tax": Decimal("10500.00")},
        cpp={"employee": Decimal("0.00")},
        ei={"employee": Decimal("0.00")},
        provincial_additions={},
    )


def test_division_c_deductions_line_is_rendered(tmp_path):
    """The line 25000 amount that reconciles net to taxable income must be
    visible on the printout, not just silently applied to the totals."""
    request = _make_input()
    calc = _make_calc_with_t5007_offset()
    pdf_path = tmp_path / "t1.pdf"

    render_t1_pdf(str(pdf_path), request, calc)
    decoded = _decode_content_stream(pdf_path.read_bytes())

    # Parentheses in the label are backslash-escaped by reportlab in the raw
    # content stream, so match on the unambiguous unescaped portion.
    assert "Other payments deduction" in decoded
    assert "line 25000" in decoded
    assert "$3,000.00" in decoded


def test_render_t1_pdf_respects_explicit_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    request = _make_input()
    calc = _make_calc()
    explicit = tmp_path / "custom" / "return.pdf"

    pdf_path = Path(render_t1_pdf(str(explicit), request, calc))

    assert pdf_path == explicit
    assert pdf_path.exists()
