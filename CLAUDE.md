# CLAUDE.md — Catalyst System Map
**Last updated:** 2026-04-05 (Session 30)
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
│   │   ├── models.py            ← 21 Django models (1847 lines)
│   │   ├── views.py             ← 45 API endpoints (3947 lines) — CORE
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
│   │   ├── propublica_connector.py    ← ProPublica 990 API [PARTIALLY WIRED]
│   │   ├── county_recorder_connector.py ← 88 OH counties [PARTIALLY WIRED]
│   │   ├── county_auditor_connector.py  ← ODNR parcel API [NOT WIRED]
│   │   ├── irs_connector.py            ← IRS Pub 78 + EO BMF [NOT WIRED]
│   │   ├── ohio_sos_connector.py       ← OH Secretary of State [NOT WIRED]
│   │   ├── ohio_aos_connector.py       ← OH Auditor of State [NOT WIRED]
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
| ProPublica | propublica_connector.py | YES (`/api/cases/<uuid>/fetch-990s/`) | **NO** — no button exists | Untested | No UI button |
| County Recorder | county_recorder_connector.py | YES (`/research/recorder/`) + auto DEED | Research tab (URL builder) | **YES** ✅ | — |
| County Auditor | county_auditor_connector.py | YES (`/research/parcels/`) | Research tab | **NO** ❌ | ODNR ArcGIS API returning 404; fallback URL times out |
| IRS (Pub 78/BMF) | irs_connector.py | YES (`/research/irs/`) | Research tab | **NO** ❌ | Bulk CSV download — same pattern as SOS, likely fails |
| Ohio SOS | ohio_sos_connector.py | YES (`/research/ohio-sos/`) | Research tab | **NO** ❌ | HTTP 403 — SOS file server blocking Railway IP |
| Ohio AOS | ohio_aos_connector.py | YES (`/research/ohio-aos/`) | Research tab | **YES** ✅ | — |

**Session 29 update:** Tested all connectors on production. 2 of 6 confirmed working (AOS, Recorder). 3 broken due to external API issues (ODNR down, SOS blocking, IRS untested but same pattern). ProPublica still has no UI. AOS was rewritten to use ASP.NET ViewState postback. Recorder had logger crash (`name` is reserved in Python LogRecord).

### WHAT NEEDS TO BE BUILT

1. **IRSx integration** — Replace bulk CSV approach with IRSx library (pulls 990 XML from AWS S3). Fixes reliability AND gets full Part IV/VI/VII data.
2. **Ohio SOS alternative** — Switch from bulk file download to web scraping (avoids 403 block from Railway).
3. **ODNR parcel API** — Monitor if ArcGIS endpoint recovers, or find new URL. Both primary and fallback URLs currently unreachable from Railway.
4. **Result-to-case wiring** — "Add to Case" buttons exist but need testing on working connectors (AOS, Recorder).
5. **ProPublica UI button** — Add fetch-990s button to frontend (low priority if IRSx replaces it).

---

## DATA MODELS (21 Models)

### Core Investigation Models
- **Case** — name, status (ACTIVE/PAUSED/REFERRED/CLOSED), notes, referral_ref
- **Document** — filename, sha256_hash, doc_type, ocr_status, extraction_status, is_generated
- **Signal** — rule_id (SR-001..SR-029), severity, status (OPEN/UNDER_REVIEW/CONFIRMED/DISMISSED/ESCALATED)
- **Detection** — confirmed anomaly with evidence_snapshot, confidence_score
- **Finding** — investigator narrative with severity, legal_refs[], status (DRAFT→INCLUDED_IN_MEMO)

### Entity Models
- **Person** — name, aliases[], date_of_birth, date_of_death, role_tags[]
- **Organization** — name, ein, entity_number, state, org_type, formation_date
- **Property** — parcel_number, address, county, assessed_value, purchase_price, valuation_delta (generated)
- **FinancialInstrument** — instrument_type, filing_number, amount, anomaly_flags[]
- **FinancialSnapshot** — org FK, tax_year, revenue, expenses, net_assets (from 990)
- **Address** — normalized street/city/state/zip for ADDRESS_NEXUS detection

