from decimal import Decimal

D = Decimal

CPP_YMPE = D("68500")
CPP_YAMPE = D("73200")
CPP_BASIC_EXEMPTION = D("3500")
CPP_RATE = D("0.0595")
CPP2_RATE = D("0.04")
# 2024 max base CPP employee contribution (informational):
CPP_MAX_EMPLOYEE = D("3867.50")

EI_MIE = D("63200")
EI_RATE_EMP = D("0.0166")
EI_MAX_EMPLOYEE = (EI_MIE * EI_RATE_EMP).quantize(D("0.01"))
