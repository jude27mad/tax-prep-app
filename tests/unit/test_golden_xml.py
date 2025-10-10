import base64
from datetime import datetime
from io import BytesIO
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from app.core.tax_years._2025_alias import compute_return
from app.efile.t183 import _compute_expiry
from app.efile.t619 import NS_T183, NS_T619, build_t619_package
from tests.fixtures.min_client import make_min_input


def _schema_cache():
    return {p.name: p.read_text() for p in Path("app/schemas").glob("*.xsd")}


def test_t619_matches_golden():
    req = make_min_input(include_examples=True)
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
    t183_root = ET.fromstring(package.t183_xml)
    signed_at = datetime.fromisoformat(
        t183_root.findtext(f"{{{NS_T183}}}Signature/{{{NS_T183}}}SignedAt")
    )
    expires_at = datetime.fromisoformat(
        t183_root.findtext(f"{{{NS_T183}}}Signature/{{{NS_T183}}}ExpiresAt")
    )
    assert expires_at == _compute_expiry(signed_at)
    payload_documents = _decode_payload(package.envelope_xml)
    assert payload_documents["T1Return.xml"] == package.t1_xml
    assert payload_documents["T183Authorization.xml"] == package.t183_xml


def _decode_payload(envelope_xml: str) -> dict[str, str]:
    root = ET.fromstring(envelope_xml)
    payload_b64 = root.findtext(f"{{{NS_T619}}}Payload")
    assert payload_b64 is not None
    archive_bytes = base64.b64decode(payload_b64)
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        return {
            name: archive.read(name).decode("utf-8")
            for name in archive.namelist()
        }
