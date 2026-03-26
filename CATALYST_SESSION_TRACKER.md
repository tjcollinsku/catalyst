# Catalyst Session Tracker

## Purpose

This file is the lightweight running log for session-to-session continuity.

Use it to track:
- open tasks
- immediate next steps
- blockers
- short end-of-session recaps

## Current Open Tasks

- Add proper `ModelAdmin` classes for remaining plain-registered models (Property, FinancialInstrument, junction tables)
- Enter first real case through the new intake API or UI
- Decide the next Phase 1 backend milestone after core case/document API completion

## Immediate Next Steps

- Exercise the expanded case/document API with a real intake payload set
- Add proper `ModelAdmin` classes for remaining plain-registered models
- Decide whether to keep the API Django-native or introduce DRF later

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

## Update Pattern

At the end of each session, update:
- `Current Open Tasks`
- `Immediate Next Steps`
- `Current Blockers`
- newest entry under `Session Recap Log`
