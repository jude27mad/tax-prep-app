from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

NT_2025 = (
    Bracket(50_597, 0.0590),
    Bracket(101_198, 0.0860),
    Bracket(164_525, 0.1220),
    Bracket(None, 0.1405),
)

NT_BPA_2025 = 16_593.0
NT_CREDIT_RATE = 0.0590

adapter = ProvincialAdapter(
    code="NT",
    name="Northwest Territories",
    brackets=NT_2025,
    credit_rate=NT_CREDIT_RATE,
    bpa_fn=basic_personal_amount(NT_BPA_2025),
    additions_fn=no_additions,
)

