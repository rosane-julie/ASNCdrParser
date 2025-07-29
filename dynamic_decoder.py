import logging
from typing import Any, Dict, List, Tuple

import xmltodict
from pyasn1.type import univ, char, namedtype
from typing import Any
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


def _build_schema(node: Dict[str, Any]) -> Tuple[Any, List[str]]:
    """Recursively build a pyasn1 schema from a decoded XML node."""
    field_names: List[str] = []

    def build(node: Dict[str, Any]) -> Any:
        if "sequence" in node:
            container = node["sequence"]
            cls = univ.Sequence
        elif "set" in node:
            container = node["set"]
            cls = univ.Set
        elif "choice" in node:
            container = node["choice"]
            cls = univ.Choice
        else:
            # single field definition
            typ_name = node.get("@type") or node.get("type") or "IA5String"
            asn1_cls = ASN1_TYPE_MAP.get(typ_name, char.IA5String)
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
                typ_name = fld.get("@type") or fld.get("type") or "IA5String"
                asn1_cls = ASN1_TYPE_MAP.get(typ_name, char.IA5String)
                comp = namedtype.OptionalNamedType(name, asn1_cls())
                field_names.append(name)
            components.append(comp)

        return cls(componentType=namedtype.NamedTypes(*components))

    schema = build(node)
    return schema, field_names


def parse_xml_spec(xml_content: str) -> Tuple[Any, List[str]]:
    """Parse decoder XML into a pyasn1 schema."""
    logger = logging.getLogger(__name__)
    if xml_content.strip().startswith("<"):
        xml_data = xml_content
    else:
        with open(xml_content, "r", encoding="utf-8") as fh:
            xml_data = fh.read()

    spec = xmltodict.parse(xml_data)
    field_entries = spec.get("decoder", {}).get("field", [])
    if isinstance(field_entries, dict):
        field_entries = [field_entries]

    field_names: List[str] = []
    named_types: List[namedtype.NamedType] = []
    for entry in field_entries:
        name = entry.get("@name") or entry.get("name")
        if not name:
            logger.debug("Skipped field with no name in XML spec")
            continue
        typ_name = entry.get("@type") or entry.get("type") or "IA5String"
        asn1_cls = ASN1_TYPE_MAP.get(typ_name, char.IA5String)
        named_types.append(namedtype.OptionalNamedType(name, asn1_cls()))
        field_names.append(name)

    schema = univ.Sequence(componentType=namedtype.NamedTypes(*named_types))
    return schema, field_names


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
            offset += 1
            continue
        asn1_dict = _asn1_to_dict(decoded)
        record = _extract_fields(asn1_dict)
        record["raw"] = asn1_dict
        records.append(record)

    if not records:
        import re
        phone_matches = re.findall(rb"\d{6,15}", cdr_bytes)
        if phone_matches:
            fallback: Dict[str, Any] = {}
            fallback["calling_number"] = phone_matches[0].decode("ascii", errors="ignore")
            if len(phone_matches) > 1:
                fallback["called_number"] = phone_matches[1].decode("ascii", errors="ignore")
            if len(phone_matches) > 2:
                try:
                    fallback["duration"] = int(phone_matches[2].decode("ascii", errors="ignore"))
                except Exception:
                    fallback["duration"] = phone_matches[2].decode("ascii", errors="ignore")
            records.append(fallback)

    return records
