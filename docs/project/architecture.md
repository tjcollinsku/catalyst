# Catalyst — System Architecture

**Last Updated:** 2026-04-01
**Status:** Living document — update at end of each session

---

## Architecture Overview

Catalyst is a Django monolith with a React SPA frontend. The decision to use a monolith (rather than microservices) is intentional: it keeps deployment simple, avoids inter-service complexity, and is the right choice for a single-developer project at this scale. The codebase is organized into logical modules that could be extracted into services later if needed, but there is no plan to do so.

```
                    ┌─────────────────────────────┐
                    │      React SPA (Vite)        │
                    │      TypeScript + CSS         │
                    │      Port 5173 (dev)          │
                    └──────────┬──────────────────┘
                               │ HTTP (JSON API)
                               ▼
                    ┌─────────────────────────────┐
                    │      Django Backend           │
                    │      Port 8000                │
                    │                               │
                    │  ┌─────────┐ ┌────────────┐  │
                    │  │ Views / │ │ Middleware  │  │
                    │  │ API     │ │ (CSRF,Rate)│  │
                    │  └────┬────┘ └────────────┘  │
                    │       │                       │
                    │  ┌────┴──────────────────┐    │
                    │  │  Processing Pipeline   │   │
                    │  │  extract → classify →  │   │
                    │  │  entities → signals    │   │
                    │  └────┬──────────────────┘   │
                    │       │                       │
                    │  ┌────┴──────────────────┐    │
                    │  │  External Connectors   │   │
                    │  │  (ProPublica, IRS,     │   │
                    │  │   Ohio SOS/AOS/County) │   │
                    │  └───────────────────────┘   │
                    └──────────┬──────────────────┘
                               │
                               ▼
                    ┌─────────────────────────────┐
                    │   PostgreSQL 16 (Docker)      │
                    │   Port 5432                   │
                    └─────────────────────────────┘
```

---

## Backend Structure

The entire backend lives in one Django app: `investigations`. This app contains 5 logical tiers:

### Tier 1: Stateless Utilities (No Django dependency)

These modules are pure Python — no Django imports, no database access. They can be used in CLI scripts, background jobs, or tested without Django setup.

| Module | Purpose |
|--------|---------|
| `extraction.py` | PDF text extraction (PyMuPDF direct + Tesseract OCR fallback) |
| `classification.py` | Rule-based document type classification by keyword scoring |
| `entity_extraction.py` | Regex-based entity candidate extraction (persons, orgs, dates, amounts, parcels) |
| `entity_normalization.py` | Canonical form normalization (uninvert names, strip designators) |
| `propublica_connector.py` | ProPublica Nonprofit Explorer API (search orgs, fetch 990 filings) |
| `irs_connector.py` | IRS Pub78 + EO BMF bulk download (tax-exempt org status) |
| `ohio_sos_connector.py` | Ohio Secretary of State bulk CSV (business entity filings) |
| `county_auditor_connector.py` | ODNR ArcGIS parcel API + county auditor portal URL builder |
| `county_recorder_connector.py` | County recorder URL builder + deed/mortgage document parser |
| `ohio_aos_connector.py` | Ohio Auditor of State audit report HTML scraper |

### Tier 2: Pipeline Integration (Needs Django ORM)

| Module | Purpose | DB Access |
|--------|---------|-----------|
| `entity_resolution.py` | Exact match upsert + fuzzy candidate surfacing | Writes Person/Org records |
| `signal_rules.py` | Evaluates 16 fraud signal rules (SR-001 through SR-016) | Reads entities, writes Signals |

### Tier 3: Django Infrastructure

| Module | Purpose |
|--------|---------|
| `models.py` | 21 ORM models + choice enums (see Data Models below) |
| `serializers.py` | Request validation + JSON response shaping (no DRF) |
| `views.py` | 35 API endpoints + HTML views (~2600 lines) |
| `urls.py` | URL routing for all endpoints |
| `admin.py` | Django admin with full ModelAdmin classes |
| `middleware.py` | CSRF handling + sliding-window rate limiting |
| `forms.py` | Django form classes for HTML views |

---

## Document Processing Pipeline

The core pipeline runs automatically on every document upload:

```
Upload PDF
    │
    ▼
Stage 0: SHA-256 hash on original bytes (chain of custody)
    │
    ▼
Stage 1: Text extraction (PyMuPDF direct → OCR fallback if sparse)
    │        Files > 30MB stay PENDING for async handling
    ▼
Stage 2: Document classification (keyword scoring → doc_type)
    │
    ▼
Stage 3: Entity extraction (regex → raw candidates)
    │
    ▼
Stage 4: Entity normalization (canonical form for comparison)
    │
    ▼
Stage 5: Entity resolution (exact match → upsert; fuzzy → flag for review)
    │
    ▼
Stage 6: Signal detection (evaluate document + case against 16 rules)
    │
    ▼
Stage 7: Financial extraction (for IRS 990 forms → FinancialSnapshot)
    │
    ▼
Extraction status recorded: COMPLETED / PARTIAL / FAILED / SKIPPED
```

Each stage is best-effort — a failure in entity extraction never blocks the upload. Extraction status tracks which stages succeeded.

---

## Data Models (21 models, 15 migrations)

### Core Models
- **Case** — Investigation container (UUID PK, status, referral_ref)
- **Document** — Uploaded file with hash chain-of-custody (SHA-256, OCR status, extraction status)
- **Person** — Identified individual with role tags and aliases
- **Organization** — Identified entity with type, EIN, status
- **Property** — Parcel record with assessed/purchase values and computed delta
- **FinancialInstrument** — UCC filings, loans, liens with anomaly flags

