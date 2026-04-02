# Catalyst Frontend — Detailed Design Specification

**Date:** 2026-03-31
**Status:** Draft — for implementation planning
**Decisions locked:** Always-expanded sidebar, cross-case triage, Kanban view, dark-primary + light toggle, persistent AI search bar

---

## Table of Contents

1. Global Shell (Sidebar + Header + AI Search)
2. Dashboard View
3. Cases View (Table + Kanban)
4. Case Detail View (5 tabs)
5. Signal Triage Queue View
6. Referrals View
7. Search View
8. Settings View
9. Keyboard Shortcuts (Global)
10. API Additions Needed
11. Component Inventory

---

## 1. Global Shell

The shell wraps every view. It consists of three persistent elements: the sidebar, the top header bar, and the AI search bar.

### 1.1 Sidebar (Always Expanded)

```
┌──────────────────┐
│  ◆ CATALYST       │
│                    │
│  ▦  Dashboard      │
│  📁 Cases          │
│  ⚡ Triage         │
│  📤 Referrals      │
│  🔍 Search         │
│                    │
│  ─── ─── ─── ───  │  ← visual divider
│                    │
│  ⚙  Settings       │
│                    │
│                    │
│                    │
│  ┌──────────────┐ │
│  │  TC           │ │  ← user avatar/initials at bottom
│  │  Investigator │ │
│  └──────────────┘ │
└──────────────────┘
```

**Specifications:**

- Width: 240px fixed
- Background: `var(--bg-surface)` (one shade lighter than `--bg-ink`)
- Active route item: left accent border (4px, `var(--accent)`) + highlighted background
- Hover state: subtle background shift
- Icons: simple line icons (Lucide icon set, already available in the React ecosystem)
- The sidebar does NOT collapse. It is always expanded as decided. This keeps orientation clear for investigators who may not be power users.
- Bottom of sidebar: user initials badge + role label. For now hardcoded ("TC / Investigator"). Future: pulled from auth context.
- Settings is separated from the main nav by a divider — it's a utility, not a workflow destination.

**Badge counts on sidebar items:**

| Item | Badge | Source |
|------|-------|--------|
| Triage | Open signal count (e.g., "12") | `/api/signal-summary/` aggregated |
| Referrals | DRAFT count (e.g., "2") | Aggregated from referrals fetch |

Badges appear as small colored pills next to the label. Red for triage (these need attention), blue for referrals (drafts in progress).

---

### 1.2 Top Header Bar

```
┌─────────────────────────────────────────────────────────────────────┐
│  [AI Search: "Ask anything about your cases..."                   ] │
│                                                                     │
│  Breadcrumb: Dashboard  >  Cases  >  Oak Hills Farm  >  Documents   │
└─────────────────────────────────────────────────────────────────────┘
```

The header has two rows:

**Row 1: AI Search Bar** (persistent, always visible)
**Row 2: Breadcrumb trail** (contextual, shows current navigation path)

---

### 1.3 Persistent AI Search Bar

This is the natural-language search field that stays at the top of every view. It's the "if an idea pops up, just ask" feature.

**Behavior:**

```
┌─────────────────────────────────────────────────────────┐
│  🔍  Ask anything about your cases...          Cmd+K    │
└─────────────────────────────────────────────────────────┘
```

- **Resting state:** Single-line input with placeholder text and `Cmd+K` hint
- **Focus state:** Expands into a dropdown overlay panel below the search bar
- **While typing:** Shows real-time suggestions categorized into groups:

