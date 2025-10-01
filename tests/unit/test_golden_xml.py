from pathlib import Path

from app.core.tax_years._2025_alias import compute_return
from app.efile.t619 import build_t619_package
from tests.fixtures.min_client import make_min_input


def _schema_cache():
    return {p.name: p.read_text() for p in Path("app/schemas").glob("*.xsd")}


def test_t619_matches_golden():
    req = make_min_input()
    calc = compute_return(req)
    profile = {
        "Environment": "CERT",
        "SoftwareId": "TAXAPP-CERT",
        "SoftwareVersion": "0.0.3",
        "TransmitterId": "900000",
    }
    package = build_t619_package(req, calc, profile, _schema_cache(), "CERTX999")
    assert package.sbmt_ref_id == "CERTX999"
    golden_dir = Path("tests/golden")
    assert package.envelope_xml == (golden_dir / "t619_envelope.xml").read_text(encoding="utf-8")
    assert package.t1_xml == (golden_dir / "t1_return.xml").read_text(encoding="utf-8")
    assert package.t183_xml == (golden_dir / "t183_authorization.xml").read_text(encoding="utf-8")
