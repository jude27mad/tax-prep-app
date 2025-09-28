from decimal import Decimal
from app.core.models import ReturnCalc, ReturnInput

class EfileEnvelope:
  def __init__(self, software_id: str, software_ver: str, transmitter_id: str):
    self.software_id = software_id
    self.software_ver = software_ver
    self.transmitter_id = transmitter_id

def build_records(env: EfileEnvelope, in_: ReturnInput, calc: ReturnCalc) -> dict:
  return {
    "env": {
      "software_id": env.software_id,
      "software_ver": env.software_ver,
      "transmitter_id": env.transmitter_id,
    },
    "return": {
      "year": calc.tax_year,
      "province": calc.province,
      "line_items": calc.line_items,
      "totals": calc.totals,
    },
  }
