from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab import rl_config

from app.config import get_settings
from app.core.models import ReturnCalc, ReturnInput


PAGE_WIDTH, PAGE_HEIGHT = LETTER
LEFT_MARGIN = 54
RIGHT_MARGIN = PAGE_WIDTH - LEFT_MARGIN
LINE_HEIGHT = 16

# Vertical distance from a section header's baseline to its first content row.
HEADER_TO_ROW_GAP = 18
# Vertical gap between the last content of one summary section and the next
# section's header. A fixed constant, but applied *after* each section reports
# how much vertical space it actually consumed -- see the "top_y in, next y
# out" pattern below.
SECTION_GAP = 24
# Extra space above the bolded "Net tax payable" row, separating it visually
# from the line items it totals.
TOTAL_ROW_GAP = 8

HEADER_FONT = "Helvetica-Bold"
BODY_FONT = "Helvetica"
SMALL_FONT = "Helvetica"

IDENTITY_COORDS = {
    "last_name": (LEFT_MARGIN, PAGE_HEIGHT - 120),
    "first_name": (LEFT_MARGIN, PAGE_HEIGHT - 136),
    "address": (LEFT_MARGIN, PAGE_HEIGHT - 152),
    "city": (LEFT_MARGIN, PAGE_HEIGHT - 168),
    "province": (LEFT_MARGIN + 200, PAGE_HEIGHT - 168),
    "postal_code": (LEFT_MARGIN + 280, PAGE_HEIGHT - 168),
    "sin": (LEFT_MARGIN + 320, PAGE_HEIGHT - 120),
    "dob": (LEFT_MARGIN + 320, PAGE_HEIGHT - 136),
    "residency": (LEFT_MARGIN + 320, PAGE_HEIGHT - 152),
}

LINE_ITEM_ROWS = (
    ("income_total", "Total income"),
    ("total_deductions", "Deductions"),
    ("net_income", "Net income"),
    ("division_c_deductions", "Other payments deduction (line 25000)"),
    ("taxable_income", "Taxable income"),
    ("federal_tax", "Federal tax"),
    ("prov_tax", "Provincial tax"),
)

RRSP_ROWS = (
    ("rrsp_contrib", "RRSP payroll deduction"),
    ("rrsp_receipts", "RRSP contribution receipts"),
    ("rrsp_total", "Total RRSP contributions"),
)

CPP_EI_ROWS = (
    ("cpp_employee", "CPP contributions"),
    ("ei_employee", "EI premiums"),
)


