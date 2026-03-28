# Catalyst

Catalyst is an investigation intelligence platform focused on fraud pattern detection, defensible audit history, and human-in-the-loop evidence workflows.

This repository demonstrates practical backend engineering for compliance-sensitive systems: schema design, migration discipline, API design, ingestion pipelines, connector architecture, and production-minded controls.

## Why This Project Exists

Most investigation tooling is either:
- too manual to scale, or
- too automated to be legally defensible.

Catalyst is designed for the middle path:
- automate extraction and triage,
- preserve investigator control,
- keep a clean and auditable chain of evidence.

## What I Built

### Platform Foundation
- Django backend with PostgreSQL
- SQL bootstrap migrations for clean environment initialization
- Django migration path as canonical source of truth for app evolution
- Timezone-aware timestamps and immutable timestamp guards where audit integrity matters

### Core Data Model
Implemented investigation-centered entities and link tables including:
- cases, documents, persons, organizations, properties, financial_instruments
- findings, signals, audit_log, government_referrals
- relationship tables for person-document, org-document, person-org, and property transactions

### Processing Pipeline
- PDF text extraction with OCR fallback
- Rule-based document classification
- 3-stage entity pipeline:
  - extraction
  - normalization
  - resolution (exact upsert + fuzzy candidate surfacing)
- Signal detection engine with rule-based anomaly triggers (SR-001 through SR-010)

### Integrations and Connectors
Implemented stateless connectors for external intelligence sources:
- ProPublica Nonprofit Explorer
- IRS Pub78 + EO BMF bulk files
- Ohio Secretary of State bulk files
- Ohio county recorder portal support
- Ohio county auditor support via statewide parcel layer + county links
- Ohio Auditor of State report search

### API Surface
Built case and document intake endpoints with:
- validation
- pagination
- filtering
- deterministic sorting
- conflict-aware deletion behavior

### Test Architecture
- Reorganized tests into a dedicated package for maintainability
- Connector tests run offline with mocked HTTP
- API and signal tests cover behavior and edge cases
- Emphasis on reproducibility and confidence during refactors

## Engineering Decisions That Matter

### 1. SQL bootstrap + Django evolution
I used SQL migrations for baseline clarity and environment bootstrap, then Django migrations for day-to-day schema evolution. This gives both operational portability and developer velocity.

### 2. Audit-first controls
I treated auditability as a primary feature:
- immutable fields for key timestamps
- append-only style audit logging
- strict timestamp handling

### 3. Human-in-the-loop by design
Connectors and fuzzy entity logic surface candidates rather than silently merging uncertain matches. This supports legal defensibility and investigator trust.

### 4. Failure isolation
Extraction and connector paths are best-effort where appropriate. A partial failure should not collapse the full intake workflow.

## Current State

- Backend schema and migration story are stable
- Documentation now reflects the schema evolution path
- Idempotent SQL sync migration exists for repeat bootstrap scenarios
- Project is ready for frontend implementation phase

## Repo Map

- [backend](backend)
- [backend/README.md](backend/README.md)
- [database/migrations](database/migrations)
- [database/migrations/README.md](database/migrations/README.md)
- [CATALYST_SYSTEM_OVERVIEW.md](CATALYST_SYSTEM_OVERVIEW.md)
- [CATALYST_FILE_WALKTHROUGH.md](CATALYST_FILE_WALKTHROUGH.md)

## How To Run

1. Start PostgreSQL via Docker Compose from repo root.
2. Create and activate Python virtual environment.
3. Install dependencies from [backend/requirements.txt](backend/requirements.txt).
4. Run migrations from [backend](backend):
   - python manage.py migrate
5. Start Django server:
   - python manage.py runserver

## Portfolio Value (What This Shows Employers)

This project demonstrates ability to:
- design relational schemas for real investigative workflows
- evolve schema safely with migration discipline
- build resilient ingestion and normalization pipelines
- implement APIs with real validation and operational constraints
- structure tests for confidence in a growing codebase
- engineer for audit/compliance requirements, not just happy-path features

## Next Phase

Frontend implementation to expose:
- case timeline and evidence views
- signal triage workflows
- investigator review queues for fuzzy entity matches
- referral and audit status dashboards
