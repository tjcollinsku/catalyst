# API Cookbook

Quick copy/paste examples for the current investigations API.

## Base Patterns

- JSON body requests use Content-Type: application/json.
- Collection endpoints support pagination with limit and offset.
- Collection endpoints support sorting with order_by and direction.
- Collection responses include count, limit, offset, next_offset, previous_offset, and results.

## Cases

### Create Case

```bash
curl -X POST http://localhost:8000/api/cases/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Example Township Intake",
    "status": "ACTIVE",
    "notes": "Initial intake.",
    "referral_ref": "IC3-78A987D4"
  }'
```

### List Cases (Paginated)

```bash
curl "http://localhost:8000/api/cases/?limit=25&offset=0"
```

### List Cases (Filters)

```bash
curl "http://localhost:8000/api/cases/?status=ACTIVE&q=example_township&created_from=2026-03-01&created_to=2026-03-31"
```

### List Cases (Sorting)

```bash
curl "http://localhost:8000/api/cases/?order_by=name&direction=asc"
```

### Get Case Detail

```bash
curl "http://localhost:8000/api/cases/<case_uuid>/"
```

### Patch Case Detail

Allowed fields: status, notes, referral_ref

```bash
curl -X PATCH "http://localhost:8000/api/cases/<case_uuid>/" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "PAUSED",
    "notes": "Waiting on new documents.",
    "referral_ref": "NEW-REF-2026"
  }'
```

### Delete Case

```bash
curl -X DELETE "http://localhost:8000/api/cases/<case_uuid>/"
```

Expected responses:

- 204 No Content when the case has no related records.
- 409 Conflict when related records prevent deletion.

## Case Documents

### Create Document

```bash
curl -X POST "http://localhost:8000/api/cases/<case_uuid>/documents/" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "packet.pdf",
    "file_path": "cases/<case_uuid>/packet.pdf",
    "sha256_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "file_size": 2048,
    "doc_type": "OTHER",
    "source_url": "https://example.org/packet",
    "ocr_status": "PENDING"
  }'
```

### List Documents (Paginated)

```bash
curl "http://localhost:8000/api/cases/<case_uuid>/documents/?limit=25&offset=0"
```

### List Documents (Filters)

```bash
curl "http://localhost:8000/api/cases/<case_uuid>/documents/?doc_type=DEED&ocr_status=COMPLETED&uploaded_from=2026-03-01&uploaded_to=2026-03-31"
```

### List Documents (Sorting)

```bash
curl "http://localhost:8000/api/cases/<case_uuid>/documents/?order_by=file_size&direction=asc"
```

### Get Document Detail

```bash
curl "http://localhost:8000/api/cases/<case_uuid>/documents/<document_uuid>/"
```

### Patch Document Detail

Allowed fields: doc_type, source_url, ocr_status, extracted_text

```bash
curl -X PATCH "http://localhost:8000/api/cases/<case_uuid>/documents/<document_uuid>/" \
  -H "Content-Type: application/json" \
  -d '{
    "doc_type": "DEED",
    "ocr_status": "COMPLETED",
    "source_url": "https://example.org/updated"
  }'
```

### Delete Document

```bash
curl -X DELETE "http://localhost:8000/api/cases/<case_uuid>/documents/<document_uuid>/"
```

Expected response: 204 No Content

## Error Shape

```json
{
  "errors": {
    "non_field_errors": ["..."]
  }
}
```

Field errors use the field name key:

```json
{
  "errors": {
    "sha256_hash": ["Enter a valid 64-character hexadecimal SHA-256 hash."]
  }
}
```