### Relationship Models
- **PersonDocument**, **OrgDocument** — entity-to-document links
- **PersonOrganization** — role_type (OFFICER, BOARD_MEMBER, COUNSEL, ADVISOR)
- **PropertyTransaction** — grantor/grantee with polymorphic entity link
- **Relationship** — person-to-person (FAMILY/BUSINESS/SOCIAL)
- **TransactionChain** + **TransactionChainLink** — grouped property deals
- **SocialMediaConnection** — platform + connection_strength

### Operational Models
- **GovernmentReferral** — agency, submission_id, status, immutable filing_date
- **InvestigatorNote** — polymorphic target (any entity/signal/detection)
- **AuditLog** — append-only forensic log (NEVER UPDATE OR DELETE)

---

## SIGNAL RULES (29 Rules)

| Rule | Severity | What It Detects |
|------|----------|----------------|
| SR-001 | CRITICAL | SHELL_ENTITY — Org with no people, address, or financials |
| SR-002 | HIGH | PHANTOM_OFFICER — Named in 990 but missing from SOS |
| SR-003 | MEDIUM | NAME_CONFLICT — Same entity, different names across sources |
| SR-004 | HIGH | TIMELINE_COMPRESSION — Entity formed + major transaction within 30 days |
| SR-005 | MEDIUM | CHARTER_CONFLICT — Actions inconsistent with stated mission |
| SR-006 | MEDIUM | ADDRESS_NEXUS — 5+ unrelated entities at same address |
| SR-007 | HIGH | REVENUE_ANOMALY — Revenue changes >50% year-over-year |
| SR-008 | MEDIUM | EXPENSE_ANOMALY — Expenses change >40% year-over-year |
| SR-009 | HIGH | EXCESSIVE_COMPENSATION — Officer salary >60% of revenue |
| SR-010 | MEDIUM | GRANT_DIVERSION — Funds to entity instead of beneficiary |
| SR-011 | MEDIUM | INSIDER_SWAP — Officer buys property then org donates |
| SR-012 | MEDIUM | CIRCULAR_TRANSFER — Funds loop through multiple entities |
| SR-013 | HIGH | RELATED_PARTY_TRANSACTION — Officer is also vendor |
| SR-014 | MEDIUM | DUPLICATE_GRANTS — Same recipient across multiple years |
| SR-015 | MEDIUM | BLACKOUT_PERIOD — Document during regulatory action |
| SR-016 | LOW | UNVERIFIED_EIN — Invalid EIN format |
| SR-017 | MEDIUM | FILING_GAP — 990 filing >18 months late |
| SR-018 | HIGH | PHANTOM_BENEFICIARY — Beneficiary has no contact info |
| SR-019 | MEDIUM | CASH_HEAVY — >60% of assets in cash |
| SR-020 | MEDIUM | RAPID_DISSOLUTION — Dissolved <1 year after major transaction |
| SR-021 | HIGH | CONFLICTED_ADVISOR — Advisor on multiple boards |
| SR-022 | MEDIUM | REAL_ESTATE_FLIP — Property bought and sold within 2 years |
| SR-023 | MEDIUM | DORMANT_ORG — No transactions >6 months |
| SR-024 | MEDIUM | ASSET_SHIFT — Assets transferred before referral |
| SR-025 | HIGH | PASS_THROUGH_ORG — Receives grant, immediately passes 95%+ out |
| SR-026 | MEDIUM | OFFICER_CONCENTRATION — Single officer controls >2 orgs |
| SR-027 | LOW | COMPLIANCE_GAP — Missing required 990 Schedule |
| SR-028 | HIGH | FRAUD_PATTERN_MATCH — Matches known fraud type |
| SR-029 | MEDIUM | TEMPORAL_ANOMALY — Multiple events on same date |

---