```
┌─────────────────────────────────────────────────────────┐
│  🔍  "who signed the oak hills deed"           Cmd+K    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  CASES                                                  │
│    📁 Oak Hills Farm Investigation                      │
│                                                         │
│  DOCUMENTS                                              │
│    📄 deed-2019-04.pdf (Oak Hills Farm)                 │
│    📄 deed-amendment-2020.pdf (Oak Hills Farm)          │
│                                                         │
│  SIGNALS                                                │
│    ⚡ SR-001: Deceased signer on deed (Oak Hills Farm)  │
│                                                         │
│  ─── ─── ─── ───                                       │
│  Press Enter for full semantic search →                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Two modes of operation:**

1. **Quick-jump mode** (as you type): Fuzzy-matches against case names, document filenames, signal titles, person/org names. Clicking a result navigates directly to it (e.g., clicking a case goes to `/cases/:id`, clicking a signal goes to `/triage?signal=:id`).

2. **Full semantic search** (press Enter): Navigates to `/search?q=...` and runs the backend semantic search endpoint. Shows ranked results with relevance scores, highlighted snippets, and source attribution.

**Technical approach:**
- Quick-jump is frontend-only: filter against cached case/document/signal lists already loaded by the app
- Full semantic search hits the existing `/api/cases/:id/semantic-search/` endpoint (or a new cross-case variant)
- Debounced input (300ms) for quick-jump suggestions
- `Cmd+K` / `Ctrl+K` global shortcut focuses the search bar from anywhere
- `Escape` closes the dropdown and blurs the input

---

### 1.4 Breadcrumb Bar

Shows the user's current location in the navigation hierarchy. Helps answer "where am I" at a glance.

**Examples by route:**

| Route | Breadcrumb |
|-------|-----------|
| `/` | Dashboard |
| `/cases` | Cases |
| `/cases/:id` | Cases > Oak Hills Farm |
| `/cases/:id/signals` | Cases > Oak Hills Farm > Signals |
| `/triage` | Signal Triage |
| `/referrals` | Referrals |
| `/search?q=deed` | Search > "deed" |
| `/settings` | Settings |

Each breadcrumb segment is clickable and navigates to that level.

---

## 2. Dashboard View (`/`)

**Purpose:** Operational overview — "What needs my attention?"

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐│
│  │ Total Cases│ │ Open Cases │ │  Open      │ │  Draft     ││
│  │     18     │ │     12     │ │  Signals   │ │  Referrals ││
│  │            │ │            │ │     47     │ │      5     ││
│  │ [click →]  │ │ [click →]  │ │ [click →]  │ │ [click →]  ││
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘│
│                                                              │
│  ┌────────────────────────────┐  ┌──────────────────────────┐│
│  │  RECENT ACTIVITY           │  │  SIGNALS BY SEVERITY     ││
│  │                            │  │                          ││
│  │  ● Case "Shell Corp" creat│  │  CRITICAL  ████████  8   ││
│  │    ed — 2h ago             │  │  HIGH      ██████    6   ││
│  │  ● 3 signals fired on     │  │  MEDIUM    ████████████ 19││
│  │    "Oak Hills" — 3h ago   │  │  LOW       ██████████  14 ││
│  │  ● Referral to Ohio AG    │  │                          ││
│  │    submitted — 1d ago     │  │                          ││
│  │  ● OCR completed: 12 docs │  │                          ││
│  │    on "FCA" — 1d ago      │  │                          ││
│  │  ● Signal SR-005 reviewed │  │                          ││
│  │    on "Oak Hills" — 2d ago│  │                          ││
│  │                            │  │                          ││
│  │  [View all activity →]     │  │                          ││
│  └────────────────────────────┘  └──────────────────────────┘│
│                                                              │
│  ┌────────────────────────────┐  ┌──────────────────────────┐│
│  │  TOP OPEN SIGNALS          │  │  CASES NEEDING ATTENTION ││
│  │                            │  │                          ││
│  │  🔴 SR-005 Self-dealing    │  │  🔴 Shell Corp Network   ││
│  │     Oak Hills — CRITICAL   │  │     19 open signals      ││
│  │  🔴 SR-001 Deceased signer │  │  🔴 Oak Hills Farm       ││
│  │     Oak Hills — CRITICAL   │  │     12 open signals      ││
│  │  🟡 SR-007 Procurement     │  │  🟡 FCA Lending          ││
│  │     FCA — HIGH             │  │     8 open signals       ││
│  │  🟡 SR-003 Valuation       │  │                          ││
│  │     County Audit — HIGH    │  │                          ││
│  │                            │  │                          ││
│  │  [Go to Triage →]          │  │  [View all cases →]      ││
│  └────────────────────────────┘  └──────────────────────────┘│
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Dashboard widgets (6 total):**

| Widget | Content | Click action |
|--------|---------|-------------|
| KPI: Total Cases | Count from `/api/cases/` | Navigate to `/cases` |
| KPI: Open Cases | Count filtered by status=OPEN | Navigate to `/cases?status=OPEN` |
| KPI: Open Signals | Sum of open_count from signal summary | Navigate to `/triage` |
| KPI: Draft Referrals | Count of DRAFT referrals | Navigate to `/referrals?status=DRAFT` |
| Recent Activity | Last 10 audit log entries (cross-case) | Each item links to source |
| Signals by Severity | Horizontal bar chart, grouped by severity | Click bar → `/triage?severity=X` |
| Top Open Signals | Top 5 by severity, then recency | Click → navigate to signal in triage |
| Cases Needing Attention | Cases ranked by open signal count | Click → navigate to case detail |

**API needed:** A new `GET /api/activity-feed/` endpoint that returns the last N audit log entries across all cases, formatted for display. Alternatively, we aggregate from existing endpoints on the frontend.

---

## 3. Cases View (`/cases`)

This view has two display modes toggled by the user: **Table** and **Board** (Kanban).

### 3.1 Cases — Table Mode (default)

```
┌──────────────────────────────────────────────────────────────┐
│  CASES                                      [+ New Case]     │
│                                                              │
│  View: [▐Table] [Board]                                     │
│                                                              │
│  Filters: [Status ▾] [Severity ▾] [Search...         ]      │
│  Sort: [Last Updated ▾]                                      │
│                                                              │
│  ┌──┬─────────────────┬────────┬──────┬──────┬──────┬──────┐│
│  │  │ Case Name       │ Status │ Sigs │ Docs │ Refs │ Updated│
│  ├──┼─────────────────┼────────┼──────┼──────┼──────┼──────┤│
│  │🔴│ Shell Corp Net  │ OPEN   │19(7🔴)│  89 │  1  │ 3h    ││
│  │🔴│ Oak Hills Farm  │ OPEN   │12(3🔴)│  47 │  2  │ 2h    ││
│  │🟡│ FCA Lending     │ OPEN   │ 8(1🔴)│  23 │  1  │ 1d    ││
│  │🟢│ County Audit    │ CLOSED │ 2(0🔴)│  15 │  1  │ 5d    ││
│  │⚪│ New Intake #5   │ OPEN   │ 0    │   0 │  0  │ 1h    ││
│  └──┴─────────────────┴────────┴──────┴──────┴──────┴──────┘│
│                                                              │
│  Showing 5 of 18 cases         [< Prev]  Page 1  [Next >]   │
└──────────────────────────────────────────────────────────────┘
```

**Table columns:**

| Column | Source | Notes |
|--------|--------|-------|
| Severity dot | Signal summary → highest severity | Color: red/amber/green/gray |
| Case Name | `case.name` | Clickable → `/cases/:id` |
| Status | `case.status` | Pill badge (OPEN/REFERRED/CLOSED) |
| Signals | Signal summary → `open_count` (total) | Shows open/critical breakdown |
| Documents | `case.documents.length` | Count |
| Referrals | Referral count for case | Count |
| Updated | `case.updated_at` | Relative time ("3h ago") |

**Click behavior:** Clicking any row navigates to `/cases/:caseId`.

**"+ New Case" button:** Opens a modal dialog (not a separate page) with the case creation form:

```
┌──────────────────────────────────────────┐
│  CREATE NEW CASE                    [✕]  │
│                                          │
│  Case Name *                             │
│  ┌──────────────────────────────────┐    │
│  │                                  │    │
│  └──────────────────────────────────┘    │
│                                          │
│  Referral Reference                      │
│  ┌──────────────────────────────────┐    │
│  │                                  │    │
│  └──────────────────────────────────┘    │
│                                          │
│  Notes                                   │
│  ┌──────────────────────────────────┐    │
│  │                                  │    │
│  │                                  │    │
│  └──────────────────────────────────┘    │
│                                          │
│             [Cancel]  [Create Case]      │
└──────────────────────────────────────────┘
```

---

### 3.2 Cases — Board Mode (Kanban)

```
┌──────────────────────────────────────────────────────────────┐
│  CASES                                      [+ New Case]     │
│                                                              │
│  View: [Table] [▐Board]                                     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ OPEN (12)    │  │ REFERRED (4) │  │ CLOSED (2)   │       │
│  │              │  │              │  │              │       │
│  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │       │
│  │ │Shell Corp│ │  │ │Oak Hills │ │  │ │County    │ │       │
│  │ │🔴 19 sigs│ │  │ │🔴 12 sigs│ │  │ │Audit     │ │       │
│  │ │89 docs   │ │  │ │47 docs   │ │  │ │🟢 2 sigs │ │       │
│  │ │3h ago    │ │  │ │AG+IRS    │ │  │ │15 docs   │ │       │
│  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │       │
│  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │       │
│  │ │FCA       │ │  │ │ ...      │ │  │ │ ...      │ │       │
│  │ │Lending   │ │  │ │          │ │  │ │          │ │       │
│  │ │🟡 8 sigs │ │  │ │          │ │  │ │          │ │       │
│  │ │23 docs   │ │  │ │          │ │  │ │          │ │       │
│  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │       │
│  │ ...          │  │              │  │              │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└──────────────────────────────────────────────────────────────┘
```

**Kanban columns** correspond to case statuses. The current model has a free-text `status` field, so we'll need to standardize the status values:

| Column | Status Value | Color |
|--------|-------------|-------|
| Open | `OPEN` | Blue header bar |
| Referred | `REFERRED` | Amber header bar |
| Closed | `CLOSED` | Green header bar |

**Card content:**
- Case name (bold, clickable → `/cases/:id`)
- Severity dot + open signal count
- Document count
- Referral agencies (abbreviated, e.g., "AG+IRS")
- Relative time since last update

**Drag-and-drop** (Phase D enhancement): Dragging a card between columns updates the case status via `PATCH /api/cases/:id/`. Confirm before moving to CLOSED (destructive-ish action).

**Sorting within columns:** Cards sorted by highest signal severity first, then by most recently updated. This naturally puts "hottest" cases at the top.

---

## 4. Case Detail View (`/cases/:caseId`)

This is the deep-dive view for a single case. It has a case header and five tabs.

### 4.1 Case Header (always visible within case detail)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ← Back to Cases                                             │
│                                                              │
│  OAK HILLS FARM INVESTIGATION                  Status: [OPEN ▾]
│                                                              │
│  Created: Jan 15, 2026  |  Ref: OAG-2026-0042               │
│  47 documents  |  12 signals  |  3 detections  |  2 referrals│
│                                                              │
│  Notes: Land conservation fraud pattern involving...    [Edit]│
│                                                              │
│  ┌──────────┬──────────┬────────────┬──────────┬──────────┐  │
│  │▐Documents│ Signals  │ Detections │ Referrals│ Timeline │  │
│  └──────────┴──────────┴────────────┴──────────┴──────────┘  │
│                                                              │
│  [Tab content renders below]                                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Header elements:**
- **Back link:** "← Back to Cases" navigates to `/cases` (preserves filter state)
- **Case name:** Large heading
- **Status dropdown:** Inline editable. Changes fire `PATCH /api/cases/:id/` immediately
- **Metadata row:** Created date, referral reference
- **Stats row:** Document/signal/detection/referral counts (live, not cached)
- **Notes:** Truncated with [Edit] button that opens inline editing (textarea + save/cancel)
- **Tab bar:** Five tabs, each one a nested route

---

### 4.2 Tab: Documents (`/cases/:caseId/documents`)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  DOCUMENTS (35/47)           [Upload Files] [Process OCR (4)]│
│                                                              │
│  Filters: [Type ▾] [OCR Status ▾] [Search filenames...]     │
│                                                              │
│  ┌──────────────────┬──────────┬──────────┬──────┬─────────┐│
│  │ Filename         │ Type     │ OCR      │ Size │ Uploaded ││
│  ├──────────────────┼──────────┼──────────┼──────┼─────────┤│
│  │ deed-2019-04.pdf │ DEED     │ ✅ Done  │ 2.1M │ Jan 20  ││
│  │ 990-2020.pdf     │ TAX_FORM │ ✅ Done  │ 4.8M │ Jan 20  ││
│  │ board-minutes.pdf│ MINUTES  │ ⏳ Pend. │ 1.2M │ Jan 22  ││
│  │ loan-docs.pdf    │ CONTRACT │ ✅ Done  │ 890K │ Jan 25  ││
│  │ scan-batch-3.pdf │ OTHER    │ ❌ Error │ 31M  │ Feb 1   ││
│  └──────────────────┴──────────┴──────────┴──────┴─────────┤│
│                                                     [Delete] │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │                                                          ││
│  │     Drag and drop files here to upload                   ││
│  │     or click [Upload Files]                              ││
│  │                                                          ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  ACTIONS                                                 ││
│  │  [Generate Referral Memo]  [Re-evaluate Signals]         ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**OCR status icons:**
- ✅ `COMPLETE` — green checkmark
- ⏳ `PENDING` — amber clock
- ❌ `ERROR` — red X
- ⬜ `NOT_NEEDED` — gray dash

**Row selection:** Clicking a row selects it (highlights). Selected row shows a [Delete] action. Future: multi-select with checkboxes for batch delete.

**Upload area:** Persistent drop zone below the table. Also accessible via the [Upload Files] button in the toolbar.

**Actions bar:** "Generate Referral Memo" and "Re-evaluate Signals" live at the bottom. These are case-level actions that affect documents/signals, so they live in the Documents tab since that's where the investigator is adding evidence.

---

### 4.3 Tab: Signals (`/cases/:caseId/signals`)

This is the **per-case** signal view. It shows only signals for this case. (The cross-case triage queue is `/triage`.)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  SIGNALS (8/12)                    [Go to Cross-Case Triage →]│
│                                                              │
│  Filters: [Severity ▾] [Status ▾]                            │
│                                                              │
│  ┌─────────────────────────┬────────────────────────────────┐│
│  │  LIST                   │  DETAIL                        ││
│  │                         │                                ││
│  │  🔴 SR-005 Self-dealing │  SR-005: SELF-DEALING          ││
│  │     CRITICAL — OPEN     │  Rule: SR-005                  ││
│  │  ─────────────────────  │  Severity: CRITICAL            ││
│  │  🔴 SR-001 Deceased     │  Detected: Jan 20, 2026       ││
│  │     CRITICAL — OPEN     │                                ││
│  │  ─────────────────────  │  DESCRIPTION                   ││
│  │  🟡 SR-007 Procurement  │  Board member listed as both   ││
│  │     HIGH — OPEN         │  grantor and grantee on...     ││
│  │  ─────────────────────  │                                ││
│  │  🟡 SR-003 Valuation    │  DETECTED SUMMARY              ││
│  │     HIGH — REVIEWED     │  Entity "John Doe" appears in  ││
│  │  ─────────────────────  │  deed-2019-04.pdf as grantor   ││
│  │  🟢 SR-009 Revenue      │  and in board-roster.pdf as... ││
│  │     MEDIUM — DISMISSED  │                                ││
│  │                         │  ──────────────────────────     ││
│  │                         │  TRIAGE                        ││
│  │                         │  Status: [OPEN        ▾]       ││
│  │  j/k ↑↓  1/2/3 status  │  Note: [                     ] ││
│  │                         │        [                     ] ││
│  │                         │  [Save Triage]                 ││
│  └─────────────────────────┴────────────────────────────────┘│
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Master-detail layout:** Same pattern as the cross-case triage queue, but scoped to this case. The "[Go to Cross-Case Triage →]" link navigates to `/triage?case=:caseId` which prefilters the triage queue.

**Signal list item content:**
- Severity dot (color)
- Signal title
- Rule ID
- Severity label + status label
- Background tint: subtle row coloring by severity (red tint for CRITICAL, amber for HIGH, etc.)

**Signal detail panel:**
- Full signal info: rule_id, title, description, detected_summary
- Trigger entity and document links (clickable, navigate to the relevant document or entity)
- Detected timestamp
- Triage controls: status dropdown + note textarea + save button
- Quick-status buttons: OPEN | REVIEWED | DISMISSED as clickable chips

---

### 4.4 Tab: Detections (`/cases/:caseId/detections`)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  DETECTIONS (3)                                              │
│                                                              │
│  Filters: [Severity ▾] [Status ▾] [Method ▾]                │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  🔴 CRITICAL — OPEN                     Conf: 0.92      ││
│  │  Signal Type: SR-005                                     ││
│  │  Method: rule_based                                      ││
│  │  Detected: Jan 20, 2026                                  ││
│  │                                                          ││
│  │  Evidence Snapshot:                                       ││
│  │  ┌────────────────────────────────────────────────────┐  ││
│  │  │ { "grantor": "John Doe", "grantee": "Oak Hills    │  ││
│  │  │   Conservancy", "consideration": 0.00,             │  ││
│  │  │   "document": "deed-2019-04.pdf" }                 │  ││
│  │  └────────────────────────────────────────────────────┘  ││
│  │                                                          ││
│  │  Status: [OPEN ▾]  Note: [                        ]      ││
│  │  [Save]                                    [Delete]      ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  🟡 HIGH — REVIEWED                     Conf: 0.85      ││
│  │  Signal Type: SR-001                                     ││
│  │  ...                                                     ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Detection cards** are stacked vertically (not master-detail). Each card shows:
- Severity + status as header badges
- Confidence score as a percentage bar or numeric display
- Signal type and detection method
- Evidence snapshot as a formatted JSON block (collapsible if large)
- Linked document/person/org/property IDs as clickable chips
- Inline status dropdown + note field + save/delete buttons

**Status progression:** OPEN → REVIEWED → CONFIRMED / DISMISSED / ESCALATED. The dropdown shows all five options.

---

### 4.5 Tab: Referrals (`/cases/:caseId/referrals`)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  REFERRALS (2)                             [+ New Referral]  │
│                                        [Generate Memo]       │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  OHIO ATTORNEY GENERAL                                   ││
│  │  Status: [SUBMITTED ▾]                                   ││
│  │  Submission ID: OAG-2026-0042                            ││
│  │  Contact: J. Smith (AG Charitable Law)                   ││
│  │  Filed: Feb 15, 2026                                     ││
│  │  Notes: Initial filing with supporting documentation     ││
│  │         for conservation easement fraud pattern.          ││
│  │                                                          ││
│  │  [Edit]  [Delete]                                        ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  IRS EXEMPT ORGANIZATIONS                                ││
│  │  Status: [DRAFT ▾]                                       ││
│  │  Submission ID: —                                        ││
│  │  Contact: —                                              ││
│  │  Filed: —                                                ││
│  │  Notes: Preparing Form 13909 for tax-exempt status...    ││
│  │                                                          ││
│  │  [Edit]  [Delete]                                        ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  STATUS PIPELINE                                             │
│  DRAFT ──→ SUBMITTED ──→ ACKNOWLEDGED ──→ CLOSED            │
│    (1)        (1)            (0)           (0)               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Referral cards:** Each referral is a card with inline-editable fields. Status is a dropdown (DRAFT → SUBMITTED → ACKNOWLEDGED → CLOSED). [Edit] toggles the card into edit mode for all fields.

**Status pipeline visualization:** A horizontal flow diagram at the bottom showing the referral lifecycle with counts in each stage. This gives investigators a quick sense of progress.

**"+ New Referral" modal:** Same pattern as New Case — a modal form with agency name, submission ID, contact alias, and notes.

---

### 4.6 Tab: Timeline (`/cases/:caseId/timeline`)

**This is a new feature.** It renders the audit trail as a chronological narrative.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  TIMELINE                         Filter: [All Events ▾]    │
│                                                              │
│  ┌─ Mar 1, 2026 ──────────────────────────────────────────  │
│  │                                                           │
│  │  ● 3:42 PM — Signal SR-005 status changed to REVIEWED    │
│  │    by investigator. Note: "Confirmed self-dealing         │
│  │    pattern, preparing referral."                          │
│  │                                                           │
│  │  ● 2:15 PM — 3 new signals detected                      │
│  │    SR-005 (CRITICAL), SR-003 (HIGH), SR-009 (MEDIUM)     │
│  │                                                           │
│  │  ● 1:30 PM — OCR completed on 5 documents                │
│  │    board-minutes.pdf, loan-docs.pdf, ...                  │
│  │                                                           │
│  ├─ Feb 28, 2026 ─────────────────────────────────────────  │
│  │                                                           │
│  │  ● 4:00 PM — 12 documents uploaded                        │
│  │    deed-2019-04.pdf, 990-2020.pdf, ...                    │
│  │                                                           │
│  │  ● 3:45 PM — Referral to Ohio AG created (DRAFT)         │
│  │    Agency: Ohio Attorney General                          │
│  │                                                           │
│  ├─ Jan 15, 2026 ─────────────────────────────────────────  │
│  │                                                           │
│  │  ● 10:00 AM — Case created                                │
│  │    "Oak Hills Farm Investigation"                         │
│  │                                                           │
│  └───────────────────────────────────────────────────────────│
│                                                              │
│  [Load earlier events...]                                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Event types to display:**
- Case created/updated
- Document uploaded/deleted
- OCR completed/failed
- Signals detected
- Signal triage actions (status change + note)
- Detection created/updated
- Referral created/submitted/acknowledged/closed
- Memo generated

**Data source:** The existing `AuditLog` model, filtered by case. Each entry already has `action`, `table_name`, `record_id`, `changed_fields`, `performed_at`, and `performed_by`. We just need a frontend that renders these as human-readable sentences.

**Filter dropdown:** Filter by event type (Documents, Signals, Referrals, All).

**API needed:** `GET /api/cases/:id/timeline/` — returns audit log entries for this case, ordered by `performed_at DESC`, paginated.

---

## 5. Signal Triage Queue View (`/triage`)

This is the dedicated cross-case triage view. It was already wireframed in the first proposal. Here's the complete specification:

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  SIGNAL TRIAGE                                               │
│                                                              │
│  Queue: 47 total │ 12 OPEN │ 28 REVIEWED │ 7 DISMISSED      │
│                                                              │
│  Filters: [Severity ▾] [Status ▾] [Case ▾] [Rule ▾]        │
│  Sort: [Severity ▾] then [Newest ▾]                          │
│                                                              │
│  ┌─────────────────────────┬────────────────────────────────┐│
│  │  QUEUE                  │  DETAIL                        ││
│  │  (scrollable list)      │  (selected signal)             ││
│  │                         │                                ││
│  │  🔴 SR-005 Self-dealing │  ┌──────────────────────────┐  ││
│  │     Oak Hills Farm      │  │ SR-005: SELF-DEALING     │  ││
│  │     CRITICAL — OPEN     │  │ Case: Oak Hills Farm     │  ││
│  │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │  │ Rule: SR-005             │  ││
│  │  🔴 SR-001 Deceased     │  │ Severity: CRITICAL       │  ││
│  │     Oak Hills Farm      │  │ Detected: Jan 20, 2026   │  ││
│  │     CRITICAL — OPEN     │  │                          │  ││
│  │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │  │ DESCRIPTION              │  ││
│  │  🟡 SR-007 Procurement  │  │ Board member "John Doe"  │  ││
│  │     FCA Lending         │  │ appears as both grantor  │  ││
│  │     HIGH — OPEN         │  │ and grantee on deed...   │  ││
│  │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │  │                          │  ││
│  │  🟡 SR-003 Valuation    │  │ EVIDENCE LINKS           │  ││
│  │     County Audit        │  │ 📄 deed-2019-04.pdf      │  ││
│  │     HIGH — REVIEWED     │  │ 👤 John Doe (Person)     │  ││
│  │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │  │                          │  ││
│  │  🟢 SR-010 Phantom      │  │ DETECTED SUMMARY         │  ││
│  │     Shell Corp Net      │  │ Entity "John Doe" found  │  ││
│  │     MEDIUM — OPEN       │  │ in deed as grantor and   │  ││
│  │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │  │ in board roster as...   │  ││
│  │  🟢 SR-009 Revenue      │  │                          │  ││
│  │     Oak Hills Farm      │  │ ──────────────────────── │  ││
│  │     MEDIUM — DISMISSED  │  │ TRIAGE                   │  ││
│  │                         │  │                          │  ││
│  │                         │  │ Status:                  │  ││
│  │                         │  │ [OPEN] [REVIEWED] [DISM] │  ││
│  │                         │  │                          │  ││
│  │                         │  │ Investigator Note:       │  ││
│  │                         │  │ ┌──────────────────────┐ │  ││
│  │                         │  │ │                      │ │  ││
│  │                         │  │ │                      │ │  ││
│  │                         │  │ └──────────────────────┘ │  ││
│  │                         │  │                          │  ││
│  │                         │  │ [Save]  [→ View Case]    │  ││
│  │  ─────────────────────  │  └──────────────────────────┘  ││
│  │  j/k navigate           │                                ││
│  │  1 OPEN  2 REV  3 DISM  │                                ││
│  └─────────────────────────┴────────────────────────────────┘│
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Key behaviors:**

- **Cross-case by default:** Shows signals from ALL cases. The Case filter dropdown lets you narrow to one case.
- **URL integration:** `/triage?case=abc&severity=CRITICAL&status=OPEN` — all filters reflected in URL, bookmarkable
- **Queue counter bar:** Shows total and breakdown by status, updates live as you triage
- **"→ View Case" button:** Navigates to the full case detail for the signal's parent case
- **Evidence links:** Clickable links to the trigger document and entity. Document link goes to `/cases/:caseId/documents` with the doc highlighted. Entity links are future (entity detail view).
- **After saving a triage:** The list automatically advances to the next signal (like email — after archiving, show the next message)
- **List panel width:** 320px. Detail panel takes remaining space.

**API needed:** A new `GET /api/signals/` endpoint (not scoped to a case) that returns signals across all cases, with filters for severity, status, case_id, and rule_id. Paginated. This doesn't exist yet — current API only supports per-case signal fetch.

---

## 6. Referrals View (`/referrals`)

Cross-case referral tracking. Already wireframed in the first proposal, here's the detailed spec:

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  REFERRALS                                   [+ New Referral]│
│                                                              │
│  Filters: [Agency ▾] [Status ▾] [Case ▾]                    │
│                                                              │
│  PIPELINE SUMMARY                                            │
│  DRAFT(2) ──→ SUBMITTED(2) ──→ ACKNOWLEDGED(1) ──→ CLOSED(1)│
│                                                              │
│  ┌───────────┬────────────────┬──────────────┬───────┬──────┐│
│  │ Agency    │ Case           │ Status       │ Filed │      ││
│  ├───────────┼────────────────┼──────────────┼───────┼──────┤│
│  │ Ohio AG   │ Oak Hills Farm │ ● SUBMITTED  │ 2/15  │[View]││
│  │ IRS       │ Oak Hills Farm │ ○ DRAFT      │ —     │[Edit]││
│  │ FBI       │ Shell Corp Net │ ● SUBMITTED  │ 3/01  │[View]││
│  │ FCA OIG   │ FCA Lending    │ ● ACKNOWLEDGED│1/20  │[View]││
│  │ Ohio AG   │ County Audit   │ ✓ CLOSED     │11/10  │[View]││
│  │ IRS       │ Shell Corp Net │ ○ DRAFT      │ —     │[Edit]││
│  └───────────┴────────────────┴──────────────┴───────┴──────┘│
│                                                              │
│  Showing 6 referrals                                         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Status indicators:**
- ○ DRAFT — hollow circle
- ● SUBMITTED — filled blue
- ● ACKNOWLEDGED — filled amber
- ✓ CLOSED — checkmark green

**Click behavior:** [View] opens a detail panel (slide-over from the right) with full referral info. [Edit] opens the same panel in edit mode.

**Case column:** Clickable — navigates to `/cases/:caseId/referrals`.

**"+ New Referral":** Requires selecting a case first (case dropdown in the modal form).

**API needed:** A new `GET /api/referrals/` endpoint (cross-case) that returns all referrals with their parent case info. Currently referrals are only fetchable per-case.

---

## 7. Search View (`/search`)

Full semantic search results page. Reached by pressing Enter in the AI search bar.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  SEARCH RESULTS for "who signed the oak hills deed"          │
│                                                              │
│  47 results across 3 cases (0.8s)                            │
│                                                              │
│  Filter: [All Types ▾] [Case ▾]                              │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  📄 DOCUMENT — deed-2019-04.pdf                          ││
│  │  Case: Oak Hills Farm                                    ││
│  │  "...John Doe, as Grantor, hereby conveys to Oak Hills   ││
│  │  Conservancy, as Grantee, the following described..."     ││
│  │  Relevance: ██████████ 0.95                              ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  ⚡ SIGNAL — SR-005: Self-Dealing Pattern                 ││
│  │  Case: Oak Hills Farm                                    ││
│  │  "Board member John Doe appears as signatory on deed     ││
│  │  while serving as board officer of grantee org..."       ││
│  │  Relevance: ██████████ 0.91                              ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  👤 PERSON — John Doe                                    ││
│  │  Cases: Oak Hills Farm, Shell Corp Network               ││
│  │  "Appears in 7 documents across 2 cases. Board member,   ││
│  │  grantor, registered agent."                             ││
│  │  Relevance: ████████░░ 0.82                              ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  [Load more results...]                                      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Result types:** Documents, Signals, Detections, Persons, Organizations. Each has a distinct icon and card layout.

**Click behavior:** Clicking a result navigates to the relevant view (document → case documents tab, signal → triage, person → future entity view).

---

## 8. Settings View (`/settings`)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  SETTINGS                                                    │
│                                                              │
│  ┌─────────────┬─────────────────────────────────────────── │
│  │             │                                            │
│  │ Appearance  │  APPEARANCE                                │
│  │             │                                            │
│  │ Keyboard    │  Theme                                     │
│  │             │  ┌─────────────────────────────────┐       │
│  │ Data        │  │ (●) Dark    ( ) Light   ( ) Auto│       │
│  │             │  └─────────────────────────────────┘       │
│  │ Connectors  │  "Auto" follows your system preference.    │
│  │             │                                            │
│  │ About       │  Accent Color                              │
│  │             │  ┌─────────────────────────────────┐       │
│  │             │  │ [🔵 Blue] [🟣 Purple] [🟢 Green]│       │
│  │             │  └─────────────────────────────────┘       │
│  │             │                                            │
│  │             │  Density                                   │
│  │             │  ┌─────────────────────────────────┐       │
│  │             │  │ ( ) Comfortable  (●) Compact    │       │
│  │             │  └─────────────────────────────────┘       │
│  │             │  Compact reduces padding in tables and     │
│  │             │  lists for denser information display.     │
│  │             │                                            │
│  └─────────────┴────────────────────────────────────────── │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

Settings uses a left sub-nav + right content panel layout (common pattern in VS Code, GitHub, etc.)

### 8.1 Appearance Settings

| Setting | Options | Default | Storage |
|---------|---------|---------|---------|
| Theme | Dark / Light / Auto | Dark | localStorage |
| Accent Color | Blue / Purple / Green | Blue | localStorage |
| Density | Comfortable / Compact | Compact | localStorage |

**Theme implementation:** CSS variables swap between two sets of values. The `<html>` element gets a `data-theme="dark"` or `data-theme="light"` attribute. All existing CSS already uses variables (`--bg-ink`, `--accent`, etc.), so this is mainly defining the light-theme variable set.

**Light theme values** (to complement the existing dark theme):

```css
[data-theme="light"] {
    --bg-ink: #f8f9fa;
    --bg-surface: #ffffff;
    --bg-raised: #f0f1f3;
    --text-primary: #1a1d23;
    --text-secondary: #5a5f6b;
    --border-subtle: #d0d3d9;
    --accent: #0f62fe;        /* stays the same */
    --danger: #da1e28;        /* slightly adjusted for light bg */
    --warn: #d97706;          /* adjusted for contrast */
}
```

**Auto mode:** Uses `prefers-color-scheme` media query. Falls back to dark if no system preference.

---

### 8.2 Keyboard Settings

```
│  KEYBOARD SHORTCUTS                                         │
│                                                             │
│  Global                                                     │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Focus AI Search        │  Cmd+K / Ctrl+K        │       │
│  │ Go to Dashboard        │  G then D               │       │
│  │ Go to Cases            │  G then C               │       │
│  │ Go to Triage           │  G then T               │       │
│  │ Go to Referrals        │  G then R               │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  Signal Triage                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Next signal            │  J or ↓                 │       │
│  │ Previous signal        │  K or ↑                 │       │
│  │ Set status: OPEN       │  1                      │       │
│  │ Set status: REVIEWED   │  2                      │       │
│  │ Set status: DISMISSED  │  3                      │       │
│  │ Save current triage    │  Cmd+S / Ctrl+S         │       │
│  │ Open case for signal   │  Enter                  │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  Case List                                                  │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Next case              │  J or ↓                 │       │
│  │ Previous case          │  K or ↑                 │       │
│  │ Open selected case     │  Enter                  │       │
│  │ Create new case        │  N                      │       │
│  └──────────────────────────────────────────────────┘       │
```

This page is **read-only** for now — it documents shortcuts, doesn't let you rebind them. Rebinding is a future feature.

---

### 8.3 Data & Processing Settings

```
│  DATA & PROCESSING                                          │
│                                                             │
│  OCR                                                        │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Auto-process OCR on upload     [ON / off]        │       │
│  │ OCR file size limit            [30] MB           │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  Signal Detection                                           │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Auto-evaluate signals on upload [ON / off]       │       │
│  │ Re-evaluate on document delete  [on / OFF]       │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  Entity Resolution                                          │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Fuzzy match threshold          [0.75]            │       │
│  │ High-confidence threshold      [0.92]            │       │
│  └──────────────────────────────────────────────────┘       │
```

These map to backend settings. For now, they can be display-only (showing current backend config values). Making them editable requires a `PATCH /api/settings/` endpoint on the backend.

---

### 8.4 Connectors Settings

```
│  DATA CONNECTORS                                            │
│                                                             │
│  ┌──────────────────────────────────────────────────┐       │
│  │  ProPublica Nonprofit Explorer       ● Connected │       │
│  │  No auth required                                │       │
│  │  Last used: Mar 15, 2026                [Test]   │       │
│  ├──────────────────────────────────────────────────┤       │
│  │  IRS Pub78 / EO BMF                  ● Connected │       │
│  │  No auth required                                │       │
│  │  Last download: Mar 10, 2026          [Refresh]  │       │
│  ├──────────────────────────────────────────────────┤       │
│  │  Ohio Secretary of State             ● Connected │       │
│  │  No auth required                                │       │
│  │  Last download: Mar 8, 2026           [Refresh]  │       │
│  ├──────────────────────────────────────────────────┤       │
│  │  Ohio County Recorders              ◐ Manual     │       │
│  │  Human-in-the-loop (no direct API)               │       │
│  │  88 counties configured              [View Map]  │       │
│  ├──────────────────────────────────────────────────┤       │
│  │  Ohio County Auditors               ● Connected  │       │
│  │  ODNR ArcGIS API (no auth)                       │       │
│  │  Last query: Mar 12, 2026             [Test]     │       │
│  ├──────────────────────────────────────────────────┤       │
│  │  Ohio Auditor of State              ● Connected  │       │
│  │  HTML scraper (no auth)                          │       │
│  │  Last query: Mar 5, 2026              [Test]     │       │
│  └──────────────────────────────────────────────────┘       │
```

Each connector card shows status, auth requirement, last activity, and a [Test] button that pings the data source. For the county recorder (human-in-the-loop), [View Map] could show the county registry with portal links.

---

### 8.5 About

```
│  ABOUT CATALYST                                             │
│                                                             │
│  Version: 0.1.0-alpha                                       │
│  Environment: Development                                   │
│  Backend: Django 5.x / PostgreSQL 16                        │
│  Frontend: React 18 / TypeScript / Vite                     │
│                                                             │
│  Database                                                   │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Status: Connected                                │       │
│  │ Tables: 23                                       │       │
│  │ Cases: 18                                        │       │
│  │ Documents: 247                                   │       │
│  │ Signals: 89                                      │       │
│  │ Audit Log Entries: 1,247                         │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  Project Charter                                            │
│  Built for fraud pattern detection with defensible audit    │
│  history and human-in-the-loop evidence workflows.          │
│                                                             │
│  [View System Docs]  [View API Cookbook]                     │
```

---

## 9. Global Keyboard Shortcuts

Full keyboard shortcut map implemented via a custom `useKeyboardShortcuts` hook:

### Navigation Shortcuts (available everywhere)

| Keys | Action | Notes |
|------|--------|-------|
| `Cmd+K` / `Ctrl+K` | Focus AI search bar | Blurs current element, opens search dropdown |
| `Escape` | Close search / close modal / deselect | Context-dependent |
| `G` then `D` | Go to Dashboard | Two-key sequence (vim-style) |
| `G` then `C` | Go to Cases | |
| `G` then `T` | Go to Triage | |
| `G` then `R` | Go to Referrals | |
| `G` then `S` | Go to Settings | |
| `?` | Show keyboard shortcut overlay | Modal with full shortcut reference |

### Triage Shortcuts (active in Triage view and Case Signals tab)

| Keys | Action |
|------|--------|
| `J` or `↓` | Select next signal in list |
| `K` or `↑` | Select previous signal in list |
| `1` | Set draft status to OPEN |
| `2` | Set draft status to REVIEWED |
| `3` | Set draft status to DISMISSED |
| `Cmd+S` / `Ctrl+S` | Save current triage |
| `Enter` | Navigate to parent case |

### Case List Shortcuts (active in Cases view)

| Keys | Action |
|------|--------|
| `J` or `↓` | Select next case in list |
| `K` or `↑` | Select previous case in list |
| `Enter` | Open selected case |
| `N` | Open "New Case" modal |

### Guard: All single-key shortcuts suppressed when focus is in an `<input>`, `<textarea>`, `<select>`, or `[contenteditable]` element. This is already implemented in the current codebase.

---

## 10. New API Endpoints Needed

The current backend API is scoped per-case. Several new views need cross-case data:

| Endpoint | Method | Purpose | Priority |
|----------|--------|---------|----------|
| `GET /api/signals/` | GET | Cross-case signal list with filters (severity, status, case, rule) | HIGH — needed for Triage view |
| `GET /api/referrals/` | GET | Cross-case referral list with filters (agency, status, case) | HIGH — needed for Referrals view |
| `GET /api/cases/:id/timeline/` | GET | Audit log entries for a case, ordered chronologically | MEDIUM — needed for Timeline tab |
| `GET /api/activity-feed/` | GET | Recent audit log entries across all cases (for Dashboard) | MEDIUM — needed for Dashboard |
| `GET /api/stats/` | GET | Aggregated counts for Dashboard KPIs | LOW — can compute from existing endpoints initially |

---

## 11. Component Inventory

Complete list of components to build, organized by category:

### Layout Components (new)

| Component | File | Purpose |
|-----------|------|---------|
| AppShell | `layouts/AppShell.tsx` | Sidebar + header + AI search + breadcrumb + `<Outlet>` |
| Sidebar | `components/ui/Sidebar.tsx` | Navigation sidebar with route links and badges |
| Breadcrumb | `components/ui/Breadcrumb.tsx` | Dynamic breadcrumb trail |
| AISearchBar | `components/ui/AISearchBar.tsx` | Persistent search with dropdown results |
| CommandPalette | `components/ui/CommandPalette.tsx` | Cmd+K overlay (powers the search dropdown) |

### View Components (new)

| Component | File | Route |
|-----------|------|-------|
| DashboardView | `views/DashboardView.tsx` | `/` |
| CasesListView | `views/CasesListView.tsx` | `/cases` |
| CaseDetailView | `views/CaseDetailView.tsx` | `/cases/:caseId` |
| TriageView | `views/TriageView.tsx` | `/triage` |
| ReferralsView | `views/ReferralsView.tsx` | `/referrals` |
| SearchView | `views/SearchView.tsx` | `/search` |
| SettingsView | `views/SettingsView.tsx` | `/settings` |

### Case Detail Tab Components (refactored from CaseDetailPanel)

| Component | File | Tab Route |
|-----------|------|-----------|
| DocumentsTab | `components/cases/DocumentsTab.tsx` | `/cases/:id/documents` |
| SignalsTab | `components/cases/SignalsTab.tsx` | `/cases/:id/signals` |
| DetectionsTab | `components/cases/DetectionsTab.tsx` | `/cases/:id/detections` |
| ReferralsTab | `components/cases/ReferralsTab.tsx` | `/cases/:id/referrals` |
| TimelineTab | `components/cases/TimelineTab.tsx` | `/cases/:id/timeline` |

### Feature Components (refactored + new)

| Component | File | Purpose |
|-----------|------|---------|
| CaseTable | `components/cases/CaseTable.tsx` | Full-width sortable case table |
| CaseBoard | `components/cases/CaseBoard.tsx` | Kanban board view |
| CaseCard | `components/cases/CaseCard.tsx` | Card for Kanban board |
| CaseCreateModal | `components/cases/CaseCreateModal.tsx` | Modal form for new case |
| CaseHeader | `components/cases/CaseHeader.tsx` | Case detail header with stats |
| SignalList | `components/signals/SignalList.tsx` | Scrollable signal queue list |
| SignalDetail | `components/signals/SignalDetail.tsx` | Signal detail + triage panel |
| SignalTriageControls | `components/signals/SignalTriageControls.tsx` | Status chips + note + save |
| DocumentTable | `components/documents/DocumentTable.tsx` | Document table with filters |
| DocumentUpload | `components/documents/DocumentUpload.tsx` | Drag-drop upload zone |
| DetectionCard | `components/detections/DetectionCard.tsx` | Detection display + controls |
| ReferralTable | `components/referrals/ReferralTable.tsx` | Cross-case referral table |
| ReferralCard | `components/referrals/ReferralCard.tsx` | Single referral detail card |
| ReferralForm | `components/referrals/ReferralForm.tsx` | Create/edit referral modal |
| ReferralPipeline | `components/referrals/ReferralPipeline.tsx` | Status flow visualization |
| TimelineEvent | `components/timeline/TimelineEvent.tsx` | Single timeline entry |
| TimelineFeed | `components/timeline/TimelineFeed.tsx` | Scrollable timeline list |
| KpiCards | `components/dashboard/KpiCards.tsx` | Clickable KPI card grid |
| RecentActivity | `components/dashboard/RecentActivity.tsx` | Activity feed widget |
| SeverityChart | `components/dashboard/SeverityChart.tsx` | Horizontal bar chart |

### Shared UI Primitives (existing + new)

| Component | Status | Purpose |
|-----------|--------|---------|
| Button | EXISTS | Action buttons |
| FormInput | EXISTS | Text input |
| FormSelect | EXISTS | Dropdown select |
| FormTextarea | EXISTS | Multiline input |
| StateBlock | EXISTS | Loading/empty state display |
| EmptyState | EXISTS | Empty state with title + detail |
| ToastStack | EXISTS | Notification toasts |
| DataTable | NEW | Reusable sortable/filterable table |
| Modal | NEW | Overlay dialog container |
| TabBar | NEW | Horizontal tab navigation |
| Badge | NEW | Colored pill for counts/status |
| Tooltip | NEW | Hover information |
| SlideOver | NEW | Right-side panel overlay |
| ConfirmDialog | NEW | "Are you sure?" dialogs |
| ThemeToggle | NEW | Dark/Light/Auto radio group |
| StatusDot | NEW | Colored severity/status indicator |

---

## Summary: What Gets Built and When

### Phase A — Skeleton (router + shell)
- React Router v6 setup
- AppShell with sidebar (always expanded)
- Breadcrumb bar
- Route definitions (all views as empty placeholders)
- Theme toggle (dark/light/auto CSS variable swap)

### Phase B — View Migration
- Move existing CasesPanel → CasesListView (table mode)
- Move CaseDetailPanel → CaseDetailView with tab routing
- Break CaseDetailPanel into 4 tab components (Documents, Signals, Detections, Referrals)
- Wire up existing API calls to new view structure

### Phase C — New Features
- AI Search bar (quick-jump mode first, full semantic later)
- Signal Triage Queue view (cross-case)
- Referrals cross-case view
- Kanban board for cases
- Backend: cross-case signals + referrals endpoints

### Phase D — Polish
- Dashboard with all widgets
- Timeline tab
- Settings page (all sections)
- Keyboard shortcut expansion (G+D, G+C, etc.)
- Light theme CSS variable set
- Command palette overlay

---

*This document should be the single reference for frontend implementation decisions. Update it as decisions change.*
