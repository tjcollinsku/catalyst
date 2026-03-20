# Catalyst System Overview

## Purpose

Catalyst is being built as an intelligence triage and investigation support platform.

Its current Phase 1 focus is:
- defining the database schema
- scaffmain the Django backend
- preserving defensible audit history
- preparing for cloud deployment with trustworthy timestamps

## Current Architecture

### Backend
- Django project lives in `backend/`
- Primary app is `investigations`
- Django models now represent the Phase 1 schema

### Database
- PostgreSQL runs locally through Docker Compose
- SQL bootstrap migrations live in `database/migrations/`
- Django migrations live in `backend/investigations/migrations/`

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

## Next Updates

Use this file for:
- high-level architecture recap
- milestone tracking
- decisions and rationale
- end-of-session summaries
