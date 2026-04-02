# Catalyst Session Tracker

## Purpose

This file is the lightweight running log for session-to-session continuity.

Use it to track:
- open tasks
- immediate next steps
- blockers
- short end-of-session recaps

## Current Open Tasks

- **Milestone 4: AI Memo Generation** — NOT STARTED per charter v3
- **Milestone 5: Deploy** — NOT STARTED
- ~~**Redesign signal/detection/finding UI**~~ — **COMPLETE (Session 27).** All 6 phases of FRONTEND_REDESIGN_GAMEPLAN.md implemented.
- **Run Osgood/Do Good case end-to-end** — create case, bulk upload ~100 docs in two batches, watch pipeline, create 4 referrals (FBI, State AG, IRS, FCA), generate memo
- Backend catch-up: `/api/search/`, `/api/cases/:id/export/`
- Monitor OCC/CIC document classification accuracy — may need keyword rule tuning once actual docs are uploaded
- Phase 3: Build investigator UI for fuzzy match candidate review (confirm/reject/merge)
- Case list pagination — hardcoded to 25
- Phase 5 (future): Multi-state SOS connector support (same interface pattern as Ohio)
- Frontend: Entity merge functionality — deferred, needs backend merge + audit log endpoint
- Frontend: Processing status panel (async upload/OCR tracking) — deferred, needs backend websocket or polling endpoint
- Frontend: Notification bell dropdown — placeholder button exists, needs backend notification model + API
- **⚠️ MUST RETURN: Re-verify all CountyFusion counties once GovOS outage resolves** — see blocker below

## Immediate Next Steps

- **Run full end-to-end demo** with the redesigned UI — verify graph, timeline, pipeline, and AI panel all work with real case data
- **AI Memo Generation (Milestone 4)** — extend ai_proxy to generate formal referral memos
- Key remaining backend endpoints:
  1. `GET /api/search/?q=...&type=...&case_id=...` — full-text search
  2. `GET /api/cases/<uuid>/export/?format=json|csv` — raw data export
- Stack startup (unchanged):
  - Terminal 1 (backend): `cd C:\Users\tjcol\Catalyst\backend && ../.venv/Scripts/python.exe manage.py runserver`
  - Terminal 2 (frontend): `cd C:\Users\tjcol\Catalyst\frontend && npm run dev`
  - Open: http://localhost:5173
- **After CF outage clears:** spot-check Seneca (key Osgood county) + ~5 other CF counties, then update checklist ❌ → ✅

## Current Blockers

### ⚠️ GovOS CountyFusion Platform Outage — ONGOING as of 2026-03-28
- **All CountyFusion servers are DOWN** — countyfusion2, countyfusion4, countyfusion6, countyfusion14 all fail to load (confirmed via browser testing and user report of Van Wert spinning)
- **~20 Ohio counties affected**, including **Seneca County** (key Osgood investigation county)
- All other systems (Fidlar AVA, GovOS Cloud Search, DTS PAXWorld, Cott Systems, EagleWeb) are fully operational and verified
- **Action required when CF recovers:** run spot-checks on Seneca, Richland, Wayne, Tuscarawas, Van Wert, Ashland, and update `county_recorder_portal_checklist.md` statuses from ❌ to ✅
- Seneca recorder phone (if urgent): 419-447-4476

## Session Recap Log

