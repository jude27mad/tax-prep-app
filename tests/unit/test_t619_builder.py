from pathlib import Path

from app.core.tax_years._2025_alias import compute_return
from app.efile.t619 import build_t619_package
from tests.fixtures.min_client import make_min_input


def _schema_cache():
    return {
        schema_path.name: schema_path.read_text()
        for schema_path in Path("app/schemas").glob("*.xsd")
    }


def test_build_t619_package():
    req = make_min_input()
    calc = compute_return(req)
    profile = {
        "Environment": "CERT",
        "SoftwareId": "X",
        "SoftwareVersion": "0.1.0",
        "TransmitterId": "T",
    }
    sbmt_ref_id = "CERT0001"
    package = build_t619_package(req, calc, profile, _schema_cache(), sbmt_ref_id)
    assert package.sbmt_ref_id == sbmt_ref_id
    assert "<T1Return" in package.t1_xml
    assert "<sbmt_ref_id>CERT0001</sbmt_ref_id>" in package.envelope_xml
    assert package.payload_documents["t1"].startswith("<?xml")
