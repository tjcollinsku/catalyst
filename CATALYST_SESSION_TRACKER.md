# Catalyst Session Tracker

## Purpose

This file is the lightweight running log for session-to-session continuity.

Use it to track:
- open tasks
- immediate next steps
- blockers
- short end-of-session recaps

## Current Open Tasks

- Enter first real case through the intake UI to exercise the hardened upload workflow
- Phase 3: Build investigator UI for fuzzy match candidate review (confirm/reject/merge)
- Phase 5 (future): Multi-state SOS connector support (same interface pattern as Ohio)
- **⚠️ MUST RETURN: Re-verify all CountyFusion counties once GovOS outage resolves** — see blocker below

## Immediate Next Steps

- Signal Detection Engine is **complete** — all 10 rules wired, tested, and green.
- Next Phase 3 items per charter:
  1. Referral memo generator — auto-draft narrative from confirmed signals and findings
  2. Government referral tracking — mark signals as referred, log agency + date
  3. React frontend (Phase 3 charter item) — case list, signal triage UI, finding editor
- **County Recorder connector corrections are complete** for all non-CF counties — verified working
- **After CF outage clears:** spot-check Seneca (key Osgood county) + ~5 other CF counties, then update checklist ❌ → ✅

## Current Blockers

### ⚠️ GovOS CountyFusion Platform Outage — ONGOING as of 2026-03-28
- **All CountyFusion servers are DOWN** — countyfusion2, countyfusion4, countyfusion6, countyfusion14 all fail to load (confirmed via browser testing and user report of Van Wert spinning)
- **~20 Ohio counties affected**, including **Seneca County** (key Osgood investigation county)
- All other systems (Fidlar AVA, GovOS Cloud Search, DTS PAXWorld, Cott Systems, EagleWeb) are fully operational and verified
- **Action required when CF recovers:** run spot-checks on Seneca, Richland, Wayne, Tuscarawas, Van Wert, Ashland, and update `county_recorder_portal_checklist.md` statuses from ❌ to ✅
- Seneca recorder phone (if urgent): 419-447-4476

## Session Recap Log

### 2026-03-28 (Session 18) — County Recorder Connector Full Audit + Test Suite Update

#### ⚠️ GovOS CountyFusion Platform Outage (UNRESOLVED — must revisit)
- Confirmed platform-wide outage affecting all CountyFusion servers (cf2, cf4, cf6, cf14 all dead)
- ~20 Ohio counties inaccessible including **Seneca** (key Osgood investigation county)
- Root cause of original timeout reports: combination of (1) CF outage and (2) many counties having migrated away from CF entirely

#### County Recorder Connector — Full 88-County Audit
- Conducted Gemini-assisted 4-batch audit of all 88 Ohio county recorder portals
- Corrected the connector from ~60+ counties wrongly listed as CountyFusion to accurate systems
- **RecorderSystem enum expanded** from 6 → 10 values: added `DTS_PAXWORLD`, `FIDLAR_AVA`, `EAGLEWEB`, `COTT_SYSTEMS`
- **System breakdown after audit:**
  - GovOS CountyFusion: ~20 counties (Seneca, Richland, Wayne, Tuscarawas, Ashland, Van Wert, etc.) — currently ALL DOWN
  - Fidlar AVA: ~17 counties (Holmes, Wood, Mercer, Athens, Champaign, Darke, Defiance, Fairfield, Geauga, Lake, Marion, Miami, Paulding, Scioto, Vinton, Williams, Wyandot)
  - GovOS Cloud Search: ~14 counties (Carroll, Clark, Ottawa, Franklin, Butler, Cuyahoga, Warren, Greene, Harrison, Jefferson, Washington, etc.)
  - DTS PAXWorld: 6 counties (Allen, Licking, Lorain, Lucas, Stark, Trumbull)
  - Cott Systems: 3 counties (Ashtabula, Knox, Lawrence)
  - EagleWeb (Tyler): 2 counties (Erie, Summit)
  - USLandRecords (Avenu): 2 counties (Madison, Pike)
  - Custom/Other: ~12 counties
  - LAREDO: 0 counties (legacy enum value retained for requires_login logic)
