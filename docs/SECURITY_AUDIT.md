# Catalyst Security Audit Report

**Audit Date:** 2026-03-31
**Auditor:** Claude (AI-assisted, reviewed by Tyler Collins)
**Scope:** Full stack — 43 Python backend files, 70+ frontend modules
**Codebase State:** Session 21 (Phase E complete, backend catch-up in progress)

---

## Executive Summary

This audit examined every source file in the Catalyst forensic investigation platform
across backend (Django/Python) and frontend (React/TypeScript). The audit identified
**55 findings** across the full stack:

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 6     | Must fix before any deployment |
| HIGH     | 17    | Should fix before production use |
| MEDIUM   | 19    | Address in next development cycle |
| LOW/INFO | 13    | Improve when convenient |

The single most important finding: **Catalyst has no authentication or authorization
layer protecting its API endpoints.** Every endpoint is accessible to anyone who can
reach the server. This is expected for local-only development but must be resolved
before any network-facing deployment.

---

## How to Use This Report

Each finding has a checkbox. Work through them in severity order. When you fix one,
check it off and note the session number. This becomes your security remediation log.

---

## CRITICAL Findings (Fix Before Any Deployment)

### [ ] SEC-001: No Authentication on API Endpoints
- **Where:** `views.py` — all 25+ API view functions
- **What:** Every API endpoint accepts requests from any user without verifying
  identity. All views are `@csrf_exempt` with no auth check.
- **Impact:** Anyone who can reach the server can view, create, modify, or delete
  all case data, documents, signals, findings, and referrals.
- **Fix:** Implement Django's authentication system or a custom auth decorator
  that runs before every API view. The existing `TokenAuthMiddleware` is a start
  but is disabled by default (`CATALYST_API_TOKENS` is empty).

### [ ] SEC-002: No Authorization / Case Access Control (IDOR)
- **Where:** `views.py` — all case-scoped endpoints
- **What:** Functions use `get_object_or_404(Case, pk=pk)` without verifying the
  requesting user has permission to access that specific case. Any user with a
  case UUID can access any case.
- **Impact:** An investigator on Case A could access confidential data from Case B.
  Cross-case endpoints (`/api/signals/`, `/api/entities/`, `/api/search/`,
  `/api/activity-feed/`, `/api/referrals/`) return data from ALL cases.
- **Fix:** Add a permission check after every `get_object_or_404()` call. For
  cross-case endpoints, filter querysets to only cases the user has access to.

### [ ] SEC-003: DEBUG Defaults to True
- **Where:** `settings.py` line 11
- **What:** `DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"` — if the
  env var is missing, DEBUG is on. In production, DEBUG exposes full stack traces,
  SQL queries, environment variables, and file paths.
- **Impact:** A deployed instance without the env var set leaks internal details
  to any visitor.
- **Fix:** Change default to `"False"`:
  ```python
  DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
  ```

### [ ] SEC-004: SECRET_KEY Has Hardcoded Fallback
- **Where:** `settings.py` line 10
- **What:** `SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "replace-me-in-env")` —
  if the env var is missing, Django uses a known placeholder string for session
  signing, CSRF tokens, and password hashing.
- **Impact:** An attacker who knows the placeholder can forge sessions and CSRF tokens.
- **Fix:** Crash on startup if SECRET_KEY is not set:
  ```python
  SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # Crash if missing
  ```

### [ ] SEC-005: File Upload Path Traversal
- **Where:** `views.py` line 176 (`_process_uploaded_file`)
- **What:** `relative_path = f"cases/{case.pk}/{uploaded_file.name}"` — the
  filename comes directly from the upload. A filename like `../../../etc/passwd`
  could write files outside the intended directory.
- **Impact:** An attacker could overwrite critical files or escape the storage directory.
- **Fix:**
  ```python
  import os
  safe_name = os.path.basename(uploaded_file.name)
  relative_path = f"cases/{case.pk}/{safe_name}"
  ```

