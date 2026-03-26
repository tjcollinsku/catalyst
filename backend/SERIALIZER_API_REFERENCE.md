# Serializer and API Reference (Investigations App)

This is a beginner-friendly reference for what we are building and how the pieces connect.

## What We Are Writing

We are building a small API layer for investigations data.

- Models define what is stored in the database.
- Serializers validate incoming JSON and shape outgoing JSON.
- Views handle HTTP requests and responses.
- URLs map endpoint paths to view functions.
- Tests verify behavior and protect against regressions.

## Project Connection Map

In this project, the main files are:

- backend/investigations/models.py
- backend/investigations/serializers.py
- backend/investigations/views.py
- backend/investigations/urls.py
- backend/investigations/tests.py

Flow:

1. A client sends an HTTP request.
2. URL routing sends it to a view.
3. The view parses JSON and calls a serializer.
4. The serializer validates data and/or serializes model objects.
5. The view saves or reads model data.
6. The view returns JSON response.

## serializers.py Walkthrough

### 1) _serialize_datetime(value)

Purpose:

- Convert Python datetime values into JSON-safe ISO strings.
- Return null if no datetime exists.

Why this matters:

- JSON cannot directly represent Python datetime objects.

### 2) serialize_document(document)

Purpose:

- Convert a Document model instance into a plain dictionary for API output.

Returns fields like:

- id
- filename
- file_path
- sha256_hash
- file_size
- doc_type
- source_url
- ocr_status
- uploaded_at
- updated_at

### 3) serialize_case(case)

Purpose:

- Convert a Case model instance into a plain dictionary for API output.

Returns fields like:

- id
- name
- status
- notes
- referral_ref
- created_at
- updated_at

### 4) serialize_case_detail(case)

Purpose:

- Build an expanded case response.
- Start from serialize_case(case), then add documents.

Behavior:

- Includes documents ordered newest first.

### 5) CaseIntakeSerializer class

Purpose:

- Validate incoming JSON for creating a Case.
- Save a new Case when validation passes.

#### allowed_fields

- Whitelist of permitted incoming keys.
- Unexpected keys are rejected.

#### __init__(data=None, instance=None)

- Stores input payload and optional model instance.
- Initializes containers for validated_data and errors.

#### errors property

- Exposes validation errors collected by is_valid().

#### data property

- Returns serialized output for instance if present.
- Returns empty object if instance is missing.

#### is_valid()

Validation pipeline:

1. Reset previous errors and validated state.
2. Ensure payload is a JSON object (dictionary).
3. Reject unexpected fields.
4. Build candidate values with defaults.
5. Run Django model validation through full_clean(validate_unique=False).
6. If validation fails, store error messages.
7. If validation succeeds, store cleaned values in validated_data.

Defaults used:

- status defaults to the model default if omitted.
- notes defaults to empty string.
- referral_ref defaults to empty string.

#### save()

- Requires is_valid() to run first.
- Creates and stores a new Case row using validated_data.
- Returns the created model instance.

## API Endpoints (Current)

### Case Collection

- GET /api/cases/
- POST /api/cases/

Optional GET filters:

- status (ACTIVE, PAUSED, REFERRED, CLOSED)
- q (case-insensitive name contains search)

Optional GET sorting:

- order_by (created_at, name, status, id)
- direction (asc, desc)

### Case Detail

- GET /api/cases/<uuid>/
- PATCH /api/cases/<uuid>/
- DELETE /api/cases/<uuid>/

### Case Document Collection

- GET /api/cases/<uuid>/documents/
- POST /api/cases/<uuid>/documents/

Optional GET filters:

- doc_type (DEED, UCC, IRS_990, AUDITOR, OTHER)
- ocr_status (PENDING, COMPLETED, FAILED, NOT_NEEDED)
- uploaded_from (ISO date or datetime)
- uploaded_to (ISO date or datetime)

Optional GET sorting:

- order_by (uploaded_at, filename, file_size, doc_type, ocr_status, id)
- direction (asc, desc)

### Case Document Detail

- GET /api/cases/<uuid>/documents/<uuid>/
- PATCH /api/cases/<uuid>/documents/<uuid>/
- DELETE /api/cases/<uuid>/documents/<uuid>/

## Shared Pagination Contract (Collection GET Endpoints)

Both collection endpoints use the same query params and response metadata:

- Query params:
	- limit (default 25, min 1, max 100)
	- offset (default 0, min 0)
- Response keys:
	- count
	- limit
	- offset
	- next_offset
	- previous_offset
	- results

Example shape:

```json
{
	"count": 57,
	"limit": 25,
	"offset": 25,
	"next_offset": 50,
	"previous_offset": 0,
	"results": []
}
```

Notes:

- next_offset is null when there is no next page.
- previous_offset is null on the first page.
- ordering is deterministic for ties by sorting on timestamp then id descending.

## Filter Examples

Case list with status and name search:

```http
GET /api/cases/?status=ACTIVE&q=example_township
```

Document list with type and OCR status filters:

```http
GET /api/cases/<case_uuid>/documents/?doc_type=DEED&ocr_status=COMPLETED
```

Case list sorted by name ascending:

```http
GET /api/cases/?order_by=name&direction=asc
```

Document list sorted by file size ascending:

```http
GET /api/cases/<case_uuid>/documents/?order_by=file_size&direction=asc
```

## Update and Delete Examples

Patch document metadata:

```http
PATCH /api/cases/<case_uuid>/documents/<document_uuid>/
Content-Type: application/json

{
	"doc_type": "DEED",
	"ocr_status": "COMPLETED",
	"source_url": "https://example.org/updated"
}
```

Delete a document:

```http
DELETE /api/cases/<case_uuid>/documents/<document_uuid>/
```

Response:

- 204 No Content on success

Delete a case:

```http
DELETE /api/cases/<case_uuid>/
```

Responses:

- 204 No Content when deletion succeeds
- 409 Conflict when related records prevent deletion

## Error Shape

Validation and parsing errors return:

```json
{
	"errors": {
		"non_field_errors": ["..."]
	}
}
```

Model validation errors return field-keyed messages:

```json
{
	"errors": {
		"field_name": ["..."]
	}
}
```

## How This Connects During POST /api/cases/

At a high level:

1. Client sends POST request to api/cases/.
2. View parses JSON body.
3. View creates CaseIntakeSerializer with payload.
4. View calls is_valid().
5. If invalid, response is 400 with errors.
6. If valid, serializer saves Case to database.
7. Response is 201 with the serialized Case data.

## Why This Pattern Is Useful

- Keeps view logic clean and focused.
- Centralizes validation and output shaping.
- Makes behavior easier to test.
- Protects database from malformed input.

## Suggested Next Step

Add case detail PATCH support with a controlled update serializer for status, notes, and referral_ref.
