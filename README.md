# Catalyst

Investigation intelligence platform for fraud pattern detection, defensible
audit history, and human-in-the-loop evidence workflows.

Built to support a real nonprofit fraud investigation that produced formal
referrals to the Ohio Attorney General Charitable Law Section,
the IRS, the FBI, and the Example Lender Administration OIG. The manual investigation process exposed specific
organizational and tooling gaps — Catalyst is the systematic solution to those
gaps.

This repository demonstrates practical backend engineering for
compliance-sensitive systems: schema design, migration discipline, API design,
ingestion pipelines, connector architecture, and production-minded controls.

---

## Why this project exists

Most investigation tooling is either:
- too manual to scale, or
- too automated to be legally defensible.

Catalyst is designed for the middle path: automate extraction and triage,
preserve investigator control, keep a clean and auditable chain of evidence.

---

## What I built

### Platform foundation
- Django backend with PostgreSQL
- SQL bootstrap migrations for clean environment initialization
- Django migration path as canonical source of truth for schema evolution
- Timezone-aware timestamps and immutable timestamp guards where audit
  integrity matters

### Core data model
Investigation-centered entities and link tables:
- cases, documents, persons, organizations, properties, financial instruments
- findings, signals, audit log, government referrals
- relationship tables for person-document, org-document, person-org, and
  property transactions

### Processing pipeline
- PDF text extraction with OCR fallback
- Rule-based document classification
- 3-stage entity pipeline: extraction → normalization → resolution
  (exact upsert + fuzzy candidate surfacing)
- Signal detection engine with 10 rule-based anomaly triggers (SR-001
  through SR-010), derived directly from patterns found in the founding
  investigation

### Integrations and connectors
Stateless connectors for external intelligence sources:
- ProPublica Nonprofit Explorer
- IRS Pub78 + EO BMF bulk files
- Ohio Secretary of State bulk files
- Ohio county recorder portal (88-county coverage)
- Ohio county auditor via statewide parcel layer + county links
- Ohio Auditor of State report search

### API surface
Case and document intake endpoints with validation, pagination, filtering,
deterministic sorting, and conflict-aware deletion behavior.

### Test architecture
- Connector tests run fully offline with mocked HTTP
- API and signal tests cover behavior and edge cases
- Organized into a dedicated test package for maintainability
- Emphasis on reproducibility and confidence during refactors

---

## Engineering decisions that matter

### 1. SQL bootstrap + Django evolution
SQL migrations for baseline clarity and environment bootstrap, then Django
migrations for day-to-day schema evolution. Operational portability without
sacrificing developer velocity.

### 2. Audit-first controls
Auditability treated as a primary feature, not an afterthought:
- immutable fields for key timestamps
- append-only audit logging
- strict timestamp handling throughout

### 3. Human-in-the-loop by design
Connectors and fuzzy entity logic surface candidates rather than silently
merging uncertain matches. Investigator confirmation is required before any
match becomes a resolved entity. This is a deliberate legal defensibility
decision, not a missing feature.

### 4. Failure isolation
Extraction and connector paths are best-effort where appropriate. A partial
failure in one connector or OCR step does not collapse the full intake
workflow.

---

## Status

Backend schema and migration story are stable. Signal detection engine,
connector suite, and API surface are production-ready for the backend phase.
Frontend implementation is the active next phase.

---

## Repo map

- [backend](backend)
- [backend/README.md](backend/README.md)
- [database/migrations](database/migrations)
- [docs/project/system-overview.md](docs/project/system-overview.md)
- [docs/project/file-walkthrough.md](docs/project/file-walkthrough.md)

---

## How to run

**Backend**

1. Start PostgreSQL: `docker-compose up`
2. Create and activate a Python virtual environment
3. Install dependencies: `pip install -r backend/requirements.txt`
4. Run migrations: `python manage.py migrate`
5. Start server: `python manage.py runserver`

**Frontend**

1. `cd frontend`
2. `npm install`
3. `npm run dev`

Vite runs on `http://127.0.0.1:5173`. API requests to `/api/*` proxy to
Django at `http://127.0.0.1:8000`. Keep Django running in parallel.

Keyboard shortcuts (case list):
- `j` / `k` — move down / up
- `1` / `2` / `3` — set active signal status to Open / Reviewed / Dismissed
- Shortcuts are suppressed while typing in form fields

---

## Workflow guardrails

Lightweight controls to keep the repo clean as it grows.

- Contributor standards: [CONTRIBUTING.md](CONTRIBUTING.md)
- PR checklist: [.github/pull_request_template.md](.github/pull_request_template.md)
- Commit template: [.gitmessage.txt](.gitmessage.txt)

One-time setup:
```bash
git config commit.template .gitmessage.txt
pip install -r backend/requirements-dev.txt
bash ./pc install
```

Daily usage:
```bash
bash ./pc           # run checks before committing
bash ./pc run --all-files
```
