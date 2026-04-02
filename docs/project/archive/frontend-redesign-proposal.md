# Catalyst Frontend Redesign Proposal

**Date:** 2026-03-31
**Status:** Draft — for discussion

---

## The Problem

Right now, Catalyst's entire frontend lives on a single page. Cases, documents, signals, detections, referrals, search — everything is stacked into one dashboard view with tabs inside the case detail panel. This worked fine for proving out the backend and wiring up API calls, but it has real problems as a working investigation tool:

1. **Cognitive overload.** An investigator looking at signal triage doesn't need the case creation form in their peripheral vision. A manager checking referral status doesn't need the document upload controls.

2. **No sense of "where am I."** There's no navigation. No URL you can bookmark. No way to link a colleague to a specific case or signal.

3. **The App.tsx god component.** All state (cases, signals, detections, referrals, documents, UI state, toasts, drafts) lives in one 749-line file. Every new feature makes this worse.

4. **No role-based views.** An investigator doing daily triage has completely different needs than someone preparing a referral package for the Ohio AG. Right now they use the same screen.

5. **No context persistence.** If you're deep in signal triage on Case 47 and want to check a referral, you lose your place. There's no concept of "open this in a new context."

---

## Reference Software — What Works in the Real World

Before proposing a structure, here's what professional investigation and case management tools do well, and what we should steal from each:

### Palantir Gotham
- **What they do right:** Multiple "applications" (Graph, Map, Dossier, Timeline) all backed by the same data layer. You move between views seamlessly — the data follows you, not the other way around.
- **What we steal:** The concept of *multiple analytical views* on the same case data. Our "case" is the anchor. Documents, signals, detections, and referrals are different *lenses* on that case.

### Splunk SOAR / Enterprise Security
- **What they do right:** The "Analyst Queue" pattern — a dedicated triage view where analysts process alerts one by one with a right-hand detail panel. Wayfinder keyboard navigation for jumping between views without touching the mouse.
- **What we steal:** A dedicated *Signal Triage Queue* view that is purpose-built for the j/k/1/2/3 keyboard workflow. Not a tab inside another panel — a first-class view.

### Unit21 (Fraud Case Management)
- **What they do right:** Role-specific dashboards. An "Agent Command Center" for individual analysts, a "Case Intelligence" view for managers, a "Service Command Center" for leadership. Each shows the same underlying data but with different emphasis.
- **What we steal:** The idea that the *dashboard* view should be configurable by role. An investigator's home screen is the triage queue. A supervisor's home screen is case status overview.

### Linear (Project Management)
- **What they do right:** A collapsible left sidebar for navigation that stays consistent everywhere. Clean URL-based routing (`/project/ABC/issue/123`). Keyboard-first design (`Cmd+K` command palette).
- **What we steal:** The sidebar navigation pattern, deep-linkable URLs, and the command palette concept for power users.

### Notion
- **What they do right:** Multiple "views" on the same database — table, board, timeline, calendar. Each view has its own filters and sort.
- **What we steal:** The idea of *saved views* on case lists. "My open signals" vs "All critical cases" vs "Pending referrals" — same data, different filters, bookmarkable.

---

## Proposed Architecture: Shell + Views

The core idea is a **persistent shell** (sidebar + header) with **swappable view panels** driven by a router.

### The Shell

The shell is always visible. It provides orientation ("where am I"), navigation ("where can I go"), and global actions ("search anything").

```
┌──────────────────────────────────────────────────────────────┐
│  ┌─────┐  CATALYST          [🔍 Search... ]  [⚙]  [👤 TC]  │
│  │ nav │                     Cmd+K to search                 │
│  │     │─────────────────────────────────────────────────────│
│  │     │                                                     │
│  │  📊 │   ┌─────────────────────────────────────────────┐   │
│  │     │   │                                             │   │
│  │  📁 │   │          ACTIVE VIEW PANEL                  │   │
│  │     │   │                                             │   │
│  │  🔔 │   │   (Dashboard / Cases / Triage /             │   │
│  │     │   │    Case Detail / Referrals / etc.)          │   │
│  │  📄 │   │                                             │   │
│  │     │   │                                             │   │
│  │  📤 │   │                                             │   │
│  │     │   │                                             │   │
│  │  ⚙  │   └─────────────────────────────────────────────┘   │
│  └─────┘                                                     │
└──────────────────────────────────────────────────────────────┘
```

