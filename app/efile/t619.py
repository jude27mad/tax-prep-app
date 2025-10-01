from __future__ import annotations

import base64
from dataclasses import dataclass
from io import StringIO
from typing import Any, Dict
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

import xmlschema

from app.core.models import ReturnCalc, ReturnInput
from app.efile.t183 import mask_sin

NS_T1 = "http://www.cra-arc.gc.ca/xmlns/efile/t1/1.0"
NS_T183 = "http://www.cra-arc.gc.ca/xmlns/efile/t183/1.0"
NS_T619 = "http://www.cra-arc.gc.ca/xmlns/efile/t619/1.0"

SCHEMA_T1 = "cra_t1_return_v1.xsd"
SCHEMA_T183 = "cra_t183_authorization_v1.xsd"
SCHEMA_T619 = "cra_t619_envelope_v1.xsd"

_COMPILED_SCHEMAS: Dict[str, xmlschema.XMLSchemaBase] = {}


@dataclass
class T619Package:
    sbmt_ref_id: str
    t1_xml: str
    t183_xml: str
    envelope_xml: str
    payload_documents: dict[str, str]


def _get_schema(schema_cache: dict[str, str], name: str) -> xmlschema.XMLSchemaBase:
    if name in _COMPILED_SCHEMAS:
        return _COMPILED_SCHEMAS[name]
    if name not in schema_cache:
        raise ValueError(f"Schema {name} not loaded")
    schema_text = schema_cache[name]
    schema = xmlschema.XMLSchema(StringIO(schema_text))
    _COMPILED_SCHEMAS[name] = schema
    return schema


def _validate(xml_payload: str, schema_cache: dict[str, str], schema_name: str) -> None:
    schema = _get_schema(schema_cache, schema_name)
    schema.validate(xml_payload)


def _prettify(element: Element) -> str:
    rough = tostring(element, encoding="utf-8")
    parsed = minidom.parseString(rough)
    return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def _build_t1_element(data: dict[str, Any]) -> Element:
    root = Element("T1Return", {"xmlns": NS_T1})
    for key, value in data.items():
        child = SubElement(root, key)
        child.text = value
    return root


def _build_t183_element(data: dict[str, Any]) -> Element:
    root = Element("T183Authorization", {"xmlns": NS_T183})
    for key, value in data.items():
        child = SubElement(root, key)
        child.text = value
    return root


def _build_t619_element(profile: dict[str, str], payload_b64: str, sbmt_ref_id: str) -> Element:
    root = Element("T619Transmission", {"xmlns": NS_T619})
    SubElement(root, "sbmt_ref_id").text = sbmt_ref_id
    for key, value in profile.items():
        SubElement(root, key).text = value
    SubElement(root, "Payload").text = payload_b64
    return root


def map_t1_fields(req: ReturnInput, calc: ReturnCalc) -> dict[str, str]:
    taxable = calc.line_items.get("taxable_income") or calc.line_items.get("income_total")
    taxable_str = format(taxable, "f") if taxable is not None else "0"
    return {
        "TaxYear": str(calc.tax_year),
        "TaxpayerSIN": req.taxpayer.sin,
        "Province": req.province,
        "NetIncome": taxable_str,
    }


def map_t183_fields(req: ReturnInput) -> dict[str, str]:
    signed_at = req.t183_signed_ts.isoformat() if req.t183_signed_ts else ""
    expires_at = ""
    if req.t183_signed_ts:
        expires_at = req.t183_signed_ts.isoformat()
    return {
        "TaxpayerSINMasked": mask_sin(req.taxpayer.sin),
        "SignedAt": signed_at,
        "ExpiresAt": expires_at,
        "SignatureIPAddress": req.t183_ip_hash or "",
    }


def build_t619_package(
    req: ReturnInput,
    calc: ReturnCalc,
    profile: dict[str, str],
    schema_cache: dict[str, str],
    sbmt_ref_id: str,
) -> T619Package:
    t1_data = map_t1_fields(req, calc)
    t183_data = map_t183_fields(req)

    t1_element = _build_t1_element(t1_data)
    t183_element = _build_t183_element(t183_data)

    t1_xml = _prettify(t1_element)
    t183_xml = _prettify(t183_element)

    _validate(t1_xml, schema_cache, SCHEMA_T1)
    _validate(t183_xml, schema_cache, SCHEMA_T183)

    payload_documents = {
        "t1": t1_xml,
        "t183": t183_xml,
    }
    payload_blob = base64.b64encode(str(payload_documents).encode("utf-8")).decode("ascii")

    envelope_element = _build_t619_element(profile, payload_blob, sbmt_ref_id)
    envelope_xml = _prettify(envelope_element)
    _validate(envelope_xml, schema_cache, SCHEMA_T619)

    return T619Package(
        sbmt_ref_id=sbmt_ref_id,
        t1_xml=t1_xml,
        t183_xml=t183_xml,
        envelope_xml=envelope_xml,
        payload_documents=payload_documents,
    )
