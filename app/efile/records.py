"""Legacy JSON EFILE envelope helpers.

These structures power the deprecated JSON workflow used by
``app.api.http.legacy_efile``. They exist solely for backwards compatibility
until all callers migrate to the XML/T619 flow assembled in
``app.efile.service``/``app.efile.t619`` and will be removed once that happens.
"""

from app.core.models import ReturnCalc, ReturnInput

class EfileEnvelope:
  def __init__(self, software_id: str, software_ver: str, transmitter_id: str, environment: str):
    self.software_id = software_id
    self.software_ver = software_ver
    self.transmitter_id = transmitter_id
    self.environment = environment

def build_records(env: EfileEnvelope, in_: ReturnInput, calc: ReturnCalc) -> dict:
  return {
    "env": {
      "software_id": env.software_id,
      "software_ver": env.software_ver,
      "transmitter_id": env.transmitter_id,
      "environment": env.environment,
    },
    "return": {
      "year": calc.tax_year,
      "province": calc.province,
      "line_items": calc.line_items,
      "totals": calc.totals,
    },
  }