**Sidebar items** (icon + label, collapsible to icons-only):

| Icon | Label | Route | Purpose |
|------|-------|-------|---------|
| 📊 | Dashboard | `/` | KPI overview, recent activity, quick stats |
| 📁 | Cases | `/cases` | Filterable/sortable case list (table view) |
| 🔔 | Triage | `/triage` | Signal triage queue (dedicated analyst workflow) |
| 📤 | Referrals | `/referrals` | Cross-case referral tracking |
| 🔍 | Search | `/search` | Semantic search (full-text, cross-case) |
| ⚙ | Settings | `/settings` | Future: connector config, user prefs |

**Case detail** is a nested route: `/cases/:caseId` — with its own internal tabs for Documents, Signals, Detections, Referrals.

---

## The Five Core Views

### View 1: Dashboard (`/`)

**Purpose:** "What needs my attention right now?"

This is the landing page. It replaces the current KPI cards + everything-else layout with a focused operational overview.

```
┌──────────────────────────────────────────────────────────────┐
│  DASHBOARD                                                    │
│                                                               │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐│
│  │ Open Cases │ │ Unreviewed │ │  Critical  │ │  Pending   ││
│  │     12     │ │  Signals   │ │ Detections │ │ Referrals  ││
│  │            │ │     47     │ │      3     │ │      5     ││
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘│
│                                                               │
│  RECENT ACTIVITY                    SIGNAL HEATMAP            │
│  ┌─────────────────────────┐  ┌──────────────────────────┐   │
│  │ Case "Oak Hills" updated│  │                          │   │
│  │ 3 new signals on "FCA"  │  │  [signals by severity    │   │
│  │ Referral submitted to AG│  │   over last 30 days]     │   │
│  │ OCR completed: 12 docs  │  │                          │   │
│  │ ...                     │  │                          │   │
│  └─────────────────────────┘  └──────────────────────────┘   │
│                                                               │
│  MY OPEN SIGNALS (top 5)        CASES BY STATUS               │
│  ┌─────────────────────────┐  ┌──────────────────────────┐   │
│  │ SR-005 Self-dealing...  │  │ ██████████ Open (12)     │   │
│  │ SR-001 Deceased signer  │  │ ████ Referred (4)        │   │
│  │ SR-007 Procurement...   │  │ ██ Closed (2)            │   │
│  │ ...                     │  │                          │   │
│  └─────────────────────────┘  └──────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

**What's different from today:** The dashboard is *just* a dashboard — an at-a-glance view. Clicking any widget navigates you to the relevant detailed view. "3 new signals on FCA" takes you to `/cases/fca-uuid/signals`. The KPI cards are clickable shortcuts.

**Reference:** Unit21's role-specific dashboards, Splunk ES's "Posture Dashboard."

---

### View 2: Cases List (`/cases`)

**Purpose:** "Show me all my cases and let me find what I need."

This replaces the current left-sidebar case list, giving it a full-width dedicated view with proper table layout, richer filtering, and batch actions.

```
┌──────────────────────────────────────────────────────────────┐
│  CASES                                    [+ New Case]        │
│                                                               │
│  Filters: [Status ▾] [Severity ▾] [Date Range] [Search...]   │
│  View:    [Table] [Board]                                     │
│                                                               │
│  ┌──────┬────────────────┬────────┬──────────┬───────┬──────┐│
│  │  ●   │ Name           │ Status │ Signals  │ Docs  │ Updated│
│  ├──────┼────────────────┼────────┼──────────┼───────┼──────┤│
│  │ 🔴   │ Oak Hills Farm │ OPEN   │ 12 (3🔴) │  47   │ 2h ago│
│  │ 🟡   │ FCA Lending    │ OPEN   │  8 (1🔴) │  23   │ 1d ago│
│  │ 🟢   │ County Audit   │ CLOSED │  2 (0🔴) │  15   │ 5d ago│
│  │ 🔴   │ Shell Corp Net │ OPEN   │ 19 (7🔴) │  89   │ 3h ago│
│  │ ...  │ ...            │ ...    │ ...      │  ...  │ ...   │
│  └──────┴────────────────┴────────┴──────────┴───────┴──────┘│
│                                                               │
│  Showing 1-25 of 18 cases          [< Prev]  [Next >]        │
└──────────────────────────────────────────────────────────────┘
```

**Key improvement:** Clicking a case row navigates to `/cases/:caseId`, which opens the Case Detail view. The case list is no longer a cramped sidebar — it's a proper data table with visible columns for signal counts, document counts, severity indicators, and last-updated timestamps.

**Board view** (future, Notion-style): Cases as cards in columns by status (OPEN → REFERRED → CLOSED). Drag-and-drop to change status.

**Reference:** Linear's issue list, Jira's backlog view.

---

### View 3: Case Detail (`/cases/:caseId`)

**Purpose:** "Everything about this one case."

This is the deep-dive view. It replaces the current CaseDetailPanel but gives it the full viewport width and a proper tab bar.

```
┌──────────────────────────────────────────────────────────────┐
│  ← Back to Cases    OAK HILLS FARM INVESTIGATION    [OPEN ▾] │
│  Created: 2026-01-15  |  Ref: OAG-2026-0042  |  47 docs     │
│                                                               │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐    │
│  │▐Documents│ Signals  │Detections│Referrals │ Timeline │    │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘    │
│                                                               │
│  DOCUMENTS                           [Upload Files] [Run OCR] │
│                                                               │
│  Filters: [Type ▾] [OCR Status ▾] [Search...]                │
│                                                               │
│  ┌──────────────────┬──────────┬───────────┬────────────────┐│
│  │ Filename         │ Type     │ OCR       │ Entities Found ││
│  ├──────────────────┼──────────┼───────────┼────────────────┤│
│  │ deed-2019-04.pdf │ DEED     │ COMPLETE  │ 3 persons, 1 org│
│  │ 990-2020.pdf     │ TAX_FORM │ COMPLETE  │ 2 orgs, 4 amts ││
│  │ board-minutes.pdf│ MINUTES  │ PENDING   │ —              ││
│  │ loan-agreement.. │ CONTRACT │ COMPLETE  │ 5 persons      ││
│  └──────────────────┴──────────┴───────────┴────────────────┘│
│                                                               │
│  Drop files here to upload                                    │
└──────────────────────────────────────────────────────────────┘
```

**Tabs within Case Detail:**

| Tab | Route | Content |
|-----|-------|---------|
| Documents | `/cases/:id/documents` | Document table + upload + OCR controls |
| Signals | `/cases/:id/signals` | Signal list + inline triage (same keyboard shortcuts) |
| Detections | `/cases/:id/detections` | Detection cards with status/severity controls |
| Referrals | `/cases/:id/referrals` | Referral tracking + memo generation |
| Timeline | `/cases/:id/timeline` | NEW: Chronological audit log for this case |

**The Timeline tab** is new. It pulls from the existing `AuditLog` table to show a chronological narrative: "Document uploaded → OCR completed → 3 signals detected → Signal SR-005 reviewed by investigator → Referral drafted to Ohio AG." This is the audit trail that makes Catalyst defensible.

**Reference:** Palantir Gotham's "Dossier" view (everything about one entity), GitHub's issue detail with tabs.

---

### View 4: Signal Triage Queue (`/triage`)

**Purpose:** "Let me burn through my signal queue efficiently."

This is the **most important new view**. Right now, signal triage is buried as a tab inside case detail. But triage is the core investigator workflow — it deserves a dedicated, purpose-built screen.

```
┌──────────────────────────────────────────────────────────────┐
│  SIGNAL TRIAGE                              Showing: All Cases│
│                                                               │
│  Filters: [Severity ▾] [Status ▾] [Case ▾] [Rule ▾]         │
│  Queue: 47 signals  |  12 OPEN  |  28 REVIEWED  |  7 DISMISSED│
│                                                               │
│  ┌─────────────────────────┬────────────────────────────────┐│
│  │  SIGNAL LIST            │  SIGNAL DETAIL                 ││
│  │                         │                                ││
│  │  🔴 SR-005 Self-dealing │  SR-005: SELF-DEALING          ││
│  │     Oak Hills Farm      │  Case: Oak Hills Farm          ││
│  │     OPEN                │  Severity: CRITICAL            ││
│  │  ─────────────────────  │  Status: [OPEN ▾]              ││
│  │  🔴 SR-001 Deceased     │                                ││
│  │     Oak Hills Farm      │  DESCRIPTION                   ││
│  │     OPEN                │  Board member John Doe appears ││
│  │  ─────────────────────  │  as signatory on deed dated    ││
│  │  🟡 SR-007 Procurement  │  2021-03-15 but SSA death      ││
│  │     FCA Lending         │  index shows death 2019-08-22. ││
│  │     OPEN                │                                ││
│  │  ─────────────────────  │  EVIDENCE                      ││
│  │  🟢 SR-003 Valuation    │  • deed-2019-04.pdf (pg 3)    ││
│  │     County Audit        │  • death-index-extract.pdf     ││
│  │     REVIEWED            │                                ││
│  │                         │  INVESTIGATOR NOTE             ││
│  │  ↑↓ j/k to navigate    │  [                           ] ││
│  │  1/2/3 to set status    │  [Save] [Dismiss] [Escalate]  ││
│  └─────────────────────────┴────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

