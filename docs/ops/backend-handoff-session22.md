# Catalyst Backend Catch-Up — Session 22 Handoff

> **Purpose:** Paste this entire document as your opening message in a new chat to bring a fresh Claude session up to speed on the Catalyst backend. It provides everything needed to implement the 4 priority backend endpoints without re-reading the full codebase.

---

## 1. What Is Catalyst?

Catalyst is an **investigation intelligence platform** for detecting fraud in county government records (deeds, UCC filings, 990s, court records, etc.). It's built for a county prosecutor's office in Ohio.

**Stack:**
- **Backend:** Django 5.1 + PostgreSQL 16 (single `investigations` app)
- **Frontend:** React 18 + TypeScript 5.6 + Vite 5 (SPA with React Router v6)
- **No Django REST Framework** — all serializers and views are hand-rolled (plain `JsonResponse`, manual validation classes)
- **No authentication yet** — all endpoints are `@csrf_exempt` for development

The frontend is fully built through Phase E (polish). The backend needs 4 new endpoints to catch up with what the frontend already calls.

---

## 2. Database Schema (23 Tables, 12 Migrations)

### Core Models

| Model | Table | PK | Key Fields |
|-------|-------|----|------------|
| `Case` | `cases` | UUID | name, status (ACTIVE/PAUSED/REFERRED/CLOSED), notes, referral_ref |
| `Document` | `documents` | UUID | case FK, filename, file_path, sha256_hash, file_size, doc_type (19 choices), is_generated, doc_subtype, source_url, ocr_status, extracted_text |
| `Person` | `persons` | UUID | case FK, full_name, aliases (ArrayField), role_tags (ArrayField, 17 PersonRole choices), date_of_death, notes |
| `Organization` | `organizations` | UUID | case FK, name, org_type, ein, registration_state, status, formation_date, notes |
| `Property` | `properties` | UUID | case FK, parcel_number, address, county, assessed_value, purchase_price, valuation_delta (GeneratedField) |
| `FinancialInstrument` | `financial_instruments` | UUID | case FK, instrument_type, filing_number, filing_date, signer FK→Person, secured_party_id, debtor_id, amount, anomaly_flags |

### Junction/Relationship Tables

| Model | Table | Purpose |
|-------|-------|---------|
| `PersonDocument` | `person_document` | Links Person↔Document with page_reference, context_note |
| `OrgDocument` | `org_document` | Links Organization↔Document |
| `PersonOrganization` | `person_org` | Links Person↔Organization with role, start/end dates |
| `PropertyTransaction` | `property_transaction` | Links Property↔Document with buyer/seller UUIDs, price |
| `FindingEntity` | `finding_entity` | Links Finding↔any entity (polymorphic via entity_id + entity_type) |
| `FindingDocument` | `finding_document` | Links Finding↔Document |
| `EntitySignal` | `entity_signal` | Links Signal↔any entity (polymorphic) |

### Detection & Analysis Models

| Model | Table | PK | Key Fields |
|-------|-------|----|------------|
| `Signal` | `signals` | UUID | case FK, rule_id (SR-001 through SR-010), severity, status (OPEN/CONFIRMED/DISMISSED/ESCALATED), trigger_entity_id, trigger_doc FK, investigator_note, detected_summary, detected_at |
| `Detection` | `detections` | UUID | case FK, signal_type (16 SignalType choices), severity, status, detection_method, primary/secondary_document FKs, person/org/property/financial_instrument FKs, evidence_snapshot (JSON), confidence_score, investigator_note |
| `Finding` | `findings` | UUID | case FK, detection FK, title, narrative, severity, confidence, status, signal_type, signal_rule_id, legal_refs (ArrayField) |
| `GovernmentReferral` | `government_referrals` | AutoField int | case FK, agency_name, submission_id, filing_date (immutable after creation), contact_alias, status (DRAFT/SUBMITTED/ACKNOWLEDGED/CLOSED), notes |
| `AuditLog` | `audit_log` | UUID | case_id, table_name, record_id, action, before/after_state (JSON), performed_by, performed_at, ip_address, notes |

### Migrations

12 migrations exist (0001 through 0012). The latest is `0012_finding_detection.py`. Any new models will need migration 0013+.

---

## 3. Existing API Surface

All endpoints live in `backend/investigations/urls.py` and `views.py`.

