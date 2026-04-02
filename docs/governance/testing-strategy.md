# Catalyst — Testing Strategy

**Last Updated:** 2026-04-01
**Purpose:** Define what gets tested, how, and what the minimum bar is.

---

## Current State

The backend has 555+ tests across 6 test files. The frontend has zero tests. This strategy defines the minimum testing bar for V1 and a growth path for V2.

---

## V1 Testing Bar (Minimum)

### Backend

**What MUST be tested:**
- Every API endpoint: at least one happy-path test (correct request → correct response)
- Every connector: mocked HTTP tests covering search, error handling, and parsing
- Entity resolution: exact match and fuzzy match paths
- Signal rules: at least one test per rule confirming it fires on expected input

**What CAN be tested manually for V1:**
- Upload pipeline end-to-end (upload PDF → check entities/signals created)
- Memo generation output quality
- Cross-view navigation in the frontend

**How to run backend tests:**
```bash
# Connector tests (no database needed)
cd backend
python -m unittest investigations/tests_propublica.py
python -m unittest investigations/tests_ohio_sos.py
python -m unittest investigations/tests_irs.py
python -m unittest investigations/tests_county_recorder.py
python -m unittest investigations/tests_county_auditor.py

# Django tests (requires PostgreSQL running)
cd backend
python manage.py test investigations
```

### Frontend

**V1 minimum:** The frontend compiles (`npm run build` succeeds). No automated tests required for V1, but the build check is a hard gate.

**Why no frontend tests for V1:** The frontend is currently broken (4 truncated files). The priority is getting it to compile and work, not testing it. Once it's stable, tests become valuable.

---

## V2 Testing Growth Path

### Backend Additions
- Integration tests: upload a real PDF → verify full pipeline output (entities, signals, detection)
- Memo generation: verify output structure and citation accuracy
- Auth tests: verify user-scoped filtering when auth is added

### Frontend Additions
- Component tests with Vitest + React Testing Library
- Critical path: upload flow, signal triage, finding creation
- API mocking with MSW (Mock Service Worker)
- Visual regression tests (optional, nice-to-have)

---

## Test Organization

```
backend/
├── investigations/
│   ├── tests.py                    # Django API tests (requires DB)
│   ├── tests_propublica.py         # ProPublica connector (no DB)
│   ├── tests_ohio_sos.py           # Ohio SOS connector (no DB)
│   ├── tests_irs.py                # IRS connector (no DB)
│   ├── tests_county_recorder.py    # County recorder (no DB, no HTTP)
│   └── tests_county_auditor.py     # County auditor (no DB)

frontend/
├── src/
│   └── test/
│       └── setup.ts                # Test setup (exists but empty)
```

---

## Testing Rules

1. **Connectors are always tested with mocked HTTP.** No real network calls in tests. This keeps tests fast, reliable, and free from API quotas.
2. **Never skip the build check.** If `npm run build` fails, the session is not done.
3. **New signal rules get a test.** Every new SR-xxx rule must have at least one test proving it fires correctly.
4. **Regression tests after bug fixes.** If a bug is found and fixed, add a test that would catch the bug if it returns.
5. **Don't test framework code.** Don't test that Django's ORM works or that React renders. Test YOUR logic.
