# CLAUDE.md — Catalyst System Map
**Last updated:** 2026-04-10 (Session 33)
**Owner:** Tyler Collins (tjcollinsku@gmail.com)
**Purpose:** This is the single source of truth for the entire Catalyst system. Read this FIRST before doing any work.

---

## WHAT IS CATALYST

Catalyst is a nonprofit fraud investigation platform. An investigator opens a case, pulls data from government sources (IRS, Ohio SOS, county auditor/recorder, Ohio Auditor of State), uploads documents, and the system automatically extracts entities, detects fraud signals, and helps build referral packages for government agencies.

Tyler is a beginner programmer building this through the IBM Full-Stack certificate program. He wants thorough explanations, visual diagrams, and progressive concept building. He does NOT want to be the one debugging code — Claude should handle that. He DOES want to make decisions when they matter.

---

## DECISION MODEL

- **GREEN:** Claude acts autonomously (code style, file organization, refactoring)
- **YELLOW:** Claude recommends + Tyler confirms (new libraries, architecture changes, external API choices)
- **RED:** Claude presents options + Tyler decides (scope changes, data source priorities, UX direction)

---

## PROJECT STRUCTURE

```
Catalyst/
├── backend/
│   ├── investigations/          ← ALL backend logic lives here
│   │   ├── models.py            ← 27 Django models (1847 lines) [being consolidated — see Session 32]
│   │   ├── views.py             ← 47 API endpoints (6141 lines) — CORE
│   │   ├── urls.py              ← URL routing
│   │   ├── serializers.py       ← JSON serialization (1476 lines)
│   │   ├── forms.py             ← Legacy HTML forms
│   │   ├── admin.py             ← Django admin config
│   │   ├── middleware.py         ← Auth + rate limiting
│   │   ├── apps.py              ← Django app config
│   │   │
│   │   ├── # --- PROCESSING PIPELINE (ALL LIVE) ---
│   │   ├── extraction.py        ← PDF text extraction (PyPDF2 + Tesseract OCR)
│   │   ├── classification.py    ← Document type classification
│   │   ├── entity_extraction.py ← Rule-based entity extraction from text
│   │   ├── entity_resolution.py ← Fuzzy matching + dedup entities
│   │   ├── entity_normalization.py ← Name/EIN/address standardization
│   │   ├── signal_rules.py      ← 29 fraud detection rules (SR-001 to SR-029)
│   │   ├── data_quality.py      ← Data validation + audit logging
│   │   ├── ai_extraction.py     ← Claude AI entity/financial extraction
│   │   ├── ai_proxy.py          ← Claude API wrapper with caching
│   │   ├── form990_parser.py    ← IRS 990 text parser (Part IV/VI/VII)
│   │   │
│   │   ├── # --- CONNECTORS ---
│   │   ├── propublica_connector.py    ← ProPublica 990 API [SUPERSEDED by IRS TEOS]
│   │   ├── county_recorder_connector.py ← 88 OH counties [WORKING ✅]
│   │   ├── county_auditor_connector.py  ← ODNR parcel API [BROKEN — ODNR down]
│   │   ├── irs_connector.py            ← IRS TEOS 990 XML pipeline [WORKING ✅]
│   │   ├── ohio_sos_connector.py       ← OH Secretary of State [LOCAL CSV ✅]
│   │   ├── ohio_aos_connector.py       ← OH Auditor of State [WORKING ✅]
│   │   └── verify_recorder_portals.py  ← Utility script
│   │
│   ├── backend/                 ← Django project settings
│   │   ├── settings.py
│   │   ├── urls.py              ← Root URL config (includes investigations/)
│   │   ├── wsgi.py
│   │   └── asgi.py
│   └── manage.py
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx              ← Router: 8 main routes
│   │   ├── api/                 ← API client functions
│   │   ├── components/          ← Reusable UI components
│   │   ├── views/               ← Page-level components
│   │   ├── types/               ← TypeScript interfaces
│   │   └── context/             ← React context providers
│   ├── package.json             ← React 18, D3.js, Vite
│   └── vite.config.ts
│
├── docs/
│   ├── charter/                 ← v3 charter (vision + roadmap)
│   ├── architecture/            ← Design decisions, frontend spec
│   ├── governance/              ← Tech debt, risk register, testing strategy
│   ├── operations/              ← Session tracker (27 sessions)
│   └── team/                    ← Specialist briefing books + playbook
│
├── tests/                       ← 555+ backend tests + API health check
├── Dockerfile                   ← Multi-stage build (node + python)
├── docker-compose.yml
├── railway.json                 ← Railway deployment config
├── requirements.txt             ← Python dependencies
└── CLAUDE.md                    ← THIS FILE
```

---

## THE CRITICAL GAP: CONNECTORS → UI

This is the #1 problem. We have 6 data source connectors. Here is their actual status:

### CONNECTOR WIRING STATUS