### [ ] SEC-006: Truncated Detection Model
- **Where:** `models.py` — final lines (line 695)
- **What:** The `Detection` model definition is cut off mid-field. The file ends
  with `detection_method = models.CharField` and no closing parenthesis, class
  body, or Meta class.
- **Impact:** If migrations are regenerated from this file, the Detection model
  will be incomplete or cause errors. The truncation may also affect other
  model features that were defined after Detection.
- **Fix:** Restore the complete Detection model from Git history or from the
  working copy on your local machine.

---

## HIGH Findings (Fix Before Production Use)

### [ ] SEC-007: No Audit Logging on State-Changing Operations
- **Where:** `views.py` — PATCH/DELETE handlers for cases, documents, signals,
  findings, notes, referrals
- **What:** No `AuditLog.objects.create()` calls after modifications. The
  `AuditLog` model and `AuditAction` enum exist but are not used in views.
- **Impact:** Investigators cannot answer "who changed this?" or "what was the
  previous value?" — breaking chain of custody requirements.
- **Fix:** Add `AuditLog.log()` calls (using the helper we just built) after
  every successful PATCH, DELETE, and POST operation.

### [ ] SEC-008: No File Size Limit on Uploads
- **Where:** `views.py` — `_process_uploaded_file()` and `api_case_document_bulk_upload()`
- **What:** No maximum file size check before processing. Users can upload
  arbitrarily large files.
- **Impact:** Storage exhaustion, memory exhaustion during OCR, denial of service.
- **Fix:** Add size validation as the first step:
  ```python
  MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
  if uploaded_file.size > MAX_UPLOAD_SIZE:
      return JsonResponse({"errors": {"file": ["Exceeds 100 MB limit."]}}, status=400)
  ```

### [ ] SEC-009: No MIME Type Validation on Uploads
- **Where:** `views.py` — `_process_uploaded_file()`
- **What:** No validation that uploaded files match their claimed extension. A
  `.exe` renamed to `.pdf` would be accepted and stored.
- **Impact:** Malicious files stored alongside evidence; potential execution if
  served back to users.
- **Fix:** Check `uploaded_file.content_type` against an allowlist before processing.

### [x] SEC-010: Cross-Case Data Exposure in Global Endpoints
- **Where:** `views.py` — `api_signal_collection`, `api_referral_collection`,
  `api_entity_collection`, `api_activity_feed`, `api_search`
- **What:** These endpoints return data from ALL cases without any filtering.
  Even if auth is added later, these need case-level access control.
- **Impact:** Any authenticated user sees all investigation data system-wide.
- **Fix:** Filter all querysets by accessible case IDs once auth is implemented.

### [ ] SEC-011: Case Export Unrestricted
- **Where:** `views.py` — `api_case_export` (lines 1398-1573)
- **What:** Exports all case data (documents, signals, findings, persons,
  organizations, financial instruments) as JSON/CSV with no access control.
- **Impact:** One-click full data exfiltration of any case.
- **Fix:** Require authentication + case-level authorization. Log all exports
  to AuditLog.

### [ ] SEC-012: Missing Transaction Atomicity
- **Where:** `views.py` — `_process_uploaded_file()`
- **What:** Multi-step operations (create Document, extract entities, persist
  signals, save financial snapshots) are not wrapped in `transaction.atomic()`.
- **Impact:** If a mid-pipeline step fails, partial data remains in the database.
- **Fix:** Wrap the DB-write portion in `transaction.atomic()`. File storage
  should happen after the transaction (see ERROR_HANDLING.md Section 6).

### [ ] SEC-013: Error Messages Leak Internal Details
- **Where:** `views.py` — bulk upload error responses, process-pending responses
- **What:** `errors.append({"filename": ..., "error": str(exc)})` returns raw
  exception messages to the client, which may include file paths, DB errors,
  or stack details.
- **Impact:** Helps attackers understand system internals.
- **Fix:** Log full exception internally, return generic message to client.

