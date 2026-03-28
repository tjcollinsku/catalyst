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

### `backend/investigations/migrations/0005_document_doc_subtype_document_is_generated_and_more.py`
- Adds `is_generated` and `doc_subtype` fields to `Document`
- Expands `DocumentType` enum with recorder, mortgage, lien, and forgery types

### `backend/investigations/migrations/0006_alter_person_notes_alter_person_role_tags.py`
- Constrains `Person.role_tags` to use `PersonRole` enum choices
- Makes `Person.notes` non-nullable with empty string default

### `backend/investigations/extraction.py`
- PDF text extraction service — Stage 1 of the document processing pipeline
- Two-stage: direct extraction (PyMuPDF) → OCR fallback (Tesseract + Pillow)
- Returns `(extracted_text, ocr_status)` tuple
- Files over 30 MB stay `PENDING` for async handling; smaller scanned files get sync OCR

### `backend/investigations/classification.py`
- Rule-based document type classifier
- Auto-assigns `doc_type` when user leaves it as `OTHER`
- Uses keyword matching against extracted text
- Called automatically from `document_upload` view after text extraction

### `backend/investigations/entity_extraction.py`
- Stage 1 of the entity resolution pipeline — pure Python, no Django imports
- Regex patterns for: persons (labeled context + inverted LAST, FIRST format), orgs (anchored on legal designators), dates (4 formats, all normalized to ISO 8601), dollar amounts, parcel numbers, and filing reference numbers
- Returns structured dicts with `raw`, `normalized`, and `context` fields
- Stateless — accepts raw text string, returns plain Python data structures

### `backend/investigations/entity_normalization.py`
- Stage 2 of the entity resolution pipeline — pure Python, no Django imports
- `normalize_person_name()`: uninverts LAST, FIRST → First Last; strips honorifics, suffixes, punctuation; lowercases
- `normalize_org_name()`: strips legal designators (Inc., LLC, Corp.), filler words (the, a, of), punctuation; lowercases
- Foundation that makes `"EXAMPLE, JOHN A."` and `"John A. Example"` compare as equal

### `backend/investigations/entity_resolution.py`
- Stage 3 of the entity resolution pipeline — has Django model imports, writes to DB
- Two-tier matching: exact match (automatic upsert) + fuzzy match (flagged, never auto-merged)
- `resolve_person()` and `resolve_org()`: match or create, return result with fuzzy candidates
- `resolve_all_entities()`: batch entry point — processes full `extract_entities()` output
- Creates `PersonDocument` and `OrgDocument` links automatically, idempotent
- Fuzzy threshold 0.75 (SequenceMatcher); candidates sorted by similarity, returned to caller for review

### `backend/investigations/propublica_connector.py`
- ProPublica Nonprofit Explorer API connector — stateless, no Django imports, no DB writes
- `search_organizations(query, state)`: search by name/keyword, returns list of `OrganizationSummary`
- `fetch_organization(ein)`: full IRS profile by EIN, returns `OrganizationProfile`
- `fetch_filings(ein)`: all 990 filings with financial totals and PDF URLs, returns list of `Filing`
- `fetch_full_profile(ein)`: convenience wrapper — profile + filings in one HTTP call
- `Filing.pdf_url` feeds directly into Catalyst's document intake pipeline
- Explicit `ProPublicaError` type for 404s, rate limits, timeouts, bad EINs
- EIN normalization: accepts integer or string with/without dash (`"12-3456789"` → `123456789`)
- No API key required; polite delay between calls configurable via `POLITE_DELAY`

### `backend/investigations/tests.py`
- Main Django test suite — requires DB connection (run inside Docker)
- Covers API endpoints, upload pipeline routing, entity resolution (DB-backed)
- 46 passing tests through Session 7; DB resolution tests added in Session 8 (run in Docker to verify)

### `backend/investigations/tests_propublica.py`
- Standalone test file for the ProPublica connector — pure `unittest`, no Django, no DB, no network
- All HTTP calls mocked with `unittest.mock` — runs offline, fast, no API quota consumed
- 29/29 tests covering search, org profile, filings parsing, EIN validation, error handling

