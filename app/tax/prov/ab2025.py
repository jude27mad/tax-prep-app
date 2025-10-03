from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

AB_2025 = (
    Bracket(148_269, 0.10),
    Bracket(177_922, 0.12),
    Bracket(237_230, 0.13),
    Bracket(355_845, 0.14),
    Bracket(None, 0.15),
)

AB_BPA_2025 = 21_885.0
AB_CREDIT_RATE = 0.10

adapter = ProvincialAdapter(
    code="AB",
    name="Alberta",
    brackets=AB_2025,
    credit_rate=AB_CREDIT_RATE,
    bpa_fn=basic_personal_amount(AB_BPA_2025),
    additions_fn=no_additions,
)