**Key design decisions:**

- **Cross-case by default.** The triage queue shows signals from ALL cases, sorted by severity then date. An investigator processes the hottest signals first regardless of which case they belong to. A case filter narrows it down when needed.

- **Master-detail layout.** Left panel is the scrollable signal list. Right panel shows the selected signal's full detail with triage controls. This is the Splunk ES "Analyst Queue" pattern — purpose-built for burn-down workflows.

- **Keyboard-first.** The existing `j/k/1/2/3` shortcuts stay, but now they're in a view designed around them. No risk of accidentally triggering shortcuts while filling out a case form on the same page.

- **Batch actions** (future): Select multiple signals, dismiss all, or escalate all to a detection.

**Reference:** Splunk SOAR's Analyst Queue, Gmail's inbox (list + reading pane), VS Code's problem panel.

---

### View 5: Referrals (`/referrals`)

**Purpose:** "Track all government referrals across all cases."

Right now, referrals are per-case tabs. But a supervisor tracking referral status across the entire portfolio needs a cross-case view.

```
┌──────────────────────────────────────────────────────────────┐
│  REFERRALS                                    [+ New Referral]│
│                                                               │
│  Filters: [Agency ▾] [Status ▾] [Case ▾]                     │
│                                                               │
│  ┌───────────┬────────────────┬──────────┬─────────┬────────┐│
│  │ Agency    │ Case           │ Status   │ Filed   │ Actions││
│  ├───────────┼────────────────┼──────────┼─────────┼────────┤│
│  │ Ohio AG   │ Oak Hills Farm │SUBMITTED │ 2/15/26 │ [View] ││
│  │ IRS       │ Oak Hills Farm │ DRAFT    │ —       │ [Edit] ││
│  │ FBI       │ Shell Corp Net │SUBMITTED │ 3/01/26 │ [View] ││
│  │ FCA OIG   │ FCA Lending    │ACKNOWLEDGED│1/20/26│ [View] ││
│  │ Ohio AG   │ County Audit   │ CLOSED   │11/10/25 │ [View] ││
│  └───────────┴────────────────┴──────────┴─────────┴────────┘│
│                                                               │
│  Status Summary:  2 DRAFT  |  2 SUBMITTED  |  1 ACKNOWLEDGED  │
│                   1 CLOSED                                    │
└──────────────────────────────────────────────────────────────┘
```

