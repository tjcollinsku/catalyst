# Catalyst System Overview

## Purpose

Catalyst is being built as an intelligence triage and investigation support platform.

Its current Phase 1 focus is:
- defining the database schema
- scaffolding the Django backend
- preserving defensible audit history
- preparing for cloud deployment with trustworthy timestamps

## Current Architecture

### Backend
- Django project lives in `backend/`
- Primary app is `investigations`
- Django models now represent the Phase 1 schema

### Database
- PostgreSQL 16 runs locally in Docker container `catalyst_db` (port 5432)
- SQL bootstrap migrations live in `database/migrations/`
- Django migrations live in `backend/investigations/migrations/`
- 20 Django migrations applied; 23 tables confirmed in database
- Django connects via credentials in `.env` at project root — loaded by `load_dotenv()` in `settings.py`

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

## API Layer

- Django-native JSON intake endpoints now exist for case workflows
- `GET /api/cases/` returns paginated case list data with filters and allowlisted sorting
- `POST /api/cases/` validates and creates a case record from JSON payloads
- `GET /api/cases/<uuid>/` returns case metadata plus linked document metadata
- `PATCH /api/cases/<uuid>/` supports controlled case updates for status, notes, and referral reference
- `DELETE /api/cases/<uuid>/` supports case deletion with conflict handling when related records exist
- `GET /api/cases/<uuid>/documents/` returns paginated, filterable, sortable document lists scoped to a case
- `POST /api/cases/<uuid>/documents/` validates and creates a document record under the case
- `GET /api/cases/<uuid>/documents/<uuid>/` returns one document scoped to a case
- `PATCH /api/cases/<uuid>/documents/<uuid>/` supports controlled document metadata updates
- `DELETE /api/cases/<uuid>/documents/<uuid>/` deletes a case-scoped document
- Validation and serialization logic is isolated in `investigations/serializers.py`
- API usage is documented in `backend/SERIALIZER_API_REFERENCE.md` and `backend/API_COOKBOOK.md`

## Phase 2 Processing Layer (Current State)

### Document Processing
- Upload pipeline performs direct PDF text extraction (PyMuPDF) automatically on document upload
- Scanned/sparse PDFs use synchronous OCR fallback (Tesseract + Pillow) for files up to 30 MB
- Files above the 30 MB OCR gate are preserved with `ocr_status=PENDING` for later async handling
- Rule-based document classification auto-assigns `doc_type` when user input stays at `OTHER`
- `Document` model separates source evidence from generated outputs via `is_generated`
- `doc_subtype` added for fine-grained subtype detail without enum explosion

### Entity Extraction Pipeline
Three-stage pipeline runs automatically after OCR/classification on every upload:

```
Stage 1: extract_entities()       — regex → raw candidate strings
Stage 2: normalize_*()            — canonical form for comparison
Stage 3: resolve_all_entities()   — exact upsert or fuzzy candidate flag
```

- Stage 1 (`entity_extraction.py`): extracts persons, orgs, dates, amounts, parcel numbers, filing refs
- Stage 2 (`entity_normalization.py`): uninverts names, strips honorifics/designators, lowercases
- Stage 3 (`entity_resolution.py`): exact match → idempotent upsert; fuzzy match → review queue (never auto-merged)
- Fuzzy threshold: 0.75 similarity (SequenceMatcher); high-confidence threshold: 0.92
- Extraction is best-effort — a failure here never aborts an upload
- Fuzzy candidates logged with top-5 detail; investigator review UI planned for Phase 3

### Data Source Connectors
- `propublica_connector.py`: ProPublica Nonprofit Explorer API (no auth required)
  - `search_organizations(query, state)` → list of `OrganizationSummary`
  - `fetch_organization(ein)` → `OrganizationProfile` (ruling date, NTEE code, exemption status)
  - `fetch_filings(ein)` → list of `Filing` with financial totals and PDF URLs
  - `Filing.pdf_url` feeds directly into the document intake pipeline
  - Explicit `ProPublicaError` for 404s, rate limits, timeouts, and bad EINs