### 2026-04-02 (Session 27) — Frontend Redesign COMPLETE (Phases 2–6)
- **Phase 2 (Entity Graph):** Built D3 force-directed graph (EntityGraph.tsx) as OverviewTab centerpiece. Node shapes by entity type, signal count sizing, hover highlights, click-to-select, drag, zoom/pan. EntityProfilePanel slides in with type-specific metadata. Backend `api_case_graph()` endpoint gathers nodes/edges from 6 junction tables with CO_APPEARS_IN edge consolidation.
- **Phase 3 (Timeline):** Built TimelineView.tsx with 4 toggle-able layers (document/signal/financial/transaction). Brush selection filters graph by date range. Click marker selects referenced entity. Two-way graph↔timeline synchronization.
- **Phase 4 (Pipeline):** Built PipelineTab.tsx replacing 3 separate tabs. SOAR-style 5-stage status bar with dynamic counts. Quick-action buttons (Start Review, Confirm, Dismiss, Draft Finding, Publish). Signal/Detection/Finding detail panels. Added UNDER_REVIEW to SignalStatus model.
- **Phase 5 (AI Integration):** Built `ai_proxy.py` (400 lines) with 4 AI functions, caching (10min TTL), rate limiting (10/min/case). Haiku for summarize, Sonnet for connections/narrative/ask. 4 Django POST views + URL routes. Frontend: AISummaryBadge component on pipeline cards + entity profiles. AIAssistantPanel with 6 quick actions + free-text chat, multi-turn conversation, source linking, follow-up suggestions. AI toggle button in AppShell topbar.
- **Phase 6 (Polish):** Theme toggle (dark/light/auto) in topbar with smooth 200ms transition. Staggered card entrance animations. Loading skeletons (GraphSkeleton, TimelineSkeleton, KPI skeletons). Enhanced EmptyState component. Accessibility: skip-to-content link, ARIA live region for graph, ARIA labels, Escape-to-close, reduced motion support.
- **Build:** tsc zero errors, vite build clean (684 modules, 425KB JS / 133KB gzip)
- **Files:** 14 new components, 15+ modified files, 4 new backend endpoints, ~3000 lines of new code

### 2026-04-02 (Session 26) — TS Fix, Investigative Platform Research, State Updates
- Fixed remaining TypeScript errors in DetectionsTab.tsx (`evidence_snapshot` unknown→string casting)
- `tsc --noEmit` passes with zero errors
- Researched 9+ investigative platforms for UI/UX inspiration: Palantir Gotham/Foundry, Maltego, i2 Analyst's Notebook, NICE Actimize, Chainalysis Reactor, Splunk SOAR, Microsoft Sentinel, CrowdStrike Falcon, PANO OSINT
- Key UI patterns identified: triage queue with quick-action buttons, severity+confidence dual-axis scoring, entity graph + timeline synchronized dual view, annotation-driven collaboration (private/shared notes), visual state machine for escalation flow, evidence chain visualization, narrative auto-generation for findings
- Recommended 3-phase UI redesign: Phase 1 (signal queue + graph + evidence panel), Phase 2 (scoring dashboard + escalation + annotation), Phase 3 (case narrative builder + audit trail + export)
- Updated CURRENT_STATE.md with sessions 24-26 work, resolved blockers, updated stats
- Updated session tracker with current open tasks and next steps

### 2026-04-02 (Session 25) — Blocker Cleanup + OverviewTab + Root Folder Reorganization
- **Resolved TD-017 (Signal vs Detection overlap):** Rewrote `persist_signals()` to create Signal records instead of Detection records. Added `escalate_signal_to_detection()` bridge function. Updated signal detail PATCH to auto-escalate on CONFIRMED status.
- **Resolved TD-016 (No Escalate to Finding button):** Added `onEscalateToFinding` prop to DetectionsPanel, "Escalate to Finding" button in UI, `handleEscalateToFinding()` handler in DetectionsTab that pre-fills findings from detection data.
- **Resolved TD-015 (Parcel records):** Verified already working — `_extract_property_data()` runs for PARCEL_RECORD/DEED docs, SR-003/SR-018 evaluate property data.
- Built OverviewTab — case intelligence dashboard with KPI cards, signal severity bars, top rules, pipeline health, financial overview, coverage audit
- Added `api_case_dashboard()` and `api_case_coverage()` backend endpoints
- Root folder cleanup: moved ~530MB of case evidence/reports/analysis/IRS bulk data into organized `case_data/` subdirectory. Archived legacy SQL migrations. Renamed `pc` → `scripts/pre-commit.sh`. Updated .gitignore.

### 2026-04-01 (Session 24) — Signal Engine Expansion + AI Extraction + PDF Forensics
- Expanded signal rules engine from 16 to 29 rules (SR-001 through SR-029)
- Added 9 new signal type labels to frontend DetectionsPanel
- Implemented AI-assisted entity extraction using Claude API
- Added `extract_pdf_metadata()` using PyMuPDF — captures author, creator software, producer, creation/modification dates, page count, encryption status, form detection
- Added `ingestion_metadata` JSONField to Document model for chain-of-custody forensic provenance
- Wired PDF metadata extraction into upload pipeline between OCR and classification
- Implemented forensic file rename on disk after filename generation
- Updated FY2020 officer table and financial data in CASE_EVIDENCE_TRACKER.md
- Generated migration 0018 for ingestion_metadata field

