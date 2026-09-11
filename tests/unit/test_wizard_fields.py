import pytest

from app.wizard.fields import coerce_for_field, parse_number


def test_parse_number_plain() -> None:
    assert parse_number("100") == 100.0
    assert parse_number("123.45") == 123.45


def test_parse_number_currency_and_separators() -> None:
    assert parse_number("$1,234.56") == 1234.56
    assert parse_number(" $ 1_000_000.00 _ ") == 1000000.0


def test_parse_number_unicode_minuses() -> None:
    assert parse_number("−50.5") == -50.5
    assert parse_number("–25") == -25.0


def test_parse_number_suffixes() -> None:
    assert parse_number("10k") == 10000.0
    assert parse_number("1.5m") == 1500000.0
    assert parse_number("2b") == 2000000000.0


@pytest.mark.parametrize("invalid", ["", "   ", "$", "-", ".", "_"])
def test_parse_number_invalid(invalid: str) -> None:
    with pytest.raises(ValueError, match="Please enter a number."):
        parse_number(invalid)


def test_parse_number_invalid_text() -> None:
    with pytest.raises(ValueError, match="Could not understand number"):
        parse_number("invalid_number_abc")


def test_coerce_for_field_numeric() -> None:
    assert coerce_for_field("box14", "$57,000.00") == 57000.0
    assert coerce_for_field("box22", "10k") == 10000.0
