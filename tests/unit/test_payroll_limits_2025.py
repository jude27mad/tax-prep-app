from decimal import Decimal as D

from app.core.payroll import limits_2025


def test_cpp_limits_2025():
    assert limits_2025.CPP_YMPE == D("71300")
    assert limits_2025.CPP_RATE == D("0.0595")
    assert limits_2025.CPP_MAX_EMPLOYEE == D("4034.10")
    assert limits_2025.CPP_YAMPE == D("81200")
    assert limits_2025.CPP2_RATE == D("0.04")
    assert limits_2025.CPP2_MAX_EMPLOYEE == D("396.00")


def test_ei_limits_2025():
    assert limits_2025.EI_MIE == D("65700")
    assert limits_2025.EI_RATE_EMP == D("0.0164")
    assert limits_2025.EI_MAX_EMPLOYEE == D("1077.48")