| Connector | Backend File | Has Endpoint? | Frontend Calls It? | Works on Railway? | Root Cause if Broken |
|-----------|-------------|---------------|--------------------|--------------------|----------------------|
| IRS TEOS XML | irs_connector.py | YES (`/research/irs/` + `/fetch-990s/`) | **YES** — Fetch 990 Data button | **YES** ✅ | — |
| County Recorder | county_recorder_connector.py | YES (`/research/recorder/`) + auto DEED | Research tab (URL builder) | **YES** ✅ | — |
| Ohio AOS | ohio_aos_connector.py | YES (`/research/ohio-aos/`) | Research tab | **YES** ✅ | — |
| Ohio SOS | ohio_sos_connector.py | YES (`/research/ohio-sos/`) + admin upload | Research tab | **YES** ✅ (local CSV) | Requires manual CSV upload via admin endpoint |
| County Auditor | county_auditor_connector.py | YES (`/research/parcels/`) | Research tab | **NO** ❌ | ODNR ArcGIS API returning 404; fallback URL times out |
| ProPublica | propublica_connector.py | YES (`/fetch-990s/`) | Superseded | N/A | Replaced by IRS TEOS XML for financial data |

**Session 30 update:** IRS connector completely rewritten — now fetches 990 XML directly from IRS TEOS (apps.irs.gov) using HTTP range requests (~5KB per filing vs 100MB bulk). Parses full 990: Part I financials, Part IV checklist, Part VI governance, Part VII officer compensation. Frontend has "Fetch 990 Data" button with expandable detail panel. Ohio SOS rewritten to use local CSV approach — admin uploads CSVs, connector searches from disk. **4 of 6 connectors now working.** Only ODNR remains broken (external API issue).

### WHAT NEEDS TO BE BUILT

1. ~~**IRSx integration**~~ — **DONE (Session 30).** Replaced with IRS TEOS XML pipeline. Full 990 data including Parts IV/VI/VII.
2. ~~**Ohio SOS alternative**~~ — **DONE (Session 30).** Local CSV upload approach. Admin uploads CSVs, connector searches from disk.
3. **ODNR parcel API** — Monitor if ArcGIS endpoint recovers, or find new URL. Both primary and fallback URLs currently unreachable from Railway.
4. **Result-to-case wiring** — "Add to Case" buttons exist but need testing on working connectors (AOS, Recorder, IRS, SOS).
5. ~~**ProPublica UI button**~~ — **SUPERSEDED.** IRS TEOS XML provides richer data. "Fetch 990 Data" button now exists on Research tab.

---

## DATA MODELS (22 Models — consolidated in Session 33)

### Core Investigation Models
- **Case** — name, status (ACTIVE/PAUSED/REFERRED/CLOSED), notes, referral_ref
- **Document** — filename, sha256_hash, doc_type, ocr_status, extraction_status, is_generated
- **Finding** — consolidated model (replaces old Signal → Detection → Finding pipeline). Two dimensions: `status` (NEW/NEEDS_EVIDENCE/DISMISSED/CONFIRMED) and `evidence_weight` (SPECULATIVE/DIRECTIONAL/DOCUMENTED/TRACED). Also has: rule_id, title, description, narrative, severity, source (AUTO/MANUAL), legal_refs[], evidence_snapshot, trigger_doc FK
- **FindingEntity** — links a Finding to an entity (person, org, property)
- **FindingDocument** — links a Finding to a source document with page reference

### Entity Models
- **Person** — name, aliases[], date_of_birth, date_of_death, role_tags[]
- **Organization** — name, ein, entity_number, state, org_type, formation_date
- **Property** — parcel_number, address, county, assessed_value, purchase_price, valuation_delta (generated)
- **FinancialInstrument** — instrument_type, filing_number, amount, anomaly_flags[]
- **FinancialSnapshot** — org FK, tax_year, revenue, expenses, net_assets (from 990)
- **Address** — normalized street/city/state/zip

### Relationship Models
- **PersonDocument**, **OrgDocument** — entity-to-document links
- **PersonOrganization** — role_type (OFFICER, BOARD_MEMBER, COUNSEL, ADVISOR)
- **PropertyTransaction** — grantor/grantee with polymorphic entity link
- **Relationship** — person-to-person (FAMILY/BUSINESS/SOCIAL)
- **TransactionChain** + **TransactionChainLink** — grouped property deals

### Operational Models
- **InvestigatorNote** — polymorphic target (any entity/finding)
- **AuditLog** — append-only forensic log (NEVER UPDATE OR DELETE)

---

## SIGNAL RULES (14 Rules — cut from 29 in Session 32)

Every rule below is grounded in a real pattern from the founding investigation.
Speculative rules were cut. New rules can be added in later versions as new
patterns emerge from real cases.

| Rule | Severity | What It Detects | Anomaly Source |
|------|----------|----------------|----------------|
| SR-003 | HIGH | VALUATION_ANOMALY — Purchase price deviates >50% from assessed value | Overpayment on property |
| SR-004 | HIGH | UCC_BURST — 3+ UCC amendments to same filing within 24 hours | Debt restructuring |
| SR-005 | HIGH | ZERO_CONSIDERATION — Zero-consideration transfer between related parties | Land swaps w/o equal value |
| SR-006 | HIGH | SCHEDULE_L_MISSING — 990 Part IV Line 28 Yes but no Schedule L | Missing 990 schedules |
| SR-010 | MEDIUM | MISSING_990 — Tax-exempt org has no Form 990 on file | Missing 990 schedules |
| SR-012 | HIGH | NO_COI_POLICY — No conflict of interest policy despite material revenue | Missing 990 schedules |
| SR-013 | HIGH | ZERO_OFFICER_PAY — $0 officer compensation at high-revenue org | Self-dealing (hidden comp) |
| SR-015 | CRITICAL | INSIDER_SWAP — Related party on both sides of property transaction | Self-dealing |
| SR-017 | HIGH | BLANKET_LIEN — UCC blanket lien on charity-connected entity | Debt restructuring |
| SR-021 | HIGH | REVENUE_SPIKE — Year-over-year revenue increase exceeds 100% | Rapid asset growth |
| SR-024 | HIGH | CHARITY_CONDUIT — Charity buys from family, transfers to insider | Self-dealing |
| SR-025 | CRITICAL | FALSE_DISCLOSURE — 990 denies related-party tx, evidence contradicts | Self-dealing |
| SR-026 | HIGH | CONTRACTOR_DENIAL — 990 denies contractors, permits show otherwise | Missing 990 schedules |
| SR-029 | HIGH | LOW_PROGRAM_RATIO — <50% of expenses go to program services | Charity funds for personal growth |