### Currently Working Endpoints

```
GET/POST   /api/cases/                              — List/create cases (paginated, filterable)
GET/PATCH/DELETE /api/cases/<uuid>/                  — Case detail/update/delete
GET/POST   /api/cases/<uuid>/documents/              — List/create documents (paginated, filterable)
POST       /api/cases/<uuid>/documents/bulk/         — Multipart bulk upload (up to 50 files)
POST       /api/cases/<uuid>/documents/process-pending/ — Run deferred OCR/extraction
GET/PATCH/DELETE /api/cases/<uuid>/documents/<uuid>/ — Document detail/update/delete
GET        /api/cases/<uuid>/signals/                — Case signals (paginated, filterable)
GET/PATCH  /api/cases/<uuid>/signals/<uuid>/         — Signal detail/update
GET        /api/signal-summary/                      — Highest severity per case (for sidebar badges)
GET/POST   /api/cases/<uuid>/referrals/              — Case referrals list/create
GET/PATCH/DELETE /api/cases/<uuid>/referrals/<int>/  — Referral detail/update/delete
POST       /api/cases/<uuid>/referral-memo/          — Generate referral memo document
GET/POST   /api/cases/<uuid>/detections/             — Case detections list/create
GET/PATCH/DELETE /api/cases/<uuid>/detections/<uuid>/ — Detection detail/update/delete
POST       /api/cases/<uuid>/reevaluate-signals/     — Re-run all signal rules

# Cross-case endpoints (added Session 21, Phase C):
GET        /api/signals/                             — All signals across cases (filterable by status, severity, case_id, rule_id)
GET        /api/referrals/                           — All referrals across cases (filterable by status, agency, case_id)
GET        /api/entities/                            — All entities across cases (unions Person, Org, Property, FinancialInstrument)
GET        /api/activity-feed/                       — Recent AuditLog entries
```

### API Patterns to Follow

Every endpoint follows these conventions — new endpoints **must** match:

1. **Pagination:** `_parse_limit_offset(request)` returns (limit, offset, error_response). Max 100 per page. Response shape:
   ```json
   { "count": 42, "limit": 25, "offset": 0, "next_offset": 25, "previous_offset": null, "results": [...] }
   ```

2. **Sorting:** `_parse_sort_params(request, allowed_fields=..., default_field=...)` validates `order_by` and `direction` (asc/desc) query params.

3. **JSON body parsing:** `_parse_json_body(request)` returns (payload_dict, error_response).

4. **Error format:** Always `{"errors": {"field_name": ["Message."]}}` with appropriate HTTP status.

5. **Serializers:** Hand-rolled classes with `is_valid() -> bool`, `errors`, `data`, `save()`. No DRF.

6. **Decorators:** `@csrf_exempt` + `@require_http_methods([...])` on every view.

7. **UUID PKs:** All model lookups use `get_object_or_404(Model, pk=uuid)`.

---

## 4. Existing Serializer Functions

These are already defined in `serializers.py` and available for reuse:

```python
serialize_case(case) -> dict           # id, name, status, notes, referral_ref, timestamps
serialize_case_detail(case) -> dict    # Above + documents list
serialize_document(document) -> dict   # Full document fields
serialize_signal(signal) -> dict       # Includes rule title/description from RULE_REGISTRY
serialize_detection(detection) -> dict # Full detection fields with all FK IDs
serialize_referral(referral) -> dict   # Full referral fields
serialize_person(person) -> dict       # Adds entity_type="person", case_id
serialize_organization(org) -> dict    # Adds entity_type="organization", case_id
serialize_property(prop) -> dict       # Adds entity_type="property", case_id
serialize_financial_instrument(fi) -> dict  # Adds entity_type="financial_instrument", case_id
serialize_audit_log(entry) -> dict     # Audit log entry
```

---

## 5. Signal Detection Engine

`signal_rules.py` implements 10 rules (SR-001 through SR-010):

| Rule | Severity | Description |
|------|----------|-------------|
| SR-001 | CRITICAL | Deceased person named in post-death document |
| SR-002 | CRITICAL | Entity named before formation date |
| SR-003 | HIGH | Purchase price >50% deviation from assessed value |
| SR-004 | HIGH | UCC amendment burst (3+ in 24 hours) |
| SR-005 | HIGH | Zero-consideration transfer |
| SR-006 | MEDIUM | Missing required fields |
| SR-007 | MEDIUM | 990 revenue anomaly |
| SR-008 | MEDIUM | Self-dealing indicator |
| SR-009 | HIGH | Phantom officer |
| SR-010 | MEDIUM | Charter status conflict |

