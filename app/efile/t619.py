from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from typing import Any, Dict
import zipfile
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


def _append_children(parent: Element, data: dict[str, Any]) -> None:
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, dict):
            child = SubElement(parent, key)
            _append_children(child, value)
        elif isinstance(value, list):
            for item in value:
                child = SubElement(parent, key)
                if isinstance(item, dict):
                    _append_children(child, item)
                else:
                    child.text = str(item)
        else:
            child = SubElement(parent, key)
            child.text = str(value)


def _build_t1_element(data: dict[str, Any]) -> Element:
    root = Element("T1Return", {"xmlns": NS_T1})
    _append_children(root, data)
    return root


def _build_t183_element(data: dict[str, Any]) -> Element:
    root = Element("T183Authorization", {"xmlns": NS_T183})
    _append_children(root, data)
    return root


def _build_t619_element(profile: dict[str, str], payload_b64: str, sbmt_ref_id: str) -> Element:
    root = Element("T619Transmission", {"xmlns": NS_T619})
    SubElement(root, "sbmt_ref_id").text = sbmt_ref_id
    for key, value in profile.items():
        SubElement(root, key).text = value
    SubElement(root, "Payload").text = payload_b64
    return root


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "0.00"
    quantized = value.quantize(Decimal("0.01")) if isinstance(value, Decimal) else Decimal(value).quantize(Decimal("0.01"))
    return format(quantized, "f")


def map_t1_fields(req: ReturnInput, calc: ReturnCalc) -> dict[str, Any]:
    taxpayer = req.taxpayer
    household = req.household
    line_items = calc.line_items
    totals = calc.totals
    t1_data: dict[str, Any] = {
        "TaxYear": str(calc.tax_year),
        "Taxpayer": {
            "SIN": taxpayer.sin,
            "FirstName": taxpayer.first_name,
            "LastName": taxpayer.last_name,
            "DateOfBirth": taxpayer.dob.isoformat(),
            "Address": {
                "Line1": taxpayer.address_line1,
                "City": taxpayer.city,
                "Province": taxpayer.province,
                "PostalCode": taxpayer.postal_code,
            },
            "ResidencyStatus": taxpayer.residency_status,
        },
        "Household": None,
        "LineItems": {
            "IncomeTotal": _format_decimal(line_items.get("income_total")),
            "TaxableIncome": _format_decimal(line_items.get("taxable_income")),
            "FederalTax": _format_decimal(line_items.get("federal_tax")),
            "ProvincialTax": _format_decimal(line_items.get("prov_tax")),
        },
        "Totals": {
            "NetTax": _format_decimal(totals.get("net_tax")),
        },
    }
    if household is not None:
        household_data: dict[str, Any] = {
            "MaritalStatus": household.marital_status,
        }
        if household.spouse_sin:
            household_data["SpouseSIN"] = household.spouse_sin
        if household.dependants:
            household_data["Dependants"] = {
                "DependantsCount": len(household.dependants),
            }
        t1_data["Household"] = household_data
    return t1_data


def map_t183_fields(req: ReturnInput) -> dict[str, Any]:
    if not req.t183_signed_ts:
        raise ValueError("T183 signature timestamp is required for CRA payload")
    signed_at: datetime = req.t183_signed_ts
    expires_at = signed_at + timedelta(days=90)
    data: dict[str, Any] = {
        "TaxpayerSINMasked": mask_sin(req.taxpayer.sin),
        "TaxpayerName": {
            "FirstName": req.taxpayer.first_name,
            "LastName": req.taxpayer.last_name,
        },
        "TaxpayerDOB": req.taxpayer.dob.isoformat(),
        "Signature": {
            "SignedAt": signed_at.isoformat(),
            "ExpiresAt": expires_at.isoformat(),
        },
    }
    if req.t183_ip_hash:
        data["Signature"]["IPAddress"] = req.t183_ip_hash
    if req.t183_user_agent_hash:
        data["Signature"]["UserAgentHash"] = req.t183_user_agent_hash
    consent: dict[str, Any] = {}
    if req.t183_pdf_path:
        consent["DocumentPath"] = req.t183_pdf_path
    if consent:
        data["Consent"] = consent
    return data


def _serialize_payload(documents: dict[str, str]) -> str:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(documents.keys()):
            info = zipfile.ZipInfo(f"{name}.xml")
            info.date_time = (2020, 1, 1, 0, 0, 0)
            info.external_attr = 0o600 << 16
            archive.writestr(info, documents[name].encode("utf-8"))
    zipped_bytes = buffer.getvalue()
    return base64.b64encode(zipped_bytes).decode("ascii")


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
        "T1Return": t1_xml,
        "T183Authorization": t183_xml,
    }
    payload_blob = _serialize_payload(payload_documents)

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
