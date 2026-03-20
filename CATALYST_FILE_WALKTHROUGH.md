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

### `backend/investigations/models.py`
- Main Phase 1 data model definitions
- Includes core case, document, entity, finding, audit, and referral models

### `backend/investigations/admin.py`
- Full `ModelAdmin` classes for `GovernmentReferral`, `Case`, `Document`, `Person`, `Organization`, `Finding`, `AuditLog`
- `GovernmentReferral`: list view with status/agency filters, search, `filing_date` read-only
- `AuditLog`: all write permissions disabled — completely append-only at the admin layer
- Remaining models (Property, FinancialInstrument, junction tables) still use plain `admin.site.register()`

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

## Next Updates

Use this file for:
- file-by-file explanations
- tracking newly added files
- noting when a file changes purpose
- quick re-orientation at the start of each session