**Reference:** Jira's cross-project filter views.

---

## Routing Plan

Using React Router v6:

```
/                           → Dashboard
/cases                      → Cases list
/cases/:caseId              → Case detail (default: documents tab)
/cases/:caseId/documents    → Case detail → documents tab
/cases/:caseId/signals      → Case detail → signals tab
/cases/:caseId/detections   → Case detail → detections tab
/cases/:caseId/referrals    → Case detail → referrals tab
/cases/:caseId/timeline     → Case detail → timeline tab
/triage                     → Signal triage queue (cross-case)
/referrals                  → Referral tracking (cross-case)
/search                     → Semantic search
/settings                   → App settings (future)
```

Every route is bookmarkable and shareable. You can send a colleague a link to a specific case's signals tab.

---

## State Management Refactor

The current `App.tsx` god component needs to be broken up. Here's the plan:

### Option A: React Context + useReducer (recommended for now)

Create focused contexts that each own a slice of state:

```
src/
├── contexts/
│   ├── CasesContext.tsx      ← case list, filters, selected case
│   ├── SignalsContext.tsx     ← signal queue, triage drafts, active signal
│   ├── DocumentsContext.tsx   ← document list, upload state, OCR state
│   ├── ReferralsContext.tsx   ← referral list, form state
│   ├── DetectionsContext.tsx  ← detection list, edit state
│   ├── ToastContext.tsx       ← notification queue
│   └── AppShellContext.tsx    ← sidebar collapsed state, active route
```

