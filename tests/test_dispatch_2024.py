from __future__ import annotations

import pytest

from app.core.provinces.dispatch_2024 import CALC_2024


@pytest.mark.parametrize(
    ("code", "mod"),
    [
        ("SK", "sk"),
        ("NS", "ns"),
        ("NB", "nb"),
        ("NL", "nl"),
        ("PE", "pe"),
        ("YT", "yt"),
        ("NT", "nt"),
        ("NU", "nu"),
    ],
)
def test_dispatch_2024_routes_to_expected_module(code: str, mod: str) -> None:
    assert CALC_2024[code].__name__.endswith(f"provinces.{mod}")


def test_dispatch_2024_unknown_province() -> None:
    with pytest.raises(KeyError):
        _ = CALC_2024["XX"]
