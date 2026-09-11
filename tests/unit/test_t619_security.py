import pytest
from defusedxml.common import EntitiesForbidden

from app.efile.service import T619Package, validate_t619_preflight
from app.efile.t619 import minidom


def test_t619_minidom_blocks_entity_expansion() -> None:
    malicious_xml = """<?xml version="1.0"?>
    <!DOCTYPE lolz [
     <!ENTITY lol "lol">
     <!ELEMENT lolz (#PCDATA)>
     <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
    ]>
    <lolz>&lol1;</lolz>"""

    with pytest.raises(EntitiesForbidden):
        minidom.parseString(malicious_xml)


def test_validate_t619_preflight_blocks_entity_expansion() -> None:
    malicious_xml = """<?xml version="1.0"?>
    <!DOCTYPE lolz [
     <!ENTITY lol "lol">
     <!ELEMENT lolz (#PCDATA)>
     <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
    ]>
    <lolz>&lol1;</lolz>"""

    pkg = T619Package(
        sbmt_ref_id="TEST001",
        t1_xml="",
        t183_xml="",
        envelope_xml=malicious_xml,
        payload_documents={},
    )
    issues = validate_t619_preflight(pkg)
    assert issues == ["T619 envelope XML is malformed"]