Entry points: `evaluate_document()`, `evaluate_case()`, `persist_signals()`.

The `RULE_REGISTRY` dict maps rule_id → `RuleInfo(rule_id, severity, title, description)` and is used by `serialize_signal()` to attach human-readable titles.

---

## 6. The 4 Endpoints to Build (Priority Order)

### 6A. Full-Text Search — `GET /api/search/`

**Frontend calls:** `searchAll(query, {type?, case_id?})` in `api.ts`
**Frontend URL:** `/api/search/?q=...&type=...&case_id=...`

**Expected response shape** (from `frontend/src/types.ts`):
```typescript
interface SearchResponse {
    query: string;
    total: number;
    results: SearchResult[];
}

interface SearchResult {
    type: "case" | "signal" | "entity" | "document";
    id: string;
    title: string;
    snippet: string;
    score: number;
    case_id?: string;
    case_name?: string;
    url: string;
}
```

**Implementation approach:**
- Query `Case.name`, `Document.filename + extracted_text`, `Person.full_name + aliases`, `Organization.name`, `Signal.detected_summary`, etc.
- Use PostgreSQL `SearchVector`/`SearchQuery` for full-text search, or simple `__icontains` for MVP
- Filter by `type` (case/signal/entity/document) and `case_id`
- Return unified results sorted by relevance score
- The frontend currently does client-side search as a fallback — this endpoint replaces that

### 6B. Case Export — `GET /api/cases/<uuid>/export/`

**Frontend calls:** `exportCaseReport(caseId, format)` in `api.ts`
**Frontend URL:** `/api/cases/<uuid>/export/?format=json|csv`

**Expected response shape:**
```typescript
interface ReportExportResult {
    format: string;
    filename: string;
    download_url: string;
}
```

**Implementation approach:**
- Gather all case data: case details, documents, signals, detections, findings, referrals, entities (persons, orgs, properties, financial instruments)
- For JSON: serialize everything into a nested structure and return as downloadable file
- For CSV: flatten into tabular format (one sheet per entity type) — could use Python `csv` module
- Store generated file in media storage, return a URL the frontend can use to download
- Alternative simpler approach: return the data directly as JSON response body for JSON format, or as `text/csv` content-type for CSV format

### 6C. Entity Detail — `GET /api/entities/<type>/<id>/`

**Frontend calls:** Used in `EntityDetailView.tsx`
**Frontend URL:** `/api/entities/<type>/<id>/` where type is person/organization/property/financial_instrument

**Expected response:** The entity's full serialized data plus:
- Related documents (via junction tables)
- Related signals (via EntitySignal)
- Related cases
- Related findings (via FindingEntity)
- Relationship data (PersonOrganization for persons, PropertyTransaction for properties)

**Implementation approach:**
- Add URL pattern: `path("api/entities/<str:entity_type>/<uuid:entity_id>/", views.api_entity_detail)`
- Look up the correct model based on `entity_type`
- Serialize with related data attached
- Currently the `EntityDetailView` component fetches entity data from the cross-case `/api/entities/` endpoint and filters client-side — this dedicated endpoint would be more efficient

### 6D. Investigator Notes CRUD — New Model + API

**Not yet in the database** — needs a new model and migration.

**Purpose:** Let investigators attach timestamped notes to cases, documents, entities, signals, or detections.

**Suggested model:**
```python
class InvestigatorNote(UUIDPrimaryKeyModel):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="investigator_notes")
    target_type = models.CharField(max_length=50)  # "case", "document", "signal", "detection", "person", etc.
    target_id = models.UUIDField()
    content = models.TextField()
    created_by = models.CharField(max_length=255, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "investigator_notes"
        indexes = [
            models.Index(fields=["case"], name="idx_inv_notes_case"),
            models.Index(fields=["target_type", "target_id"], name="idx_inv_notes_target"),
        ]
```

**Endpoints:**
```
GET/POST   /api/cases/<uuid>/notes/                 — List/create notes for a case
GET/PATCH/DELETE /api/cases/<uuid>/notes/<uuid>/     — Note detail/update/delete
```