### [x] SEC-014: No PDF Validation Before Processing
- **Where:** `extraction.py` — `extract_from_pdf()`
- **What:** No file header validation. A corrupted or malicious PDF is passed
  directly to PyMuPDF/fitz without checking if it's actually a valid PDF.
  No hard file size cap before OCR processing.
- **Impact:** Malicious PDFs could crash the extraction pipeline or cause
  resource exhaustion (PDF bomb).
- **Fix:** Validate PDF magic bytes (`%PDF-`), add hard size cap before processing.

### [ ] SEC-015: Silent Classification Failures
- **Where:** `classification.py` — `classify_document()`
- **What:** Returns `"OTHER"` silently when confidence is too low. No logging,
  no confidence score returned to caller.
- **Impact:** A deed misclassified as "OTHER" won't trigger deed-specific signal
  rules (e.g., SR-005 zero-consideration transfer). Investigators won't know.
- **Fix:** Return `(doc_type, confidence_score)` tuple. Log low-confidence
  classifications at WARNING level.

### [x] SEC-016: Unvalidated External URLs from ProPublica API
- **Where:** `propublica_connector.py` — `fetch_filings()`
- **What:** `pdf_url` from API responses is stored without scheme or domain
  validation. If the API is compromised, malicious URLs could be injected.
- **Impact:** Investigators may click on or auto-fetch a malicious PDF URL.
- **Fix:** Validate that `pdf_url` starts with `https://projects.propublica.org/`
  or another ProPublica domain.

### [x] SEC-017: No Download Timeouts on Large Files
- **Where:** `irs_connector.py` — `_download()`, `county_auditor_connector.py`
- **What:** With `stream=True`, the timeout applies only to the initial connection,
  not the entire download. A slow server could hang the connector indefinitely.
- **Impact:** Blocked investigation workflows, thread exhaustion.
- **Fix:** Implement per-chunk timeout and total download deadline.

### [x] SEC-018: Signal Rule SR-009 Logic Bug
- **Where:** `signal_rules.py` — SR-009 (single contractor detection)
- **What:** The rule uses `contractors[0]` in the message instead of
  `most_common_name`, and the trigger condition logic is inverted.
- **Impact:** Signal either never fires or fires with wrong contractor name.
  A valid fraud pattern goes undetected.
- **Fix:** Use `most_common_name` in the message. Review trigger condition logic.

### [ ] SEC-019: Unvalidated External Search URLs (Frontend)
- **Where:** `SettingsView.tsx`, `externalSearchLaunchers.ts`, `EntityDetailView.tsx`
- **What:** Users can create custom search launchers with arbitrary URL templates
  stored in localStorage. No validation that URLs use https:// scheme.
  `javascript:` or `data:` URLs would be accepted.
- **Impact:** XSS or open redirect attacks targeting investigators.
- **Fix:** Validate that `urlTemplate` starts with `https://` before saving.

### [ ] SEC-020: Sensitive Checklist Data in localStorage
- **Where:** `investigationChecklists.ts`
- **What:** Investigation checklist state stored in localStorage with keys
  containing case IDs and signal rule IDs. Keys reveal which cases and rules
  are being actively investigated.
- **Impact:** Any JavaScript running on the same origin (via XSS) can see
  active investigation targets.
- **Fix:** Move checklist state to server-side storage, or use sessionStorage
  (cleared on tab close).

### [ ] SEC-021: Admin Panel Changes Not Audit-Logged
- **Where:** `admin.py`
- **What:** Changes made through Django admin (cases, documents, persons,
  organizations) are not written to the AuditLog table. Only the AuditLog
  admin itself is properly locked down (read-only).
- **Impact:** An investigator could modify case data via admin without any record.
- **Fix:** Add Django admin action logging middleware or use django-auditlog
  to capture all admin modifications.

### [ ] SEC-022: Hardcoded Case-Specific Stopwords
- **Where:** `entity_extraction.py` — person name validation
- **What:** Stopwords list includes "example_city", "example_township", "maria", "stein" —
  place names from the Example Charity Ministries test case hardcoded into production code.