Each context provides both state and actions (like `triageSignal()`, `uploadDocuments()`, etc.). Components consume only the contexts they need.

**Why not Redux/Zustand yet:** The app isn't complex enough to justify a third-party state library. Context + useReducer handles the current scope cleanly. If we hit performance issues with too many re-renders, Zustand is a clean upgrade path.

### Option B: React Query for server state (future consideration)

As noted in your architecture doc, React Query makes sense "if fetch complexity grows enough to justify it." With multiple views now fetching independently, that threshold is approaching. React Query would give us automatic caching, background refetching, and optimistic updates for free. This is a Phase 2 refactor — not needed for the initial view split.

---

## New File Structure

```
frontend/src/
├── main.tsx                    ← entry point (unchanged)
├── App.tsx                     ← SLIM: just router + providers + shell
├── api.ts                      ← HTTP client (unchanged)
├── types.ts                    ← data contracts (unchanged)
├── styles.css                  ← global styles + CSS variables
│
├── layouts/
│   └── AppShell.tsx            ← sidebar + header + outlet
│
├── views/                      ← one file per route
│   ├── DashboardView.tsx       ← /
│   ├── CasesListView.tsx       ← /cases
│   ├── CaseDetailView.tsx      ← /cases/:caseId (with tab routing)
│   ├── TriageView.tsx          ← /triage
│   ├── ReferralsView.tsx       ← /referrals
│   └── SearchView.tsx          ← /search
│
├── components/                 ← reusable pieces within views
│   ├── cases/
│   │   ├── CaseTable.tsx
│   │   ├── CaseCard.tsx
│   │   └── CaseCreateForm.tsx
│   ├── signals/
│   │   ├── SignalList.tsx
│   │   ├── SignalDetail.tsx
│   │   └── SignalTriageControls.tsx
│   ├── documents/
│   │   ├── DocumentTable.tsx
│   │   ├── DocumentUpload.tsx
│   │   └── OcrStatusBadge.tsx
│   ├── detections/
│   │   ├── DetectionCard.tsx
│   │   └── DetectionControls.tsx
│   ├── referrals/
│   │   ├── ReferralTable.tsx
│   │   ├── ReferralForm.tsx
│   │   └── ReferralMemoButton.tsx
│   ├── dashboard/
│   │   ├── KpiCards.tsx
│   │   ├── RecentActivity.tsx
│   │   └── SignalHeatmap.tsx
│   └── ui/                     ← shared primitives (existing)
│       ├── Button.tsx
│       ├── FormInput.tsx
│       ├── FormSelect.tsx
│       ├── FormTextarea.tsx
│       ├── StateBlock.tsx
│       ├── EmptyState.tsx
│       ├── ToastStack.tsx
│       ├── DataTable.tsx       ← NEW: reusable sortable/filterable table
│       ├── CommandPalette.tsx   ← NEW: Cmd+K search overlay
│       └── Sidebar.tsx         ← NEW: collapsible nav sidebar
│
├── contexts/                   ← state management
│   ├── CasesContext.tsx
│   ├── SignalsContext.tsx
│   ├── DocumentsContext.tsx
│   ├── ReferralsContext.tsx
│   ├── DetectionsContext.tsx
│   └── ToastContext.tsx
│
├── hooks/                      ← custom hooks
│   ├── useKeyboardShortcuts.ts ← extracted from App.tsx
│   ├── useCaseFilters.ts       ← filter/sort logic
│   └── useSignalTriage.ts      ← triage draft management
│
└── utils/                      ← helpers (existing)
    ├── format.ts
    └── queryParams.ts
```

