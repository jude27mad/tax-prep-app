import pytest

from app.efile.error_map import explain_error, get_reject_details, RejectCodeInfo


def test_specific_rc4018_code():
    assert "SIN" in explain_error("10021")


def test_family_rc4018_code():
    assert explain_error("30042").startswith("Business-rule")


def test_unknown_rc4018_code():
    msg = explain_error("99999")
    assert "Unknown" in msg


@pytest.mark.parametrize(
    "code,expected_category,summary_phrase,remediation_phrase",
    [
        (
            "50113",
            "Authorization",
            "signature missing",
            "T183",
        ),
        (
            "10021",
            "Identification",
            "cannot match the SIN",
            "Confirm the client’s SIN",
        ),
        (
            "30022",
            "Business rule",
            "Province or territory of residence",
            "province of residence",
        ),
    ],
)
def test_common_rc4018_guidance(code, expected_category, summary_phrase, remediation_phrase):
    details = get_reject_details(code)
    assert isinstance(details, RejectCodeInfo)
    assert details.category == expected_category
    assert summary_phrase in details.summary
    assert remediation_phrase in details.remediation
