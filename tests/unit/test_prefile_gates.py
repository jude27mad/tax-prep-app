import pytest

from app.core.tax_years._2025_alias import compute_return
from app.efile.service import PrefileValidationError, enforce_prefile_gates
from tests.fixtures.min_client import make_min_input


def test_prefile_gate_requires_t183():
    req = make_min_input()
    req.t183_signed_ts = None
    calc = compute_return(req)
    with pytest.raises(PrefileValidationError) as exc:
        enforce_prefile_gates(req, calc)
    assert exc.value.issues[0].code == "50010"