---

## 7. Key Backend Files

```
backend/
├── catalyst/
│   ├── settings.py          — Django settings (PostgreSQL config, MEDIA_ROOT, etc.)
│   └── urls.py              — Root URL conf (includes investigations.urls)
├── investigations/
│   ├── models.py            — All 23 models + TextChoices enums
│   ├── views.py             — All API views (~1150 lines)
│   ├── urls.py              — URL patterns (currently 17 patterns)
│   ├── serializers.py       — All serializer classes + serialize_* functions (~1000 lines)
│   ├── signal_rules.py      — SR-001 through SR-010 detection engine
│   ├── extraction.py        — PDF text extraction (pdfplumber + OCR fallback)
│   ├── classification.py    — Document auto-classification from extracted text
│   ├── entity_extraction.py — NLP entity extraction from document text
│   ├── entity_resolution.py — Fuzzy matching to deduplicate entities
│   ├── entity_normalization.py — Name/address normalization
│   ├── forms.py             — Django forms (legacy HTML views)
│   ├── admin.py             — Django admin registration
│   ├── logging_utils.py     — Structured logging helpers
│   ├── ohio_sos_connector.py      — Ohio Secretary of State API
│   ├── ohio_aos_connector.py      — Ohio Attorney's Office scraper
│   ├── county_auditor_connector.py — County auditor data
│   ├── county_recorder_connector.py — County recorder data
│   ├── irs_connector.py     — IRS 990 data via ProPublica
│   ├── propublica_connector.py    — ProPublica nonprofit API
│   ├── verify_recorder_portals.py — Portal connectivity checker
│   ├── management/commands/
│   │   └── dedup_documents.py     — Management command for document deduplication
│   ├── migrations/          — 0001 through 0012
│   └── tests/
│       ├── test_api.py      — API endpoint tests
│       ├── test_signals.py  — Signal detection tests
│       └── test_*.py        — Connector tests
```

---

## 8. Frontend API Client Reference

The frontend's `api.ts` file shows exactly what the frontend expects. Here are the Phase D endpoints that need backend implementation:

```typescript
// SEARCH — frontend falls back to client-side search if this 404s
export async function searchAll(query, filters) {
    return request(`/api/search/?q=${query}&type=${filters.type}&case_id=${filters.case_id}`);
}

// EXPORT — frontend shows error toast if this 404s
export async function exportCaseReport(caseId, format) {
    return request(`/api/cases/${caseId}/export/?format=${format}`);
}
```

The entity detail view currently uses the cross-case `/api/entities/?type=X&case_id=Y` endpoint and filters results — there's no dedicated single-entity endpoint yet.

---

## 9. Development Notes

- **Python version:** 3.12+
- **Virtual env:** `backend/venv/` (may need to be created)
- **Run server:** `cd backend && python manage.py runserver`
- **Run tests:** `cd backend && python manage.py test investigations`
- **Make migrations:** `cd backend && python manage.py makemigrations investigations`
- **Migrate:** `cd backend && python manage.py migrate`
- **Vite dev server** proxies `/api/` to Django (configured in `frontend/vite.config.ts`)

---

## 10. Instructions

You are continuing development on the Catalyst backend. I am Tyler, a beginner programmer in the IBM Full-Stack Software Development certificate program. When explaining concepts, please be detailed and thorough — I want to understand not just what something is, but how it works and why it matters. Use visual explanations wherever possible (diagrams, step-by-step breakdowns, concrete examples). Avoid jargon without explanation, and build on concepts progressively.

**Your task:** Implement the 4 endpoints described in Section 6, in priority order (6A → 6B → 6C → 6D). For each one:
1. Show me the code changes needed (models, serializers, views, urls)
2. Explain the design decisions
3. Run tests to verify
4. Commit with clear messages

**Important patterns to follow:**
- Match the existing hand-rolled serializer pattern (no DRF)
- Use `@csrf_exempt` + `@require_http_methods` decorators
- Use `_parse_limit_offset()` and `_parse_sort_params()` helpers for paginated endpoints
- Return errors as `{"errors": {"field": ["message"]}}` format
- All new models use `UUIDPrimaryKeyModel` base class
- Add proper indexes on ForeignKey and frequently-queried fields

Start by reading the key files listed in Section 7 to orient yourself, then begin with endpoint 6A (Full-Text Search).
