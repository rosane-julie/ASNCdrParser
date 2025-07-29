# SENORA ASN

SENORA ASN is a web-based tool for parsing telecom Call Detail Records stored in binary ASN.1 format. It allows uploading large CDR files, viewing parsed records, and exporting data. Originally created by Rosane, this project now includes performance improvements and a convenient **Save As** feature to duplicate processed files.

## Features
- Efficient parsing for large and small files
- Database-backed storage of parsed records
- Searchable, sortable tables
- Export to CSV or JSON
- "Save As" to create new files from existing records
- Incremental parsing in batches of 1000 records
- Option to split a selection of records into a new file
- Faster incremental parsing using stored file offsets
- Optional parsing using a custom ASN.1 specification for better field mapping

## Running
Install dependencies with `pip install -r requirements.txt` or via `poetry install`.
The `requirements.txt` file lists all packages used by the app, including
`xmltodict`, which is required for decoder functionality. After installing,
start the app with:

```bash
python main.py
```

The application will be available at `http://localhost:5000`.

### ASN.1 specification

For more accurate decoding you can provide an ASN.1 specification. A simple
example is included in `specs/sample_cdr.asn` with a matching XML description
in `specs/sample_decoder.xml`. When uploading a CDR file you may optionally
upload either an ASN.1 spec or a decoder XML. SENORA ASN will attempt to
translate basic decoder XML files into an ASN.1 specification so subsequent
incremental parsing also uses it.

### Dynamic Decoder API

The `/decode-cdr` route provides a programmatic way to decode CDR files without storing them in the database. Submit a `POST` request with the following multipart form fields:

- `cdr_file` – the binary CDR file.
- `xml_spec` – a decoder XML describing the record layout.

The response is JSON containing a list of records under the key `records`. Each record includes any recognised fields such as `calling_number`, `called_number`, `duration` and timestamp values along with a `raw` object of the full decoded structure.

Example using the provided `specs/sample_decoder.xml`:

```bash
curl -X POST \
  -F "cdr_file=@uploads/test_cdr.dat" \
  -F "xml_spec=@specs/sample_decoder.xml" \
  http://localhost:5000/decode-cdr
```

A successful response will look similar to:

```json
{
  "records": [
    {
      "calling_number": "...",
      "called_number": "...",
      "duration": 30,
      "raw": { "callingNumber": "...", "calledNumber": "...", "callDuration": "30" }
    }
  ]
}
```