- `ohio_sos_connector.py`: Ohio Secretary of State bulk CSV connector (no auth required)
  - Bulk CSV download from `publicfiles.ohiosos.gov` — updated second Saturday of each month
  - `fetch_report(report_type)` → list of `EntityRecord` (one report file)
  - `load_reports(report_types)` → combined list across multiple report types
  - `search_entities(query, records, fuzzy)` → `SearchResult` with matches and `StalenessWarning`
  - `search_ohio(query)` → one-call convenience wrapper using `CATALYST_DEFAULT_REPORTS`
  - `StalenessWarning` always included — human-in-the-loop design; tiers LOW/MEDIUM/HIGH
  - `ReportType` enum covers 15 report types (new entity + amendment/dissolution/reinstatement)
  - Handles Ohio SOS CSV header typo ("TRANSASCTION") transparently
  - Phase 5 future: multi-state support using same public interface pattern

- `irs_connector.py`: IRS Tax Exempt Organization connector — dual-source bulk download strategy
  - Source 1 (Pub78): zip download from apps.irs.gov, pipe-delimited, deductibility-eligible orgs
  - Source 2 (EO BMF): CSV regional/state files from irs.gov/pub/irs-soi/ — full master file
  - `EoBmfRegion` enum: 4 regional files (eo1–eo4) + 7 state-level files including `STATE_OH`
  - `Pub78Record` and `EoBmfRecord` dataclasses model both sources explicitly
  - `StalenessWarning` pattern consistent with Ohio SOS: LOW/MEDIUM/HIGH tiers
  - `fetch_pub78()`, `fetch_eo_bmf(region)` — download and parse respective bulk files
  - `search_pub78()`, `search_eo_bmf()` — case-insensitive substring match + optional state filter
  - `lookup_ein(ein, records)` — exact EIN match → returns ruling year/month for SR-002 signal detection
  - `search_ohio_nonprofits(query)` — one-call convenience wrapper (downloads STATE_OH + searches)

- `county_recorder_connector.py`: Ohio county recorder portal connector — human-in-the-loop design (Phase 3)
  - No HTTP requests in the module — investigator downloads docs manually and drops into intake pipeline
  - `OhioCounty` enum: all 88 Ohio counties as lowercase slugs
  - `RecorderSystem` enum: 6 vendor types (GovOS CountyFusion, GovOS Cloud Search, Laredo, USLandRecords, Custom, Unavailable)
  - `_REGISTRY`: complete mapping of all 88 counties — portal URL, system vendor, phone, address, records_from year
  - System breakdown: ~70 CountyFusion, 5 Cloud Search (Carroll/Clark/Ottawa/Sandusky/Franklin), 3 Laredo (Holmes/Warren/Wood), 5+ USLandRecords (Madison/Paulding/Pike/Richland/Tuscarawas/Wayne), 4 Custom (Butler/Cuyahoga/Delaware/Union)
  - `get_county_info(county)` → `CountyInfo` with portal URL and investigator instructions
  - `list_counties(system=None)` → all 88 alphabetically sorted, optional system filter
  - `get_search_url(county, grantor_grantee)` → `SearchUrlResult` with URL + instructions; Cloud Search counties with template build direct search URLs; CountyFusion/Laredo set `requires_login=True`
  - `parse_recorder_document(text, county)` → `RecorderDocument` with structured fields:
    - 18 instrument type patterns (warranty deed, quitclaim, mortgage, easement, UCC, affidavit, etc.)
    - Grantor(s)/grantee(s) via label-format and inline-format patterns; title-cased output
    - Zero-consideration detection → `consideration=0.0` (feeds SR-005 signal)
    - Dollar amount extraction, nominal consideration detection (ten dollars/love and affection)
    - Parcel ID extraction (Ohio format XX-XXXXXX.XXX)
    - Recording date, instrument number, book/page
    - Legal description snippet (first 500 chars from "Situated in..." etc.)
    - Preparer name + title search disclaimer → `preparer_notes` (feeds SR-005 signal)

