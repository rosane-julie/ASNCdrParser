import logging
from typing import List, Dict, Any, Tuple

import xmltodict
from pyasn1.type import univ, char, namedtype
from pyasn1.codec.ber import decoder as ber_decoder


def parse_xml_spec(xml_content: str) -> Tuple[univ.Sequence, List[str]]:
    """Parse a simple decoder XML and return a pyasn1 schema."""
    logger = logging.getLogger(__name__)
    if xml_content.strip().startswith('<'):
        xml_data = xml_content
    else:
        with open(xml_content, 'r', encoding='utf-8') as fh:
            xml_data = fh.read()

    spec = xmltodict.parse(xml_data)
    field_entries = spec.get('decoder', {}).get('field', [])
    if isinstance(field_entries, dict):
        field_entries = [field_entries]

    named_types = []
    field_names = []
    for entry in field_entries:
        name = entry.get('@name') or entry.get('name')
        if not name:
            logger.debug('Skipped field with no name in XML spec')
            continue
        field_names.append(name)
        named_types.append(namedtype.OptionalNamedType(name, char.VisibleString()))

    schema = univ.Sequence()
    schema.componentType = namedtype.NamedTypes(*named_types)
    return schema, field_names


def decode_cdr(cdr_bytes: bytes, xml_spec: str) -> List[Dict[str, Any]]:
    """Decode ASN.1 CDR bytes using the provided XML spec."""
    schema, field_names = parse_xml_spec(xml_spec)
    offset = 0
    records: List[Dict[str, Any]] = []
    while offset < len(cdr_bytes):
        try:
            decoded, rest = ber_decoder.decode(cdr_bytes[offset:], asn1Spec=schema)
            offset = len(cdr_bytes) - len(rest)
        except Exception as exc:  # pragma: no cover - best effort
            logging.debug("Decode error at offset %d: %s", offset, exc)
            break
        rec_dict: Dict[str, Any] = {}
        for name in field_names:
            value = decoded.getComponentByName(name)
            if value is not None:
                rec_dict[name] = str(value)
            else:
                logging.debug("Missing optional field %s", name)
        records.append(rec_dict)
    return records