### 2026-03-31 (Session 21) — Frontend Phases C, D, E Complete (Multi-View Redesign)

**Scope:** Complete frontend redesign from single-page prototype into a multi-view application across 3 phases.

#### Phase C — Cross-Case Views
- **DashboardView** (`/`) — KPI cards (Total Cases, Open Signals, Entities, Referred Cases), severity breakdown bar chart, recently updated cases list, cross-case activity feed.
- **TriageView** (`/triage`) — Cross-case signal triage queue with status/severity filters, expandable cards with quick-action triage buttons, note textarea, save with API call.
- **ReferralsView** (`/referrals`) — Pipeline stage overview (DRAFT→SUBMITTED→ACKNOWLEDGED→CLOSED), filterable table, search by agency name.
- **EntityBrowserView** (`/entities`) — Type filter pills, debounced search, table with type icons and entity-specific detail columns.
- **EntityDetailView** (`/entities/:type/:id`) — Entity dossier with type-specific field layouts (person/org/property/financial instrument).
- **CasesListView** — Added Kanban board toggle with 4-column layout (ACTIVE/PAUSED/REFERRED/CLOSED).
- **4 backend endpoints added:** `GET /api/signals/` (cross-case), `GET /api/referrals/` (cross-case), `GET /api/entities/` (unions 4 model types), `GET /api/activity-feed/` (recent audit log).
- **ShellContext** created — React context providing live sidebar badge counts (triage + draft referrals) and case name to the shell. Fetches on mount + 60s polling interval.

#### Phase D — Advanced Features
- **SearchView** (`/search`) — Client-side cross-case search across cases, signals, entities. Fans out to existing endpoints, scores by keyword relevance, displays AI Overview summary panel, type filter pills, ranked result cards.
- **Legal citations** — 10 signal rules (SR-001 through SR-010) each display relevant ORC, IRC, and federal regulation citations as clickable links to authoritative sources. Data in `data/legalCitations.ts`.
- **Investigation checklists** — Per-signal-type investigation step templates ("Investigators typically check...") with checkable items. State stored per-case in localStorage. Data in `data/investigationChecklists.ts`.
- **PDF viewer** — Slide-over panel from right side with iframe PDF renderer, "Open externally" and "Download" links. Activated via "View" button on document rows.
- **External search launchers** — 7 default sources (Google News, Newspapers.com, Legacy.com, Find-a-Grave, Ohio eCourts, PACER, Ohio SOS) on EntityDetailView. Configurable in Settings. Data in `data/externalSearchLaunchers.ts`.
- **Enhanced SettingsView** — Left sub-nav with 4 sections: Appearance (theme), Keyboard (shortcut reference), External Search (full CRUD for launcher URLs), About (system info).
- **Report generation / export** — JSON and CSV export buttons on ReferralsTab calling `GET /api/cases/:id/export/`.
- **API additions:** `searchAll()`, `exportCaseReport()` functions in `api.ts`. Backend endpoints do not exist yet — frontend gracefully degrades.

#### Phase E — Polish & Hardening
- **Light theme CSS overhaul** — Replaced 30+ hardcoded dark-mode hex colors with 25 new CSS custom property tokens (`--card-bg`, `--control-bg`, `--form-bg`, `--tag-low-color`, `--shadow-card`, `--focus-ring`, etc.) with proper light/dark/auto values. All components now theme-aware.
- **Command palette** — `Cmd+Shift+P` overlay with fuzzy-filtered navigation commands, arrow key selection, Enter to execute. Also wired G+key navigation (G+D=Dashboard, G+C=Cases, G+E=Entities, G+T=Triage, G+R=Referrals, G+S=Settings).
- **Error boundary** — React class component wrapping the entire app, catches rendering crashes and shows friendly fallback with "Try Again" button.
- **Accessibility** — ARIA landmarks on shell/sidebar/topbar, `aria-hidden` on decorative icons, `:focus-visible` global rule for keyboard focus rings, `role="main"` on content area.
- **Dead code cleanup** — Removed `void checklistTick` hack, replaced with proper `[, setter]` destructure.
- **Missing `.form-input` class** — Added CSS rule for settings launcher form inputs.