- `county_auditor_connector.py`: Ohio county auditor connector — dual-mode design (Phase 3)
  - Mode 1 (automated): ODNR Statewide Parcel Layer ArcGIS REST API — queryable across all 88 counties simultaneously, no auth required
  - Mode 2 (human-in-the-loop): Beacon/county portal URL builder for financial details not in the statewide layer
  - Design rationale: ODNR layer gives ownership identity for cross-county fraud pattern detection; individual county portals give sale price, assessed value, transfer history for verification
  - `OhioCounty` enum: all 88 counties as lowercase slugs (module-level, no Django dependency)
  - `AuditorPortalSystem` enum: BEACON (Schneider Geospatial), COUNTY_SITE, UNAVAILABLE
  - `_AUDITOR_REGISTRY`: all 88 counties — system, portal URL, Beacon app ID, phone, address, FIPS, seat
  - System breakdown: ~80 on Beacon; notable county-hosted exceptions: Cuyahoga, Franklin, Hamilton, Mercer, Seneca, Trumbull
  - `get_auditor_info(county)` → `AuditorInfo`
  - `list_counties(system=None)` → all 88 alphabetically sorted, optional system filter
  - `get_auditor_url(county, owner_name, parcel_id)` → `AuditorUrlResult`; `requires_login=False` for all (all Ohio auditor portals are free public access)
  - `search_parcels_by_owner(owner_name, county, session)` → `ParcelSearchResult`; searches both `OWNER1` and `OWNER2`; cross-county when no filter, county-scoped when `county=` provided
  - `search_parcels_by_pin(pin, county, session)` → `ParcelSearchResult`; searches both `PIN` and `STATEWIDE_PIN`
  - ODNR fields: `OBJECTID`, `PIN`, `STATEWIDE_PIN`, `COUNTY`, `OWNER1`, `OWNER2`, `CALC_ACRES`, `ASSR_ACRES`, `AUD_LINK`
  - `AuditorError` raised on HTTP errors, connection failure, timeout, JSON parse failure, ArcGIS API error envelope
  - `_escape_like()` doubles single quotes for SQL LIKE injection safety
  - `ParcelRecord.aud_link` carries direct link to full county auditor record for investigator follow-up

- `ohio_aos_connector.py`: Ohio Auditor of State connector (Phase 3)
  - Stateless HTML scraper that extracts audit reports and flags "Findings for Recovery".
  - Evaluates HTML table structure via regex (avoids extra dependencies).

## Hardening & Observability

- Upload pipeline emits structured decision logs through dedicated logger `investigations.upload_pipeline`
- Logs are JSON-formatted for machine parsing in production (`INFO` level by default)
- Test/dev logging noise suppressed by default; override with `ENABLE_UPLOAD_PIPELINE_LOGS=true`
- Person role tags use constrained `PersonRole` choices instead of free-text arrays
- Entity extraction wired as best-effort post-processing — upload never blocked by extraction failure
- Connector tests use `unittest.mock` — no real network calls, no API quota consumed

## Test Coverage Summary

| Test file | Runner | Count | Notes |
|---|---|---|---|
| `investigations/tests.py` | Django (requires Docker DB) | 46+ | API, upload pipeline, entity resolution |
| `investigations/tests_propublica.py` | `python -m unittest` (no DB) | 29 | All HTTP mocked |
| `investigations/tests_ohio_sos.py` | `python -m unittest` (no DB) | 59 | All HTTP mocked |
| `investigations/tests_irs.py` | `python -m unittest` (no DB) | 104 | All HTTP mocked |
| `investigations/tests_county_recorder.py` | `python -m unittest` (no DB) | 191 | No HTTP (connector has none) |
| `investigations/tests_county_auditor.py` | `python -m unittest` (no DB) | 126 | All HTTP mocked via MagicMock session |
| Inline extraction/normalization | `python -c` standalone | 20 | Pure Python assertions |

## Session Recap Log

### 2026-03-20 (Session 1)
- Phase 1 Django backend scaffold created
- Initial investigation schema modeled in Django
- SQL bootstrap path corrected under `database/migrations/`
- PostgreSQL container started and verified
- `government_referrals` added and migrated
- `filing_date` hardened with DB defaults and immutability trigger