- **Impact:** Legitimate person names matching these words would be rejected
  in future cases.
- **Fix:** Move case-specific stopwords to configuration or remove entirely.

### [ ] SEC-023: Forms Allow Upload to Any Case
- **Where:** `forms.py` — `DocumentUploadForm`
- **What:** `case` field uses `queryset=Case.objects.all()` with no filtering
  by user permissions.
- **Impact:** Any authenticated user can upload documents to any case.
- **Fix:** Filter queryset to cases the current user has access to.

---

## MEDIUM Findings (Address in Next Development Cycle)

### [x] SEC-024: All Endpoints Are @csrf_exempt
- **Where:** `views.py` — all 25+ API views
- **What:** CSRF protection is disabled on every endpoint. No alternative
  protection (custom headers, token validation) is documented.
- **Impact:** CSRF attacks could cause an investigator's browser to make
  unauthorized API requests.
- **Fix:** For SPA consumption, implement double-submit CSRF token pattern.
  Add `X-CSRFToken` header handling to frontend `api.ts`.

### [x] SEC-025: No Rate Limiting
- **Where:** All API endpoints
- **What:** No request rate limits. A user can enumerate all cases, brute-force
  entity IDs, or exhaust storage via rapid uploads.
- **Impact:** DoS attacks, data exfiltration, resource exhaustion.
- **Fix:** Add `django-ratelimit` or DRF throttling classes.

### [ ] SEC-026: CORS with Credentials Enabled
- **Where:** `settings.py` — `CORS_ALLOW_CREDENTIALS = True`
- **What:** Credentials are sent cross-origin. Combined with permissive
  `CORS_ALLOWED_ORIGINS`, this increases credential theft risk.
- **Impact:** JavaScript from allowed origins can make authenticated requests.
- **Fix:** Set `CORS_ALLOW_CREDENTIALS = False` unless explicitly needed.

### [x] SEC-027: Silent Entity Extraction Failures
- **Where:** `views.py` lines 220-249, 339-360
- **What:** Entity extraction and signal detection failures are caught with
  `except Exception:` and logged, but processing continues. The document is
  marked as successfully uploaded even if extraction failed.
- **Impact:** Evidence is "ingested" but entities and signals are silently missing.
  Investigators won't know critical analysis was skipped.
- **Fix:** Add an `extraction_status` field or flag on Document. Surface failures
  in the UI so investigators know to review manually.

### [x] SEC-028: Silent OCR Failures
- **Where:** `extraction.py` — `_ocr_page()`
- **What:** All OCR exceptions return empty string. If Tesseract isn't installed,
  every scanned PDF silently gets no text. Only a log warning is emitted.
- **Impact:** Entire categories of evidence (scanned documents) produce no
  extracted text, causing all text-based signal rules to silently fail.
- **Fix:** Return a distinct status (e.g., `OCR_DEPENDENCY_MISSING`) if
  Tesseract is not found. Surface this in the UI.

### [ ] SEC-029: Signal Deduplication Uses JSON Field Query
- **Where:** `signal_rules.py` — `persist_signals()`
- **What:** Deduplication queries `evidence_snapshot__rule_id` (a JSON field).
  If the JSON structure doesn't contain the expected key, dedup silently fails.
- **Impact:** Duplicate signals could be created, or valid signals could be
  incorrectly skipped.
- **Fix:** Use explicit database columns for dedup keys rather than JSON field queries.

### [ ] SEC-030: Signal Rule SR-007 False Positives
- **Where:** `signal_rules.py` — SR-007 (procurement bypass)
- **What:** Uses substring matching (`applicant_lower in entity_name`) to compare
  building permit applicants with case entities. "Smith Corporation" matches "Smith".
- **Impact:** False positives erode investigator confidence in the signal system.
- **Fix:** Use normalized name comparison or fuzzy matching with minimum threshold.

