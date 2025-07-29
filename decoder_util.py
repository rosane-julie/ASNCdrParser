import logging
from typing import List, Dict, Any
import xmltodict
import asn1tools


def decode_cdr(cdr_bytes: bytes, xml_spec: str) -> List[Dict[str, Any]]:
    """Decode ASN.1 CDR bytes using the provided XML spec.

    Parameters
    ----------
    cdr_bytes: bytes
        Raw bytes of the CDR file.
    xml_spec: str
        XML string describing the decoder fields.

    Returns
    -------
    list of dict
        Decoded records with mapped field names.
    """
    logger = logging.getLogger(__name__)
    spec_dict = xmltodict.parse(xml_spec)
    field_entries = spec_dict.get("decoder", {}).get("field", [])
    if isinstance(field_entries, dict):
        field_entries = [field_entries]

    field_names = []
    for entry in field_entries:
        name = entry.get("name")
        if name:
            field_names.append(name)
        else:
            logger.warning("Skipped field with no name in XML spec")
    if not field_names:
        raise ValueError("No fields defined in XML spec")

    asn_lines = ["DECODER DEFINITIONS ::= BEGIN", "Record ::= SEQUENCE {"]
    for idx, fname in enumerate(field_names):
        comma = "," if idx < len(field_names) - 1 else ""
        asn_lines.append(f"    {fname} IA5String OPTIONAL{comma}")
    asn_lines.append("}")
    asn_lines.append("END")
    asn_text = "\n".join(asn_lines)

    compiled = asn1tools.compile_string(asn_text, "ber")

    records: List[Dict[str, Any]] = []
    offset = 0
    data = cdr_bytes
    while offset < len(data):
        try:
            decoded, rest = compiled.decode("Record", data[offset:], check_constraints=False)
            offset = len(data) - len(rest)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Decode error at offset %d: %s", offset, exc)
            break
        rec_dict: Dict[str, Any] = {}
        for k, v in decoded.items():
            value = str(v)
            lk = k.lower()
            if "calling" in lk and "number" in lk:
                rec_dict["calling_number"] = value
            elif "called" in lk and "number" in lk:
                rec_dict["called_number"] = value
            elif "duration" in lk:
                try:
                    rec_dict["duration"] = int(value)
                except ValueError:
                    rec_dict["duration"] = value
            elif "start" in lk and "time" in lk:
                rec_dict["start_time"] = value
            elif "end" in lk and "time" in lk:
                rec_dict["end_time"] = value
            else:
                logger.info("Unknown field %s skipped", k)
                rec_dict[k] = value
        records.append(rec_dict)
    return records