## API ENDPOINTS (45 Total)

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
POST   /api/cases/<uuid>/referral-memo/         → Generate memo
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

### Referrals
```
GET    /api/cases/<uuid>/referrals/             → Case referrals
POST   /api/cases/<uuid>/referrals/             → Create referral
PATCH  /api/cases/<uuid>/referrals/<uuid>/      → Update referral
DELETE /api/cases/<uuid>/referrals/<uuid>/      → Delete referral
GET    /api/referrals/                          → Cross-case referrals
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
POST   /api/cases/<uuid>/fetch-990s/            → Fetch 990 PDFs from ProPublica [NO UI BUTTON YET]
```

### Research Endpoints (NEW — Session 28)
```
POST   /api/cases/<uuid>/research/parcels/      → County Auditor parcel search (ODNR API)
POST   /api/cases/<uuid>/research/ohio-sos/     → Ohio SOS entity lookup
POST   /api/cases/<uuid>/research/ohio-aos/     → Ohio AOS audit report search
POST   /api/cases/<uuid>/research/irs/          → IRS EO BMF nonprofit lookup
POST   /api/cases/<uuid>/research/recorder/     → County Recorder portal URL builder
POST   /api/cases/<uuid>/research/add-to-case/ → Import research result as entity/note
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

### propublica_connector.py (667 lines) — PARTIALLY WIRED
- **What it does:** Calls ProPublica API by EIN, returns list of 990 filings
- **What it returns:** Filing year, form type, revenue, expenses, assets (SUMMARY ONLY)
- **Limitation:** Does NOT return Part IV, VI, VII line items. Only summary financials.
- **Wired to:** `api_case_fetch_990s()` endpoint exists, but NO frontend button calls it
- **Key function:** `fetch_990_by_ein(ein)` → `(list[dict], error)`

### county_recorder_connector.py (2045 lines) — PARTIALLY WIRED
- **What it does:** Maps all 88 Ohio counties to recorder portals, builds search URLs, parses OCR'd deed documents
- **Wired to:** `parse_recorder_document()` auto-triggers when a DEED is uploaded
- **Key functions:** `get_search_url(county, name)`, `parse_recorder_document(text)`, `get_county_info(county)`

### county_auditor_connector.py (1795 lines) — NOT WIRED
- **What it does:** Two modes:
  - Mode 1: Queries ODNR statewide parcel API (ArcGIS REST) — covers all 88 Ohio counties
  - Mode 2: Builds direct URLs to county auditor portals
- **Key functions:** `search_parcels_by_owner(name)`, `search_parcels_by_pin(parcel)`, `get_auditor_url(county)`
- **Why it matters:** Cross-county property ownership detection for fraud patterns

### irs_connector.py (994 lines) — NOT WIRED
- **What it does:** IRS Publication 78 lookup (deductibility check) + Exempt Organizations BMF search
- **Key functions:** `check_pub78(ein)`, `search_eo_bmf(ein)`
- **Limitation:** Uses bulk file download + local search, needs staleness management

### ohio_sos_connector.py (717 lines) — NOT WIRED
- **What it does:** Ohio Secretary of State entity lookup (business registration, statutory agents, formation dates)
- **Key functions:** Query by entity name, entity number, or registered agent
- **Why it matters:** Verifies if organizations actually exist, detects PHANTOM_OFFICER (SR-002)

### ohio_aos_connector.py (189 lines) — NOT WIRED
- **What it does:** Scrapes Ohio Auditor of State audit reports, finds "Finding for Recovery" determinations
- **Key functions:** Search by entity name
- **Why it matters:** Government audit findings are direct evidence of mismanagement

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

### Known Issues
- Git pre-commit hook points to Windows Python path (doesn't work in sandbox)
- form990_parser.py not integrated into extraction pipeline
- ProPublica fetch endpoint has no UI button
- ODNR ArcGIS parcel API returning 404 from Railway (both primary and fallback URLs)
- Ohio SOS bulk file server returning HTTP 403 from Railway (all 4 CSV files blocked)
- IRS bulk EO BMF download likely fails on Railway (same pattern as SOS — untested)
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
- Ohio SOS (bulk CSV + bizimage API for document PDFs)
- ODNR Statewide Parcel API (ArcGIS REST)
- Ohio Auditor of State (web scraper)
- County recorder portals (88 counties, multiple vendors)
- Hinkle System (Ohio AOS financial reporting portal) — FUTURE

---

## CURRENT PRIORITIES (Session 31)

### Priority 0: Tyler Learns the Codebase (ACTIVE)
Claude wrote most of the code in sessions 1-29. Tyler needs to understand every file he'd be asked about in an interview. Current approach: guided walkthrough of each layer — models first, then views, then frontend. No new features until Tyler can explain the existing ones.

**Completed so far (Session 30):**
- models.py: Case, Document, Person, Organization, link tables (PersonDocument, OrgDocument)
- Key concepts understood: UUIDs, ForeignKey/RESTRICT/CASCADE/SET_NULL, TextChoices, ArrayField, many-to-many relationships, abstract base models
- views.py: case listing (GET with pagination/filtering), case creation (POST with validation + audit log), document upload pipeline (validate → hash → save → extract → classify → entity extraction)
- Key concepts understood: pagination (limit/offset), serializer validation, transaction.atomic(), SHA-256 hashing for chain of custody

**Next up:**
- Frontend: how React calls the API endpoints and displays data
- entity_extraction.py / entity_resolution.py: how the system finds and deduplicates entities
- signal_rules.py: how fraud detection rules work
- Connectors: what each one does and why some are broken

### Priority 1: IRSx Integration (YELLOW — Tyler confirmed, ON HOLD)
Replace bulk CSV IRS connector with IRSx library. On hold until Tyler understands the existing codebase well enough to participate in building it.

### Priority 2: Ohio SOS Alternative Approach (ON HOLD)
Current approach downloads 4 bulk CSV files (~50MB each) from publicfiles.ohiosos.gov — Railway gets HTTP 403. On hold for same reason as Priority 1.

### Priority 3: ODNR Parcel API Recovery (ON HOLD)
Both ArcGIS endpoints unreachable from Railway. Monitor for recovery.

### Priority 4: Integrate form990_parser.py (ON HOLD)
After classification identifies a 990, run form990_parser to extract governance data.

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

30 sessions completed. Key milestones:
- Sessions 1-5: Initial Django + React scaffold, models, basic CRUD
- Sessions 6-10: Entity extraction, signal rules, document processing pipeline
- Sessions 11-15: Connectors (Ohio SOS, county auditor/recorder, ProPublica)
- Sessions 16-20: AI integration (Claude API), financial analysis, referral workflow
- Sessions 21-25: Frontend redesign (6 phases), entity graph, timeline, pipeline tab
- Session 26: Production bug fixes, CSRF fixes, API health check suite
- Session 27: 8 production bugs fixed, frontend redesign complete
- Session 28: System audit, CLAUDE.md creation, 5 research endpoints built, Research tab frontend built, all connectors wired to UI
- Session 29: Production debugging — fixed frontend crash (missing `notes` field), rewrote Ohio AOS connector (ASP.NET postback), fixed county enum case mismatch, fixed recorder logger crash, added ODNR fallback URL. Result: Ohio AOS + County Recorder confirmed working on Railway. ODNR/SOS/IRS blocked by external API issues. Commits: 4578786, f5b6325, 7ae653b, plus logger fix.
- Session 30: **Pivot session.** Tyler recognized that Claude wrote most of the code and he can't explain it in interviews. Shifted from feature-building to codebase education. Walked through models.py (Case, Document, Person, Organization, link tables) and views.py (case CRUD, document upload pipeline). Tyler can now explain: UUIDs, ForeignKeys, TextChoices, ArrayField, many-to-many relationships, pagination, SHA-256 hashing, serializer validation, transaction.atomic(). No code changes — learning session only. Next: frontend layer, then entity extraction, then signal rules.

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
