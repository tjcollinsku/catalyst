# Catalyst — Current Project State

**Last Updated:** 2026-04-02 (Session 27)
**Current Milestone:** Frontend Redesign — **COMPLETE (All 6 Phases)**
**Charter Version:** v3

---

## Quick Stats

| Metric | Count |
|--------|-------|
| Django Models | 21 |
| Database Migrations | 20 (including ingestion_metadata) |
| API Endpoints | 45 (38 JSON + 7 HTML legacy) — added graph + 4 AI endpoints |
| Backend Test Count | 555+ |
| External Connectors | 6 complete, 1 not started (UCC), 1 deferred (PACER) |
| Frontend Views | 11 |
| Frontend Components | 42 (added 14 new components in redesign) |
| Signal Rules | 29 (SR-001 through SR-029) |

---

## Build Status

| Component | Status | Last Checked |
|-----------|--------|-------------|
| Backend (Django) | PASS (python ast.parse) | 2026-04-02 |
| Frontend (tsc --noEmit) | **PASS** — zero type errors | 2026-04-02 |
| Frontend (vite build) | **PASS** — 684 modules, 425KB JS / 133KB gzipped | 2026-04-02 |
| Backend Tests | PASS (connector tests) | 2026-04-01 |
| Frontend Tests | NONE EXIST | — |

---

## Frontend Redesign — 6-Phase Completion Summary

### Phase 1: Foundation (Sessions 18–25)
- CSS Modules architecture, design tokens (dark/light/auto themes), AppShell layout, Sidebar, Breadcrumb, CommandPalette, shared UI components

### Phase 2: Entity Relationship Graph
- D3.js v7 force-directed graph as Overview tab centerpiece
- Node shapes by type (circle=person, square=org, triangle=property, diamond=financial)
- Hover highlights, click-to-select, drag-to-reposition, zoom/pan toolbar
- Slide-in EntityProfilePanel with type-specific metadata
- Backend `api_case_graph()` endpoint collecting nodes/edges from 6 junction tables

### Phase 3: Synchronized Timeline
- D3 horizontal timeline with 4 toggle-able layers (document, signal, financial, transaction)
- Brush selection filters graph nodes by date range
- Click timeline marker → selects referenced entity on graph
- Graph selection → dims unrelated timeline markers

### Phase 4: Unified Pipeline
- Replaced 3 separate tabs (Signals/Detections/Findings) with single Pipeline tab
- SOAR-style 5-stage status bar (New → Reviewing → Confirmed → Draft → Published)
- Quick-action buttons (Start Review, Confirm, Dismiss, Draft Finding, Publish)
- Severity filter, detail panels with full edit forms

### Phase 5: Deep AI Integration
- **Backend:** `ai_proxy.py` module with 4 AI functions (summarize, connections, narrative, ask)
- **Models:** Haiku for summarize (cheap/fast), Sonnet for deeper analysis
- **Endpoints:** 4 POST routes under `/api/cases/<uuid>/ai/`
- **Inline AI badges:** AISummaryBadge on every pipeline card + entity profile panel
- **AI Assistant Panel:** Slide-in chat panel with 6 quick actions + free-text conversation, multi-turn history, source linking, follow-up suggestions
- **AppShell integration:** AI toggle button in topbar (visible on case pages only)

### Phase 6: Polish
- **Theme system:** Smooth 200ms transition on theme switch, cycle toggle (dark/light/auto) in topbar
- **Animations:** Staggered card entrance (rise-in + per-card delay), enhanced card hover lift, graph resize transition
- **Loading states:** GraphSkeleton, TimelineSkeleton, KPI skeleton blocks in OverviewTab
- **Empty states:** Enhanced EmptyState component with icon + action button. Graph, timeline, and pipeline all show contextual empty states
- **Accessibility:** Skip-to-content link, ARIA live region for graph selection, ARIA labels on graph SVG and AI panel, Escape-to-close on AI panel, reduced motion support, focus-visible ring

---

## Frontend View Status

