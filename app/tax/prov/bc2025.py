from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

# 2025 British Columbia personal income tax brackets and rates
BC_2025 = (
    Bracket(47_937, 0.0506),
    Bracket(95_875, 0.0770),
    Bracket(110_076, 0.1050),
    Bracket(133_664, 0.1229),
    Bracket(181_232, 0.1470),
    Bracket(None, 0.1680),
)

BC_BPA_2025 = 12_580.0
BC_CREDIT_RATE = 0.0506

adapter = ProvincialAdapter(
    code="BC",
    name="British Columbia",
    brackets=BC_2025,
    credit_rate=BC_CREDIT_RATE,
    bpa_fn=basic_personal_amount(BC_BPA_2025),
    additions_fn=no_additions,
)
