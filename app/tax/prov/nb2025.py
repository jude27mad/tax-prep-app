from __future__ import annotations

from app.tax.ca2025 import Bracket
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount, no_additions

NB_2025 = (
    Bracket(49_958, 0.0940),
    Bracket(99_916, 0.1400),
    Bracket(185_064, 0.1600),
    Bracket(None, 0.1900),
)

NB_BPA_2025 = 12_758.0
NB_CREDIT_RATE = 0.0940

adapter = ProvincialAdapter(
    code="NB",
    name="New Brunswick",
    brackets=NB_2025,
    credit_rate=NB_CREDIT_RATE,
    bpa_fn=basic_personal_amount(NB_BPA_2025),
    additions_fn=no_additions,
)

