from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

NU_2025 = (
    Bracket(53_268, 0.0400),
    Bracket(106_537, 0.0700),
    Bracket(172_155, 0.0900),
    Bracket(None, 0.1150),
)

NU_BPA_2025 = 17_925.0
NU_CREDIT_RATE = 0.0400

adapter = ProvincialAdapter(
    code="NU",
    name="Nunavut",
    brackets=NU_2025,
    credit_rate=NU_CREDIT_RATE,
    bpa_fn=basic_personal_amount(NU_BPA_2025),
    additions_fn=no_additions,
)