### Analysis Models
- **Signal** — Automated detection of suspicious patterns (16 rule types)
- **Detection** — Confirmed anomalies (auto or manual, with evidence snapshot)
- **Finding** — Investigator-curated findings from detections
- **FinancialSnapshot** — Extracted IRS Form 990 financial data

### Linking Models
- **PersonDocument**, **OrgDocument** — Entity-to-document links with page references
- **PersonOrganization** — Person-to-org role relationships with date ranges
- **PropertyTransaction** — Property transfer records
- **FindingEntity**, **FindingDocument** — Finding evidence links
- **EntitySignal** — Signal-to-entity links

### Operational Models
- **AuditLog** — Append-only audit trail (action, before/after state, SHA-256, IP)
- **GovernmentReferral** — Referral tracking with immutable filing dates
- **InvestigatorNote** — Free-form notes attachable to any entity

### Key Enums
- **16 SignalTypes**: DECEASED_SIGNER, SELF_DEALING, VALUATION_DELTA, UCC_LOOP, PHANTOM_OFFICER, etc.
- **21 DocumentTypes**: DEED, MORTGAGE, IRS_990, COURT_FILING, DEATH_RECORD, etc.
- **18 PersonRoles**: BOARD_MEMBER, OFFICER, REGISTERED_AGENT, GRANTOR, DECEASED, etc.

---

## External Connectors (6 total)

All connectors are stateless, have no Django dependency, and return structured dataclass results. None write to the database — results are presented to the investigator for review.

| Connector | Source | Auth | Strategy |
|-----------|--------|------|----------|
| ProPublica | ProPublica Nonprofit Explorer API | None | Direct API calls |
| IRS | IRS Pub78 + EO BMF bulk files | None | Bulk download + local search |
| Ohio SOS | Ohio SOS monthly CSV exports | None | Bulk download + local search |
| County Auditor | ODNR ArcGIS REST API + portal URLs | None | Automated query + URL builder |
| County Recorder | 88 county portals | None | URL builder + document parser (no scraping) |
| Ohio AOS | Ohio Auditor of State search | None | HTML scraper |

All include staleness warnings (LOW/MEDIUM/HIGH) to alert investigators when data may be outdated.

---

## Frontend Structure

React SPA built with Vite + TypeScript. Shell + Views architecture with React Router v6.

### Routes
| Route | View | Status |
|-------|------|--------|
| `/` | DashboardView | Working |
| `/cases` | CasesListView | Working |
| `/cases/:caseId` | CaseDetailView | BROKEN (truncated) |
| `/cases/:caseId/documents` | DocumentsTab | BROKEN (truncated) |
| `/cases/:caseId/signals` | SignalsTab | Working |
| `/cases/:caseId/detections` | DetectionsTab | Working |
| `/cases/:caseId/referrals` | ReferralsTab | Working |
| `/cases/:caseId/financials` | FinancialsTab | Working |
| `/entities` | EntityBrowserView | Working |
| `/entities/:type/:id` | EntityDetailView | Working |
| `/triage` | TriageView | Working |
| `/referrals` | ReferralsView | Working |
| `/search` | SearchView | Working |
| `/settings` | SettingsView | Working |

### Frontend File Counts
- 9 view components (src/views/)
- 26 reusable components (src/components/)
- 1 layout (AppShell.tsx)
- 1 API layer (api.ts — 25+ endpoint functions)
- 1 type definitions file (types.ts)
- 1 context (ShellContext.tsx)
- 1 custom hook (useKeyboardShortcuts.ts)
- 2 utility files (format.ts, queryParams.ts)

### Known Frontend Issues (as of 2026-04-01)
- **4 truncated files prevent compilation**: types.ts, CaseDetailView.tsx, DocumentsTab.tsx, PdfViewer.tsx
- **Missing API function**: `fetchDocumentDetail()` imported but not defined in api.ts
- **No connector UI**: All 6 external connectors are backend-only, no frontend integration
- **No relationship graph**: Entity connections exist in the database but have no visual representation

---

## Security Infrastructure

- SHA-256 hash computed on original bytes before any processing (chain of custody)
- CSRF protection (cookie + X-CSRFToken header for SPA)
- Sliding-window rate limiting (200 reads/min, 30 writes/min per IP)
- PDF magic bytes validation before processing
- URL domain allowlists on all external connector responses
- Chunked downloads with size caps and deadlines (IRS connector)
- Path traversal prevention on file uploads
- Audit logging on all data changes
- `ExtractionStatus` enum tracking pipeline success/failure per document

---

## Test Coverage

| Test File | Count | Runner | Coverage |
|-----------|-------|--------|----------|
| tests.py | 46+ | Django (requires DB) | API endpoints, upload pipeline, entity resolution |
| tests_propublica.py | 29 | unittest (no DB) | All HTTP mocked |
| tests_ohio_sos.py | 59 | unittest (no DB) | All HTTP mocked |
| tests_irs.py | 104 | unittest (no DB) | All HTTP mocked |
| tests_county_recorder.py | 191 | unittest (no DB) | No HTTP (connector has none) |
| tests_county_auditor.py | 126 | unittest (no DB) | All HTTP mocked |
| **Total** | **555+** | | |

No frontend tests exist currently.
