import pytest

from app.main import _parse_number


def test_parse_number_standard_values() -> None:
    assert _parse_number("123") == 123.0
    assert _parse_number("123.45") == 123.45
    assert _parse_number("-50.5") == -50.5
    assert _parse_number("0") == 0.0
    assert _parse_number("0.00") == 0.0


def test_parse_number_with_formatting_and_symbols() -> None:
    assert _parse_number("$1,234.56") == 1234.56
    assert _parse_number(" $ 50_000 ") == 50000.0
    assert _parse_number("10 000") == 10000.0
    assert _parse_number("$100,000.00") == 100000.0


def test_parse_number_suffix_shorthand() -> None:
    assert _parse_number("57k") == 57000.0
    assert _parse_number("57K") == 57000.0
    assert _parse_number("$57k") == 57000.0
    assert _parse_number("1.5m") == 1500000.0
    assert _parse_number("2b") == 2000000000.0


def test_parse_number_unicode_minuses() -> None:
    assert _parse_number("−50") == -50.0  # U+2212 Minus Sign
    assert _parse_number("–100") == -100.0  # U+2013 En Dash


@pytest.mark.parametrize(
    "invalid_input",
    [
        "",
        "   ",
        "$",
        "-",
        ".",
        "$,.",
        "k",
        "m",
        "b",
        "abc",
        "123abc",
        "hello",
    ],
)
def test_parse_number_invalid_inputs(invalid_input: str) -> None:
    with pytest.raises(ValueError):
        _parse_number(invalid_input)