---

## API ENDPOINTS (43 Total — updated Session 33)

### Case Management
```
GET    /api/cases/                              → Paginated case list
POST   /api/cases/                              → Create case
GET    /api/cases/<uuid>/                       → Case detail + documents
GET    /api/cases/<uuid>/dashboard/             → KPI metrics
GET    /api/cases/<uuid>/coverage/              → Signal rule coverage audit
GET    /api/cases/<uuid>/graph/                 → Entity relationship graph
POST   /api/cases/<uuid>/export/                → Export JSON/CSV
```

### Documents
```
POST   /api/cases/<uuid>/documents/bulk/        → Upload files (multipart)
POST   /api/cases/<uuid>/documents/process-pending/ → Batch OCR
GET    /api/cases/<uuid>/documents/<uuid>/      → Document detail
DELETE /api/cases/<uuid>/documents/<uuid>/      → Delete document
POST   /api/cases/<uuid>/referral-memo/         → AI-powered referral memo generation
POST   /api/cases/<uuid>/referral-pdf/          → Deterministic referral package PDF export (NEW Session 33)
```

### Signals & Detections
```
GET    /api/cases/<uuid>/signals/               → Case signals
PATCH  /api/cases/<uuid>/signals/<uuid>/        → Update signal status/notes
GET    /api/signals/                            → Cross-case signals (triage)
GET    /api/signal-summary/                     → Global signal counts
GET    /api/cases/<uuid>/detections/            → Case detections
PATCH  /api/cases/<uuid>/detections/<uuid>/     → Update detection
DELETE /api/cases/<uuid>/detections/<uuid>/     → Delete detection
POST   /api/cases/<uuid>/reevaluate-signals/    → Re-run all signal rules
```

### Findings
```
GET    /api/cases/<uuid>/findings/              → Case findings
POST   /api/cases/<uuid>/findings/              → Create finding
PATCH  /api/cases/<uuid>/findings/<uuid>/       → Update finding
DELETE /api/cases/<uuid>/findings/<uuid>/       → Delete finding
```

### Referrals (removed in Session 33)
```
# GovernmentReferral CRUD endpoints removed — referral concept replaced
# by deterministic PDF exporter at POST /api/cases/<uuid>/referral-pdf/
```

### Financials & Entities
```
GET    /api/cases/<uuid>/financials/            → 990 financial snapshots
GET    /api/entities/                           → Browse/search entities
GET    /api/entities/<type>/<uuid>/             → Entity detail
```

### AI
```
POST   /api/cases/<uuid>/ai/summarize/          → AI case summary
POST   /api/cases/<uuid>/ai/connections/        → AI relationship analysis
POST   /api/cases/<uuid>/ai/narrative/          → AI narrative draft
POST   /api/cases/<uuid>/ai/ask/                → Free-text AI chat
```

### Data Fetching
```
POST   /api/cases/<uuid>/fetch-990s/            → Fetch 990 XML from IRS TEOS + create FinancialSnapshots
```

### Research Endpoints
```
POST   /api/cases/<uuid>/research/parcels/      → County Auditor parcel search (ODNR API)
POST   /api/cases/<uuid>/research/ohio-sos/     → Ohio SOS entity lookup (local CSV)
POST   /api/cases/<uuid>/research/ohio-aos/     → Ohio AOS audit report search
POST   /api/cases/<uuid>/research/irs/          → IRS TEOS 990 XML lookup (by EIN or name)
POST   /api/cases/<uuid>/research/recorder/     → County Recorder portal URL builder
POST   /api/cases/<uuid>/research/add-to-case/ → Import research result as entity/note
```

### Admin Endpoints (NEW — Session 30)
```
POST   /api/admin/upload-sos-csv/               → Upload Ohio SOS CSV file for local search
GET    /api/admin/sos-csv-status/                → Check which SOS CSVs are uploaded
```

### Notes
```
GET    /api/cases/<uuid>/notes/                 → Case notes
POST   /api/cases/<uuid>/notes/                 → Create note
PATCH  /api/cases/<uuid>/notes/<uuid>/          → Update note
DELETE /api/cases/<uuid>/notes/<uuid>/          → Delete note
```

### Utility
```
GET    /api/health/                             → Health check
GET    /api/csrf/                               → CSRF token
GET    /api/search/                             → Full-text search
GET    /api/activity-feed/                      → Recent audit log
```

---

## FRONTEND VIEWS (What the User Sees)

