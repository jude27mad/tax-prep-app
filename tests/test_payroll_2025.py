from fastapi.testclient import TestClient

from app.main import app, _expected_cpp_contributions, _expected_ei_contribution


def test_cpp_ei_edges():
    c1, c2 = _expected_cpp_contributions(60000)
    assert round(c1, 2) == 3361.75
    assert round(c2, 2) == 0.00
    c1, c2 = _expected_cpp_contributions(75000)
    assert round(c1, 2) == 4034.10
    assert round(c2, 2) == 148.00
    c1, c2 = _expected_cpp_contributions(80000)
    assert round(c1, 2) == 4034.10
    assert round(c2, 2) == 348.00
    c1, c2 = _expected_cpp_contributions(90000)
    assert round(c1, 2) == 4034.10
    assert round(c2, 2) == 396.00
    assert round(_expected_ei_contribution(60000), 2) == 984.00
    assert round(_expected_ei_contribution(75000), 2) == 1077.48


def test_t4_endpoint_refund_flow():
    client = TestClient(app)
    payload = {
        "box14_employment_income": 60000,
        "box22_tax_withheld": 9000,
        "box16_cpp": 3361.75,
        "box16A_cpp2": 0,
        "box18_ei": 984.00,
        "rrsp_deduction": 5000,
    }
    response = client.post("/tax/t4", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "total_tax" in body and "balance_positive_is_amount_owing" in body
