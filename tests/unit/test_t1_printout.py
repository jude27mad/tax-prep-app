from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.tax_years._2025_alias import compute_return
from app.printout.t1_render import render_t1_pdf
from tests.fixtures.min_client import make_min_input


GOLDEN_DIGEST_PATH = Path(__file__).resolve().parents[1] / "golden" / "t1_printout.sha256"


def test_t1_printout_matches_golden(tmp_path: Path) -> None:
    """Render a representative T1 PDF and ensure the output stays stable."""

    request = make_min_input(include_examples=True)
    calc = compute_return(request)

    pdf_path = tmp_path / "t1.pdf"
    render_t1_pdf(str(pdf_path), request, calc)

    pdf_bytes = pdf_path.read_bytes()
    digest = hashlib.sha256(pdf_bytes).hexdigest()

    expected_digest = GOLDEN_DIGEST_PATH.read_text().strip()
    assert digest == expected_digest, (
        "T1 printout digest changed.\n"
        "If the template changed intentionally, regenerate the golden value by "
        "rendering a fresh PDF with `make_min_input(include_examples=True)` and "
        "updating tests/golden/t1_printout.sha256."
    )

    pdf_text = pdf_bytes.decode("latin-1")

    # Sanity checks to guard against partially-rendered documents.
    assert "/Count 1" in pdf_text, "expected a single-page T1 printout"
    expected_title = (
        f"T1 Summary - {request.taxpayer.last_name}, {request.taxpayer.first_name} ({calc.tax_year})"
    )
    escaped_title = expected_title.replace("(", r"\(").replace(")", r"\)")
    assert escaped_title in pdf_text
    assert f"CRA T1 return for tax year {calc.tax_year}" in pdf_text
    assert "Tax Preparer App" in pdf_text
    assert "CreationDate (D:20000101000000+00'00')" in pdf_text