#### Build Stats
- **70 modules**, 257KB JS (78KB gzipped), 47KB CSS (9KB gzipped)
- TypeScript: 0 errors, Vite build: clean
- **13 routes**, 9 view components, 4 nested tab components, 2 context providers

#### Files Created (this session)
- `frontend/src/contexts/ShellContext.tsx`
- `frontend/src/views/DashboardView.tsx`, `TriageView.tsx`, `ReferralsView.tsx`, `EntityBrowserView.tsx`, `EntityDetailView.tsx`
- `frontend/src/data/legalCitations.ts`, `investigationChecklists.ts`, `externalSearchLaunchers.ts`
- `frontend/src/components/ui/PdfViewer.tsx`, `CommandPalette.tsx`, `ErrorBoundary.tsx`
- `backend/investigations/serializers.py` — 5 new serializer functions (person, org, property, financial instrument, audit log)
- `backend/investigations/views.py` — 4 new view functions (signal_collection, referral_collection, entity_collection, activity_feed)
- `backend/investigations/urls.py` — 4 new URL patterns

#### Files Modified (this session)
- `frontend/src/App.tsx`, `api.ts`, `types.ts`, `styles.css`
- `frontend/src/layouts/AppShell.tsx`
- `frontend/src/views/SearchView.tsx`, `SettingsView.tsx`, `CasesListView.tsx`, `CaseDetailView.tsx`
- `frontend/src/components/cases/DocumentsTab.tsx`, `SignalsTab.tsx`, `ReferralsTab.tsx`
- `frontend/src/components/ui/Sidebar.tsx`

### 2026-03-29 (Session 20) — Referral Workflow, Bulk Upload, OCC/CIC Types, CSRF Fix

- **Government referral lifecycle workflow** — added `ReferralStatus` TextChoices (DRAFT/SUBMITTED/ACKNOWLEDGED/CLOSED), FK from `GovernmentReferral` to `Case` (Option A), `notes` field; migrations `0009` and `0010` generated and applied.
- **Referral memo generation** — `POST /api/cases/<uuid>/referral-memo/` builds plain-text memo from case + referrals, stores as `Document` with `doc_type=REFERRAL_MEMO`, `is_generated=True`.
- **`ReferralsPanel` component** (new) — inline create/edit/delete referral cards, status badge rendering, `REFERRAL_STATUS_LABELS` map.
- **Bulk signal severity endpoint** — `GET /api/signal-summary/` runs single `GROUP BY` aggregation with SQL CASE expression severity ranking; returns `{case_id, highest_severity, open_count}` per case; fetched in parallel with case list on page load; severity badges now visible in case queue before clicking into a case.
- **Bulk file upload** — `POST /api/cases/<uuid>/documents/bulk/` accepts up to 50 files via `multipart/form-data`; runs full upload pipeline per file (SHA-256, storage, OCR, classification, entity extraction, signal detection); shared `_process_uploaded_file()` helper extracted from `document_upload`.
- **`BulkUploadPanel` component** (new) — drag-and-drop zone, deduplication by filename, per-file status rows (pending/done/error), up to 50 PDFs per batch.
- **OCC and CIC document types** — added `OCC_REPORT` and `CIC_REPORT` to `DocumentType` enum; migration `0010` applied; keyword classification rules added to `classification.py`.
- **CSRF fix** — `@csrf_exempt` added to all 11 `api_` view functions; `CSRF_TRUSTED_ORIGINS` set to `localhost:5173` in `settings.py`; admin and HTML views retain full CSRF protection.
- **CSS filter overflow fixes** — two separate filter-row layouts were clipping dropdowns; fixed `compact-filters` (`flex` + `width: auto`) and `filter-row` grid columns (`minmax(0, 1fr) auto auto`).
- **Test suite kept green** — `CasesPanel.test.tsx` updated with `caseSeverityMap` prop; `CaseDetailPanel.test.tsx` updated with shared `referralProps` fixture including bulk upload handlers.

