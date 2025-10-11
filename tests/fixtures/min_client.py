from decimal import Decimal

from app.core.models import (
  DeductionCreditInputs,
  Household,
  RRSPReceipt,
  ReturnInput,
  T4ASlip,
  T4Slip,
  T5Slip,
  Taxpayer,
)

_PROVINCE_FIXTURES: dict[str, dict] = {
  "ON": {
    "city": "Toronto",
    "postal": "M1M1M1",
    "t4_slips": [
      {
        "employment_income": Decimal("62000.00"),
        "tax_deducted": Decimal("9300.00"),
        "cpp_contrib": Decimal("3100.00"),
        "ei_premiums": Decimal("890.00"),
        "pensionable_earnings": Decimal("62000.00"),
        "insurable_earnings": Decimal("62000.00"),
      },
      {
        "employment_income": Decimal("18000.00"),
        "tax_deducted": Decimal("2100.00"),
        "pensionable_earnings": Decimal("18000.00"),
        "insurable_earnings": Decimal("18000.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("1200.00"),
        "tax_deducted": Decimal("150.00"),
      },
      {
        "other_income": Decimal("300.00"),
        "research_grants": Decimal("220.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("45.50"),
        "eligible_dividends": Decimal("12.34"),
        "foreign_income": Decimal("25.00"),
        "foreign_tax_withheld": Decimal("3.75"),
      },
      {
        "other_dividends": Decimal("18.25"),
        "capital_gains": Decimal("90.00"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("1000.00"),
        "issuer": "Sample Bank",
        "receipt_type": "official",
      },
      {
        "contribution_amount": Decimal("500.00"),
        "issuer": "Sample Bank",
        "receipt_type": "official",
      },
    ],
    "deductions": {
      "tuition_fees": Decimal("2000.00"),
      "medical_expenses": Decimal("450.00"),
      "charitable_donations": Decimal("250.00"),
      "student_loan_interest": Decimal("125.00"),
    },
    "rrsp_contrib": Decimal("650.00"),
  },
  "BC": {
    "city": "Vancouver",
    "postal": "V5K0A1",
    "t4_slips": [
      {
        "employment_income": Decimal("54000.00"),
        "tax_deducted": Decimal("7800.00"),
        "cpp_contrib": Decimal("2890.00"),
        "ei_premiums": Decimal("860.00"),
      },
      {
        "employment_income": Decimal("22000.00"),
        "tax_deducted": Decimal("3200.00"),
        "pensionable_earnings": Decimal("22000.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("950.00"),
        "tax_deducted": Decimal("100.00"),
      },
      {
        "other_income": Decimal("525.00"),
        "self_employment_commissions": Decimal("300.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("75.00"),
        "other_dividends": Decimal("40.00"),
      },
      {
        "foreign_income": Decimal("120.00"),
        "foreign_tax_withheld": Decimal("18.00"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("1500.00"),
        "issuer": "Coastal Credit Union",
        "receipt_type": "official",
      }
    ],
    "deductions": {
      "medical_expenses": Decimal("650.00"),
      "charitable_donations": Decimal("400.00"),
    },
    "rrsp_contrib": Decimal("700.00"),
  },
  "AB": {
    "city": "Calgary",
    "postal": "T2P1J9",
    "t4_slips": [
      {
        "employment_income": Decimal("68000.00"),
        "tax_deducted": Decimal("9800.00"),
        "cpp_contrib": Decimal("3100.00"),
        "ei_premiums": Decimal("910.00"),
      },
      {
        "employment_income": Decimal("24000.00"),
        "tax_deducted": Decimal("3600.00"),
        "pensionable_earnings": Decimal("24000.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("1500.00"),
        "tax_deducted": Decimal("200.00"),
      },
      {
        "self_employment_commissions": Decimal("420.00"),
        "research_grants": Decimal("350.00"),
      },
    ],
    "t5_slips": [
      {
        "eligible_dividends": Decimal("80.00"),
        "capital_gains": Decimal("140.00"),
      },
      {
        "foreign_income": Decimal("210.00"),
        "foreign_tax_withheld": Decimal("31.50"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("1250.00"),
        "issuer": "Prairie Wealth",
        "receipt_type": "official",
      },
      {
        "contribution_amount": Decimal("900.00"),
        "issuer": "Prairie Wealth",
        "receipt_type": "official",
      },
    ],
    "deductions": {
      "student_loan_interest": Decimal("210.00"),
      "tuition_fees": Decimal("1800.00"),
    },
    "rrsp_contrib": Decimal("800.00"),
  },
  "MB": {
    "city": "Winnipeg",
    "postal": "R3C4T3",
    "t4_slips": [
      {
        "employment_income": Decimal("51000.00"),
        "tax_deducted": Decimal("7200.00"),
        "cpp_contrib": Decimal("2860.00"),
        "ei_premiums": Decimal("860.00"),
      },
      {
        "employment_income": Decimal("20500.00"),
        "tax_deducted": Decimal("2950.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("800.00"),
      },
      {
        "other_income": Decimal("610.00"),
        "self_employment_commissions": Decimal("275.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("55.00"),
        "capital_gains": Decimal("60.00"),
      },
      {
        "foreign_income": Decimal("95.00"),
        "foreign_tax_withheld": Decimal("12.00"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("800.00"),
        "issuer": "Red River Savings",
        "receipt_type": "official",
      }
    ],
    "deductions": {
      "medical_expenses": Decimal("375.00"),
      "charitable_donations": Decimal("310.00"),
    },
    "rrsp_contrib": Decimal("500.00"),
  },
  "SK": {
    "city": "Saskatoon",
    "postal": "S7K1A1",
    "t4_slips": [
      {
        "employment_income": Decimal("56000.00"),
        "tax_deducted": Decimal("7800.00"),
        "cpp_contrib": Decimal("3000.00"),
        "ei_premiums": Decimal("860.00"),
        "pensionable_earnings": Decimal("56000.00"),
        "insurable_earnings": Decimal("56000.00"),
      },
      {
        "employment_income": Decimal("21000.00"),
        "tax_deducted": Decimal("2900.00"),
        "pensionable_earnings": Decimal("21000.00"),
        "insurable_earnings": Decimal("21000.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("900.00"),
        "tax_deducted": Decimal("110.00"),
      },
      {
        "other_income": Decimal("480.00"),
        "research_grants": Decimal("180.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("65.00"),
        "eligible_dividends": Decimal("18.00"),
      },
      {
        "foreign_income": Decimal("105.00"),
        "foreign_tax_withheld": Decimal("15.00"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("950.00"),
        "issuer": "Prairie Credit Union",
        "receipt_type": "official",
      }
    ],
    "deductions": {
      "medical_expenses": Decimal("420.00"),
      "charitable_donations": Decimal("280.00"),
    },
    "rrsp_contrib": Decimal("520.00"),
  },
  "NS": {
    "city": "Halifax",
    "postal": "B3J1A1",
    "t4_slips": [
      {
        "employment_income": Decimal("53000.00"),
        "tax_deducted": Decimal("7600.00"),
        "cpp_contrib": Decimal("2950.00"),
        "ei_premiums": Decimal("850.00"),
        "pensionable_earnings": Decimal("53000.00"),
        "insurable_earnings": Decimal("53000.00"),
      },
      {
        "employment_income": Decimal("19500.00"),
        "tax_deducted": Decimal("2600.00"),
        "pensionable_earnings": Decimal("19500.00"),
        "insurable_earnings": Decimal("19500.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("875.00"),
        "tax_deducted": Decimal("95.00"),
      },
      {
        "other_income": Decimal("440.00"),
        "self_employment_commissions": Decimal("240.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("58.00"),
        "other_dividends": Decimal("32.00"),
      },
      {
        "foreign_income": Decimal("90.00"),
        "foreign_tax_withheld": Decimal("13.00"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("880.00"),
        "issuer": "Harbour Bank",
        "receipt_type": "official",
      }
    ],
    "deductions": {
      "medical_expenses": Decimal("360.00"),
      "charitable_donations": Decimal("295.00"),
    },
    "rrsp_contrib": Decimal("480.00"),
  },
  "NB": {
    "city": "Fredericton",
    "postal": "E3B1A1",
    "t4_slips": [
      {
        "employment_income": Decimal("54500.00"),
        "tax_deducted": Decimal("7900.00"),
        "cpp_contrib": Decimal("2975.00"),
        "ei_premiums": Decimal("840.00"),
        "pensionable_earnings": Decimal("54500.00"),
        "insurable_earnings": Decimal("54500.00"),
      },
      {
        "employment_income": Decimal("20500.00"),
        "tax_deducted": Decimal("2750.00"),
        "pensionable_earnings": Decimal("20500.00"),
        "insurable_earnings": Decimal("20500.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("920.00"),
        "tax_deducted": Decimal("105.00"),
      },
      {
        "other_income": Decimal("410.00"),
        "research_grants": Decimal("210.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("62.00"),
        "capital_gains": Decimal("85.00"),
      },
      {
        "foreign_income": Decimal("115.00"),
        "foreign_tax_withheld": Decimal("16.00"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("910.00"),
        "issuer": "Maritime Savings",
        "receipt_type": "official",
      }
    ],
    "deductions": {
      "medical_expenses": Decimal("375.00"),
      "charitable_donations": Decimal("265.00"),
    },
    "rrsp_contrib": Decimal("505.00"),
  },
  "NL": {
    "city": "St. John's",
    "postal": "A1B2C3",
    "t4_slips": [
      {
        "employment_income": Decimal("57500.00"),
        "tax_deducted": Decimal("8200.00"),
        "cpp_contrib": Decimal("3025.00"),
        "ei_premiums": Decimal("845.00"),
        "pensionable_earnings": Decimal("57500.00"),
        "insurable_earnings": Decimal("57500.00"),
      },
      {
        "employment_income": Decimal("21500.00"),
        "tax_deducted": Decimal("3100.00"),
        "pensionable_earnings": Decimal("21500.00"),
        "insurable_earnings": Decimal("21500.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("980.00"),
        "tax_deducted": Decimal("120.00"),
      },
      {
        "other_income": Decimal("470.00"),
        "self_employment_commissions": Decimal("255.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("70.00"),
        "other_dividends": Decimal("34.00"),
      },
      {
        "foreign_income": Decimal("125.00"),
        "foreign_tax_withheld": Decimal("18.50"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("990.00"),
        "issuer": "Atlantic Trust",
        "receipt_type": "official",
      }
    ],
    "deductions": {
      "medical_expenses": Decimal("390.00"),
      "charitable_donations": Decimal("305.00"),
    },
    "rrsp_contrib": Decimal("540.00"),
  },
  "PE": {
    "city": "Charlottetown",
    "postal": "C1A1A1",
    "t4_slips": [
      {
        "employment_income": Decimal("50500.00"),
        "tax_deducted": Decimal("7100.00"),
        "cpp_contrib": Decimal("2880.00"),
        "ei_premiums": Decimal("820.00"),
        "pensionable_earnings": Decimal("50500.00"),
        "insurable_earnings": Decimal("50500.00"),
      },
      {
        "employment_income": Decimal("18500.00"),
        "tax_deducted": Decimal("2450.00"),
        "pensionable_earnings": Decimal("18500.00"),
        "insurable_earnings": Decimal("18500.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("810.00"),
        "tax_deducted": Decimal("90.00"),
      },
      {
        "other_income": Decimal("395.00"),
        "research_grants": Decimal("205.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("55.00"),
        "eligible_dividends": Decimal("16.50"),
      },
      {
        "foreign_income": Decimal("88.00"),
        "foreign_tax_withheld": Decimal("12.00"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("840.00"),
        "issuer": "Island Credit",
        "receipt_type": "official",
      }
    ],
    "deductions": {
      "medical_expenses": Decimal("345.00"),
      "charitable_donations": Decimal("255.00"),
    },
    "rrsp_contrib": Decimal("455.00"),
  },
  "YT": {
    "city": "Whitehorse",
    "postal": "Y1A1A1",
    "t4_slips": [
      {
        "employment_income": Decimal("59000.00"),
        "tax_deducted": Decimal("8300.00"),
        "cpp_contrib": Decimal("3050.00"),
        "ei_premiums": Decimal("870.00"),
        "pensionable_earnings": Decimal("59000.00"),
        "insurable_earnings": Decimal("59000.00"),
      },
      {
        "employment_income": Decimal("22500.00"),
        "tax_deducted": Decimal("3150.00"),
        "pensionable_earnings": Decimal("22500.00"),
        "insurable_earnings": Decimal("22500.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("1025.00"),
        "tax_deducted": Decimal("125.00"),
      },
      {
        "other_income": Decimal("505.00"),
        "self_employment_commissions": Decimal("285.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("78.00"),
        "capital_gains": Decimal("95.00"),
      },
      {
        "foreign_income": Decimal("132.00"),
        "foreign_tax_withheld": Decimal("19.00"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("1040.00"),
        "issuer": "Yukon Savings",
        "receipt_type": "official",
      }
    ],
    "deductions": {
      "medical_expenses": Decimal("410.00"),
      "charitable_donations": Decimal("320.00"),
    },
    "rrsp_contrib": Decimal("560.00"),
  },
  "NT": {
    "city": "Yellowknife",
    "postal": "X1A1A1",
    "t4_slips": [
      {
        "employment_income": Decimal("58500.00"),
        "tax_deducted": Decimal("8250.00"),
        "cpp_contrib": Decimal("3035.00"),
        "ei_premiums": Decimal("865.00"),
        "pensionable_earnings": Decimal("58500.00"),
        "insurable_earnings": Decimal("58500.00"),
      },
      {
        "employment_income": Decimal("21800.00"),
        "tax_deducted": Decimal("3050.00"),
        "pensionable_earnings": Decimal("21800.00"),
        "insurable_earnings": Decimal("21800.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("995.00"),
        "tax_deducted": Decimal("118.00"),
      },
      {
        "other_income": Decimal("490.00"),
        "research_grants": Decimal("215.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("74.00"),
        "other_dividends": Decimal("36.00"),
      },
      {
        "foreign_income": Decimal("128.00"),
        "foreign_tax_withheld": Decimal("18.00"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("1010.00"),
        "issuer": "Northern Bank",
        "receipt_type": "official",
      }
    ],
    "deductions": {
      "medical_expenses": Decimal("405.00"),
      "charitable_donations": Decimal("315.00"),
    },
    "rrsp_contrib": Decimal("555.00"),
  },
  "NU": {
    "city": "Iqaluit",
    "postal": "X0A1H0",
    "t4_slips": [
      {
        "employment_income": Decimal("60000.00"),
        "tax_deducted": Decimal("8400.00"),
        "cpp_contrib": Decimal("3080.00"),
        "ei_premiums": Decimal("880.00"),
        "pensionable_earnings": Decimal("60000.00"),
        "insurable_earnings": Decimal("60000.00"),
      },
      {
        "employment_income": Decimal("23000.00"),
        "tax_deducted": Decimal("3200.00"),
        "pensionable_earnings": Decimal("23000.00"),
        "insurable_earnings": Decimal("23000.00"),
      },
    ],
    "t4a_slips": [
      {
        "pension_income": Decimal("1035.00"),
        "tax_deducted": Decimal("130.00"),
      },
      {
        "other_income": Decimal("520.00"),
        "self_employment_commissions": Decimal("295.00"),
      },
    ],
    "t5_slips": [
      {
        "interest_income": Decimal("80.00"),
        "capital_gains": Decimal("105.00"),
      },
      {
        "foreign_income": Decimal("135.00"),
        "foreign_tax_withheld": Decimal("19.50"),
      },
    ],
    "rrsp_receipts": [
      {
        "contribution_amount": Decimal("1080.00"),
        "issuer": "Arctic Trust",
        "receipt_type": "official",
      }
    ],
    "deductions": {
      "medical_expenses": Decimal("430.00"),
      "charitable_donations": Decimal("330.00"),
    },
    "rrsp_contrib": Decimal("575.00"),
  },
}


def _fixture_for_province(province: str) -> tuple[str, dict]:
  code = province.upper()
  if code not in _PROVINCE_FIXTURES:
    code = "ON"
  return code, _PROVINCE_FIXTURES[code]


def make_min_input(
  tax_year: int = 2025,
  include_examples: bool = False,
  province: str = "ON",
) -> ReturnInput:
  province_code, fixture = _fixture_for_province(province)
  tp = Taxpayer(
    sin="046454286",
    first_name="Test",
    last_name="User",
    dob="1990-01-01",
    address_line1="1 Main St",
    city=fixture["city"],
    province=province_code,
    postal_code=fixture["postal"],
    residency_status="resident",
  )
  hh = Household(marital_status="single")
  t4_slip_data = fixture["t4_slips"][0]
  slips_t4 = [T4Slip(**t4_slip_data)]
  slips_t4a: list[T4ASlip] = []
  slips_t5: list[T5Slip] = []
  rrsp_receipts: list[RRSPReceipt] = []
  deductions = DeductionCreditInputs()
  rrsp_contrib = Decimal("0.00")
  if include_examples:
    slips_t4 = [T4Slip(**data) for data in fixture["t4_slips"]]
    slips_t4a = [T4ASlip(**data) for data in fixture["t4a_slips"]]
    slips_t5 = [T5Slip(**data) for data in fixture["t5_slips"]]
    rrsp_receipts = [RRSPReceipt(**data) for data in fixture["rrsp_receipts"]]
    deductions = DeductionCreditInputs(**fixture["deductions"])
    rrsp_contrib = fixture["rrsp_contrib"]
  return ReturnInput(
    taxpayer=tp,
    household=hh,
    slips_t4=slips_t4,
    slips_t4a=slips_t4a,
    slips_t5=slips_t5,
    rrsp_receipts=rrsp_receipts,
    deductions=deductions,
    rrsp_contrib=rrsp_contrib,
    province=province_code,
    tax_year=tax_year,
    t183_signed_ts="2025-02-15T09:00:00",
    t183_ip_hash="hash-ip",
    t183_user_agent_hash="hash-ua",
    t183_pdf_path="/tmp/t183.pdf",
  )


def make_provincial_examples(tax_year: int = 2025) -> dict[str, ReturnInput]:
  return {
    province: make_min_input(tax_year=tax_year, include_examples=True, province=province)
    for province in _PROVINCE_FIXTURES
  }
