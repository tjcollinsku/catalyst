# Catalyst System Overview

## Purpose

Catalyst is being built as an intelligence triage and investigation support platform.

Its current Phase 1 focus is:
- defining the database schema
- scaffolding the Django backend
- preserving defensible audit history
- preparing for cloud deployment with trustworthy timestamps

## Current Architecture

### Backend
- Django project lives in `backend/`
- Primary app is `investigations`
- Django models now represent the Phase 1 schema

### Database
- PostgreSQL 16 runs locally in Docker container `catalyst_db` (port 5432)
- SQL bootstrap migrations live in `database/migrations/`
- Django migrations live in `backend/investigations/migrations/`
- 18 Django migrations applied; 23 tables confirmed in database
- Django connects via credentials in `.env` at project root — loaded by `load_dotenv()` in `settings.py`

### Key Design Direction
- SQL-first baseline for initial schema clarity
- Django-managed evolution after bootstrap
- UTC / timezone-aware timestamps for audit-sensitive records
- append-only / immutable behavior where audit accuracy matters

## Phase 1 Tables Implemented
- `cases`
- `documents`
- `persons`
- `organizations`
- `properties`
- `financial_instruments`
- `findings`
- `audit_log`
- `person_document`
- `org_document`
- `person_org`
- `property_transaction`
- `government_referrals`

## Government Referrals

The `government_referrals` table now exists in both:
- Django model/migration flow
- SQL migration flow

It is hardened so that:
- `filing_date` is auto-set if omitted
- `filing_date` cannot be edited after creation
- timestamps are timezone-aware for cloud accuracy

## Admin Layer

Django admin is now configured with proper `ModelAdmin` classes for the primary models:
- List displays, filters, and search on all major models
- `GovernmentReferral.filing_date` locked read-only in admin (mirrors DB trigger)
- `AuditLog` is fully read-only in admin — no add, change, or delete allowed

## API Layer

- Django-native JSON intake endpoints now exist for case workflows
- `GET /api/cases/` returns paginated case list data with filters and allowlisted sorting
- `POST /api/cases/` validates and creates a case record from JSON payloads
- `GET /api/cases/<uuid>/` returns case metadata plus linked document metadata
- `PATCH /api/cases/<uuid>/` supports controlled case updates for status, notes, and referral reference
- `DELETE /api/cases/<uuid>/` supports case deletion with conflict handling when related records exist
- `GET /api/cases/<uuid>/documents/` returns paginated, filterable, sortable document lists scoped to a case
- `POST /api/cases/<uuid>/documents/` validates and creates a document record under the case
- `GET /api/cases/<uuid>/documents/<uuid>/` returns one document scoped to a case
- `PATCH /api/cases/<uuid>/documents/<uuid>/` supports controlled document metadata updates
- `DELETE /api/cases/<uuid>/documents/<uuid>/` deletes a case-scoped document
- Validation and serialization logic is isolated in `investigations/serializers.py`
- API usage is documented in `backend/SERIALIZER_API_REFERENCE.md` and `backend/API_COOKBOOK.md`

## Session Recap Log

### 2026-03-20 (Session 1)
- Phase 1 Django backend scaffold created
- initial investigation schema modeled in Django
- SQL bootstrap path corrected under `database/migrations/`
- PostgreSQL container started and verified
- `government_referrals` added and migrated
- `filing_date` hardened with DB defaults and immutability trigger

### 2026-03-20 (Session 2)
- Removed obsolete `version` field from `docker-compose.yml` — no more warnings
- Upgraded Django admin with proper `ModelAdmin` classes across all key models
- AuditLog admin locked completely — append-only enforced at admin layer

### 2026-03-20 (Session 3)
- Fixed Django → PostgreSQL auth: `load_dotenv()` added to `settings.py`
- Reset `catalyst_user` DB password to match `.env`
- 18 migrations confirmed applied; 23 tables confirmed in PostgreSQL
- Database fully live — Django connected and verified
- Next milestone: intake API (`serializers.py`, `views.py`, `urls.py`)

### 2026-03-26 (Session 4)
- Intake API implemented without adding DRF dependency
- JSON endpoints now cover case list, case create, and case detail workflows
- API test coverage added for core happy path and validation path
- Next milestone shifts from API scaffolding to real data entry and admin cleanup

### 2026-03-26 (Session 5)
- The backend API expanded from basic intake into a broader case/document management surface
- Collection endpoints now support pagination metadata, date-range filtering, field filters, and allowlisted sorting
- Detail endpoints now support PATCH updates for both cases and documents
- Delete semantics added for documents and cases, with case delete conflict handling when related records exist
- Strict document SHA-256 validation added at intake time
- API docs were formalized with a narrative reference and a copy/paste cookbook
- Test coverage expanded to 41 passing API tests, giving the Phase 1 backend a stronger regression safety net

## Next Updates

Use this file for:
- high-level architecture recap
- milestone tracking
- decisions and rationale
- end-of-session summaries