---

## Implementation Phases

### Phase A: Router + Shell (1-2 sessions)
- Install React Router v6
- Create `AppShell.tsx` with sidebar navigation
- Create route definitions
- Move existing views into route-based files (minimal refactor — just reorganize, don't rewrite)
- The app should look and work roughly the same, just with navigation and URLs

### Phase B: View Separation (2-3 sessions)
- Break `CaseDetailPanel.tsx` into separate tab components
- Create `CasesListView` as a full-width table (not sidebar)
- Create `TriageView` with master-detail layout
- Create `ReferralsView` with cross-case table
- Each view fetches its own data independently

### Phase C: State Refactor (1-2 sessions)
- Extract state from `App.tsx` into context providers
- Create custom hooks for keyboard shortcuts, triage workflow
- `App.tsx` becomes slim: just `<Providers>` → `<Router>` → `<AppShell>`

### Phase D: Dashboard + Polish (1-2 sessions)
- Build the real dashboard with activity feed and charts
- Add Command Palette (Cmd+K)
- Add Timeline tab to case detail
- Visual polish pass

---

## What We Are NOT Doing (Scope Control)

- **No component library migration.** We keep the existing CSS + custom components. No Tailwind/MUI/Chakra migration.
- **No auth/RBAC.** Role-based views are a *layout* concern for now, not an auth concern.
- **No SSR/Next.js.** Vite + React SPA is the right choice for this app.
- **No GraphQL.** The REST API is clean and sufficient.
- **No mobile-first redesign.** This is a desktop investigation tool. Responsive is nice; mobile-first is not the priority.

---

## Summary of the Big Shifts

| Today | Proposed |
|-------|----------|
| One page, everything visible | Multiple purpose-built views |
| No routing, no URLs | Every view is bookmarkable |
| Case list in a cramped sidebar | Full-width case table view |
| Signal triage buried in a tab | Dedicated cross-case triage queue |
| Referrals only per-case | Cross-case referral dashboard |
| 749-line god component | Slim App + context providers |
| No navigation | Persistent sidebar with icons |
| No command palette | Cmd+K for power users |
| No timeline/audit view | Timeline tab on case detail |

---

## Questions for Discussion

1. **Sidebar: always expanded or collapsed by default?** Linear collapses to icons. Palantir stays expanded. Given this is an investigation tool with limited nav items, I'd suggest expanded by default with a toggle.

2. **Triage queue: cross-case default or per-case default?** I proposed cross-case (all signals, filter by case). But if investigators always work one case at a time, per-case default with a "show all" toggle might be better.

3. **Board view for cases: priority?** A kanban-style board (OPEN → REFERRED → CLOSED columns) is useful for supervisors but not critical for investigators. Defer to Phase D?

4. **Dark theme only or light theme option?** The current dark theme is great for focused investigation work. But some agencies may require light themes for accessibility compliance.
