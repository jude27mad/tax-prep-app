import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    "payload, expected_balance_sign, cpp_status, cpp2_status, ei_status",
    [
        (
            {"box14": 70000, "box22": 12000, "box16": 3500, "box16A": 200, "box18": 1000, "rrsp": 5000, "province": "ON"},
            -1,
            "under",
            "over",
            "under",
        ),
        (
            {"box14": 71300, "box22": 11000, "box16": 4034.10, "box16A": 0, "box18": 1077.48, "rrsp": 0, "province": "ON"},
            1,
            "ok",
            "ok",
            "ok",
        ),
    ],
)
def test_t4_estimate_balance_and_contribution_statuses(
    payload, expected_balance_sign, cpp_status, cpp2_status, ei_status
):
    response = client.post("/t4/estimate", json=payload)
    assert response.status_code == 200
    body = response.json()

    balance = body["balance"]
    assert balance * expected_balance_sign > 0, "balance sign mismatch"
    assert body["is_refund"] == (balance < 0)

    assert body["cpp"]["status"] == cpp_status
    assert body["cpp2"]["status"] == cpp2_status
    assert body["ei"]["status"] == ei_status