- **Key corrections:** Trumbull → DTS PAXWorld (migrated May 2023, under OH Auditor investigation); Mercer → Fidlar AVA (key Osgood county, confirmed accessible); Butler/Cuyahoga/Warren → Cloud Search; Holmes/Wood → Fidlar AVA; Richland/Wayne/Tuscarawas/Sandusky → CountyFusion (were wrong system)
- Created `county_recorder_portal_checklist.md` — all 88 counties with system, URL, and status (✅/❌/❓)
- Non-CF counties verified working via browser testing (Mercer/Fidlar AVA confirmed live with 4,571 Homan results)

#### Test Suite Update
- Updated `tests_county_recorder.py` to match the corrected connector (was written against original 6-system, CF-dominant state)
- Key test changes: `test_six_systems_present` → `test_ten_systems_present`; all system spot-check assertions updated; `test_countyfusion_is_largest_group` (>60) → `test_countyfusion_still_significant_group` (≥15); added `test_filter_fidlar_ava`, `test_filter_laredo_legacy` (expects 0); county-specific: Holmes/Wood/Mercer/Paulding → FIDLAR_AVA; Butler/Cuyahoga/Warren → GOVOS_CLOUD_SEARCH; Richland/Wayne/Tuscarawas/Sandusky → GOVOS_COUNTYFUSION; Trumbull → DTS_PAXWORLD; USLandRecords threshold lowered to 2
- **Note:** Test suite has not been run against the live Django environment (sandbox limitation) — run `python -m unittest investigations.tests_county_recorder -v` to confirm green

### 2026-03-27 (Session 17) — Signal Detection Engine Complete
- Built the full Signal Detection Engine: `signal_rules.py` with all 10 SR rules (SR-001 through SR-010), wired into the document upload pipeline and exposed via two new API endpoints.
- **`signal_rules.py`** (created): stateless rule engine; RULE_REGISTRY with all 10 rules; `SignalTrigger` dataclass; `_run_rule` wrapper (one bad rule never aborts the rest); 10 evaluator functions returning `list[SignalTrigger]`; `evaluate_document()`, `evaluate_case()`, `persist_signals()` entry points; deduplication against existing non-DISMISSED signals.
- **`models.py`** (extended): added `Organization.formation_date` (DateField, for SR-002) and `Signal.detected_summary` (TextField, for machine-generated explanation text).
- **Migration `0008`** generated: `org_formation_date_signal_summary.py` — adds `formation_date` to organization table and `detected_summary` to signals table.
- **`serializers.py`** (extended): added `serialize_signal()` (resolves title/description from RULE_REGISTRY) and `SignalUpdateSerializer` (validates status transitions; enforces note required on DISMISS per FR-604).
- **`views.py`** (extended): wired `evaluate_document()` + `evaluate_case()` + `persist_signals()` into `document_upload` as best-effort (logs on failure, never aborts upload); added `api_case_signal_collection` (GET with `status`, `severity`, `rule_id` filters, full pagination + sorting); added `api_case_signal_detail` (GET + PATCH confirm/dismiss/escalate).
- **`urls.py`** (extended): registered `GET /api/cases/<pk>/signals/` and `GET|PATCH /api/cases/<pk>/signals/<signal_id>/`.
- **`tests_signals.py`** (created, 100 new tests): RuleRegistryTests (10 rules, severities, title/description); SR-001 through SR-010 unit tests (fires / no-fire / boundary conditions); `persist_signals()` deduplication (OPEN deduped, DISMISSED allows re-fire); `serialize_signal()` structure; `SignalUpdateSerializer` validation paths; signal collection API (filters, pagination, 404, 405); signal detail API (GET, PATCH confirm/dismiss/escalate, validation errors).
- Full suite: **704/704 tests pass** — clean green.
- Installed missing `requests` dependency into project venv (was in requirements.txt but not installed).
- Generated migration `0007_signal_entitysignal.py`: creates `Signal`, `EntitySignal`, `FindingDocument`, `FindingEntity` tables, adds `confidence`, `legal_refs`, `signal_type`, `signal_rule_id`, `status` fields to `Finding`, alters `doc_type`/`severity`/`role_tags` field choices, and adds all signal indexes and constraints.
- Fixed `_PERSON_INVERTED_PATTERN` in `entity_extraction.py`: changed first-name capture from `[A-Z][a-z]+` to `[A-Z][A-Za-z]+` so all-caps names like "HOMAN, JOHN A." are correctly extracted.
- Full suite: **604/604 tests pass** — clean baseline confirmed.
- Signal Detection Engine is unblocked.

