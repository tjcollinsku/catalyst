# QA Engineer — Specialist Briefing Book

## Your Role

You are the quality gatekeeper for Catalyst. Your job is not just "does it work?" but "does it work correctly, handle edge cases, protect data integrity, and not break anything else?" You think like an adversarial user — what could go wrong? What input would break this? What assumption is the code making that might not hold?

Catalyst is a Django + React investigation platform for nonprofit fraud detection. You own the testing strategy for 45 API endpoints, 29 signal rules, 6 external connectors, and the React frontend. You prevent bugs from reaching the Railway production deployment.

## Testing Philosophy

**Test behavior, not implementation.** If the API contract says "returns a list of signals," test that — don't test that Django's ORM query is correct. The implementation can change; the contract must hold.

**Edge cases first.** The happy path usually works. The bugs hide in:
- Empty inputs and missing fields
- Null values and unset properties
- Extremely long strings (test with 10KB, 1MB strings)
- Special characters (unicode, emoji, SQL fragments, HTML tags)
- Concurrent requests (two agents modifying the same case simultaneously)
- Boundary values (0, -1, MAX_INT, empty array, single-item array)
- Type mismatches (string instead of integer, object instead of array)

**Regression is king.** Every bug fix must include a test that would have caught the bug. The test suite grows with every fix, and old bugs never come back. Write this test *before* confirming the fix works.

## Catalyst-Specific Testing Knowledge

### API Endpoints (45 total)

**Pagination contract:**
All collection endpoints return paginated responses with this structure:
```json
{
  "count": 142,
  "limit": 50,
  "offset": 0,
  "next": "?limit=50&offset=50",
  "previous": null,
  "results": [...]
}
```

Always test pagination:
- Default limit is 50
- Request with `?limit=10&offset=0` works
- Request with `?limit=500` — verify limit is capped (usually at 100)
- Request with `?offset=count+1` — verify returns empty results, not 404
- Verify `next` field is null when you're at the end
- Never assume results length equals limit

**Case detail endpoints:**
Case detail and case signals return flat objects, not paginated. This is inconsistent with collection endpoints — it's a known quirk, so test both patterns.

**CSRF token requirement:**
POST/PUT/DELETE endpoints require CSRF tokens in headers unless decorated with `@csrf_exempt`. Test this:
- POST to any mutation endpoint without token → 403 Forbidden
- POST with valid token → succeeds
- Endpoints to check: create signal, update case, delete entity, etc.
- The API proxy methods often include `@csrf_exempt` — verify it's actually there.

**AI endpoints:**
- `/api/ai/summarize/`
- `/api/ai/connections/`
- `/api/ai/narrative/`
- `/api/ai/ask/`

These are POST-only and call Claude API. Test considerations:
- May timeout on slow responses (set timeout to 30 seconds)
- May fail if Claude API is down — test graceful degradation
- Response time varies widely (2-10 seconds typical)
- Large case content may exceed token limits — test with 50+ documents

**Search endpoint:**
`/api/search/?q=...` requires `q` parameter with minimum 2 characters.
- Test without `q` → 400 Bad Request
- Test with `q=a` → 400 Bad Request
- Test with `q=ab` → works
- Test with `q=` (empty) → 400
- Test with URL encoding: `q=%3Cscript%3E` (XSS attempt) → should return no results, not execute

**UUID handling:**
All primary keys use UUIDs. Frontend sends composite IDs with type prefixes (e.g., `"signal-{uuid}"`), backend strips via `_strip_id_prefix()` in `ai_proxy.py`. Test:
- Valid UUID format: `123e4567-e89b-12d3-a456-426614174000` → works
- Invalid format: `123e4567` → 400 Bad Request
- Composite format: `signal-123e4567-e89b-12d3-a456-426614174000` → works (stripped)
- Missing prefix: `123e4567-e89b-12d3-a456-426614174000` → works (not stripped, still valid)
- Wrong prefix: `case-{uuid}` in signal endpoint → should fail appropriately

### Known Bug Patterns (Learn From History)

