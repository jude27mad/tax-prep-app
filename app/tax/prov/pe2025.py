from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

PE_2025 = (
    Bracket(35_812, 0.0965),
    Bracket(71_625, 0.1363),
    Bracket(None, 0.1665),
)

PE_BPA_2025 = 13_500.0
PE_CREDIT_RATE = 0.0965

adapter = ProvincialAdapter(
    code="PE",
    name="Prince Edward Island",
    brackets=PE_2025,
    credit_rate=PE_CREDIT_RATE,
    bpa_fn=basic_personal_amount(PE_BPA_2025),
    additions_fn=no_additions,
)