| View | Route | Status | Notes |
|------|-------|--------|-------|
| DashboardView | `/` | Working | |
| CasesListView | `/cases` | Working | |
| CaseDetailView | `/cases/:caseId` | Working | 5 tabs (Overview, Documents, Financials, Pipeline, Referrals) |
| OverviewTab | `/cases/:caseId/overview` | **Redesigned** | KPI cards → Entity graph → Timeline → Dashboard cards |
| DocumentsTab | `/cases/:caseId/documents` | Working | |
| PipelineTab | `/cases/:caseId/pipeline` | **NEW** | Replaces Signals+Detections+Findings tabs |
| ReferralsTab | `/cases/:caseId/referrals` | Working | |
| FinancialsTab | `/cases/:caseId/financials` | Working | |
| EntityBrowserView | `/entities` | Working | |
| EntityDetailView | `/entities/:type/:id` | Working | |
| TriageView | `/triage` | Working | |
| ReferralsView | `/referrals` | Working | |
| SearchView | `/search` | Working | |
| SettingsView | `/settings` | Working | |

---

## New Files (Session 27 — Frontend Redesign Phases 2–6)

### Backend
| File | Purpose |
|------|---------|
| `backend/investigations/ai_proxy.py` | AI proxy module — 4 Claude-powered functions with caching + rate limiting |
| `backend/investigations/views.py` (modified) | Added `api_case_graph()` + 4 AI endpoint views |
| `backend/investigations/urls.py` (modified) | Added graph + 4 AI URL routes |
| `backend/investigations/models.py` (modified) | Added UNDER_REVIEW to SignalStatus |

### Frontend — Graph components
| File | Purpose |
|------|---------|
| `frontend/src/components/graph/EntityGraph.tsx` | D3 force-directed graph |
| `frontend/src/components/graph/EntityGraph.module.css` | Graph styles |
| `frontend/src/components/graph/EntityProfilePanel.tsx` | Slide-in entity profile |
| `frontend/src/components/graph/EntityProfilePanel.module.css` | Profile panel styles |
| `frontend/src/components/graph/TimelineView.tsx` | D3 horizontal timeline |
| `frontend/src/components/graph/TimelineView.module.css` | Timeline styles |

### Frontend — AI components
| File | Purpose |
|------|---------|
| `frontend/src/components/ai/AISummaryBadge.tsx` | Inline AI summary badge |
| `frontend/src/components/ai/AISummaryBadge.module.css` | Badge styles |
| `frontend/src/components/ai/AIAssistantPanel.tsx` | Chat panel with quick actions + free-text |
| `frontend/src/components/ai/AIAssistantPanel.module.css` | Chat panel styles |

### Frontend — Pipeline + UI
| File | Purpose |
|------|---------|
| `frontend/src/components/cases/PipelineTab.tsx` | Unified pipeline tab |
| `frontend/src/components/cases/PipelineTab.module.css` | Pipeline styles |
| `frontend/src/components/ui/Skeleton.tsx` | Loading skeleton components |
| `frontend/src/components/ui/Skeleton.module.css` | Skeleton styles |

### Frontend — Modified
| File | Change |
|------|--------|
| `frontend/src/types.ts` | Added graph types + AI response types |
| `frontend/src/api.ts` | Added fetchCaseGraph + 4 AI API functions |
| `frontend/src/App.tsx` | Replaced signal/detection/finding routes with pipeline |
| `frontend/src/views/CaseDetailView.tsx` | Reduced to 5 tabs |
| `frontend/src/components/cases/OverviewTab.tsx` | Rewritten — graph + timeline + skeletons + empty states |
| `frontend/src/components/cases/OverviewTab.module.css` | Added graphContainer |
| `frontend/src/components/ui/Button.tsx` | Added danger variant + sm size |
| `frontend/src/components/ui/Button.module.css` | Added danger + sm styles |
| `frontend/src/components/ui/EmptyState.tsx` | Enhanced with icon + action button |
| `frontend/src/components/ui/EmptyState.module.css` | Redesigned styles |
| `frontend/src/layouts/AppShell.tsx` | Added AI panel toggle + theme toggle + skip-to-content |
| `frontend/src/layouts/AppShell.module.css` | Added AI toggle + theme toggle styles |
| `frontend/src/hooks/useTheme.ts` | Added smooth transition on theme switch |
| `frontend/src/styles/base.css` | Added theme transition, sr-only, global classes |
| `frontend/src/styles/utilities.css` | Added cardHover, animRiseIn, animStagger |