### `backend/investigations/ohio_sos_connector.py`
- Ohio Secretary of State bulk-file connector — stateless, no Django imports, no DB writes
- Bulk CSV download strategy: downloads monthly report files from `publicfiles.ohiosos.gov` — no bot detection, no auth required
- `ReportType` enum: 15 report types (new entity + amendment); each has `.url` and `.is_amendment` properties
- `fetch_report(report_type)` → list[EntityRecord]: downloads + parses one CSV file
- `load_reports(report_types)` → list[EntityRecord]: downloads multiple reports, returns combined flat list; partial failures logged and skipped
- `search_entities(query, records, fuzzy)` → SearchResult: case-insensitive substring (default) or normalized fuzzy match
- `search_ohio(query, report_types, fuzzy)` → SearchResult: one-call convenience wrapper using CATALYST_DEFAULT_REPORTS
- `StalenessWarning`: always returned with results; tiered LOW/MEDIUM/HIGH by file age (< 7 days / 7–21 days / > 21 days)
- Handles the Ohio SOS amendment CSV header typo ("TRANSASCTION") silently in `_parse_records()`
- `CATALYST_DEFAULT_REPORTS` = [NONPROFIT_CORPS, LLC_DOMESTIC, AMENDMENTS, CORP_FORPROFIT]
- Human-in-the-loop design: StalenessWarning always prompts investigator to manually verify at `businesssearch.ohiosos.gov`

### `backend/investigations/tests_ohio_sos.py`
- Standalone test file for the Ohio SOS connector — pure `unittest`, no Django, no DB, no network
- All HTTP calls mocked with `unittest.mock` — runs offline, fast
- 59/59 tests covering: CSV parsing (new entity + amendment formats), date parsing, staleness tiers (LOW/MEDIUM/HIGH), load_reports partial failure recovery, search exact + fuzzy matching, empty query/records validation errors, OhioSOSError attributes, all ReportType URL and is_amendment properties

### `backend/investigations/irs_connector.py`
- IRS Tax Exempt Organization connector — stateless, no Django imports, no DB writes
- Two data sources: Publication 78 (zip download, pipe-delimited) and EO Business Master File (CSV, regional/state)
- `EoBmfRegion` enum: 4 regional files (NORTHEAST/SOUTHEAST/MIDWEST/SOUTH_WEST) + 7 state files (OH/IL/IN/MI/KY/PA/WV); each has a `.url` property
- `Pub78Record` dataclass: EIN, name, city, state, country, deductibility code/description
- `EoBmfRecord` dataclass: EIN, name, city, state, zip, subsection, ruling date (→ year/month), status, is_revoked, NTEE code, financial size fields, and raw dict
- `StalenessWarning`: same LOW/MEDIUM/HIGH tier system as Ohio SOS connector
- `fetch_pub78(url)` → `(list[Pub78Record], StalenessWarning)`: downloads zip, extracts pipe-delimited text
- `fetch_eo_bmf(region, url)` → `(list[EoBmfRecord], StalenessWarning)`: downloads CSV for the given region/state
- `search_pub78(query, records, staleness_warning, state)`: case-insensitive name search, optional state filter
- `search_eo_bmf(query, records, staleness_warning, state, include_revoked)`: same, with revoked-org toggle
- `lookup_ein(ein, records, staleness_warning)` → `(EoBmfRecord | None, StalenessWarning)`: exact EIN match; ruling year/month feed SR-002 signal detection
- `search_ohio_nonprofits(query, include_revoked)`: one-call convenience wrapper (downloads STATE_OH + searches)

### `backend/investigations/tests_irs.py`
- Standalone test file for the IRS connector — pure `unittest`, no Django, no DB, no network
- All HTTP calls mocked — runs offline, fast, no IRS quota consumed
- 104/104 tests covering: all 11 EoBmfRegion URLs, staleness tier thresholds, Pub78 parsing (pipe-delimited), EO BMF CSV parsing (~30 columns), all fetch error types (404/500/connection/timeout/bad-zip/empty-zip), search (name match/state filter/case-insensitive/no match/empty inputs/include_revoked), lookup_ein (found/not-found/string EIN/revoked org), search_ohio_nonprofits integration, IRSError attributes, `_safe_int` edge cases

### `backend/investigations/county_recorder_connector.py`
- Ohio county recorder connector — stateless, no Django imports, no HTTP requests (human-in-the-loop design)
- Strategy: URL builder + document parser; investigator downloads docs manually, drops into intake pipeline
- `OhioCounty` enum: all 88 Ohio counties as lowercase slugs (ADAMS through WYANDOT)
- `RecorderSystem` enum: GOVOS_COUNTYFUSION, GOVOS_CLOUD_SEARCH, LAREDO, USLANDRECORDS, CUSTOM, UNAVAILABLE
- `CountyInfo` dataclass: name, FIPS code, seat city, system, portal_url, search_url_template, portal_notes, phone, address, records_from year
- `SearchUrlResult` dataclass: county, county_name, url, system, instructions, requires_login flag
- `RecorderDocument` dataclass: all structured fields from a parsed deed/mortgage (see below)
- `_REGISTRY` dict: all 88 counties with full CountyInfo — verified system assignments and portal URLs
- `get_county_info(county)` → `CountyInfo`; raises `RecorderError` if county missing from registry
- `list_counties(system=None)` → list of OhioCounty sorted alphabetically; optional system filter
- `get_search_url(county, grantor_grantee)` → `SearchUrlResult`; Cloud Search counties with templates build direct search URLs; CountyFusion/Laredo set `requires_login=True`
- `parse_recorder_document(text, county)` → `RecorderDocument`: parses instrument type (18 patterns), grantors/grantees (label + inline patterns), consideration (zero = 0.0 for SR-005), parcel ID, recording date, instrument number, book/page, legal description, preparer + title-search disclaimer (SR-005 signal)
- Known limitation: `MORTGAGE` pattern fires before `SATISFACTION OF MORTGAGE` / `RELEASE OF MORTGAGE` in ordered pattern list — subtypes not detected; documented in test comments