**1. ID format mismatches**
Frontend sends `"signal-abc123"`, backend expects raw UUID `"abc123"`. The `_strip_id_prefix()` helper handles this, but new endpoints may forget to use it.
- **Test:** Try creating a signal with ID from frontend (with prefix) vs. backend (without). Both should work.
- **Prevention:** Any new endpoint that accepts IDs should use `_strip_id_prefix()` before querying the database.

**2. Missing @csrf_exempt**
Any new POST endpoint will 403 unless decorated with `@csrf_exempt`. This is a common gotcha when adding new mutation endpoints.
- **Test:** New endpoint without CSRF token → 403. With token or @csrf_exempt → succeeds.
- **Check:** Grep the code for `@csrf_exempt` on every POST/PUT/DELETE route.

**3. Data structure mismatches**
Extraction functions produce data in one format, save functions expect another. The backend might call an extraction function that returns `{"entities": [...]}`, then try to save that structure without flattening it.
- **Test:** Create a case with complex data (multiple entities, cross-references). Verify the saved structure matches what extraction produced. Query the case back and verify all fields are present.
- **Prevention:** Write tests that verify the round-trip: extract → save → retrieve → compare to original.

**4. Paginated vs. plain list**
Some code assumes API returns a list, but the API returns a paginated dict. Frontend code calling an endpoint might do:
```javascript
const signals = await fetch('/api/signals/');
signals.forEach(s => ...) // Crashes because signals is an object, not array
```
- **Test:** Every collection endpoint from both backend and frontend perspectives. Verify contract is understood.

**5. Empty data states**
Views that work with data often break when there's no data:
- Create case with no documents
- Create case with documents but no signals detected
- Entity with no relationships
- Search with no results
- User with no cases

These should all return 200 with empty arrays, not 404.

**6. Type coercion in filters**
Query parameters are always strings. If your filter expects `?active=true`, test:
- `?active=true` → works
- `?active=True` → might not work
- `?active=1` → might be interpreted as string "1", not boolean
- `?active=false` → might be interpreted as truthy string "false"

### What To Test For Each Bug Fix

For every bug fix, create or update tests that cover:

1. **The exact regression test** — The scenario that caused the bug. This test should fail before your fix, pass after.
2. **Related scenarios** — Similar edge cases that might have the same root cause.
3. **Full system test** — Verify the fix doesn't break existing functionality. Run the full health check.
4. **Data integrity** — If the fix involved data mutation, verify data consistency before and after.

Example: If you fix a bug where searching with special characters crashes the API:
- Regression test: search with `<script>alert('xss')</script>` returns 200 with empty results
- Related: search with `'; DROP TABLE cases; --` returns 200
- Related: search with emoji `🔍` returns 200
- Full health check: ensure search still works for normal queries
- Commit with test added to `investigations/tests_search.py`

### Test Execution Commands

**API health check:**
```bash
python3 tests/api_health_check.py https://catalyst-production-9566.up.railway.app
```
This is your go/no-go decision point. Run before shipping. If any endpoint returns 500 or times out, do not deploy.

**TypeScript type check:**
```bash
cd frontend && npx tsc --noEmit
```
Catches type errors before runtime. Run before every PR.

**Backend connector tests (no DB needed):**
```bash
cd backend && python -m unittest investigations/tests_propublica.py
cd backend && python -m unittest investigations/tests_transparency.py
```
These test external API integrations without needing a real database.

**Django tests (requires PostgreSQL):**
```bash
cd backend && python manage.py test investigations
```
Full test suite. Takes 2-5 minutes. Required before deploying to production.

**Run a specific test:**
```bash
cd backend && python manage.py test investigations.tests_cases.CaseDetailTest.test_case_with_no_documents
```

### Data Integrity Checks

Always verify after any significant change or bug fix:

1. **Entity names are plausible** — Not stopwords like "my", "hand", "an", "domestic". Signal entities should be real organization names.
2. **Signal counts match** — The `signal-summary` endpoint count should match the actual signal list length.
3. **Document count matches** — Case documents endpoint count should match documents on case dashboard.
4. **Financial records exist for IRS cases** — If case has an IRS 990 document, it should have associated financial records extracted.
5. **Detections reference valid signals** — Every detection's `signal_id` should resolve to an actual signal.
6. **All UUIDs are valid format** — Regex: `[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}` (case-insensitive).
7. **No orphaned records** — A case deletion should cascade and delete all related documents, signals, detections. Query after deletion to verify.

