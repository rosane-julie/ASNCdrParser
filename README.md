# SENORA ASN

SENORA ASN is a web-based tool for parsing telecom Call Detail Records stored in binary ASN.1 format. It allows uploading large CDR files, viewing parsed records, and exporting data. Originally created by Rosane, this project now includes performance improvements and a convenient **Save As** feature to duplicate processed files.

## Features
- Efficient parsing for large and small files
- Database-backed storage of parsed records
- Searchable, sortable tables
- Export to CSV or JSON
- "Save As" to create new files from existing records
- Incremental parsing in batches of 100 records
- Option to split a selection of records into a new file
- Faster incremental parsing using stored file offsets
- Optional parsing using a custom ASN.1 specification for better field mapping

## Running
Install dependencies with `pip install -r requirements.txt` or via `poetry install`, then start the app with:

```bash
python main.py
```

The application will be available at `http://localhost:5000`.

### ASN.1 specification

For more accurate decoding you can provide an ASN.1 specification. A simple
example is included in `specs/sample_cdr.asn` with a matching XML description
in `specs/sample_decoder.xml`. When uploading a CDR file you may optionally
upload the ASN.1 spec to map fields exactly. The uploaded spec path is stored so
subsequent incremental parsing also uses it.
