from app.efile.error_map import explain_error


def test_specific_rc4018_code():
    assert "SIN" in explain_error("10021")


def test_family_rc4018_code():
    assert explain_error("30042").startswith("Business-rule")


def test_unknown_rc4018_code():
    msg = explain_error("99999")
    assert "Unknown" in msg
