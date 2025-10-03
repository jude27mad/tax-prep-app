from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

YT_2025 = (
    Bracket(55_867, 0.0640),
    Bracket(111_733, 0.0900),
    Bracket(173_205, 0.1090),
    Bracket(500_000, 0.1280),
    Bracket(None, 0.1500),
)

YT_BPA_2025 = 15_000.0
YT_CREDIT_RATE = 0.0640

adapter = ProvincialAdapter(
    code="YT",
    name="Yukon",
    brackets=YT_2025,
    credit_rate=YT_CREDIT_RATE,
    bpa_fn=basic_personal_amount(YT_BPA_2025),
    additions_fn=no_additions,
)