def _format_currency(value: Decimal | float | int | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    quantized = value.quantize(Decimal("0.01"))
    return f"${quantized:,.2f}"


def _format_date(value: date | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d")


_NON_DIGIT_RE = re.compile(r"\D")


def _format_sin(value: str | None) -> str:
    if not value:
        return ""
    digits = _NON_DIGIT_RE.sub("", value)
    if len(digits) == 9:
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
    return digits


def _sum_decimals(values: Iterable[Decimal | None]) -> Decimal:
    return sum(
        (value if isinstance(value, Decimal) else Decimal(str(value))
         for value in values if value is not None),
        start=Decimal("0.00")
    )


def _sanitize_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower())
    segment = segment.strip("-")
    return segment or "taxpayer"


def _build_artifact_name(request: ReturnInput, calc: ReturnCalc) -> str:
    last_name = _sanitize_segment(request.taxpayer.last_name)
    sin_digits = "".join(ch for ch in request.taxpayer.sin if ch.isdigit())
    sin_suffix = sin_digits[-4:] if len(sin_digits) >= 4 else (sin_digits or "xxxx")
    return f"t1_{calc.tax_year}_{last_name}_{sin_suffix}.pdf"


def _resolve_output_path(out_path: str, request: ReturnInput, calc: ReturnCalc) -> Path:
    requested = Path(out_path)
    settings = get_settings()
    artifact_root = Path(settings.artifact_root)
    if not artifact_root.is_absolute():
        artifact_root = Path.cwd() / artifact_root

    if requested.suffix.lower() == ".pdf":
        final_path = requested if requested.is_absolute() else artifact_root / requested
    else:
        base_dir = requested if requested.is_absolute() else artifact_root / requested
        if requested.suffix:
            base_dir = base_dir.parent
        filename = _build_artifact_name(request, calc)
        final_path = base_dir / filename

    final_path.parent.mkdir(parents=True, exist_ok=True)
    return final_path


def _set_metadata(pdf: canvas.Canvas, request: ReturnInput, calc: ReturnCalc) -> None:
    taxpayer = request.taxpayer
    display_name = f"{taxpayer.last_name}, {taxpayer.first_name}".strip(", ")
    title = f"T1 Summary - {display_name} ({calc.tax_year})"
    subject = f"CRA T1 return for tax year {calc.tax_year}"
    author = f"{taxpayer.first_name} {taxpayer.last_name}".strip()

    pdf.setTitle(title)
    pdf.setSubject(subject)
    pdf.setAuthor(author)
    pdf.setCreator("Tax Preparer App")


def _draw_headers(pdf: canvas.Canvas, calc: ReturnCalc) -> None:
    pdf.setFont(HEADER_FONT, 16)
    pdf.drawString(LEFT_MARGIN, PAGE_HEIGHT - 72, f"T1 General – {calc.tax_year}")
    pdf.setFont(HEADER_FONT, 11)
    pdf.drawString(LEFT_MARGIN, PAGE_HEIGHT - 96, "Taxpayer identification")


def _draw_identity(pdf: canvas.Canvas, request: ReturnInput) -> None:
    taxpayer = request.taxpayer
    values = {
        "last_name": taxpayer.last_name,
        "first_name": taxpayer.first_name,
        "address": taxpayer.address_line1,
        "city": taxpayer.city,
        "province": taxpayer.province,
        "postal_code": taxpayer.postal_code,
        "sin": _format_sin(taxpayer.sin),
        "dob": _format_date(taxpayer.dob),
        "residency": taxpayer.residency_status,
    }

    pdf.setFont(BODY_FONT, 10)
    for key, (x, y) in IDENTITY_COORDS.items():
        value = values.get(key)
        if not value:
            continue
        pdf.drawString(x, y, str(value))


def _humanize(label: str) -> str:
    parts = label.replace("_", " ").split()
    return " ".join(part.capitalize() for part in parts)


def _draw_line_items(pdf: canvas.Canvas, calc: ReturnCalc, top_y: float) -> float:
    """Draw the income/tax summary starting at ``top_y``; return the y below it.

    Row count is variable -- provincial additions range from zero to several
    entries -- so this section's height cannot be a fixed constant. Every
    caller must position the *next* section relative to what this one actually
    drew, not a hardcoded offset from the page top.
    """
    pdf.setFont(HEADER_FONT, 11)
    pdf.drawString(LEFT_MARGIN, top_y, "Income and tax summary")
    label_x = LEFT_MARGIN
    value_x = RIGHT_MARGIN
    y = top_y - HEADER_TO_ROW_GAP

    pdf.setFont(BODY_FONT, 10)
    for key, label in LINE_ITEM_ROWS:
        amount = calc.line_items.get(key)
        if amount is None:
            y -= LINE_HEIGHT
            continue
        pdf.drawString(label_x, y, label)
        pdf.drawRightString(value_x, y, _format_currency(amount))
        y -= LINE_HEIGHT

    # Provincial additions come from their own declared field. They used to be
    # inferred as "any line_items key not in LINE_ITEM_ROWS", which meant every
    # newly added T1 line was silently printed as a provincial addition.
    additions = [
        (key, value) for key, value in calc.provincial_additions.items() if value is not None
    ]
    if additions:
        pdf.setFont(SMALL_FONT, 9)
        pdf.drawString(label_x, y, "Provincial additions")
        y -= LINE_HEIGHT
        pdf.setFont(BODY_FONT, 10)
        for key, value in sorted(additions):
            pdf.drawString(label_x + 12, y, _humanize(key))
            pdf.drawRightString(value_x, y, _format_currency(value))
            y -= LINE_HEIGHT

    net_tax = calc.totals.get("net_tax")
    if net_tax is not None:
        y -= TOTAL_ROW_GAP
        pdf.setFont(HEADER_FONT, 11)
        pdf.drawString(label_x, y, "Net tax payable")
        pdf.setFont(BODY_FONT, 10)
        pdf.drawRightString(value_x, y, _format_currency(net_tax))
        y -= LINE_HEIGHT

    return y


def _draw_cpp_ei(pdf: canvas.Canvas, calc: ReturnCalc, top_y: float) -> float:
    """Draw CPP/EI starting at ``top_y``; return the y below it.

    ``top_y`` comes from the previous section's consumed height, not a fixed
    page offset -- see :func:`_draw_line_items`.
    """
    pdf.setFont(HEADER_FONT, 11)
    pdf.drawString(LEFT_MARGIN, top_y, "CPP and EI")
    pdf.setFont(BODY_FONT, 10)
    y = top_y - HEADER_TO_ROW_GAP
    value_x = RIGHT_MARGIN

    cpp_employee = calc.cpp.get("employee") if calc.cpp else None
    ei_employee = calc.ei.get("employee") if calc.ei else None
    values = {
        "cpp_employee": cpp_employee,
        "ei_employee": ei_employee,
    }

    for key, label in CPP_EI_ROWS:
        amount = values.get(key)
        if amount is None:
            y -= LINE_HEIGHT
            continue
        pdf.drawString(LEFT_MARGIN, y, label)
        pdf.drawRightString(value_x, y, _format_currency(amount))
        y -= LINE_HEIGHT

    return y


def _draw_rrsp(pdf: canvas.Canvas, request: ReturnInput, top_y: float) -> float:
    """Draw RRSP contributions starting at ``top_y``; return the y below it."""
    pdf.setFont(HEADER_FONT, 11)
    pdf.drawString(LEFT_MARGIN, top_y, "RRSP contributions")
    pdf.setFont(BODY_FONT, 10)
    y = top_y - HEADER_TO_ROW_GAP
    value_x = RIGHT_MARGIN

    receipts_total = _sum_decimals(
        receipt.contribution_amount for receipt in request.rrsp_receipts
    )
    payroll = request.rrsp_contrib
    totals = {
        "rrsp_contrib": payroll,
        "rrsp_receipts": receipts_total,
        "rrsp_total": _sum_decimals([payroll, receipts_total]),
    }

    for key, label in RRSP_ROWS:
        amount = totals.get(key)
        if amount is None:
            y -= LINE_HEIGHT
            continue
        pdf.drawString(LEFT_MARGIN, y, label)
        pdf.drawRightString(value_x, y, _format_currency(amount))
        y -= LINE_HEIGHT

    return y


def _draw_page_number(pdf: canvas.Canvas, total_pages: int) -> None:
    pdf.setFont(SMALL_FONT, 9)
    page_text = f"Page {pdf.getPageNumber()} of {total_pages}"
    pdf.drawRightString(RIGHT_MARGIN, 36, page_text)


@contextmanager
def _pdf_invariant_mode():
    """Temporarily enable ReportLab's invariant mode for deterministic output."""

    previous = rl_config.invariant
    rl_config.invariant = True
    try:
        yield
    finally:
        rl_config.invariant = previous


def render_t1_pdf(out_path: str, request: ReturnInput, calc: ReturnCalc) -> str:
    """Render a CRA T1 printout and return the filesystem path."""

    output_path = _resolve_output_path(out_path, request, calc)
    with _pdf_invariant_mode():
        pdf = canvas.Canvas(str(output_path), pagesize=LETTER)

        _set_metadata(pdf, request, calc)
        _draw_headers(pdf, calc)
        _draw_identity(pdf, request)

        # Each section reports where it stopped; the next one starts SECTION_GAP
        # below that. This is what keeps CPP/EI and RRSP from overlapping the
        # income summary when provincial additions make it taller than usual.
        y = PAGE_HEIGHT - 210
        y = _draw_line_items(pdf, calc, y) - SECTION_GAP
        y = _draw_cpp_ei(pdf, calc, y) - SECTION_GAP
        _draw_rrsp(pdf, request, y)

        _draw_page_number(pdf, 1)

        pdf.showPage()
        pdf.save()
    return str(output_path)