### 2026-03-27 (Session 16) — Test Baseline Stabilization
- Installed missing `requests` dependency into project venv (was in requirements.txt but not installed).
- Generated migration `0007_signal_entitysignal.py`: creates `Signal`, `EntitySignal`, `FindingDocument`, `FindingEntity` tables, adds `confidence`, `legal_refs`, `signal_type`, `signal_rule_id`, `status` fields to `Finding`, alters `doc_type`/`severity`/`role_tags` field choices, and adds all signal indexes and constraints.
- Fixed `_PERSON_INVERTED_PATTERN` in `entity_extraction.py`: changed first-name capture from `[A-Z][a-z]+` to `[A-Z][A-Za-z]+` so all-caps names like "HOMAN, JOHN A." are correctly extracted.
- Full suite: **604/604 tests pass** — clean baseline confirmed.
- Signal Detection Engine is unblocked.

### 2026-03-28 (Session 15) — Bug Fix & Entity DB Testing
- Fixed `county_recorder_connector.py` regex priority bug where `MORTGAGE` intercepted `SATISFACTION OF MORTGAGE`.
- Updated `tests_county_recorder.py` to strictly enforce the correct instrument sub-type classifications.

### 2026-03-28 (Session 14) — Phase 3: Ohio Auditor of State Connector
- Built `ohio_aos_connector.py`: stateless HTML scraper for the Ohio Auditor of State audit search.
- Extracts audit reports, release dates, and critical "Findings for Recovery" flags.
- Built `tests_ohio_aos.py` with mocked HTTP responses to verify HTML parsing and error handling without network dependency.
- Recommended running DB-backed entity tests inside Docker.

### 2026-03-27 (Session 13) — Phase 3: County Auditor Connector + Tests
- Built `county_auditor_connector.py`: dual-mode Ohio county auditor connector for parcel ownership research
- Mode 1 (automated): ODNR Statewide Parcel Layer ArcGIS REST API (`gis.ohiodnr.gov`) — queryable across all 88 counties simultaneously, no auth required, no scraping
- Mode 2 (human-in-the-loop): Beacon/county portal URL builder for financial details (sale price, assessed value, transfer history) not available in the statewide layer
- Dual-mode rationale: ODNR layer carries ownership identity (cross-county fraud detection); individual county portals carry financial detail (verification step); both together give full picture without scraping session-protected portals
- `OhioCounty` enum: all 88 counties as lowercase slugs (defined independently — module is stateless, no Django imports)
- `AuditorPortalSystem` enum: BEACON, COUNTY_SITE, UNAVAILABLE (3 values)
- `_AUDITOR_REGISTRY`: all 88 counties — system vendor, portal URL, Beacon app ID, phone, address, FIPS, seat
  - System breakdown: majority (~80) on Beacon (Schneider Geospatial); notable exceptions: Cuyahoga, Franklin, Hamilton, Mercer, Seneca, Trumbull on county-hosted portals
  - Darke/Mercer confirmed by investigation origin — Darke on Beacon (AppID=DarkeCountyOH), Mercer on own portal (`auditor.mercercountyohio.gov`)
