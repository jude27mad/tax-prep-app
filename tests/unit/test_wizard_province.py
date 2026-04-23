import pytest

from app import main
from app.core.provinces import list_provincial_calculators


def test_wizard_province_choices_match_dispatch() -> None:
    expected = tuple(
        (calc.code, calc.name) for calc in list_provincial_calculators(2025)
    )
    assert main._FIELD_METADATA["province"]["choices"] == expected


def test_province_input_validated_against_registry() -> None:
    assert main._coerce_for_field("province", "on") == "ON"
    with pytest.raises(ValueError):
        main._coerce_for_field("province", "zz")
