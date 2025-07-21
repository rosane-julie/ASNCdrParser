# SENORA ASN

SENORA ASN is a web-based tool for parsing telecom Call Detail Records stored in binary ASN.1 format. It allows uploading large CDR files, viewing parsed records, and exporting data. Originally created by Rosane, this project now includes performance improvements and a convenient **Save As** feature to duplicate processed files.

## Features
- Efficient parsing for large and small files
- Database-backed storage of parsed records
- Searchable, sortable tables
- Export to CSV or JSON
- "Save As" to create new files from existing records

## Running
Install dependencies with `pip install -r requirements.txt` or via `poetry install`, then start the app with:

```bash
python main.py
```

The application will be available at `http://localhost:5000`.
