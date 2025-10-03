from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

MB_2025 = (
    Bracket(47_000, 0.1080),
    Bracket(100_000, 0.1275),
    Bracket(None, 0.1740),
)

MB_BPA_2025 = 15_780.0
MB_CREDIT_RATE = 0.1080

adapter = ProvincialAdapter(
    code="MB",
    name="Manitoba",
    brackets=MB_2025,
    credit_rate=MB_CREDIT_RATE,
    bpa_fn=basic_personal_amount(MB_BPA_2025),
    additions_fn=no_additions,
)