- `get_auditor_info(county)` → `AuditorInfo` with portal details
- `list_counties(system=None)` → all 88 sorted alphabetically, optional system filter
- `get_auditor_url(county, owner_name, parcel_id)` → `AuditorUrlResult`; `requires_login=False` for all (all Ohio auditor portals are free public access)
- `search_parcels_by_owner(owner_name, county, session)` → `ParcelSearchResult`; WHERE clause searches both `OWNER1` and `OWNER2`; cross-county when no county filter; county-filtered when `county=` provided
- `search_parcels_by_pin(pin, county, session)` → `ParcelSearchResult`; searches both `PIN` and `STATEWIDE_PIN`
- ODNR fields used: `OBJECTID`, `PIN`, `STATEWIDE_PIN`, `COUNTY`, `OWNER1`, `OWNER2`, `CALC_ACRES`, `ASSR_ACRES`, `AUD_LINK`
- `AuditorError` raised on HTTP 4xx/5xx, connection error, timeout, JSON parse failure, ArcGIS API error envelope
- `_escape_like(value)` doubles single quotes for SQL LIKE injection safety
- `_run_odnr_query()` centralizes HTTP call, result parsing, and error handling
- `ParcelRecord` dataclass: all ODNR fields + `raw` dict for full API response preservation
- `ParcelSearchResult` dataclass: query, county_filter, records, count, truncated, note (note always includes pointer to county auditor portal for sale price / assessed value lookup)
- Built `tests_county_auditor.py`: 126/126 tests pass — all HTTP mocked via `MagicMock` session injection, no real network calls
- Tests cover: `OhioCounty` enum (88 members, all lowercase), `AuditorPortalSystem` (3 values), registry completeness (all 88, FIPS all odd, Beacon URLs use `schneidercorp.com`, Beacon counties have beacon_app with "OH", county sites have `beacon_app=None`, all use https), system spot-checks (Darke/Mercer/Seneca/Franklin/Hamilton/Cuyahoga/Trumbull/Allen/Wood), `get_auditor_info` (spot checks, every county retrievable, missing-county error), `list_counties` (count, filter by system, alphabetical, filter sums to 88), `get_auditor_url` (requires_login=False for all, Beacon URL format, name/parcel hints in instructions, county site URL), search HTTP paths (success, 500, 404, timeout, connection error, JSON parse error, ArcGIS error envelope), truncation flag at MAX_RESULTS, WHERE clause content (OWNER1+OWNER2, county filter, PIN+STATEWIDE_PIN), `_parse_parcel_feature` (all fields, None for missing/empty/non-numeric), `_escape_like`, `_build_result_note`, `AuditorError` attributes, `ParcelRecord`/`ParcelSearchResult` dataclass fields

### 2026-03-20 (Session 1)
- Added recurring recap documents for architecture and file walkthroughs
- Added this tracker file for open tasks, next steps, and blockers
- Project in stable state for continuing Phase 1 work

### 2026-03-20 (Session 2)
- Fixed Docker Compose obsolete `version` warning — removed `version: "3.9"` line
- Upgraded Django admin registrations with proper `ModelAdmin` classes
- `GovernmentReferral` admin: list view, status/agency filters, search, `filing_date` locked read-only
- `AuditLog` admin: fully enforced read-only — add, change, delete all disabled
- `Case`, `Document`, `Person`, `Organization`, `Finding` all upgraded with list views and filters
- Django system check passes with 0 issues

### 2026-03-20 (Session 3)
- Fixed Django → PostgreSQL authentication: `load_dotenv()` added to `settings.py` so `.env` is loaded before DB config is read
- Reset `catalyst_user` password in Docker container to match `.env`
- Confirmed Django connects to PostgreSQL successfully
- `showmigrations` verified: 18 migrations applied across all apps
- `\dt` confirmed: 23 tables present in database including all Phase 1 domain tables
- Database is fully built and Django is live against it

