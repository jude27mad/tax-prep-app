from types import SimpleNamespace

from app.efile.service import validate_t619_preflight
from app.efile.t619 import NS_T619


def _wrap(content: str) -> str:
    return (
        f"<T619Transmission xmlns=\"{NS_T619}\">"
        f"{content}"
        "</T619Transmission>"
    )


def test_preflight_requires_sbmt_and_ids():
    xml = _wrap(
        "<Environment>CERT</Environment>"
        "<SoftwareId>SW</SoftwareId>"
        "<SoftwareVersion>1.0</SoftwareVersion>"
        "<TransmitterId>TRN</TransmitterId>"
        "<Payload>DATA</Payload>"
    )
    issues = validate_t619_preflight(SimpleNamespace(envelope_xml=xml))
    assert "sbmt_ref_id" in issues[0]
    assert any("TransmitterAccount" in msg or "RepID" in msg for msg in issues)


def test_preflight_accepts_rep_id_only():
    xml = _wrap(
        "<sbmt_ref_id>CERT1234</sbmt_ref_id>"
        "<Environment>CERT</Environment>"
        "<SoftwareId>SW</SoftwareId>"
        "<SoftwareVersion>1.0</SoftwareVersion>"
        "<TransmitterId>TRN</TransmitterId>"
        "<RepID>RP1234567</RepID>"
        "<Payload>DATA</Payload>"
    )
    issues = validate_t619_preflight(SimpleNamespace(envelope_xml=xml))
    assert issues == []
