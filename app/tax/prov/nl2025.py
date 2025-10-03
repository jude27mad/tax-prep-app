from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

NL_2025 = (
    Bracket(43_198, 0.0870),
    Bracket(86_395, 0.1250),
    Bracket(154_244, 0.1330),
    Bracket(196_456, 0.1530),
    Bracket(275_862, 0.1730),
    Bracket(551_725, 0.1830),
    Bracket(None, 0.1980),
)

NL_BPA_2025 = 11_866.0
NL_CREDIT_RATE = 0.0870

adapter = ProvincialAdapter(
    code="NL",
    name="Newfoundland and Labrador",
    brackets=NL_2025,
    credit_rate=NL_CREDIT_RATE,
    bpa_fn=basic_personal_amount(NL_BPA_2025),
    additions_fn=no_additions,
)

