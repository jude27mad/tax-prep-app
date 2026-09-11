import pytest

from app.main import _parse_bool


@pytest.mark.parametrize(
    "value",
    [
        "y",
        "yes",
        "true",
        "1",
        "ok",
        "sure",
        " YES ",
        "True",
        "SURE",
        " 1\t",
    ],
)
def test_parse_bool_truthy(value: str) -> None:
    assert _parse_bool(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "n",
        "no",
        "false",
        "0",
        " NO ",
        "False",
        " 0\n",
    ],
)
def test_parse_bool_falsy(value: str) -> None:
    assert _parse_bool(value) is False


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "maybe",
        "2",
        "-1",
        "invalid",
        "yes please",
        "none",
    ],
)
def test_parse_bool_invalid(value: str) -> None:
    with pytest.raises(ValueError, match="Enter yes or no."):
        _parse_bool(value)