### [ ] SEC-031: Date Extraction Validation Gaps
- **Where:** `entity_extraction.py` — `_normalize_date()`
- **What:** Date parsing accepts some invalid dates without bounds checking
  (e.g., month > 12 might pass certain regex branches).
- **Impact:** Invalid dates in extracted entities could invalidate investigation
  timelines.
- **Fix:** Add explicit bounds validation: 1 ≤ month ≤ 12, 1 ≤ day ≤ 31,
  1900 ≤ year ≤ current_year + 5.

### [ ] SEC-032: Empty Person Records Created
- **Where:** `entity_resolution.py` — `resolve_person()`
- **What:** When `normalize_person_name()` returns empty string, a Person record
  is still created with only `full_name` set.
- **Impact:** Orphaned/empty Person records pollute the database.
- **Fix:** Skip record creation if normalized name is empty. Log at WARNING.

### [x] SEC-033: No Frontend CSRF Token Handling
- **Where:** `api.ts` — all POST/PATCH/DELETE operations
- **What:** No `X-CSRFToken` header sent with state-modifying requests.
- **Impact:** If backend CSRF protection is enabled, all writes would fail.
  Currently masked because backend is `@csrf_exempt`.
- **Fix:** Fetch CSRF token from Django on app load, include in all write requests.

### [ ] SEC-034: Unvalidated window.open() URLs
- **Where:** `ReferralsTab.tsx`
- **What:** `window.open(result.download_url, "_blank")` opens a URL from
  backend response without frontend validation.
- **Impact:** If backend response is tampered with, malicious URL could be opened.
- **Fix:** Validate that `download_url` is same-origin or relative path.

### [ ] SEC-035: Missing Input Validation on Ohio AOS Search
- **Where:** `ohio_aos_connector.py` — `search_audit_reports()`
- **What:** User query passed to Ohio AOS search without length or character
  validation. Very long queries could trigger server-side errors.
- **Fix:** Cap query length at 256 characters. Whitelist allowed characters.

### [ ] SEC-036: No Rate Limiting on External API Connectors
- **Where:** All 6 connector files
- **What:** No rate limiting, exponential backoff, or circuit breaker pattern.
  Rapid searches could trigger IP blocking from external services.
- **Fix:** Implement per-service circuit breaker and exponential backoff.

### [x] SEC-037: Unvalidated ArcGIS Response URLs
- **Where:** `county_auditor_connector.py` — `_parse_parcel_feature()`
- **What:** `aud_link` field extracted from ArcGIS API responses returned
  as-is without domain validation.
- **Impact:** Compromised API could inject malicious auditor portal URLs.
- **Fix:** Validate URL domain against known county auditor domains.

### [x] SEC-038: Ohio AOS PDF URL Extraction
- **Where:** `ohio_aos_connector.py` — `_parse_aos_html()`
- **What:** PDF URLs extracted from HTML via regex without domain validation.
  URLs not starting with "/" are returned as-is, potentially from external domains.
- **Fix:** Validate all extracted URLs have `ohioauditor.gov` domain.

### [ ] SEC-039: IRS Bulk Files Have No Integrity Verification
- **Where:** `irs_connector.py` — `fetch_pub78()`, `fetch_eo_bmf()`
- **What:** Downloaded IRS bulk files are parsed without hash/checksum
  verification. A man-in-the-middle could deliver modified tax-exempt data.
- **Fix:** Hash downloaded files and log the hash for audit trail. Compare
  against known-good hashes if available.

### [ ] SEC-040: DB_PASSWORD Fails Silently
- **Where:** `settings.py` — database configuration
- **What:** If `DB_PASSWORD` env var is not set, Django attempts connection
  with empty password instead of failing fast.
- **Fix:** Add startup check:
  ```python
  if not os.getenv("DB_PASSWORD"):
      raise ValueError("DB_PASSWORD environment variable must be set")
  ```

### [ ] SEC-041: Dedup Command Uses Hardcoded String
- **Where:** `dedup_documents.py`
- **What:** Filters detections by `detection_method="SYSTEM_AUTO"` as a raw
  string instead of importing the `DetectionMethod` enum.