### 2026-03-20 (Session 2)
- Removed obsolete `version` field from `docker-compose.yml`
- Upgraded Django admin with proper `ModelAdmin` classes across all key models
- AuditLog admin locked completely — append-only enforced at admin layer

### 2026-03-20 (Session 3)
- Fixed Django → PostgreSQL auth: `load_dotenv()` added to `settings.py`
- 18 migrations confirmed applied; 23 tables confirmed in PostgreSQL

### 2026-03-26 (Session 4)
- Intake API implemented without DRF dependency
- JSON endpoints: case list, case create, case detail
- API test coverage added

### 2026-03-26 (Session 5)
- Full case/document API with pagination, date-range filtering, PATCH, DELETE, conflict handling
- Strict SHA-256 validation at document intake
- 41 passing API tests; API docs formalized

### 2026-03-26 (Session 6)
- Added NOTARY and TRUSTEE to `PersonRole` enum
- All remaining models given proper `ModelAdmin` classes
- Phase 1 confirmed complete — all charter items closed

### 2026-03-26 (Session 7)
- Phase 2 foundations: direct PDF extraction + OCR fallback + rule-based classification
- Added `is_generated`, `doc_subtype` fields and migrations `0005`/`0006`
- Hardened `PersonRole` choices; added `Person.is_deceased()` helper
- 46 passing tests with upload decision matrix coverage

### 2026-03-27 (Session 8)
- Full entity extraction pipeline built: `entity_extraction.py`, `entity_normalization.py`, `entity_resolution.py`
- Alias matching implemented: confirmed aliases hit exact match on next occurrence
- Wired into `document_upload` as best-effort post-processing
- 20 pure-Python extraction/normalization tests pass standalone

### 2026-03-27 (Session 10)
- Ohio SOS bulk CSV connector built: `ohio_sos_connector.py`
- Bulk download strategy chosen after Cloudflare blocked `businesssearch.ohiosos.gov` and Power BI confirmed `data.ohiosos.gov` is not queryable
- `ReportType` enum (15 types) + `EntityRecord`, `StalenessWarning`, `SearchResult` dataclasses
- Human-in-the-loop staleness design: every search result carries a StalenessWarning (LOW/MEDIUM/HIGH)
- 59/59 connector tests pass with mocked HTTP — no network required

### 2026-03-27 (Session 11)
- IRS connector built: `irs_connector.py` — dual-source Pub78 + EO BMF bulk download
- `EoBmfRegion` enum maps all 11 regional/state file URLs; `StalenessWarning` consistent with Ohio SOS
- `lookup_ein()` returns ruling year/month for SR-002 signal detection
- 104/104 connector tests pass with mocked HTTP — no network required

### 2026-03-27 (Session 12)
- County recorder connector built: `county_recorder_connector.py` — all 88 Ohio counties
- Human-in-the-loop design: URL builder + document parser, no HTTP scraping
- Full registry of all 88 counties: system vendor, portal URL, phone, address, records_from year
- `parse_recorder_document()`: zero-consideration, parcel ID, preparer/title-disclaimer detection (SR-005 signals)
- 191/191 connector tests pass — no network calls needed (connector has no HTTP)

### 2026-03-27 (Session 13)
- County auditor connector built: `county_auditor_connector.py` — dual-mode, all 88 Ohio counties
- Mode 1: ODNR Statewide Parcel Layer ArcGIS REST API — automated ownership query across all 88 counties simultaneously
- Mode 2: Beacon/county portal URL builder for financial detail (human-in-the-loop)
- Cross-county owner search supports the core fraud pattern: one owner, many counties, many parcels
- `ParcelRecord.aud_link` carries direct link back to individual county auditor record for investigator follow-up
- 126/126 connector tests pass with mocked HTTP — no real network calls

### 2026-03-27 (Session 9)
- ProPublica Nonprofit Explorer connector built: `propublica_connector.py`
- Three public functions + convenience `fetch_full_profile()` wrapper
- `requests>=2.31` added to requirements
- 29/29 connector tests pass with mocked HTTP — no network required

## Next Updates

Use this file for:
- high-level architecture recap
- milestone tracking
- decisions and rationale
- end-of-session summaries
