from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import base64
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
            "taxable_income": Decimal("70000.00"),
            "federal_tax": Decimal("15000.00"),
            "prov_tax": Decimal("6000.00"),
            "ontario_surtax": Decimal("500.00"),
        },
        totals={"net_tax": Decimal("21000.00")},
        cpp={"employee": Decimal("2898.00")},
        ei={"employee": Decimal("889.54")},
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


def test_render_t1_pdf_respects_explicit_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    request = _make_input()
    calc = _make_calc()
    explicit = tmp_path / "custom" / "return.pdf"

    pdf_path = Path(render_t1_pdf(str(explicit), request, calc))

    assert pdf_path == explicit
    assert pdf_path.exists()