### `backend/investigations/tests_county_recorder.py`
- Standalone test file for the county recorder connector — pure `unittest`, no Django, no DB, no network
- No HTTP mocking needed (the connector makes no HTTP calls)
- 191/191 tests covering: OhioCounty enum (88 members, all lowercase), RecorderSystem (6 values), registry completeness (all 88 counties, FIPS validity, domain checks, template counties, system spot-checks), `get_county_info` (every county retrievable, error path), `list_counties` (count, filter by system, alphabetical sort, filter sums to 88), `get_search_url` (requires_login by system, Cloud Search template substitution, direct URL generation, all counties have non-empty instructions), `parse_recorder_document` (empty/None/whitespace raises error, county preserved, raw_text_snippet cap, all instrument types, grantor/grantee extraction, 12 consideration cases, parcel ID, recording date, instrument number, book/page, legal description, preparer + disclaimer), `RecorderError` attributes, `_title_case_name` (ALL-CAPS conversion, LLC/INC/JR preservation, mixed-case passthrough)

### `backend/investigations/county_auditor_connector.py`
- Ohio county auditor connector — stateless, no Django imports, dual-mode design
- Mode 1 (automated): ODNR Statewide Parcel Layer ArcGIS REST API (`gis.ohiodnr.gov`) — queryable across all 88 counties at once; no auth, no scraping, no session portal
- Mode 2 (human-in-the-loop): Beacon/county portal URL builder for financial details (sale price, assessed value, transfer history) not available in the statewide layer
- `OhioCounty` enum: all 88 Ohio counties as lowercase slugs (defined at module level — no Django dependency)
- `AuditorPortalSystem` enum: BEACON (Schneider Geospatial, `~80` counties), COUNTY_SITE, UNAVAILABLE
- `AuditorInfo` dataclass: name, FIPS, seat, system, portal_url, beacon_app, portal_notes, phone, address
- `ParcelRecord` dataclass: object_id, pin, statewide_pin, county, owner1, owner2, calc_acres, assr_acres, aud_link, raw (full API response dict preserved)
- `ParcelSearchResult` dataclass: query, county_filter, records, count, truncated, note
- `AuditorUrlResult` dataclass: county, county_name, url, system, instructions, requires_login (always False — all portals are free public access)
- `_AUDITOR_REGISTRY` dict: all 88 counties — system, portal URL, Beacon app code, phone, address, FIPS code, seat city
  - Notable exceptions from Beacon: Cuyahoga, Franklin, Hamilton, Mercer, Seneca, Trumbull on county-hosted portals
  - Darke: Beacon (AppID=DarkeCountyOH); Mercer: `auditor.mercercountyohio.gov`; Seneca: `senecacountyauditoroh.gov`
- `get_auditor_info(county)` → `AuditorInfo`; raises `AuditorError` if county not in registry
- `list_counties(system=None)` → list of OhioCounty sorted alphabetically; optional system filter
- `get_auditor_url(county, owner_name, parcel_id)` → `AuditorUrlResult`; owner_name/parcel_id hints appear in instructions for investigator follow-up
- `search_parcels_by_owner(owner_name, county, session)` → `ParcelSearchResult`; WHERE clause: `UPPER(OWNER1) LIKE '%NAME%' OR UPPER(OWNER2) LIKE '%NAME%'`; add `AND UPPER(COUNTY) = 'X'` when county filter provided
- `search_parcels_by_pin(pin, county, session)` → `ParcelSearchResult`; WHERE clause: `PIN LIKE '%X%' OR STATEWIDE_PIN LIKE '%X%'`
- ODNR fields used: `OBJECTID`, `PIN`, `STATEWIDE_PIN`, `COUNTY`, `OWNER1`, `OWNER2`, `CALC_ACRES`, `ASSR_ACRES`, `AUD_LINK`
- `AuditorError`: message, county (optional), status_code (optional); raised on HTTP 4xx/5xx, connection errors, timeouts, JSON parse failures, ArcGIS error envelopes
- `_escape_like(value)`: doubles single quotes — protects SQL LIKE clause from injection
- `_run_odnr_query(where, query, county_filter, session)`: centralizes HTTP call, ArcGIS error check, feature parsing
- `_parse_parcel_feature(feature)` → `ParcelRecord`: extracts attributes dict; returns None for missing/empty/non-numeric fields