| Route | Component | What It Does |
|-------|-----------|-------------|
| `/` | Dashboard | KPI cards, recent cases, activity feed |
| `/cases` | CasesList | Table/Kanban view, create case, filter/sort |
| `/cases/:id` | CaseDetail | **6 tabs: Overview, Documents, Research, Financials, Pipeline, Referrals** |
| `/entities` | EntityBrowser | Search/filter persons, orgs, properties |
| `/entities/:type/:id` | EntityDetail | Entity profile + external search launchers |
| `/triage` | TriageQueue | Cross-case signal queue |
| `/referrals` | ReferralsView | Cross-case referral pipeline |
| `/search` | SearchView | Full-text search across everything |
| `/settings` | Settings | Theme, keyboard shortcuts, external launchers |

### Case Detail Tabs
1. **Overview** — Dashboard metrics, entity-relationship graph (D3), interactive timeline
2. **Documents** — Upload, OCR, view PDFs, generate memo
3. **Research** — Search external data sources (Parcels, Ohio SOS, Ohio AOS, IRS, Recorder) — NEW Session 28
4. **Financials** — Year-over-year 990 data table (revenue, expenses, assets)
5. **Pipeline** — Signals → Detections → Findings workflow
6. **Referrals** — Government referral tracking + case export

### What's MISSING from the Frontend
- **~~NO Research tab~~** — BUILT in Session 28 (6th tab on Case Detail)
- **~~NO connector UI~~** — BUILT in Session 28 (5 search sources wired)
- **NO inline notes on entities** — only signal notes exist
- **NO saved searches**
- **NO document annotation**
- **NO "Add to Case" button on research results** — results display but can't auto-create entities yet

---

## PROCESSING PIPELINE (How Data Flows)

```
Document Upload
      │
      ▼
extraction.py ──────── PDF text extraction (PyPDF2 → Tesseract OCR fallback)
      │
      ▼
classification.py ──── Identify doc type (990, deed, bank statement, etc.)
      │
      ▼
entity_extraction.py ── Rule-based: find persons, orgs, properties in text
      │
      ▼
ai_extraction.py ────── Claude AI fallback for complex/messy documents
      │
      ▼
entity_resolution.py ── Fuzzy match against existing entities, dedup + merge
      │
      ▼
data_quality.py ─────── Validate extracted data, log issues
      │
      ▼
signal_rules.py ─────── Run 29 fraud detection rules against case data
      │
      ▼
Results visible in Pipeline tab (Signals → Detections → Findings)
```

**form990_parser.py** is NOT in this pipeline. It should be called after classification identifies a 990, to extract Part IV/VI/VII governance data. This is a known gap.

---

## CONNECTOR DETAILS

### irs_connector.py (1466 lines) — WORKING ✅
- **What it does:** Fetches 990 XML data directly from IRS TEOS (apps.irs.gov). Uses HTTP range requests to extract individual XML files from ZIP archives (~5KB per filing instead of 100MB bulk downloads).
- **What it returns:** Full 990 data: Part I financials, Part IV checklist, Part VI governance, Part VII officer compensation
- **Wired to:** `api_research_irs()` (search by EIN or name) + `api_case_fetch_990s()` (fetch + create FinancialSnapshots)
- **Frontend:** "Fetch 990 Data" button on Research tab with expandable detail panel
- **Signal integration:** `evaluate_xml_financial_snapshots()` runs SR-006, SR-011, SR-012, SR-013, SR-025, SR-028, SR-029 using structured data
- **Replaces:** Old bulk CSV approach (Pub 78 + EO BMF) and ProPublica summary-only API

### propublica_connector.py (667 lines) — SUPERSEDED
- **What it does:** Calls ProPublica API by EIN, returns list of 990 filings
- **What it returns:** Filing year, form type, revenue, expenses, assets (SUMMARY ONLY — no Part IV/VI/VII)
- **Status:** Superseded by IRS TEOS XML pipeline. Code retained but no longer primary data source.

### county_recorder_connector.py (2045 lines) — WORKING ✅
- **What it does:** Maps all 88 Ohio counties to recorder portals, builds search URLs, parses OCR'd deed documents
- **Wired to:** `parse_recorder_document()` auto-triggers when a DEED is uploaded
- **Key functions:** `get_search_url(county, name)`, `parse_recorder_document(text)`, `get_county_info(county)`

### ohio_aos_connector.py (189 lines) — WORKING ✅
- **What it does:** Scrapes Ohio Auditor of State audit reports, finds "Finding for Recovery" determinations
- **Wired to:** Research tab via `api_research_ohio_aos()`
- **Key functions:** Search by entity name using ASP.NET ViewState postback
- **Why it matters:** Government audit findings are direct evidence of mismanagement

### ohio_sos_connector.py (896 lines) — WORKING ✅ (local CSV)
- **What it does:** Ohio Secretary of State entity lookup (business registration, statutory agents, formation dates)
- **How it works now:** Admin uploads 4 CSV files from publicfiles.ohiosos.gov via `POST /api/admin/upload-sos-csv/`. Connector searches from disk instead of downloading at runtime.
- **Admin endpoints:** `upload-sos-csv/` (upload) + `sos-csv-status/` (check which files exist)
- **Key functions:** Query by entity name, entity number, or registered agent
- **Why it matters:** Verifies if organizations actually exist, detects PHANTOM_OFFICER (SR-002)
- **Requires:** Tyler to download CSVs on home PC and upload them

### county_auditor_connector.py (1795 lines) — BROKEN ❌
- **What it does:** Two modes:
  - Mode 1: Queries ODNR statewide parcel API (ArcGIS REST) — covers all 88 Ohio counties
  - Mode 2: Builds direct URLs to county auditor portals