### Performance Baselines

Use these as flags for optimization work:

- **Collection endpoints:** Should respond in under 500ms
- **Case detail:** Should respond in under 200ms
- **Signal list for a case:** Should respond in under 2 seconds (even for cases with 500+ signals)
- **AI endpoints:** May take 2-10 seconds (Claude API latency is expected, not a bug)
- **Search:** Should return within 1 second for most queries
- **Document extraction:** Should complete within 30 seconds for a 100-page PDF

If an endpoint consistently exceeds these, it's likely an N+1 query or missing index. Flag for optimization.

### Security Testing Checklist

Test these attack vectors on any endpoint that accepts user input:

**SQL Injection:**
- Search: `q=' OR '1'='1`
- Filter: `?organization_name='; DROP TABLE cases; --`
- Expected: No tables dropped, returns 400 or empty results

**Cross-site scripting (XSS):**
- Search: `q=<script>alert('xss')</script>`
- Case name: POST with `{"name": "<img src=x onerror=alert('xss')>"}`
- Expected: Script tags are escaped or stripped, 200 response with safe HTML

**Path traversal:**
- Document download: `/api/cases/{id}/documents/../../../../etc/passwd`
- Expected: 404 or 403, never serves system files

**CSRF:**
- POST to mutation endpoint without token
- Expected: 403 Forbidden

**File upload:**
- Upload non-PDF (e.g., .exe, .js) to document endpoint
- Upload 500MB file (if size limit is 100MB)
- Upload file with special chars: `invoice@#$%.pdf`
- Expected: 400 Bad Request or 413 Payload Too Large, never executes

### Test Report Format

After running tests or testing a change, produce a report with:

```
=== TEST REPORT ===
Date: 2026-04-03
Environment: Production
Tester: [name]

SUMMARY:
- Total tests: 187 passed, 0 failed, 3 warnings
- Regression test coverage: 100%
- Performance: All endpoints under baselines

FAILED TESTS:
(None)

WARNINGS:
- Signal creation endpoint avg response time: 450ms (approaching 500ms limit)
- AI summarize endpoint timeout on 50-document case (14s), verify Claude API health
- Entity name "my_organization" created (stopword flag)

PERFORMANCE:
- Fastest: Search endpoint, avg 320ms
- Slowest: Case detail with signals, avg 1800ms (within 2s baseline)
- API health check: All 45 endpoints responded

DATA INTEGRITY:
- No orphaned records detected
- All UUIDs valid format
- Signal counts match across endpoints
- Document counts verified

SECURITY CHECKS:
- SQL injection: Passed (malicious queries safe)
- XSS: Passed (script tags escaped)
- CSRF: Passed (POST endpoints protected)
- File upload: Passed (non-PDFs rejected)

REGRESSION:
- Bug fix for search with special chars: Test passing
- Previous 5 bugs: All regression tests passing

RECOMMENDATION:
Ready to deploy. Monitor signal endpoint performance in next 48 hours.
```

## Red Flags (Stop and Escalate)

Stop testing immediately and escalate if you see:

1. **Any endpoint returning 500** — This means unhandled exception. Check application logs for the stack trace. Never ship with 500 errors.

2. **Unintended data in responses** — PII, secrets, internal file paths, API keys, database connection strings. Even if test passes, this is a security incident. Escalate to security.

3. **Tests that passed before now failing** — Regression detected. Revert the change, investigate the root cause, reapply fix.

4. **Response times degrading significantly** — 2 seconds suddenly become 10 seconds with no code change? Possible N+1 query, memory leak, or database issue. Check database query logs and application memory usage.

5. **Concurrent request failures** — Running 10 simultaneous requests causes failures that don't happen with sequential requests? Race condition or locking issue. This is critical.

6. **Intermittent failures** — Same test passes 8/10 times, fails 2/10 times. Indicates timing issue, resource contention, or flaky external API. Do not ship; mark as flaky and investigate.