### `backend/investigations/tests_county_auditor.py`
- Standalone test file for the county auditor connector — pure `unittest`, no Django, no DB, no network
- All HTTP mocked via `MagicMock` session injection (`session=` parameter on search functions)
- 126/126 tests covering: `OhioCounty` enum (88 members, all lowercase, spot checks), `AuditorPortalSystem` (3 values), registry completeness (88 entries, all FIPS codes odd, all portal URLs present and HTTPS, Beacon URLs use `schneidercorp.com`, Beacon counties have `beacon_app` ending in "OH", county-site counties have `beacon_app=None`), system spot-checks (Darke/Mercer/Seneca/Franklin/Hamilton/Cuyahoga/Trumbull/Allen/Wood), `get_auditor_info` (spot checks + every county retrievable + missing-county error), `list_counties` (count=88, system filter, alphabetical sort, filter sums to 88), `get_auditor_url` (requires_login=False for all, Beacon URL contains schneidercorp.com, county site URL, name/parcel hints in instructions), search HTTP success path (count, records list, query preserved, note content), search error paths (500/404/timeout/connection/JSON/ArcGIS error all raise AuditorError), WHERE clause verification (OWNER1+OWNER2 both present, county filter appended, PIN+STATEWIDE_PIN both present), truncation flag at MAX_RESULTS, `_parse_parcel_feature` (all fields, None for missing/empty/non-numeric), `_escape_like` (no-op / single-quote doubling / multiple quotes / empty string), `_build_result_note` (query present, count present, sale price pointer, 88-county note when no filter, truncation warning), `AuditorError` attributes, `ParcelRecord`/`ParcelSearchResult` dataclass field defaults

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

### 2026-03-26 (Session 6)
- Added NOTARY and TRUSTEE to `PersonRole` enum in `models.py`
- Fixed stale field reference in `FindingAdmin`
- Added proper `ModelAdmin` classes for all remaining plain-registered models
- Phase 1 dashboard confirmed complete via Django template views

### 2026-03-26 (Session 7)
- Added `backend/investigations/extraction.py` — PDF extraction + OCR pipeline
- Added `backend/investigations/classification.py` — rule-based document classifier
- Added migrations `0005` and `0006` for new document and person fields
- Wired both into `document_upload` view

### 2026-03-27 (Session 8)
- Added `backend/investigations/entity_extraction.py` — regex entity extractor
- Added `backend/investigations/entity_normalization.py` — canonical form normalizer
- Added `backend/investigations/entity_resolution.py` — exact + fuzzy matcher with DB upsert
- Wired `resolve_all_entities()` into `document_upload` view as best-effort post-processing step
- 20 pure-Python extraction and normalization tests pass standalone

### 2026-03-27 (Session 10)
- Added `backend/investigations/ohio_sos_connector.py` — Ohio SOS bulk CSV connector
- Added `backend/investigations/tests_ohio_sos.py` — 59 mocked tests, no network required

### 2026-03-27 (Session 11)
- Added `backend/investigations/irs_connector.py` — dual-source IRS bulk download connector
- Added `backend/investigations/tests_irs.py` — 104 mocked tests, no network required

### 2026-03-27 (Session 12)
- Added `backend/investigations/county_recorder_connector.py` — Ohio county recorder connector (88 counties, URL builder + document parser, no HTTP)
- Added `backend/investigations/tests_county_recorder.py` — 191 tests, no network required

### 2026-03-27 (Session 13)
- Added `backend/investigations/county_auditor_connector.py` — dual-mode Ohio county auditor connector (ODNR ArcGIS API + Beacon URL builder, all 88 counties)
- Added `backend/investigations/tests_county_auditor.py` — 126 tests, all HTTP mocked via MagicMock session injection, no real network calls

### 2026-03-27 (Session 9)
- Added `backend/investigations/propublica_connector.py` — ProPublica API connector
- Added `backend/investigations/tests_propublica.py` — 29 mocked tests, no network required
- Added `requests>=2.31,<3.0` to `backend/requirements.txt`

## Next Updates

Use this file for:
- file-by-file explanations
- tracking newly added files
- noting when a file changes purpose
- quick re-orientation at the start of each session