- **Impact:** If enum value is renamed, dedup could accidentally delete valid detections.
- **Fix:** Import and use `DetectionMethod.SYSTEM_AUTO` constant.

---

## LOW / INFO Findings

### [ ] SEC-042: Limit Parsing Without Validation (entity_collection)
- **Where:** `views.py` — `api_entity_collection`
- **What:** `int(request.GET.get("limit", "100"))` — no try/except. Non-numeric
  values cause 500 instead of 400.
- **Fix:** Wrap in try/except, return 400 on ValueError.

### [ ] SEC-043: Activity Feed Limit Not Clamped
- **Where:** `views.py` — `api_activity_feed`
- **What:** No validation that limit ≥ 1. limit=0 or negative values accepted.
- **Fix:** `limit = max(1, min(limit, 100))`

### [ ] SEC-044: Search Snippet Performance
- **Where:** `views.py` — `api_search` snippet building
- **What:** Substring search on potentially large `extracted_text` fields could
  be slow on large documents.
- **Fix:** Use PostgreSQL full-text search for snippets, or cap text length.

### [ ] SEC-045: Tesseract Not-Found Warning Easily Missed
- **Where:** `extraction.py` — Tesseract binary discovery
- **What:** Missing Tesseract only logs a warning, not an error. Operators may
  not notice OCR is completely disabled.
- **Fix:** Log at ERROR level or fail fast if OCR is expected.

### [ ] SEC-046: Person Name False Positives
- **Where:** `entity_extraction.py` — inverted name regex
- **What:** The ALL-CAPS inverted name pattern matches place names like
  "NEW YORK" as person names.
- **Fix:** Add geographic/organization stopword filtering.

### [ ] SEC-047: Signal Type Mapping Fallback Masks Bugs
- **Where:** `signal_rules.py` — `_RULE_TO_SIGNAL_TYPE`
- **What:** Unknown `rule_id` values silently get `MISSING_REQUIRED_FIELDS`
  as fallback signal type, hiding bugs when new rules are added.
- **Fix:** Raise KeyError or log ERROR for unmapped rule_ids.

### [ ] SEC-048: Stale County Auditor Registry
- **Where:** `county_auditor_connector.py` — `_AUDITOR_REGISTRY`
- **What:** Hardcoded at module level with no cache invalidation. If a county
  portal URL changes, the module must be redeployed.
- **Fix:** Document as a known limitation. Consider periodic URL validation.

### [ ] SEC-049: OCR Confidence Not Returned
- **Where:** `county_recorder_connector.py` — `parse_recorder_document()`
- **What:** Parsed document fields from OCR have no confidence scores.
  Investigators may not realize parsed data is unreliable.
- **Fix:** Return confidence scores alongside parsed fields.

### [ ] SEC-050: No Source Map Configuration Visible
- **Where:** `vite.config.ts`
- **What:** Cannot verify if source maps are disabled in production builds.
- **Fix:** Ensure `build: { sourcemap: false }` in production config.

### [ ] SEC-051: Frontend File Upload — No Per-File Size Check
- **Where:** `BulkUploadPanel.tsx`
- **What:** MAX_FILES=50 limit exists but no per-file size validation.
- **Fix:** Reject files > 100 MB on the frontend before upload.

### [ ] SEC-052: localStorage Poisoning Risk
- **Where:** `externalSearchLaunchers.ts`
- **What:** `JSON.parse()` of localStorage data doesn't validate the parsed
  object structure.
- **Fix:** Validate parsed objects have required properties before use.

### [ ] SEC-053: Vulnerable esbuild Dependency
- **Where:** `package.json` (via vite)
- **What:** esbuild ≤ 0.24.2 has moderate vulnerability (GHSA-67mh-4wv8-2f99)
  allowing any website to send requests to dev server.
- **Fix:** Run `npm audit fix` or update vite/esbuild.

---

## Positive Security Findings

