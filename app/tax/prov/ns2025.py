from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

NS_2025 = (
    Bracket(29_590, 0.0879),
    Bracket(59_180, 0.1495),
    Bracket(93_000, 0.1667),
    Bracket(150_000, 0.1750),
    Bracket(None, 0.2100),
)

NS_BPA_2025 = 11_481.0
NS_CREDIT_RATE = 0.0879

adapter = ProvincialAdapter(
    code="NS",
    name="Nova Scotia",
    brackets=NS_2025,
    credit_rate=NS_CREDIT_RATE,
    bpa_fn=basic_personal_amount(NS_BPA_2025),
    additions_fn=no_additions,
)