- **Key functions:** `search_parcels_by_owner(name)`, `search_parcels_by_pin(parcel)`, `get_auditor_url(county)`
- **Why it matters:** Cross-county property ownership detection for fraud patterns
- **Status:** ODNR ArcGIS API returning 404 from Railway. Both primary and fallback URLs unreachable.

---

## KNOWN BUGS & FIXES

### Fixed (Session 27)
- BUG-9: All AI POST endpoints missing @csrf_exempt (403 errors) — FIXED
- api_case_detection_collection also missing @csrf_exempt — FIXED
- API test pagination bug (expected list, got paginated dict) — FIXED
- 8 production bugs fixed in commit 79dcc78

### Fixed (Session 29)
- Frontend crash: "Cannot read properties of undefined (reading 'length')" — added `notes: []` to IRS/SOS responses + optional chaining on frontend
- Ohio AOS HTTP 404 — rewrote connector from GET `searchresults.aspx` to POST `search.aspx` with ASP.NET ViewState postback
- County Recorder 500 — `"name"` is reserved in Python LogRecord, renamed to `"search_name"` in logger.info extra dict
- County Recorder response format — restructured from `search_url`/`county_info` to standard `results`/`count` array
- County enum case mismatch — frontend sends "Darke", backend expected "DARKE"; added `.upper()` normalization
- Null byte corruption — cleaned `\x00` bytes from 4 files (views.py, App.tsx, form990_parser.py, urls.py)

### Fixed (Session 30 — from other machine)
- IRS connector OOM — rewrote to stream CSV index files instead of loading into memory
- IRS bulk download blocked — replaced entirely with IRS TEOS XML pipeline (HTTP range requests)
- ProPublica fetch endpoint had no UI button — added "Fetch 990 Data" button with expandable detail panel
- Ohio SOS HTTP 403 — rewrote connector to use locally uploaded CSVs instead of runtime download
- Referral memo was placeholder — replaced with AI-powered (Claude) narrative generator
- Ruff F841 unused variable in views.py — fixed

