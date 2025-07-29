import logging
from typing import Any, Dict, List, Tuple

import xmltodict
from pyasn1.type import univ, char, namedtype, base
from pyasn1.codec.ber import decoder as ber_decoder


# Mapping of basic type names from XML to pyasn1 classes
ASN1_TYPE_MAP: Dict[str, Any] = {
    "IA5String": char.IA5String,
    "VisibleString": char.VisibleString,
    "UTF8String": char.UTF8String,
    "NumericString": char.NumericString,
    "OctetString": univ.OctetString,
    "Integer": univ.Integer,
    "Boolean": univ.Boolean,
}


def _build_schema(node: Dict[str, Any]) -> Tuple[base.Asn1Item, List[str]]:
    """Recursively build a pyasn1 schema from a decoded XML node."""
    field_names: List[str] = []

    def build(node: Dict[str, Any]) -> base.Asn1Item:
        if "sequence" in node:
            container = node["sequence"]
            asn1_obj = univ.Sequence()
        elif "set" in node:
            container = node["set"]
            asn1_obj = univ.Set()
        elif "choice" in node:
            container = node["choice"]
            asn1_obj = univ.Choice()
        else:
            # single field definition
            typ_name = node.get("@type") or node.get("type") or "VisibleString"
            asn1_cls = ASN1_TYPE_MAP.get(typ_name, char.VisibleString)
            return asn1_cls()

        fields = container.get("field", [])
        if isinstance(fields, dict):
            fields = [fields]

        components: List[namedtype.NamedType] = []
        for fld in fields:
            name = fld.get("@name") or fld.get("name")
            if not name:
                continue
            if any(k in fld for k in ("sequence", "set", "choice")):
                sub_obj = build(fld)
                field_names.append(name)
                comp = namedtype.OptionalNamedType(name, sub_obj)
            else:
                typ_name = fld.get("@type") or fld.get("type") or "VisibleString"
                asn1_cls = ASN1_TYPE_MAP.get(typ_name, char.VisibleString)
                comp = namedtype.OptionalNamedType(name, asn1_cls())
                field_names.append(name)
            components.append(comp)

        asn1_obj.componentType = namedtype.NamedTypes(*components)
        return asn1_obj

    schema = build(node)
    return schema, field_names


def parse_xml_spec(xml_content: str) -> Tuple[base.Asn1Item, List[str]]:
    """Parse decoder XML into a pyasn1 schema."""
    logger = logging.getLogger(__name__)
    if xml_content.strip().startswith("<"):
        xml_data = xml_content
    else:
        with open(xml_content, "r", encoding="utf-8") as fh:
            xml_data = fh.read()

    spec = xmltodict.parse(xml_data)
    decoder_node = spec.get("decoder") or spec
    try:
        schema, names = _build_schema(decoder_node)
    except Exception as exc:  # pragma: no cover - best effort
        logger.error("Failed to build schema from XML: %s", exc)
        raise
    return schema, names


def _asn1_to_dict(obj: Any) -> Any:
    """Convert a pyasn1 object into basic Python types."""
    if hasattr(obj, "hasValue") and obj.hasValue():
        if hasattr(obj, "__iter__") and not isinstance(obj, (bytes, str)):
            result: Dict[str, Any] = {}
            for idx, component in enumerate(obj):
                name = None
                if hasattr(obj, "componentType"):
                    try:
                        name = obj.componentType[idx].getName()
                    except Exception:
                        name = None
                result[name or f"component_{idx}"] = _asn1_to_dict(component)
            return result
        return str(obj)
    return None


def _extract_fields(data: Any) -> Dict[str, Any]:
    """Extract common CDR fields from a decoded ASN.1 dictionary."""
    result: Dict[str, Any] = {}

    def walk(val: Any):
        if isinstance(val, dict):
            for k, v in val.items():
                lk = k.lower() if isinstance(k, str) else ""
                if "calling" in lk and "number" in lk:
                    result.setdefault("calling_number", str(v))
                elif "called" in lk and "number" in lk:
                    result.setdefault("called_number", str(v))
                elif "duration" in lk:
                    try:
                        result.setdefault("duration", int(str(v)))
                    except Exception:
                        result.setdefault("duration", str(v))
                elif "time" in lk or "date" in lk or "timestamp" in lk:
                    # store all timestamps with their keys
                    result.setdefault(k, str(v))
                walk(v)
        elif isinstance(val, list):
            for item in val:
                walk(item)

    walk(data)
    return result


def decode_cdr(cdr_bytes: bytes, xml_spec: str) -> List[Dict[str, Any]]:
    """Decode ASN.1 CDR bytes using the provided XML spec."""
    schema, _ = parse_xml_spec(xml_spec)
    offset = 0
    records: List[Dict[str, Any]] = []

    while offset < len(cdr_bytes):
        try:
            decoded, rest = ber_decoder.decode(cdr_bytes[offset:], asn1Spec=schema)
            offset = len(cdr_bytes) - len(rest)
        except Exception as exc:  # pragma: no cover - best effort
            logging.debug("Decode error at offset %d: %s", offset, exc)
            break
        asn1_dict = _asn1_to_dict(decoded)
        record = _extract_fields(asn1_dict)
        record["raw"] = asn1_dict
        records.append(record)

    return records