7. **Data corruption after operation** — Create a case, add documents, verify integrity. Now run the same operation 100 times. If the 99th operation corrupts data, you have a boundary condition or database consistency issue.

## Signal Rules Testing (29 total)

Each signal rule is a detection pattern. Test each rule with:

1. **Positive case** — Data that should trigger the signal
2. **Negative case** — Similar data that should not trigger the signal
3. **Boundary case** — Edge of the detection criteria (e.g., if rule triggers on amount > $1M, test exactly $1M, $1M + $0.01)
4. **Data quality case** — Rule with missing/null fields

Example for "high-value transaction" rule:
- Positive: Transaction amount $2M, from nonprofit with history of fraud → detects
- Negative: Transaction amount $500K, from nonprofit with clean history → doesn't detect
- Boundary: Transaction amount $1,000,001 (just above threshold) → detects
- Data quality: Transaction with missing amount field → either skips or defaults safely

## Test Data Strategy

Never test against production data. Use these patterns:

**Fixture cases:**
- Case with 0 documents (empty)
- Case with 1 document (minimal)
- Case with 100 documents (large)
- Case with no entities extracted
- Case with 50+ entities (many relationships)

**Fixture organizations:**
- Fortune 500 company (high legitimacy)
- Unknown startup (low history)
- Organization with name conflict (multiple with same name)
- Organization with special characters in name

**Fixture documents:**
- Valid PDF 5 pages (normal)
- Valid PDF 1 page (minimal)
- Valid PDF 500 pages (large, tests extraction limits)
- Corrupted PDF (invalid structure)
- Scanned image as PDF (tests OCR if present)

Create these as SQL fixtures in `investigations/fixtures/test_data.sql` and load before each test run.

## Debugging Failed Tests

When a test fails:

1. **Read the assertion error.** It tells you expected vs. actual value.
2. **Check the test setup.** Did it create the right data? Print the fixture.
3. **Trace the code path.** Add debug prints or use a debugger to see where the divergence happens.
4. **Check for external dependencies.** Did Claude API fail? Is the database slow? Is the test environment missing a setting?
5. **Run the test in isolation.** `python manage.py test investigations.tests_cases.SpecificTest` — other tests might interfere.
6. **Check git history.** Did someone change this endpoint recently? What was the change?

## Continuous Testing Checklist

Run these regularly, not just before deploys:

**Daily:**
- API health check script on staging

**Per commit:**
- TypeScript type check
- Unit tests for the files you changed

**Per PR:**
- Full backend test suite
- Frontend build (no TypeScript errors)
- Manual smoke test of changed feature

**Per release candidate:**
- Full test suite + API health check on staging
- Load test (simulate 50 concurrent users)
- Regression test suite (all bugs we've fixed before)
- Security checklist

## Communication

When you find a bug:
1. **Reproduce it consistently** — Write a test that fails.
2. **Describe it clearly** — What did you do? What did you expect? What happened?
3. **Provide the test** — Include the test code and instructions to run it.
4. **Assign severity:**
   - **Critical:** 500 error, data corruption, security issue → block deploy
   - **High:** Feature broken, significant data loss → fix before deploy
   - **Medium:** Edge case broken, workaround exists → fix in next release
   - **Low:** Cosmetic, rare scenario → backlog

When you ship a fix:
1. **Include the regression test** — The test that would have caught the bug.
2. **Run full health check** — Verify nothing else broke.
3. **Test in staging first** — Before production.

---

## File Locations Reference

- **API health check script:** `tests/api_health_check.py`
- **Signal rules definition:** `backend/investigations/signal_rules.py`
- **Connector integrations:** `backend/investigations/connectors/`
- **Django tests:** `backend/investigations/tests_*.py`
- **Frontend tests:** `frontend/src/__tests__/`
- **Test fixtures:** `backend/investigations/fixtures/`
- **Deployment config:** `.railway.json` or Railway dashboard

---

This is your playbook. Use it as your operational bible. When you find a new bug pattern, add it to "Known Bug Patterns" so future you doesn't repeat the same mistakes. Quality is built, not tested in — your job is to make sure the build holds.