### 2026-03-26 (Session 4)
- Added `investigations/serializers.py` for case intake validation and JSON serialization
- Added Django-native JSON API endpoints for case list, create, and detail under `/api/cases/`
- Added API tests covering create, validation failure, detail payload, and list ordering
- Updated project docs so the current milestone state matches the codebase

### 2026-03-26 (Session 5)
- Expanded the JSON API from basic intake to a fuller case/document workflow surface
- Added case PATCH and DELETE support with conflict handling for protected related records
- Added case and document list pagination metadata, filters, date-range filters, and allowlisted sorting
- Added case-scoped document detail, PATCH, and DELETE endpoints
- Added strict SHA-256 validation for document intake payloads
- Grew the investigations test suite to 41 passing tests covering create, list, detail, update, delete, filters, sorting, and validation paths
- Added `backend/API_COOKBOOK.md` and refreshed `backend/SERIALIZER_API_REFERENCE.md`

### 2026-03-26 (Session 6) — Phase 1 Complete
- Added NOTARY and TRUSTEE to PersonRole enum (run makemigrations to apply)
- Fixed stale `orc_reference` field reference in FindingAdmin — updated to current Finding fields (severity, confidence, status, signal_type, signal_rule_id)
- Added proper ModelAdmin classes for all 6 plain-registered models: Property, FinancialInstrument, PersonDocument, OrgDocument, PersonOrganization, PropertyTransaction
- Confirmed Phase 1 minimal dashboard is complete — Django template views (case_list, case_detail, case_form, document_upload) satisfy the Phase 1 charter requirement; React frontend deferred to Phase 3 per charter
- Phase 1 is fully closed out — all charter items complete

### 2026-03-27 (Session 12) — Phase 3: County Recorder Connector + Tests
- Built `county_recorder_connector.py`: human-in-the-loop Ohio county recorder connector
- Strategy: URL builder + document parser, no HTTP requests in the module (investigator downloads docs manually)
- `OhioCounty` enum: all 88 counties as lowercase slugs
- `RecorderSystem` enum: 6 system types (GOVOS_COUNTYFUSION, GOVOS_CLOUD_SEARCH, LAREDO, USLANDRECORDS, CUSTOM, UNAVAILABLE)
- `_REGISTRY`: complete mapping of all 88 Ohio counties — portal URL, system vendor, phone, address, records_from year
- System vendor breakdown: ~70+ CountyFusion (govos.com / kofiletech.us domains), 5 Cloud Search (publicsearch.us), 3 Laredo (Holmes/Warren/Wood), 5+ USLandRecords (Madison/Paulding/Pike/Richland/Tuscarawas/Wayne), 4 Custom (Butler/Cuyahoga/Delaware/Union)
- `get_county_info(county)`: returns CountyInfo from registry
- `list_counties(system=None)`: all 88 counties sorted alphabetically, optional system filter
- `get_search_url(county, grantor_grantee)`: URL builder — CountyFusion returns login page (requires_login=True), Cloud Search with template builds direct search URL (requires_login=False), others return portal URL
- `parse_recorder_document(text, county)`: regex parser for extracted deed/mortgage text
  - Detects 18 instrument types (warranty deed, quitclaim, mortgage, easement, UCC, affidavit, etc.)
  - Extracts grantor(s)/grantee(s) via label-format and inline-format patterns
  - Zero-consideration detection → consideration=0.0 for SR-005 signal
  - Dollar amount extraction from consideration/purchase-price clauses
  - Nominal consideration detection (ten dollars and other valuable consideration, love and affection)
  - Parcel ID extraction (Ohio format XX-XXXXXX.XXX)
  - Recording date, instrument number, book/page reference
  - Legal description snippet (first 500 chars from "Situated in..." etc.)
  - Preparer name + title search disclaimer detection → preparer_notes for SR-005 signal
