# Catalyst — Test Report
**Date:** 2026-04-03
**Deployment:** catalyst-production-9566.up.railway.app
**Commit:** 79dcc78 (8 bug fixes)

---

## Test Results Summary

| Layer | Tests | Pass | Fail | Status |
|-------|-------|------|------|--------|
| Infrastructure (health, CSRF, SPA) | 3 | 3 | 0 | CLEAN |
| Collection endpoints (cases, signals, entities, search) | 8 | 7 | 1* | CLEAN* |
| Case-specific endpoints (detail, docs, financials, etc.) | 12 | 12 | 0 | CLEAN |
| AI endpoints (summarize, connections, narrative, ask) | 4 | 0 | 4 | BROKEN |
| Edge cases (404, bad UUID, XSS) | 3 | 3 | 0 | CLEAN |
| Frontend TypeScript compilation | 1 | 1 | 0 | CLEAN |
| Frontend Vite build | 1 | 0 | 1** | N/A** |

*Search empty query returns 400 — this is CORRECT validation behavior, not a bug.
**Vite build fails in sandbox due to file permissions — builds correctly in Docker/Railway.

---

## Bugs Found

### BUG-9: AI Endpoints Return 403/500 (CSRF Missing)
- **Severity:** HIGH — All 4 AI features are broken
- **Endpoints:** `/ai/summarize/`, `/ai/connections/`, `/ai/narrative/`, `/ai/ask/`
- **Root cause:** Missing `@csrf_exempt` decorator on all 4 AI view functions
- **Impact:** AI sidebar in the frontend returns 500 for every action
- **Fix:** Added `@csrf_exempt` to all 4 AI POST endpoints in views.py
- **Status:** Fixed in code, awaiting deploy

### DATA-1: Bad Entity Extractions (Pre-Fix Data)
- **Severity:** LOW — cosmetic, doesn't break functionality
- **Count:** 5 suspect entities + 2 more borderline
- **Examples:** "Domestic Limited Liability Company", "Limited Liability Partners", "my hand", "DOM. LLC"
- **Root cause:** These were extracted before the entity extraction fix was deployed
- **Fix:** Entity extraction pipeline is now fixed. These old entities need manual cleanup or re-extraction.
- **Status:** Extraction fix deployed. Cleanup pending.

### DATA-2: Empty Financials Tab
- **Severity:** MEDIUM — feature not populating
- **Count:** 0 financial records despite 7 IRS 990 documents uploaded
- **Root cause:** The save function had a key mapping mismatch (fixed in commit 79dcc78). But existing documents were processed before the fix.
- **Fix:** Re-upload or re-process the IRS 990 documents to trigger the corrected extraction.
- **Status:** Code fix deployed. Re-processing needed.

---

## Endpoint Status (Full Map)

### All Passing (200 OK)
```
GET  /api/health/              231ms  Infrastructure heartbeat
GET  /api/csrf/                193ms  CSRF token endpoint
GET  /                         198ms  SPA frontend serves correctly
GET  /api/cases/               212ms  Lists 3 cases (paginated)
GET  /api/signals/             215ms  Lists 10 signals (paginated)
GET  /api/signal-summary/      211ms  Triage summary (1 case, 4 open)
GET  /api/referrals/           212ms  Referrals list (paginated)
GET  /api/entities/            224ms  16 entities (paginated)
GET  /api/activity-feed/       202ms  Activity feed
GET  /api/search/?q=test       347ms  Full-text search working
GET  /api/cases/{id}/          214ms  Case detail
GET  /api/cases/{id}/dashboard/ 284ms Case dashboard
GET  /api/cases/{id}/signals/  1221ms Case signals (slow — may need optimization)
GET  /api/cases/{id}/documents/ 212ms Case documents (17 docs)
GET  /api/cases/{id}/financials/ 206ms Returns empty (data issue, not code)
GET  /api/cases/{id}/detections/ 237ms 6 detections
GET  /api/cases/{id}/findings/  218ms Case findings
GET  /api/cases/{id}/referrals/ 212ms Case referrals
GET  /api/cases/{id}/notes/     214ms Case notes
GET  /api/cases/{id}/graph/     284ms Entity graph (nodes + edges)
GET  /api/cases/{id}/coverage/  262ms Coverage analysis
GET  /api/cases/{id}/export/    250ms Case export
```

### Failing
```
POST /api/cases/{id}/ai/summarize/    500  Missing @csrf_exempt (FIXED)
POST /api/cases/{id}/ai/connections/  500  Missing @csrf_exempt (FIXED)
POST /api/cases/{id}/ai/narrative/    500  Missing @csrf_exempt (FIXED)
POST /api/cases/{id}/ai/ask/          500  Missing @csrf_exempt (FIXED)
```

### Expected Errors (Correct Behavior)
```
GET  /api/search/?q=           400  Validates min 2 chars — CORRECT
GET  /api/cases/{fake-uuid}/   404  Returns 404 — CORRECT
GET  /api/cases/not-a-uuid/    404  Returns 404 — CORRECT
```

---

## Performance Notes

- Average response time: 250ms (good)
- Max response time: 1221ms on `/api/cases/{id}/signals/` (acceptable but monitor)
- No responses > 2 seconds
- All AI endpoints untested for performance (blocked by CSRF bug)

---

## Database State

| Data Type | Count | Health |
|-----------|-------|--------|
| Cases | 3 | OK |
| Signals | 10 (4 OPEN, 6 CONFIRMED) | OK |
| Entities | 16 (5 suspect) | NEEDS CLEANUP |
| Documents | 17 | OK |
| Financials | 0 | NEEDS RE-PROCESSING |
| Detections | 6 | OK |

---

## Next Steps

1. **Deploy CSRF fix** — commit and push `@csrf_exempt` on AI endpoints
2. **Re-test AI endpoints** after deploy
3. **Clean up bad entities** — delete the 5 suspect entities from the database
4. **Re-process IRS 990 docs** — trigger financial extraction on existing documents
5. **Create persistent smoke test** — run `api_health_check.py` after every deploy