---

## Milestone Progress

### Milestone 1: Frontend Compilation — COMPLETE
### Milestone 2: Golden Path Wiring — COMPLETE
### Milestone 3: Frontend Redesign (6 Phases) — COMPLETE
- [x] Phase 1: Foundation (CSS Modules, tokens, AppShell, shared UI)
- [x] Phase 2: Entity relationship graph (D3 force-directed)
- [x] Phase 3: Synchronized timeline
- [x] Phase 4: Unified pipeline tab
- [x] Phase 5: Deep AI integration (4 endpoints + badges + chat panel)
- [x] Phase 6: Polish (themes, animations, skeletons, empty states, accessibility)

### Milestone 4: AI Memo Generation — NOT STARTED
### Milestone 5: Deploy — NOT STARTED

---

## Known Blockers

- ⚠️ **GovOS CountyFusion Platform Outage** — ~20 Ohio counties affected. Need to re-verify when recovered.

---

## Connector Status

| Connector | Status | Tests |
|-----------|--------|-------|
| ProPublica | Complete | 29 pass |
| IRS | Complete | 104 pass |
| Ohio SOS | Complete | 59 pass |
| County Auditor | Complete | 126 pass |
| County Recorder | Complete | 191 pass |
| Ohio AOS | Complete | 46 pass |
| Ohio UCC | Not started | — |
| PACER | Deferred (V2) | — |

---

## Key Files

| Purpose | File |
|---------|------|
| Charter | docs/charter/catalyst-charter-v3.md |
| Architecture | docs/project/architecture.md |
| Design Decisions | docs/project/design-decisions.md |
| Frontend Spec | docs/project/frontend-spec.md |
| Frontend Redesign Gameplan | docs/project/FRONTEND_REDESIGN_GAMEPLAN.md |
| Tech Debt | docs/governance/tech-debt-register.md |
| Risk Register | docs/governance/risk-register.md |
| Session Tracker | docs/ops/session-tracker.md |
| Security Audit | docs/SECURITY_AUDIT.md |

---

## Session History (Recent)

| Session | Date | Summary |
|---------|------|---------|
| 27 | 2026-04-02 | **Frontend Redesign COMPLETE (Phases 2–6).** Built D3 entity graph + timeline (synced). Unified pipeline tab replacing 3 tabs. Deep AI integration: ai_proxy.py backend, 4 API endpoints, inline AI badges, AI assistant chat panel. Polish: theme toggle, smooth transitions, staggered card animations, loading skeletons, empty states, accessibility (skip-to-content, ARIA, reduced motion). tsc + vite build clean. |
| 26 | 2026-04-02 | Fixed TS errors. Researched 9+ investigative platforms (Palantir, Maltego, CrowdStrike, Sentinel, etc.). Created FRONTEND_REDESIGN_GAMEPLAN.md with 6-phase plan. |
| 25 | 2026-04-02 | All 3 blockers resolved (TD-015/016/017). Rewrote persist_signals(). Built OverviewTab dashboard. Root folder cleanup. |
| 24 | 2026-04-01 | Signal engine 16→29 rules. AI entity extraction via Claude API. PDF forensics. |
| 23 | 2026-04-01 | **Milestone 2 COMPLETE.** 4 missing backend views. FindingsTab. Live-tested full Golden Path. |
| 22 | 2026-04-01 | Governance reset + Milestone 1 complete. Charter v3. Fixed 5 truncated files. Frontend compiles clean. |
| 21 | 2026-03-31 | Phase 3 security hardening. All 38 security findings resolved. |