- Known limitation: `MORTGAGE` pattern fires before `SATISFACTION OF MORTGAGE` / `RELEASE OF MORTGAGE` in pattern list — subtypes not detected correctly (documented in tests and next steps)
- Built `tests_county_recorder.py`: 191/191 tests pass — no network calls (connector has no HTTP)
- Tests cover: OhioCounty enum (88 members, all lowercase), RecorderSystem enum (6 values), registry completeness (all 88 counties, FIPS codes, CountyFusion domain check, Cloud Search counties, template counties), get_county_info (spot checks, every county retrievable, missing-county error), list_counties (count, filter by system, alphabetical, filter sums to 88), get_search_url (requires_login by system, template substitution, Cloud Search direct URL, all counties have non-empty instructions), parse_recorder_document (empty/None/whitespace raises error, county preserved, raw_text_snippet cap, all instrument types, grantor/grantee extraction, consideration parsing 12 cases, parcel ID, recording date, instrument number, book/page, legal description, preparer + disclaimer), RecorderError (message/county/isinstance), _title_case_name (caps conversion, LLC/INC/JR preservation, mixed-case passthrough, strip whitespace), integration test with full Seneca-style deed text

### 2026-03-27 (Session 11) — Phase 2 Complete: IRS Connector + Tests
- Built `irs_connector.py`: dual-source IRS bulk data strategy
- Source 1 (Pub78): zip download from apps.irs.gov, pipe-delimited, gives deductibility-eligible orgs with EIN/name/city/state/country/deductibility code
- Source 2 (EO BMF): CSV downloads from irs.gov/pub/irs-soi/, regional (eo1-eo4) and state-level (eo_oh.csv etc.), gives full master file with ruling date, status, NTEE code, financial size indicators
- `EoBmfRegion` enum maps all four regional files + 7 state-level files to stable IRS download URLs
- `Pub78Record` and `EoBmfRecord` dataclasses model both data sources explicitly
- `StalenessWarning` (same tier system as Ohio SOS: LOW/MEDIUM/HIGH) always returned alongside results
- `fetch_pub78()`: downloads zip, extracts pipe-delimited text, returns records + staleness warning
- `fetch_eo_bmf(region)`: downloads CSV by region/state, returns records + staleness warning
- `search_pub78()`: case-insensitive substring match + optional state filter
- `search_eo_bmf()`: case-insensitive substring match + optional state filter + include_revoked flag
- `lookup_ein()`: exact EIN match from EO BMF — returns ruling year/month for SR-002 signal detection
- `search_ohio_nonprofits()`: one-call convenience wrapper (downloads STATE_OH + searches)
- Built `tests_irs.py`: 104/104 tests pass — all HTTP mocked, no real network calls
- Tests cover: all region URLs, staleness tiers, Pub78 parsing (pipe-delimited), EO BMF parsing (CSV), fetch errors (404/500/connection/timeout/bad-zip/empty-zip), search (name match/state filter/case-insensitive/no match/empty query/empty records/include_revoked), lookup_ein (found/not-found/string EIN normalization/revoked org), search_ohio_nonprofits integration, IRSError attributes, _safe_int edge cases
- Phase 2 connector set is now complete: ProPublica (990 filings) + Ohio SOS (entity search) + IRS (exemption status + EIN lookup)