### Known Issues
- Git pre-commit hook points to Windows Python path (doesn't work in sandbox)
- form990_parser.py not integrated into extraction pipeline (may be partially superseded by IRS TEOS XML parser)
- ODNR ArcGIS parcel API returning 404 from Railway (both primary and fallback URLs)
- Ohio SOS requires manual CSV upload — Tyler needs to download files from publicfiles.ohiosos.gov on home PC
- Null bytes occasionally appear at end of files written by Cowork Edit tool; pre-commit hooks fix them but require re-stage

---

## TECHNOLOGY STACK

### Backend
- Python 3.11, Django 4.2
- PostgreSQL 16 (Railway managed)
- Gunicorn (2 workers)
- PyPDF2 + Tesseract OCR
- Anthropic Claude API (Haiku for extraction, Sonnet for analysis)

### Frontend
- React 18.3.1, TypeScript
- Vite build system
- D3.js (entity-relationship graphs)
- React Router DOM 6.30

### Infrastructure
- Docker (multi-stage: node:20-alpine + python:3.11-slim)
- Railway (auto-deploy from GitHub main branch)
- GitHub Actions CI (ruff lint + tsc + vite build)

### Code Style (MUST FOLLOW)
- **Ruff linter** with config in `pyproject.toml`
- **Line length: 100 characters max** (E501) for all Python files except connectors and tests
- Rules enabled: E (pycodestyle errors), F (pyflakes), I (isort)
- E501 is IGNORED in: `tests/`, `irs_connector.py`, `county_auditor_connector.py`, `county_recorder_connector.py`, `propublica_connector.py`, `verify_recorder_portals.py`
- **views.py is NOT exempt** — all lines must be ≤100 chars. Break long strings with parenthesized f-strings.
- Quote style: double quotes, indent: spaces, line endings: LF
- Pre-commit hooks run ruff + ruff-format on every commit

### External Data Sources
- **IRS TEOS XML** — Direct 990 e-file XML from apps.irs.gov (Session 30) ✅
- ProPublica Nonprofit Explorer API (superseded by IRS TEOS XML for financial data)
- Ohio SOS (local CSV upload + search from disk; bizimage API for document PDFs)
- ODNR Statewide Parcel API (ArcGIS REST)
- Ohio Auditor of State (web scraper)
- County recorder portals (88 counties, multiple vendors)
- Hinkle System (Ohio AOS financial reporting portal) — FUTURE

---

## CURRENT PRIORITIES (Session 32)

### THE REFRAME (Session 32 — most important thing in this file)

Catalyst is **not** investigation software. It is **referral packaging software
for citizen investigators handing off to professionals with subpoena power.**
The customer of the OUTPUT is the AG/IRS/FBI investigator, not Tyler. Every
design decision flows from that reframe.

The quality bar is "heavy confidence that it was going to go somewhere" — a
referral package a professional investigator can read in 15 minutes and act
on. That is the only thing that matters.

Corollary: Catalyst is a **portfolio piece**, not a product. It needs to get
Tyler hired. It does not need to scale, handle every edge case, or cover every
signal rule imaginable. First 70% is 100% — not 100% of everything at 70%.

### Priority 0: Recruiter-Facing Repo Presentation (ACTIVE — blocks everything else)

Tyler has job applications already out. The repo needs to look like "a project
under active, intentional development" **right now**, not at the end of the
14-day rebuild. A recruiter clicking the repo today should see a clean story
in under 60 seconds.

In progress this session:
- README refactor (product-first hook, "Why it exists" story, contact block with GitHub/email/LinkedIn, engineering-honest framing)
- New STATUS.md at repo root: Working / In Active Refactor / Planned columns
- Surface cleanup: delete stale CURRENT_STATE.md, fix CLAUDE.md model count (DONE), gitignore pytest cache, triage root-level audit markdown files and stray directories

Open decisions at end of Session 32:
- LinkedIn URL (needs Tyler to paste)
- Whether to keep referral case numbers (, ) in README — currently pulled out for anonymity

### Priority 1: 14-Day Shipping Window (after repo cleanup lands)

5–7 hours/day, target: portfolio-ready referral-package version. Major scope
decisions already made this session:

1. **Collapse Signal / Detection / Finding into one `Finding` model.** The
   three-table design conflates two different concepts (automatic ingestion
   vs. manual triage workbench). One Finding with `status`
   (NEW/NEEDS_EVIDENCE/DISMISSED/CONFIRMED) and `evidence_weight`
   (SPECULATIVE/DIRECTIONAL/DOCUMENTED/TRACED). The second dimension exists
   because directionally-meaningful-but-unproven findings (like the timeline
   compression on Example Hmains LLP) need a place to live with proper
   labeling, not a binary keep/throw.
2. **Cut the signal rule set from 29 down to ~5–7** — only rules grounded
   in patterns from the founding investigation. No speculative rules.
3. **Build the deterministic referral package exporter.** Template-driven,
   citation-bearing, NOT AI-generated. This is the central deliverable of
   the whole system. Every sentence in the output traces back to a citation
   in the case file.
4. **Cut:** `SocialMediaConnection` model (bot can't scan social anyway;
   use Document + Relationship instead), `GovernmentReferral` model,
   AI-generated narrative memo feature.
5. **Build Example Charity as a pre-loaded demo case.** Anonymized. Available on
   first launch so anyone — recruiter, interviewer, sample user — can see
   what a finished case looks like.

### Priority 2: Tyler Learns the Codebase (continues alongside rebuild)

Tyler must be able to explain every file in the project before the rebuild
ships. Session 30 covered: models.py (Case, Document, Person, Organization,
link tables), views.py (case CRUD, document upload pipeline). Concepts
understood: UUIDs, ForeignKey behaviors, TextChoices, ArrayField, M2M,
pagination, SHA-256 hashing, transaction.atomic(), serializer validation.

Still to walk through: frontend → API, entity_extraction.py,
entity_resolution.py, signal_rules.py, each connector.

### Already Shipped (Session 30)

- **IRS TEOS XML Pipeline ✅** — Replaced bulk CSV approach with direct 990 XML from IRS TEOS (apps.irs.gov). HTTP range requests pull ~5KB per filing. Parses Part I financials, Part IV checklist, Part VI governance, Part VII officer compensation. Frontend has "Fetch 990 Data" button with expandable detail panel.
- **Ohio SOS Local CSV ✅** — Rewrote connector to search from locally uploaded CSV files instead of runtime download. Added admin upload endpoints. Tyler needs to grab the files from publicfiles.ohiosos.gov on his home PC.
- **AI-Powered Referral Memo ✅ (being CUT in rebuild)** — Was built in Session 30. Being removed in favor of a deterministic template-driven referral package exporter per Session 32 reframe.

### On Hold

- **ODNR Parcel API Recovery** — Both ArcGIS endpoints unreachable from Railway. Monitoring for upstream fix. Not blocking anything critical.
- **form990_parser.py integration** — May be partially superseded by the IRS TEOS XML parser which now extracts Parts IV/VI/VII directly. Revisit after rebuild.

---

## SPECIALIST BRIEFING BOOKS

Located in `docs/team/`:
- **PLAYBOOK.md** — Session workflow, decision model, definition of done
- **qa-engineer.md** — Testing philosophy, known bug patterns, performance baselines
- **backend-engineer.md** — Data model relationships, API patterns, signal rules, extraction pipeline
- **irs-domain-expert.md** — Complete Form 990 structure, IRS e-file XML, parsing strategies
- **data-engineer.md** — Extraction pipeline, entity resolution, financial data, data quality

---

## SESSION HISTORY

32 sessions completed. Key milestones:
- Sessions 1-5: Initial Django + React scaffold, models, basic CRUD
- Sessions 6-10: Entity extraction, signal rules, document processing pipeline
- Sessions 11-15: Connectors (Ohio SOS, county auditor/recorder, ProPublica)
- Sessions 16-20: AI integration (Claude API), financial analysis, referral workflow
- Sessions 21-25: Frontend redesign (6 phases), entity graph, timeline, pipeline tab
- Session 26: Production bug fixes, CSRF fixes, API health check suite
- Session 27: 8 production bugs fixed, frontend redesign complete
- Session 28: System audit, CLAUDE.md creation, 5 research endpoints built, Research tab frontend built, all connectors wired to UI
- Session 29: Production debugging — fixed frontend crash (missing `notes` field), rewrote Ohio AOS connector (ASP.NET postback), fixed county enum case mismatch, fixed recorder logger crash, added ODNR fallback URL. Result: Ohio AOS + County Recorder confirmed working on Railway. ODNR/SOS/IRS blocked by external API issues. Commits: 4578786, f5b6325, 7ae653b, plus logger fix.
- Session 30: **Pivot session + major feature work (other machine).** Two tracks:
  - **Learning track (Cowork):** Tyler recognized that Claude wrote most of the code and he can't explain it in interviews. Walked through models.py (Case, Document, Person, Organization, link tables) and views.py (case CRUD, document upload pipeline). Tyler can now explain: UUIDs, ForeignKeys, TextChoices, ArrayField, many-to-many relationships, pagination, SHA-256 hashing, serializer validation, transaction.atomic().
  - **Feature track (Claude Code on other machine):** IRS connector completely rewritten — IRS TEOS XML pipeline replaces bulk CSV (8ec7826). Frontend "Fetch 990 Data" button added (1fe58b8). AI-powered referral memo generator replaces placeholder (fab0d3e). IRS streaming fix for OOM (8c2151c). Ohio SOS rewritten for local CSV approach with admin upload endpoints (8feeccb). Ruff/null-byte cleanup (d2fb504). Commits: 8ec7826, 1fe58b8, fab0d3e, e03b929, 8c2151c, d2fb504, 8feeccb.
  - **Result:** 4 of 6 connectors now working (IRS, SOS, AOS, Recorder). Only ODNR broken. ProPublica superseded.
- Session 32: **The reframe session.** Tyler walked through raw narrative of the founding investigation (Ohio nonprofit, $XK → $X.XM, Karen Example, UCC filings, Example Construction, ExampleVendor, AOS dormant entities, the property transaction, ExampleBoardMember board overlap). Key reframe landed: **Catalyst is referral packaging software for citizen investigators handing to professionals with subpoena power — not investigation software.** The customer of the output is the AG/IRS/FBI investigator, not Tyler. Quality bar: "heavy confidence that it was going to go somewhere." Major scope decisions: collapse Signal/Detection/Finding into one Finding with status + evidence_weight fields; cut signal rule set from 29 to ~5-7 grounded rules; kill AI-generated narrative memo and replace with deterministic template-driven referral package exporter; cut SocialMediaConnection and GovernmentReferral models; build Example Charity as preloaded demo case. Committed to 14-day shipping window (5-7 hrs/day). **New constraint mid-session:** Tyler has job applications already out — repo must look presentable to recruiters TODAY, not at end of rebuild. Day 1 reshaped: README refactor (product-first hook + "Why it exists" story + GitHub/email/LinkedIn contact block), STATUS.md creation with Working/In Active Refactor/Planned columns, surface cleanup (stale CURRENT_STATE.md, wrong model count in CLAUDE.md, pytest cache in repo). Drafts written for README and STATUS.md; awaiting Tyler's LinkedIn URL and referral-case-number decision before committing to disk. "One project, two pitches" framing established: universal pitch for general recruiters, niche pitch for fraud/forensic firms.

- Session 33: **The execution session.** Shipped every major item from the Session 32 scope decisions. Backend: collapsed Signal/Detection/Finding into single Finding model with migration-ready code; cut signal rules from 29 to 14; built deterministic referral package PDF exporter (reportlab, 794 lines — cover page, findings with [Doc-N] citations, financial tables, document index with SHA-256 hashes); built demo case management command (`seed_demo.py`, 965 lines — "Bright Future Foundation" fictional scenario with 4 persons, 2 orgs, 2 properties, 7 documents, 6 years of financials, 9 findings across 9 signal rules); removed SocialMediaConnection model + all references; removed GovernmentReferral model + all references (serializers, 3 endpoints, 3 URL patterns, frontend types, API functions, cross-case view). Frontend: rewrote types.ts (FindingItem replaces SignalItem/DetectionItem), rewrote api.ts, rewrote PipelineTab (single Finding workflow), rewrote CaseDetailView/TriageView/DashboardView, updated EntityGraph/EntityProfilePanel/TimelineView to use finding_count, added evidence weight CSS, added "Generate Referral Package (PDF)" button to ReferralsTab, deleted 13 stale component files, simplified ReferralsView. All builds pass (tsc, vite, ruff, Python syntax). Model count: 24 → 22. JS bundle shrunk 9KB from dead code removal. Tyler learned agent orchestration pattern (parallel task decomposition). Updated resume-talking-points.md with Interview Beat #6 on AI productivity.

---

## RESUME-READY TALKING POINTS (added Session 32)

Lift these directly for resume bullets, cover letters, LinkedIn headline, or
interview framing. All claims here are true as of Session 32 — if you edit
the system, keep these accurate.

### One-line elevator pitch (universal)
> "I built a full-stack public-records investigation platform for citizen
> investigators — Django + PostgreSQL backend, React + TypeScript frontend,
> six external data source connectors, 47 API endpoints, deployed on
> Railway — and used it to support a real fraud investigation that produced
> formal referrals to four federal and state agencies."

### One-line elevator pitch (niche — fraud / forensic / compliance firms)
> "I conducted a public-records investigation into an Ohio nonprofit that
> resulted in formal referrals to the Ohio AG, IRS, FBI, and a federal
> agency OIG, then rebuilt the manual investigation process as a full-stack
> platform with evidence-grade chain of custody, automated entity
> extraction, and a deterministic referral package exporter."

### Resume bullets (rank-ordered — strongest first)

- **Designed and shipped a full-stack investigation platform** (Django 4.2 / PostgreSQL 16 / React 18 / TypeScript / D3.js / Docker / Railway) that ingests documents, extracts entities, and exports referral packages — built from a real fraud investigation I ran by hand.
- **Architected an audit-first data model** with SHA-256 chain of custody on every document, append-only audit logging on every mutation, and immutable timestamp guards on government referral filing dates — treating legal defensibility as a primary requirement, not an afterthought.
- **Built six independent, failure-isolated external data connectors** for public records (IRS Form 990 XML via TEOS range requests, Ohio Secretary of State, Ohio Auditor of State, all 88 Ohio county recorder portals, ProPublica Nonprofit Explorer, ODNR statewide parcel layer) with full mock-HTTP offline test coverage.
- **Implemented a human-in-the-loop entity resolution pipeline** (rule-based extraction → normalization → fuzzy matching → investigator confirmation) that surfaces match candidates rather than silent-merging, as a deliberate legal defensibility decision.
- **Integrated the Anthropic Claude API** as a fallback for messy document extraction and as a triage/exploration aid — while keeping the deliverable (referral package export) deterministic and citation-bearing rather than AI-generated.
- **Designed a fraud signal detection engine** with pattern rules (shell entities, timeline compression, excessive officer compensation, address nexus) derived directly from anomalies I encountered in the founding investigation — not speculative.
- **Shipped a React + TypeScript + D3 frontend** with a force-directed entity-relationship graph synchronized to a brushable timeline, dark/light/auto theming, skeleton loading states, and WCAG-aware accessibility (skip-to-content, ARIA live regions, reduced-motion support).
- **Wrote 555+ backend tests** covering connectors, API endpoints, and signal rules, with CI running ruff, TypeScript type-check, and Vite build on every push.
- **Reframed the product mid-build** after recognizing the right customer of the output is the professional investigator, not the citizen user — then consolidated an over-engineered three-table workflow (Signal / Detection / Finding) into a single two-dimensional model, cut speculative features, and refocused on a defensible referral package as the core deliverable.

### Skills / keywords for resume keyword scanning

Python · Django · Django REST Framework · PostgreSQL · SQLAlchemy-style ORMs · migrations · SQL · React · TypeScript · Vite · React Router · D3.js · CSS Modules · Docker · Docker Compose · Railway · GitHub Actions · CI/CD · ruff · pytest · REST API design · authentication · CSRF · rate limiting · PDF text extraction · OCR (Tesseract) · Anthropic Claude API · LLM integration · web scraping (requests + BeautifulSoup + ASP.NET ViewState) · fuzzy matching · entity resolution · data pipelines · ETL · chain of custody · audit logging · full-stack development · agile / session-based development · technical writing

### Interview story beats

1. **The origin story** — "I started with a real investigation, not a product idea. I built Catalyst backwards from the pain of doing the work by hand."
2. **The audit-first decision** — "Chain of custody isn't a nice-to-have when the output will be read by an AG investigator. I put SHA-256 and an append-only audit log on every mutation from day one."
3. **The human-in-the-loop decision** — "I could have auto-merged fuzzy matches. I chose to surface candidates instead because a silent merge in an evidence chain is worse than an extra click."
4. **The reframe** — "I realized the system I was building wasn't investigation software. It was referral packaging software for a professional investigator with subpoena power. That reframe cut three models, killed an AI feature, and changed the whole UI."
5. **The working-with-AI story** — "Most of the early scaffmain was written by an AI coding assistant. I learned the hard way that I had to be able to explain every file before building more. That's where this project is right now — I can walk you through models.py and views.py line by line."

### What to leave out of resumes / interviews (until you decide)
- The specific Ohio nonprofit name
- The referral case numbers (, ) unless you're comfortable making the case identifiable
- "Vibe-coded by an AI" framing — use "AI-assisted development with deliberate ownership of the codebase" instead

---

## HOW TO WORK ON THIS PROJECT

1. **Read this file first.** Every session.
2. **Check CURRENT_STATE.md** for deployment status.
3. **Check the connector wiring table above** before building anything new — wire existing code first.
4. **Use the decision model** (GREEN/YELLOW/RED) for all choices.
5. **Run tests** before and after changes: `python tests/api_health_check.py`
6. **Tyler commits from his local machine** (sandbox git has permission issues with hooks).

---

## IMPORTANT: What Tyler Has Said Repeatedly

> "We build tools but the tools do nothing."
> "I don't want to just keep clicking and see what is broken."
> "I want thoroughness not speed."
> "I don't mind making decisions, I just need to know when to make them."
> "We need to stop relying on ProPublica if the information is incomplete."
> "I don't want to have to find-download-then upload. That doesn't make sense."
> "Claude has written most of it and there is so much in there that I can't explain."
> "I need to learn the balance, be able to explain the code but also learn how to make AI work for me."

**The prime directive: Make Catalyst useful for actual investigation work, not just a file cabinet.**
**The learning directive (Session 30): Tyler must be able to explain every file in this project before building new features.**
**The reframe directive (Session 32): Catalyst is referral packaging software for citizen investigators handing off to professionals with subpoena power. The customer of the output is the investigator with the badge, not Tyler. Every design decision flows from that. First 70% is 100% — not 100% of everything at 70%.**
**The portfolio directive (Session 32): Catalyst is a portfolio piece that needs to get Tyler hired. It does not need to scale or cover every edge case. The repo must look presentable to recruiters DURING the rebuild, not only after.**
