import base64
from io import BytesIO
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from app.core.tax_years._2025_alias import compute_return
from app.efile.t619 import NS_T619, build_t619_package
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
        "RepID": "RP1234567",
    }
    sbmt_ref_id = "CERT0001"
    package = build_t619_package(req, calc, profile, _schema_cache(), sbmt_ref_id)
    assert package.sbmt_ref_id == sbmt_ref_id
    assert "<T1Return" in package.t1_xml
    assert "<sbmt_ref_id>CERT0001</sbmt_ref_id>" in package.envelope_xml
    assert "<RepID>RP1234567</RepID>" in package.envelope_xml
    payload = _decode_payload(package.envelope_xml)
    assert payload["T1Return.xml"] == package.payload_documents["T1Return"]
    assert payload["T183Authorization.xml"] == package.payload_documents["T183Authorization"]


def _decode_payload(envelope_xml: str) -> dict[str, str]:
    root = ET.fromstring(envelope_xml)
    payload_b64 = root.findtext(f"{{{NS_T619}}}Payload")
    assert payload_b64 is not None
    data = base64.b64decode(payload_b64)
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return {
            name: archive.read(name).decode("utf-8")
            for name in archive.namelist()
        }
