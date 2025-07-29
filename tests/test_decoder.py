import os
from pathlib import Path
import xmltodict
import asn1tools
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dynamic_decoder import parse_xml_spec
from decoder_util import decode_cdr

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "specs" / "sample_decoder.xml"
SAMPLE_CDR = ROOT / "uploads" / "test_cdr.dat"


def test_parse_xml_spec_fields():
    xml = SPEC_PATH.read_text()
    _, names = parse_xml_spec(xml)
    assert {"callingNumber", "calledNumber", "callDuration"}.issubset(set(names))


def test_decode_cdr_roundtrip():
    xml = SPEC_PATH.read_text()
    spec_dict = xmltodict.parse(xml)
    fields = spec_dict["decoder"]["field"]
    if isinstance(fields, dict):
        fields = [fields]
    field_names = [f["@name"] for f in fields]
    asn_lines = ["DECODER DEFINITIONS ::= BEGIN", "Record ::= SEQUENCE {"]
    for idx, name in enumerate(field_names):
        comma = "," if idx < len(field_names) - 1 else ""
        asn_lines.append(f"    {name} IA5String OPTIONAL{comma}")
    asn_lines.append("}")
    asn_lines.append("END")
    asn_text = "\n".join(asn_lines)
    compiler = asn1tools.compile_string(asn_text, "ber")
    encoded = compiler.encode(
        "Record",
        {
            "callingNumber": "12345",
            "calledNumber": "67890",
            "callDuration": "30",
        },
    )

    records = decode_cdr(encoded, xml)
    assert records
    rec = records[0]
    assert rec["calling_number"] == "12345"
    assert rec["called_number"] == "67890"
    assert rec["duration"] == 30


def test_decode_sample_file_no_error():
    xml = SPEC_PATH.read_text()
    data = SAMPLE_CDR.read_bytes()
    # Ensure the decoder runs without raising exceptions
    decode_cdr(data, xml)
