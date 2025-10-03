from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

SK_2025 = (
    Bracket(52_057, 0.1050),
    Bracket(148_734, 0.1250),
    Bracket(None, 0.1450),
)

SK_BPA_2025 = 19_936.0
SK_CREDIT_RATE = 0.1050

adapter = ProvincialAdapter(
    code="SK",
    name="Saskatchewan",
    brackets=SK_2025,
    credit_rate=SK_CREDIT_RATE,
    bpa_fn=basic_personal_amount(SK_BPA_2025),
    additions_fn=no_additions,
)

