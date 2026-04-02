# Catalyst — Tech Debt Register

**Last Updated:** 2026-04-01
**Purpose:** Track all known technical debt. Prioritize during roadmap updates, not ad-hoc.

---

## How to Use This File

When you notice tech debt during a session, add it here with a severity and brief description. Do NOT fix it immediately unless it blocks the current milestone. Tech debt is addressed during planned roadmap slots, not reactively.

Severity levels:
- **CRITICAL** — Blocks compilation, deployment, or demo. Fix in current milestone.
- **HIGH** — Degrades quality noticeably. Schedule for next milestone.
- **MEDIUM** — Should be fixed but doesn't block anything. Address when convenient.
- **LOW** — Nice to have. Fix during polish phase.

---

## Active Tech Debt

| ID | Severity | Description | Location | Added |
|----|----------|-------------|----------|-------|
| TD-001 | CRITICAL | `types.ts` truncated — ends mid-property definition at "othe" | frontend/src/types.ts:222 | 2026-04-01 |
| TD-002 | CRITICAL | `CaseDetailView.tsx` truncated — ends at "p.filt" on line 461 | frontend/src/views/CaseDetailView.tsx:461 | 2026-04-01 |
| TD-003 | CRITICAL | `DocumentsTab.tsx` truncated — missing JSX closing fragment | frontend/src/components/cases/DocumentsTab.tsx:178 | 2026-04-01 |
| TD-004 | CRITICAL | `PdfViewer.tsx` truncated — missing closing divs + button | frontend/src/components/ui/PdfViewer.tsx:87 | 2026-04-01 |
| TD-005 | CRITICAL | `fetchDocumentDetail()` imported in PdfViewer but not defined in api.ts | frontend/src/api.ts | 2026-04-01 |
| TD-006 | HIGH | Missing Django migration for ExtractionStatus fields on Document model | backend/investigations/models.py | 2026-04-01 |
| TD-007 | HIGH | `TODO(SEC-010)` markers — 6 endpoints need user-scoped filtering when auth is added | backend/investigations/views.py | 2026-04-01 |
| TD-008 | MEDIUM | views.py is ~2600 lines — should be split into logical modules | backend/investigations/views.py | 2026-04-01 |
| TD-009 | MEDIUM | No frontend tests exist | frontend/ | 2026-04-01 |
| TD-010 | MEDIUM | Signal rules not configurable without code changes (FR-605 partial) | backend/investigations/signal_rules.py | 2026-04-01 |
| TD-011 | MEDIUM | Rate limiting is in-memory only — resets on process restart | backend/investigations/middleware.py | 2026-04-01 |
| TD-012 | LOW | HTML template views still exist alongside API views (legacy from Phase 1) | backend/investigations/views.py, urls.py | 2026-04-01 |
| TD-013 | LOW | `admin.py` has some models with basic `admin.site.register()` instead of full ModelAdmin | backend/investigations/admin.py | 2026-04-01 |
| TD-014 | LOW | Session tracker (docs/ops/session-tracker.md) has stale open tasks | docs/ops/session-tracker.md | 2026-04-01 |

---

## Resolved Tech Debt

| ID | Description | Resolved | Milestone |
|----|-------------|----------|-----------|
| *(none yet)* | | | |