These are things Catalyst is already doing right:

- **SHA-256 hashing on upload** — Hash computed on original bytes before processing
- **Structured JSON logging** — `JsonKeyValueFormatter` produces machine-parseable logs
- **API token middleware** — `TokenAuthMiddleware` exists (needs to be enabled)
- **AuditLog model** — Exists with `AuditAction` enum and `log()` helper (needs to be used)
- **No secrets in frontend code** — No API keys, tokens, or passwords in TypeScript
- **No dangerouslySetInnerHTML** — React's default escaping used throughout
- **No eval()** — No dynamic code execution in frontend
- **UUID primary keys** — Prevents sequential ID enumeration
- **.gitignore covers .env** — Secrets not committed to version control
- **.env.example exists** — Documents required environment variables
- **Input validation on serializers** — Unexpected fields are rejected
- **SHA-256 format validation** — DocumentIntakeSerializer validates hex format
- **on_delete=RESTRICT on Case FK** — Prevents accidental cascade deletions
- **Enum discipline** — TextChoices enums prevent invalid data throughout
- **GovernmentReferral.filing_date is immutable** — Cannot be changed after creation

---

## Recommended Fix Order

### Phase 1: Before Any Network Deployment (Critical)
1. Fix SEC-003 (DEBUG default) and SEC-004 (SECRET_KEY fallback) — 5 minutes
2. Fix SEC-005 (path traversal) — 5 minutes
3. Fix SEC-006 (truncated Detection model) — restore from Git
4. Enable `TokenAuthMiddleware` (SEC-001 partial fix) — 10 minutes
5. Add file size and MIME validation (SEC-008, SEC-009) — 30 minutes

### Phase 2: Before Production Use (High)
6. Add `AuditLog.log()` calls to all state-changing views (SEC-007) — 2 hours
7. Add `transaction.atomic()` to upload pipeline (SEC-012) — 30 minutes
8. Add case access control to cross-case endpoints (SEC-010) — 2 hours
9. Fix signal rule SR-009 bug (SEC-018) — 15 minutes
10. Add PDF header validation (SEC-014) — 30 minutes

### Phase 3: Hardening (Medium)
11. Implement CSRF token handling (SEC-024, SEC-033) — 1 hour
12. Add rate limiting (SEC-025) — 1 hour
13. Surface extraction failures in UI (SEC-027, SEC-028) — 2 hours
14. Validate external URLs from APIs (SEC-016, SEC-037, SEC-038) — 1 hour
15. Add download timeouts (SEC-017) — 30 minutes

---

## Appendix: Files Audited

### Backend (43 files)
- `catalyst/settings.py`, `urls.py`, `asgi.py`, `wsgi.py`
- `investigations/models.py`, `views.py`, `urls.py`, `serializers.py`
- `investigations/middleware.py`, `logging_utils.py`, `admin.py`, `forms.py`
- `investigations/extraction.py`, `classification.py`
- `investigations/entity_extraction.py`, `entity_normalization.py`, `entity_resolution.py`
- `investigations/signal_rules.py`
- `investigations/irs_connector.py`, `propublica_connector.py`
- `investigations/county_auditor_connector.py`, `county_recorder_connector.py`
- `investigations/ohio_sos_connector.py`, `ohio_aos_connector.py`
- `investigations/verify_recorder_portals.py`
- `investigations/management/commands/dedup_documents.py`
- `investigations/tests/` (11 test files)
- `manage.py`

### Frontend (key files)
- `src/api.ts`, `src/types.ts`, `src/App.tsx`
- `src/views/*.tsx` (9 view components)
- `src/components/**/*.tsx` (tab components, UI components)
- `src/data/*.ts` (legal citations, checklists, search launchers)
- `src/hooks/*.ts`, `src/contexts/*.tsx`
- `vite.config.ts`, `package.json`

---

*This audit was performed by AI analysis and should be validated by a human
security reviewer before deployment to any environment handling real case data.
Update this document as findings are addressed.*