### 2026-03-27 (Session 10) — Ohio SOS Connector + Tests
- Built `ohio_sos_connector.py`: bulk CSV download strategy for Ohio Secretary of State entity search
- Pivoted away from scraping after Cloudflare blocked `businesssearch.ohiosos.gov` and Power BI Embedded confirmed `data.ohiosos.gov` is not queryable
- `ReportType` enum maps 15 report types to direct download URLs at `publicfiles.ohiosos.gov` — no auth, no bot detection
- `EntityRecord` dataclass captures all fields for both new-entity and amendment CSV formats
- `StalenessWarning` dataclass: always returned with search results; tiers LOW/MEDIUM/HIGH by file age
- Human-in-the-loop design: every search result carries a StalenessWarning prompting manual verification at `businesssearch.ohiosos.gov` for anything recent
- `fetch_report()` downloads + parses one report; `load_reports()` combines multiple; `search_entities()` does case-insensitive substring or fuzzy match; `search_ohio()` one-call convenience wrapper
- Amendment report CSV typo ("TRANSASCTION") handled silently in `_parse_records()`
- `CATALYST_DEFAULT_REPORTS` = [NONPROFIT_CORPS, LLC_DOMESTIC, AMENDMENTS, CORP_FORPROFIT]
- Built `tests_ohio_sos.py`: 59/59 tests pass — all HTTP mocked, no network required
- Tests cover: CSV parsing (new entity + amendment formats), date parsing, staleness tiers (LOW/MEDIUM/HIGH), load_reports partial failure, search exact + fuzzy, empty query/records errors, OhioSOSError attributes, all ReportType URLs
- Multi-state noted as Phase 5 future item; Ohio-specific now with clean same-interface design

### 2026-03-27 (Session 9) — Phase 2 ProPublica Connector
- Built `propublica_connector.py`: stateless connector for the ProPublica Nonprofit Explorer API (no auth required)
- Three public functions: `search_organizations(query, state)`, `fetch_organization(ein)`, `fetch_filings(ein)`
- Convenience function `fetch_full_profile(ein)` fetches org profile + all filings in one HTTP call
- `Filing.pdf_url` feeds directly into Catalyst's existing document intake pipeline
- Explicit `ProPublicaError` type for network failures, 404s, rate limits, and bad EINs
- EIN normalization: accepts integer or string with/without dash (`"12-3456789"` → `123456789`)
- Added `requests>=2.31,<3.0` to requirements.txt
- 29/29 tests pass using `unittest.mock` — no real network calls, no API quota consumed

### 2026-03-27 (Session 8) — Phase 2 Entity Extraction Pipeline
- Built `entity_extraction.py`: deterministic regex pipeline for persons, orgs, dates, amounts, parcel numbers, and filing reference numbers
- Built `entity_normalization.py`: canonical form functions — person name uninversion (LAST, FIRST → First Last), honorific/suffix stripping, org designator stripping (Inc., LLC, etc.), Unicode normalization
- Built `entity_resolution.py`: two-tier matching — exact upsert (idempotent, no human review) + fuzzy candidate flagging (SequenceMatcher, threshold 0.75, never auto-merged)
- `resolve_all_entities()` batch entry point wired into `document_upload` view — best-effort, upload never aborted on extraction failure
- Fuzzy candidates logged with top-5 detail for investigator review in Phase 3 UI
- All 20 pure-Python extraction and normalization tests pass; DB-backed resolution tests written and ready to run in Docker
- Alias matching is implemented: confirmed aliases stored on `Person.aliases`, exact-matched on next occurrence (no fuzzy needed)

### 2026-03-26 (Session 7) — Phase 2 Processing Pipeline Foundations
- Implemented direct PDF text extraction using PyMuPDF and wired automatic extraction into `document_upload`
- Added synchronous OCR fallback for scanned PDFs via Tesseract + Pillow with 30 MB gate for sync processing
- Added rule-based document classification service and wired automatic classification when user keeps `doc_type=OTHER`
- Expanded `DocumentType` taxonomy and added `is_generated` + `doc_subtype` fields for evidence/output separation
- Added and applied migrations `0005` and `0006`; database schema updated and validated
- Hardened `Person.role_tags` with `PersonRole` choices and added `Person.is_deceased()` helper
- Added structured upload decision logging with dedicated logger `investigations.upload_pipeline`
- Logging is production-ready by default, quiet in test/dev by default, and toggleable with `ENABLE_UPLOAD_PIPELINE_LOGS=true`
- Expanded test coverage to 46 passing tests, including upload decision matrix and generated-flag behavior

## Update Pattern

At the end of each session, update:
- `Current Open Tasks`
- `Immediate Next Steps`
- `Current Blockers`
- newest entry under `Session Recap Log`
