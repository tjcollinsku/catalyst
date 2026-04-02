# Database Migrations

This folder contains SQL migration files mounted by Docker at startup.

- `001_initial_schema.sql`: Phase 1 baseline schema.
- `002_government_referrals.sql`: Adds `government_referrals` tracking table.
- `003_government_referrals_timestamp_guard.sql`: Makes `government_referrals.filing_date` immutable after insert.
- `004_sync_django_models.sql`: Bootstrap sync for schema parity with current Django models.

Note: PostgreSQL only auto-runs files in `/docker-entrypoint-initdb.d` on the first container startup for a fresh data volume.

## Canonical Migration Path

For active development environments, use Django migrations as the source of truth:

- `backend/investigations/migrations/0001_initial.py`
- `backend/investigations/migrations/0002_governmentreferral.py`
- `backend/investigations/migrations/0003_referral_timestamp_guard.py`
- `backend/investigations/migrations/0004_alter_governmentreferral_filing_date_and_more.py`
- `backend/investigations/migrations/0005_document_doc_subtype_document_is_generated_and_more.py`
- `backend/investigations/migrations/0006_alter_person_notes_alter_person_role_tags.py`
- `backend/investigations/migrations/0007_signal_entitysignal.py`
- `backend/investigations/migrations/0008_org_formation_date_signal_summary.py`
- `backend/investigations/migrations/0009_governmentreferral_case_fk_status_notes.py`
- `backend/investigations/migrations/0010_documenttype_occ_cic.py`
- `backend/investigations/migrations/0011_alter_governmentreferral_status_detection.py`
- `backend/investigations/migrations/0012_finding_detection.py`

These Django migrations include the model expansion work:

- Expanded `Document.doc_type` choices (OCC, CIC, and other new types)
- Added `documents.is_generated` and `documents.doc_subtype`
- Added `organizations.formation_date`
- Added `signals`, `entity_signal`, `finding_entity`, `finding_document`
- Added finding workflow fields (`confidence`, `status`, `signal_type`, `signal_rule_id`, `legal_refs`)
- Added `GovernmentReferral.case` FK, `notes` field, expanded status choices
- Created `Detection` model (signal_type, severity, status, evidence_snapshot, confidence_score)
- Added `Finding.detection` FK for detection-to-finding escalation

## Usage Guidance

- Fresh Docker volume bootstrap: SQL files in this folder initialize the schema.
- Normal app lifecycle and upgrades: run `python manage.py migrate` from `backend/`.
- If both paths are used, Django migrations remain authoritative for application compatibility.
