ERROR_MAP = {
  "E000": "accepted",
  "E100": "rejected_invalid_payload",
  "E200": "rejected_validation_failure",
  "E300": "duplicate_submission",
}

def explain(code: str) -> str:
  return ERROR_MAP.get(code, "unknown_error")
