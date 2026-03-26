# Catalyst File Walkthrough

## Purpose

This file tracks what the important project files do so we can update it incrementally after each session.

## Root Files

### `docker-compose.yml`
- Starts the local PostgreSQL service
- Mounts SQL migrations from `database/migrations/`

### `.env.example`
- Template for local configuration values
- Includes database and Django settings

### `GOVERNMENT_CORRESPONDENCE_TRACKER.md`
- Tracks external agency handoff references
- Holds filing IDs and operational notes

## Database Files

### `database/migrations/001_initial_schema.sql`
- Initial SQL bootstrap for the Phase 1 schema
- Creates core investigation tables, enums, indexes, and triggers

### `database/migrations/002_government_referrals.sql`
- Adds the `government_referrals` table in the SQL-first path

### `database/migrations/003_government_referrals_timestamp_guard.sql`
- Adds DB-side timestamp defaults and immutability protections for `government_referrals`

## Backend Files

### `backend/manage.py`
- Django management entry point

### `backend/catalyst/settings.py`
- Django settings
- PostgreSQL connection config
- timezone support is enabled
- postgres app support is enabled for array fields
- `load_dotenv()` added at top — loads `.env` from project root before any `os.getenv()` calls

### `backend/investigations/models.py`
- Main Phase 1 data model definitions
- Includes core case, document, entity, finding, audit, and referral models

### `backend/investigations/admin.py`
- Full `ModelAdmin` classes for `GovernmentReferral`, `Case`, `Document`, `Person`, `Organization`, `Finding`, `AuditLog`
- `GovernmentReferral`: list view with status/agency filters, search, `filing_date` read-only
- `AuditLog`: all write permissions disabled — completely append-only at the admin layer
- Remaining models (Property, FinancialInstrument, junction tables) still use plain `admin.site.register()`

### `backend/investigations/serializers.py`
- Validates JSON case intake payloads without needing Django REST Framework
- Serializes `Case` and `Document` records for API responses
- Includes controlled update serializers for case and document PATCH workflows
- Enforces strict SHA-256 validation for document intake payloads

### `backend/investigations/views.py`
- Contains both HTML views and Django-native JSON API endpoints
- `/api/cases/` supports case list and case creation
- `/api/cases/<uuid>/` supports case detail, PATCH updates, and DELETE behavior
- `/api/cases/<uuid>/documents/` supports document list/create with pagination, filters, and sorting
- `/api/cases/<uuid>/documents/<uuid>/` supports GET, PATCH, and DELETE for case-scoped documents
- Shared helpers handle JSON parsing, pagination, filter validation, date-range parsing, and allowlisted sorting

### `backend/investigations/urls.py`
- Wires both browser routes and the JSON intake API routes

### `backend/investigations/tests.py`
- API regression suite for case and document collection/detail behavior
- Covers create, list, filter, sort, PATCH, DELETE, scope enforcement, and validation failures

### `backend/SERIALIZER_API_REFERENCE.md`
- Beginner-friendly explanation of serializers, endpoints, pagination contract, filters, and response shapes
- Tracks the evolving JSON API contract in narrative form

### `backend/API_COOKBOOK.md`
- Copy/paste curl examples for current case and document API workflows
- Includes create, list, filter, PATCH, and DELETE examples

### `backend/investigations/migrations/0001_initial.py`
- Initial Django migration for the investigation schema

### `backend/investigations/migrations/0002_governmentreferral.py`
- Adds the `GovernmentReferral` Django model

### `backend/investigations/migrations/0003_referral_timestamp_guard.py`
- Adds immutability protections for referral timestamps

### `backend/investigations/migrations/0004_alter_governmentreferral_filing_date_and_more.py`
- Adds DB-level defaults for referral timestamp and status

## Session Recap Log

### 2026-03-20 (Session 1)
- Documented current file roles for the root, database, and backend layers
- Captured the referral hardening migration chain

### 2026-03-20 (Session 2)
- `docker-compose.yml` updated: removed obsolete `version` field
- `backend/investigations/admin.py` upgraded: full `ModelAdmin` classes added

### 2026-03-20 (Session 3)
- `backend/catalyst/settings.py` updated: `load_dotenv()` added — fixes DB password auth
- No new files added; all 23 tables confirmed live in PostgreSQL via Django migrations

### 2026-03-26 (Session 4)
- Added `backend/investigations/serializers.py` for API validation and response shaping
- Updated `backend/investigations/views.py` and `backend/investigations/urls.py` with case intake endpoints
- Added `backend/investigations/tests.py` for intake API coverage

### 2026-03-26 (Session 5)
- Expanded `backend/investigations/views.py` into a fuller JSON API with pagination, filtering, sorting, PATCH, and DELETE behavior
- Expanded `backend/investigations/serializers.py` with update serializers and stricter document hash validation
- Grew `backend/investigations/tests.py` to cover CRUD, filters, sort behavior, date ranges, and conflict handling
- Added `backend/API_COOKBOOK.md` and updated `backend/SERIALIZER_API_REFERENCE.md` so API usage and contract are documented

## Next Updates

Use this file for:
- file-by-file explanations
- tracking newly added files
- noting when a file changes purpose
- quick re-orientation at the start of each session