### 2026-03-29 (Session 19) — Frontend Phase Completion + UX Acceleration

- Completed frontend plan phases and validated with build + automated tests.
- Phase 1 complete: success/error feedback, inline form validation, loading and empty state quality pass.
- Phase 2 complete: refactored monolithic app into structured components and utility modules.
- Shared UI primitives expanded (`Button`, `FormInput`, `FormSelect`, `FormTextarea`, `StateBlock`, `EmptyState`, `ToastStack`).
- API hardening complete in frontend client:
  - timeout handling
  - structured error extraction
  - abort-safe request flow
  - improved network failure messages
- Added frontend test harness (Vitest + Testing Library) with API and component coverage.
- Added quick triage status chips in Signals panel for faster status draft updates.
- Added case sort controls in the Cases panel (`updated`, `name`, `status`) with URL persistence.
- Replaced top banners with toast notifications for action feedback.
- Added keyboard shortcuts for investigator speed:
  - `j` / `k` case navigation
  - `1` / `2` / `3` set active signal draft status
  - shortcut handling safely ignores typing in form fields
- Current frontend baseline is ready for feature expansion, not just infrastructure work.

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

### 2026-03-26 (Session 6) — Phase 1 Complete
- Added NOTARY and TRUSTEE to PersonRole enum (run makemigrations to apply)
- Fixed stale `orc_reference` field reference in FindingAdmin — updated to current Finding fields (severity, confidence, status, signal_type, signal_rule_id)
- Added proper ModelAdmin classes for all 6 plain-registered models: Property, FinancialInstrument, PersonDocument, OrgDocument, PersonOrganization, PropertyTransaction
- Confirmed Phase 1 minimal dashboard is complete — Django template views (case_list, case_detail, case_form, document_upload) satisfy the Phase 1 charter requirement; React frontend deferred to Phase 3 per charter
- Phase 1 is fully closed out — all charter items complete

### 2026-03-26 (Session 5)
- Expanded the JSON API from basic intake to a fuller case/document workflow surface
- Added case PATCH and DELETE support with conflict handling for protected related records
- Added case and document list pagination metadata, filters, date-range filters, and allowlisted sorting
- Added case-scoped document detail, PATCH, and DELETE endpoints
- Added strict SHA-256 validation for document intake payloads
- Grew the investigations test suite to 41 passing tests covering create, list, detail, update, delete, filters, sorting, and validation paths
- Added `backend/API_COOKBOOK.md` and refreshed `backend/SERIALIZER_API_REFERENCE.md`

### 2026-03-26 (Session 4)
- Added `investigations/serializers.py` for case intake validation and JSON serialization
- Added Django-native JSON API endpoints for case list, create, and detail under `/api/cases/`
- Added API tests covering create, validation failure, detail payload, and list ordering
- Updated project docs so the current milestone state matches the codebase

### 2026-03-20 (Session 3)
- Fixed Django → PostgreSQL authentication: `load_dotenv()` added to `settings.py` so `.env` is loaded before DB config is read
- Reset `catalyst_user` password in Docker container to match `.env`
- Confirmed Django connects to PostgreSQL successfully
- `showmigrations` verified: 18 migrations applied across all apps
- `\dt` confirmed: 23 tables present in database including all Phase 1 domain tables
- Database is fully built and Django is live against it

### 2026-03-20 (Session 2)
- Fixed Docker Compose obsolete `version` warning — removed `version: "3.9"` line
- Upgraded Django admin registrations with proper `ModelAdmin` classes
- `GovernmentReferral` admin: list view, status/agency filters, search, `filing_date` locked read-only
- `AuditLog` admin: fully enforced read-only — add, change, delete all disabled
- `Case`, `Document`, `Person`, `Organization`, `Finding` all upgraded with list views and filters
- Django system check passes with 0 issues

### 2026-03-20 (Session 1)
- Added recurring recap documents for architecture and file walkthroughs
- Added this tracker file for open tasks, next steps, and blockers
- Project in stable state for continuing Phase 1 work

## Update Pattern

At the end of each session, update:
- `Current Open Tasks`
- `Immediate Next Steps`
- `Current Blockers`
- newest entry under `Session Recap Log`
