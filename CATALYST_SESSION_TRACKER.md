# Catalyst Session Tracker

## Purpose

This file is the lightweight running log for session-to-session continuity.

Use it to track:
- open tasks
- immediate next steps
- blockers
- short end-of-session recaps

## Current Open Tasks

- Begin Phase 2: ProPublica Nonprofit Explorer API connector (990 data)
- Begin Phase 2: Ohio SOS business search connector
- Begin Phase 2: Entity extraction (person/org/date/amount) from extracted text
- Enter first real case through the intake UI to exercise the hardened upload workflow

## Immediate Next Steps

- Build `entity_extraction.py` first pass (deterministic rules: names/orgs/dates/amounts)
- Wire entity extraction into `document_upload` after extraction/classification
- Persist extracted entities into existing `Person` and `Organization` models with idempotent upsert behavior
- Add entity extraction matrix tests for OCR-noisy text and duplicate entity handling

## Current Blockers

- No blockers

## Session Recap Log

### 2026-03-20 (Session 1)
- Added recurring recap documents for architecture and file walkthroughs
- Added this tracker file for open tasks, next steps, and blockers
- Project in stable state for continuing Phase 1 work

### 2026-03-20 (Session 2)
- Fixed Docker Compose obsolete `version` warning — removed `version: "3.9"` line
- Upgraded Django admin registrations with proper `ModelAdmin` classes
- `GovernmentReferral` admin: list view, status/agency filters, search, `filing_date` locked read-only
- `AuditLog` admin: fully enforced read-only — add, change, delete all disabled
- `Case`, `Document`, `Person`, `Organization`, `Finding` all upgraded with list views and filters
- Django system check passes with 0 issues

### 2026-03-20 (Session 3)
- Fixed Django → PostgreSQL authentication: `load_dotenv()` added to `settings.py` so `.env` is loaded before DB config is read
- Reset `catalyst_user` password in Docker container to match `.env`
- Confirmed Django connects to PostgreSQL successfully
- `showmigrations` verified: 18 migrations applied across all apps
- `\dt` confirmed: 23 tables present in database including all Phase 1 domain tables
- Database is fully built and Django is live against it

### 2026-03-26 (Session 4)
- Added `investigations/serializers.py` for case intake validation and JSON serialization
- Added Django-native JSON API endpoints for case list, create, and detail under `/api/cases/`
- Added API tests covering create, validation failure, detail payload, and list ordering
- Updated project docs so the current milestone state matches the codebase

### 2026-03-26 (Session 5)
- Expanded the JSON API from basic intake to a fuller case/document workflow surface
- Added case PATCH and DELETE support with conflict handling for protected related records
- Added case and document list pagination metadata, filters, date-range filters, and allowlisted sorting
- Added case-scoped document detail, PATCH, and DELETE endpoints
- Added strict SHA-256 validation for document intake payloads
- Grew the investigations test suite to 41 passing tests covering create, list, detail, update, delete, filters, sorting, and validation paths
- Added `backend/API_COOKBOOK.md` and refreshed `backend/SERIALIZER_API_REFERENCE.md`

### 2026-03-26 (Session 6) — Phase 1 Complete
- Added NOTARY and TRUSTEE to PersonRole enum (run makemigrations to apply)
- Fixed stale `orc_reference` field reference in FindingAdmin — updated to current Finding fields (severity, confidence, status, signal_type, signal_rule_id)
- Added proper ModelAdmin classes for all 6 plain-registered models: Property, FinancialInstrument, PersonDocument, OrgDocument, PersonOrganization, PropertyTransaction
- Confirmed Phase 1 minimal dashboard is complete — Django template views (case_list, case_detail, case_form, document_upload) satisfy the Phase 1 charter requirement; React frontend deferred to Phase 3 per charter
- Phase 1 is fully closed out — all charter items complete

### 2026-03-26 (Session 7) — Phase 2 Processing Pipeline Foundations
- Implemented direct PDF text extraction using PyMuPDF and wired automatic extraction into `document_upload`
- Added synchronous OCR fallback for scanned PDFs via Tesseract + Pillow with 30 MB gate for sync processing
- Added rule-based document classification service and wired automatic classification when user keeps `doc_type=OTHER`
- Expanded `DocumentType` taxonomy and added `is_generated` + `doc_subtype` fields for evidence/output separation
- Added and applied migrations `0005` and `0006`; database schema updated and validated
- Hardened `Person.role_tags` with `PersonRole` choices and added `Person.is_deceased()` helper
- Added structured upload decision logging with dedicated logger `investigations.upload_pipeline`
- Logging is production-ready by default, quiet in test/dev by default, and toggleable with `ENABLE_UPLOAD_PIPELINE_LOGS=true`
- Expanded test coverage to 46 passing tests, including upload decision matrix and generated-flag behavior

## Update Pattern

At the end of each session, update:
- `Current Open Tasks`
- `Immediate Next Steps`
- `Current Blockers`
- newest entry under `Session Recap Log`
