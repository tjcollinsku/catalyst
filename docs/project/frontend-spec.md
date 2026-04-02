# Catalyst Frontend — Master Design Specification

**Date:** 2026-03-31
**Status:** Draft v2 — consolidated from all design discussions
**Author:** Tyler Collins + Claude (Senior Engineer)

---

## Design Decisions Log

All decisions locked during design discussions:

| Decision | Choice | Notes |
|----------|--------|-------|
| Sidebar | Always expanded (240px) | Clear orientation for all skill levels |
| Triage default | Cross-case | Investigators work multiple cases |
| Kanban board | Yes, for cases | Table + Board toggle |
| Theme | Dark primary, light toggle, auto option | Toggle in Settings |
| AI search bar | Persistent at top of every view | Quick-jump + semantic + AI overview |
| Entity view | Yes — list default, graph toggle | New sidebar item |
| Entity editing | Yes — with immutable audit trail | Merges logged permanently |
| Processing status | Async with progress panel | Per-document status during batch upload |
| Notes system | Rich, taggable, searchable within case + globally | Appears on timeline |
| Document viewer | Embedded PDF viewer | Side panel within case |
| Report generation | Formal doc + raw export | Word/PDF template, polished externally |
| Investigation roadmap | Checklist approach per signal type | "Investigations typically..." framing |
| Law references | Citations with links (not full text) | ORC, IRC, Federal statutes |
| External search | Quick-launch buttons (Option B) | Expandable as needs grow |
| Notifications | In-app bell | Badge count + dropdown |
| Multi-user | Design for multi-user from start | Single user now, auth later |

---

## Table of Contents

1. Global Shell
2. Dashboard View
3. Cases View (Table + Kanban)
4. Case Detail View (6 tabs)
5. Entity View (List + Graph)
6. Signal Triage Queue View
7. Referrals View
8. Search View
9. Settings View
10. Shared Features (Notes, Notifications, Processing, PDF Viewer, Report Gen)
11. Keyboard Shortcuts
12. Backend API Additions
13. Component Inventory
14. Implementation Phases

---

## 1. Global Shell

The shell wraps every view. Four persistent elements: sidebar, AI search bar, breadcrumb, notification bell.

### 1.1 Full Shell Layout

```
┌────────────────────────────────────────────────────────────────────┐
│ SIDEBAR (240px)  │  TOP BAR                                        │
│                  │  ┌────────────────────────────────────┬───┬───┐ │
│  ◆ CATALYST      │  │🔍 Ask anything about your cases... │🔔3│ TC│ │
│                  │  └────────────────────────────────────┴───┴───┘ │
│  ▦  Dashboard    │  Breadcrumb: Cases > Oak Hills Farm > Documents │
│  📁 Cases        │ ─────────────────────────────────────────────── │
│  👤 Entities     │                                                 │
│  ⚡ Triage    12 │                                                 │
│  📤 Referrals  2 │           ACTIVE VIEW PANEL                     │
│  🔍 Search       │                                                 │
│                  │     (renders based on current route)             │
│  ─── ─── ───    │                                                 │
│  ⚙  Settings     │                                                 │
│                  │                                                 │
│  ┌────────────┐  │                                                 │
│  │ TC          │  │                                                 │
│  │ Investigator│  │                                                 │
│  └────────────┘  │                                                 │
└────────────────────────────────────────────────────────────────────┘
```

### 1.2 Sidebar Navigation Items

| Icon | Label | Route | Badge | Purpose |
|------|-------|-------|-------|---------|
| ▦ | Dashboard | `/` | — | KPI overview, recent activity |
| 📁 | Cases | `/cases` | — | Case list (table + kanban) |
| 👤 | Entities | `/entities` | — | Cross-case entity browser |
| ⚡ | Triage | `/triage` | Open signal count (red) | Signal triage queue |
| 📤 | Referrals | `/referrals` | DRAFT count (blue) | Cross-case referral tracking |
| 🔍 | Search | `/search` | — | Semantic search |
| ⚙ | Settings | `/settings` | — | App configuration |

- Active route: left 4px accent border + highlighted background
- Sidebar does NOT collapse — always expanded
- Bottom: user initials + role label (hardcoded now, from auth later)
- Badges are live-updating colored pills

### 1.3 Persistent AI Search Bar

Always visible in the top bar of every view.

```
┌──────────────────────────────────────────────────────────────┐
│  🔍  Ask anything about your cases...               Cmd+K   │
└──────────────────────────────────────────────────────────────┘
```

**Three modes of operation:**

**Mode 1 — Quick-jump (as you type):**
Fuzzy-matches against cached case names, document filenames, signal titles, entity names. Results grouped by category. Click to navigate directly.

```
┌──────────────────────────────────────────────────────────┐
│  🔍  "john doe"                                  Cmd+K   │
├──────────────────────────────────────────────────────────┤
│  ENTITIES                                                │
│    👤 John Doe (Person — 2 cases)                        │
│  CASES                                                   │
│    📁 Oak Hills Farm Investigation                       │
│  DOCUMENTS                                               │
│    📄 deed-2019-04.pdf (Oak Hills Farm)                  │
│    📄 board-roster.pdf (Oak Hills Farm)                  │
│  SIGNALS                                                 │
│    ⚡ SR-005: Self-Dealing (Oak Hills Farm)               │
│    ⚡ SR-001: Deceased Signer (Oak Hills Farm)            │
│  ─── ─── ───                                             │
│  Press Enter for full search with AI overview →           │
└──────────────────────────────────────────────────────────┘
```

**Mode 2 — Full semantic search (press Enter):**
Navigates to `/search?q=...` with ranked results.

**Mode 3 — AI Overview (top of search results):**
A synthesized, non-judgmental paragraph at the top of search results summarizing what the system knows:

```
┌──────────────────────────────────────────────────────────┐
│  🤖 AI OVERVIEW                                          │
│                                                          │
│  John Doe appears in 2 active cases across 7 documents.  │
│  He is identified as a board member of Oak Hills          │
│  Conservancy and simultaneously as grantor on a $0        │
│  consideration deed transferring Parcel 12-345678.001     │
│  to the same organization. He also appears as the         │
│  registered agent for Shell Corp LLC. The system has      │
│  flagged 4 signals involving this entity, including       │
│  SR-005 (Self-Dealing) and SR-001 (Deceased Signer).     │
│                                                          │
│  Sources: deed-2019-04.pdf, board-roster.pdf,            │
│  articles-of-incorporation.pdf                           │
└──────────────────────────────────────────────────────────┘
```

The AI overview **synthesizes only — never triages**. It connects dots, summarizes where an entity or concept appears, and cites sources. The investigator decides what it means.

**Technical approach:**
- Quick-jump: frontend-only fuzzy filter against loaded data (debounced 300ms)
- Full search: backend semantic search endpoint
- AI overview: backend endpoint that aggregates entity/signal/document data into a structured summary. Start with template-based aggregation. LLM layer optional later.
- `Cmd+K` / `Ctrl+K` focuses from anywhere. `Escape` closes dropdown.

### 1.4 Notification Bell

In the top bar next to the user avatar.

```
  🔔 3
```

Click opens a dropdown:

```
┌─────────────────────────────────────────┐
│  NOTIFICATIONS                    [Clear]│
│                                         │
│  ● 3 new signals on "Oak Hills" — 2m   │
│  ● OCR completed: board-minutes.pdf — 5m│
│  ● Referral acknowledged by Ohio AG — 1h│
│  ─── ─── ───                            │
│  ○ Signal SR-007 reviewed — 3h          │
│  ○ 5 documents uploaded — 4h            │
│                                         │
│  [View all notifications →]              │
└─────────────────────────────────────────┘
```

- ● = unread (bold), ○ = read
- Badge count shows unread count
- Each notification clickable → navigates to source
- Notifications generated by: new signals, OCR completion, referral status changes, entity merges, new detections
- Stored in a new `Notification` model (or derived from AuditLog on the frontend)

### 1.5 Breadcrumb Bar

| Route | Breadcrumb |
|-------|-----------|
| `/` | Dashboard |
| `/cases` | Cases |
| `/cases/:id` | Cases > Oak Hills Farm |
| `/cases/:id/documents` | Cases > Oak Hills Farm > Documents |
| `/cases/:id/signals` | Cases > Oak Hills Farm > Signals |
| `/cases/:id/notes` | Cases > Oak Hills Farm > Notes |
| `/entities` | Entities |
| `/entities/person/:id` | Entities > John Doe |
| `/triage` | Signal Triage |
| `/referrals` | Referrals |
| `/search?q=deed` | Search > "deed" |
| `/settings` | Settings |

Each segment is clickable.

---

## 2. Dashboard View (`/`)

"What needs my attention right now?"

```
┌──────────────────────────────────────────────────────────────┐
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐│
│  │ Total Cases│ │ Open Cases │ │  Open      │ │  Draft     ││
│  │     18     │ │     12     │ │  Signals   │ │  Referrals ││
│  │  [click →] │ │  [click →] │ │     47     │ │      5     ││
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘│
│                                                              │
│  ┌─────────────────────────┐  ┌────────────────────────────┐│
│  │ RECENT ACTIVITY         │  │ SIGNALS BY SEVERITY        ││
│  │                         │  │                            ││
│  │ ● Shell Corp created    │  │ CRITICAL  ████████  8      ││
│  │ ● 3 signals fired       │  │ HIGH      ██████    6      ││
│  │ ● Referral submitted    │  │ MEDIUM    ████████████ 19  ││
│  │ ● OCR completed: 12 doc │  │ LOW       ██████████  14   ││
│  │ ● Entity merge: J. Doe  │  │                            ││
│  │ [View all →]            │  │                            ││
│  └─────────────────────────┘  └────────────────────────────┘│
│                                                              │
│  ┌─────────────────────────┐  ┌────────────────────────────┐│
│  │ TOP OPEN SIGNALS        │  │ CASES NEEDING ATTENTION    ││
│  │                         │  │                            ││
│  │ 🔴 SR-005 Self-dealing  │  │ 🔴 Shell Corp (19 sigs)   ││
│  │ 🔴 SR-001 Deceased      │  │ 🔴 Oak Hills (12 sigs)    ││
│  │ 🟡 SR-007 Procurement   │  │ 🟡 FCA Lending (8 sigs)   ││
│  │ [Go to Triage →]       │  │ [View all cases →]        ││
│  └─────────────────────────┘  └────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ INVESTIGATION ROADMAP (aggregated across all cases)      ││
│  │                                                          ││
│  │ ☐ Verify deceased signer (SR-001) — Oak Hills Farm      ││
│  │ ☐ Pull Form 990 for self-dealing check — Oak Hills      ││
│  │ ☐ Search county recorder for related transfers — Shell   ││
│  │ ☐ Check IRS EO BMF for status — FCA Lending             ││
│  │ [View full roadmap →]                                    ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

**Dashboard widgets (7 total):**

| Widget | Content | Click action |
|--------|---------|-------------|
| KPI: Total Cases | Count | → `/cases` |
| KPI: Open Cases | Filtered count | → `/cases?status=ACTIVE` |
| KPI: Open Signals | Sum of open_count | → `/triage` |
| KPI: Draft Referrals | DRAFT count | → `/referrals?status=DRAFT` |
| Recent Activity | Last 10 audit log entries | Each item links to source |
| Signals by Severity | Horizontal bar chart | Click bar → `/triage?severity=X` |
| Top Open Signals | Top 5 by severity | Click → signal in triage |
| Cases Needing Attention | Ranked by open signal count | Click → case detail |
| Investigation Roadmap | Top checklist items from roadmap engine | Click → case/signal |

---

## 3. Cases View (`/cases`)

Two display modes toggled by the user: **Table** (default) and **Board** (Kanban).

### 3.1 Table Mode

```
┌──────────────────────────────────────────────────────────────┐
│  CASES                                      [+ New Case]     │
│  View: [▐Table] [Board]                                     │
│  Filters: [Status ▾] [Severity ▾] [Search...         ]      │
│                                                              │
│  ┌──┬─────────────────┬────────┬──────┬──────┬──────┬──────┐│
│  │  │ Case Name       │ Status │ Sigs │ Docs │ Refs │ Updated│
│  ├──┼─────────────────┼────────┼──────┼──────┼──────┼──────┤│
│  │🔴│ Shell Corp Net  │ ACTIVE │19(7🔴)│  89 │  1  │ 3h    ││
│  │🔴│ Oak Hills Farm  │ ACTIVE │12(3🔴)│  47 │  2  │ 2h    ││
│  │🟡│ FCA Lending     │ ACTIVE │ 8(1🔴)│  23 │  1  │ 1d    ││
│  │🟢│ County Audit    │ CLOSED │ 2(0🔴)│  15 │  1  │ 5d    ││
│  └──┴─────────────────┴────────┴──────┴──────┴──────┴──────┘│
│  Showing 4 of 18 cases          [< Prev]  Page 1  [Next >]  │
└──────────────────────────────────────────────────────────────┘
```

Click any row → `/cases/:caseId`. [+ New Case] opens a modal form.

### 3.2 Kanban Board Mode

Columns map to the existing `CaseStatus` enum from the backend:

```
┌──────────────────────────────────────────────────────────────────┐
│  View: [Table] [▐Board]                                         │
│                                                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────┐│
│  │ ACTIVE (10)  │ │ PAUSED (2)   │ │ REFERRED (4) │ │CLOSED(2)││
│  │              │ │              │ │              │ │         ││
│  │ ┌──────────┐ │ │ ┌──────────┐ │ │ ┌──────────┐ │ │┌───────┐││
│  │ │Shell Corp│ │ │ │Intake #3 │ │ │ │Oak Hills │ │ ││County │││
│  │ │🔴 19 sigs│ │ │ │⚪ 0 sigs │ │ │ │🔴 12 sigs│ │ ││Audit  │││
│  │ │89 docs   │ │ │ │2 docs    │ │ │ │47 docs   │ │ ││🟢 2sig│││
│  │ │3h ago    │ │ │ │1w ago    │ │ │ │AG+IRS    │ │ ││15 docs│││
│  │ └──────────┘ │ │ └──────────┘ │ │ └──────────┘ │ │└───────┘││
│  │ ┌──────────┐ │ │              │ │ ┌──────────┐ │ │         ││
│  │ │FCA       │ │ │              │ │ │ ...      │ │ │         ││
│  │ │Lending   │ │ │              │ │ │          │ │ │         ││
│  │ │🟡 8 sigs │ │ │              │ │ │          │ │ │         ││
│  │ └──────────┘ │ │              │ │ └──────────┘ │ │         ││
│  └──────────────┘ └──────────────┘ └──────────────┘ └─────────┘│
└──────────────────────────────────────────────────────────────────┘
```

**Four columns** matching `CaseStatus`:
| Column | Status | Header Color |
|--------|--------|-------------|
| Active | `ACTIVE` | Blue |
| Paused | `PAUSED` | Gray |
| Referred | `REFERRED` | Amber |
| Closed | `CLOSED` | Green |

**Card content:** Case name, severity dot, open signal count, document count, referral agencies (abbreviated), relative time.

**Drag-and-drop** (Phase D): drag card between columns → `PATCH /api/cases/:id/` to update status. Confirm before CLOSED.

**Sort within columns:** Highest severity first, then most recently updated.

---

## 4. Case Detail View (`/cases/:caseId`)

### 4.1 Case Header (always visible)

```
┌──────────────────────────────────────────────────────────────┐
│  ← Cases                                                     │
│                                                              │
│  OAK HILLS FARM INVESTIGATION                 Status: [ACTIVE▾]
│  Created: Jan 15, 2026  |  Ref: OAG-2026-0042               │
│  47 docs  |  12 signals  |  3 detections  |  2 referrals     │
│  Notes: Land conservation fraud pattern...             [Edit] │
│                                                              │
│  ┌─────────┬────────┬────────────┬─────────┬────────┬──────┐│
│  │▐Docs    │Signals │ Detections │Referrals│ Notes  │Timeln││
│  └─────────┴────────┴────────────┴─────────┴────────┴──────┘│
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Tab: Documents (`/cases/:caseId/documents`)

```
┌──────────────────────────────────────────────────────────────┐
│  DOCUMENTS (35/47)          [Upload Files] [Process OCR (4)] │
│  Filters: [Type ▾] [OCR Status ▾] [Search filenames...]     │
│                                                              │
│  ┌──────────────────┬──────────┬──────┬──────┬─────┬───────┐│
│  │ Filename         │ Type     │ OCR  │ Size │ Date│       ││
│  ├──────────────────┼──────────┼──────┼──────┼─────┼───────┤│
│  │ deed-2019-04.pdf │ DEED     │ ✅   │ 2.1M │ 1/20│ [👁][✕]│
│  │ 990-2020.pdf     │ TAX_FORM │ ✅   │ 4.8M │ 1/20│ [👁][✕]│
│  │ board-minutes.pdf│ MINUTES  │ ⏳   │ 1.2M │ 1/22│ [👁][✕]│
│  └──────────────────┴──────────┴──────┴──────┴─────┴───────┘│
│                                                              │
│  [👁] = open in embedded PDF viewer                          │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │       Drag and drop files here to upload                 ││
│  │       or click [Upload Files]                            ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  [Generate Referral Memo]  [Re-evaluate Signals]             │
└──────────────────────────────────────────────────────────────┘
```

**Upload stays in the case page** — you never leave the case to upload documents.

**[👁] button** opens the embedded PDF viewer (see Section 10.4).

**Processing status panel** appears during uploads (see Section 10.3).

### 4.3 Tab: Signals (`/cases/:caseId/signals`)

Per-case signal view with master-detail layout:

```
┌──────────────────────────────────────────────────────────────┐
│  SIGNALS (8/12)                  [Go to Cross-Case Triage →] │
│  Filters: [Severity ▾] [Status ▾]                            │
│                                                              │
│  ┌────────────────────────┬─────────────────────────────────┐│
│  │ LIST                   │ DETAIL                          ││
│  │                        │                                 ││
│  │ 🔴 SR-005 Self-dealing │ SR-005: SELF-DEALING            ││
│  │    CRITICAL — OPEN     │ Severity: CRITICAL              ││
│  │ ───────────────────    │ Detected: Jan 20, 2026          ││
│  │ 🔴 SR-001 Deceased     │                                 ││
│  │    CRITICAL — OPEN     │ DESCRIPTION                     ││
│  │ ───────────────────    │ Board member listed as both     ││
│  │ 🟡 SR-007 Procurement  │ grantor and grantee on deed...  ││
│  │    HIGH — OPEN         │                                 ││
│  │                        │ LEGAL BASIS                     ││
│  │                        │ • IRC §4941 (Self-Dealing)      ││
│  │                        │ • ORC §1702.30 (Fiduciary Duty) ││
│  │                        │ [View full statute →]           ││
│  │                        │                                 ││
│  │                        │ INVESTIGATION CHECKLIST          ││
│  │                        │ ☐ Pull board minutes for vote   ││
│  │                        │ ☐ Check Form 990 Part VI        ││
│  │                        │ ☐ Search recorder for transfers ││
│  │                        │                                 ││
│  │                        │ TRIAGE                          ││
│  │ j/k ↑↓  1/2/3 status  │ Status: [OPEN ▾]               ││
│  │                        │ Note: [                       ] ││
│  │                        │ [Save Triage]                   ││
│  └────────────────────────┴─────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

**New: Legal Basis section** on each signal showing relevant statute citations:

| Signal | Legal References |
|--------|-----------------|
| SR-001 Deceased Signer | ORC §2913.42 (Forgery), 18 USC §1028 (Identity Fraud) |
| SR-002 Date Impossibility | ORC §2913.42 (Forgery), ORC §2921.13 (Falsification) |
| SR-003 Property Valuation | IRC §170(h) (Conservation Easement), ORC §1716.04 |
| SR-004 Missing EIN | IRC §6033 (Returns by Exempt Orgs) |
| SR-005 Self-Dealing | IRC §4941 (Self-Dealing), ORC §1702.30 (Fiduciary Duty) |
| SR-006 UCC Loop | ORC §1309 (Secured Transactions), UCC Article 9 |
| SR-007 Procurement Bypass | ORC §117.16 (Competitive Bidding), 2 CFR §200.320 |
| SR-008 Revenue Anomaly | IRC §6033, ORC §1716.14 (Charitable Trust Reporting) |
| SR-009 Revenue Pattern | IRC §501(c)(3) Requirements, ORC §1716 |
| SR-010 Phantom Officer | ORC §1702.12 (Officer Requirements), IRC §4958 (Excess Benefit) |

Citations are clickable links to Ohio Legislature / IRS / Cornell LII sites.

**New: Investigation Checklist** — each signal type has pre-defined investigation steps. These are framed as "investigators typically check..." rather than recommendations. Checklist items can be checked off per-case (state stored locally or in a new model).

### 4.4 Tab: Detections (`/cases/:caseId/detections`)

Stacked detection cards with severity, confidence score, evidence snapshot (collapsible JSON), and inline status/note editing. Same as previously designed.

### 4.5 Tab: Referrals (`/cases/:caseId/referrals`)

Per-case referral cards with status pipeline visualization. Includes [+ New Referral], [Generate Memo], and [Export Referral Package] buttons.

**New: Export Referral Package** — generates a formal Word/PDF document containing:
- Case summary
- Evidence inventory (document list with descriptions)
- Signal summary with legal citations
- Investigation timeline
- Investigator notes
- Referral details

Also provides raw data export (JSON/CSV) for all case data.

### 4.6 Tab: Notes (`/cases/:caseId/notes`) — NEW

A dedicated tab for investigator notes within the case.

```
┌──────────────────────────────────────────────────────────────┐
│  NOTES (14)                                    [+ Add Note]  │
│                                                              │
│  Filters: [All types ▾] [By document ▾] [By author ▾]       │
│  Search:  [Search notes in this case...                  ]   │
│  Sort:    [Newest first ▾]                                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  Mar 15, 3:42 PM — TC                                   ││
│  │  Re: 📄 deed-2019-04.pdf | ⚡ SR-005                     ││
│  │                                                          ││
│  │  "Consideration listed as $0. This is consistent with    ││
│  │  conservation easement donation, but grantor is also     ││
│  │  board president. Need to check if board approved the    ││
│  │  transaction in minutes."                                ││
│  │                                                 [Edit ✎] ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  Mar 14, 2:15 PM — TC                                   ││
│  │  Re: ⚡ SR-005 Self-Dealing                               ││
│  │                                                          ││
│  │  "Confirmed John Doe is both grantor and board member.   ││
│  │  Need to verify if this was disclosed in Form 990        ││
│  │  Part VI Schedule L."                                    ││
│  │                                                 [Edit ✎] ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  Mar 13, 11:00 AM — TC                                  ││
│  │  Re: 📄 990-2020.pdf                                     ││
│  │                                                          ││
│  │  "No disclosure of related-party transaction in Part VI  ││
│  │  Schedule L. This strengthens the self-dealing signal."  ││
│  │                                                 [Edit ✎] ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

**Note creation form:**

```
┌──────────────────────────────────────────────────────────────┐
│  NEW NOTE                                                    │
│                                                              │
│  Link to: [📄 Select documents... ▾] [⚡ Select signals... ▾]│
│           [👤 Select entities... ▾]                           │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │                                                          ││
│  │  Type your note here...                                  ││
│  │                                                          ││
│  │                                                          ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  [Cancel]  [Save Note]                                       │
└──────────────────────────────────────────────────────────────┘
```

**Key behaviors:**
- Notes are linked to zero or more documents, signals, or entities via tag selectors
- Notes are attributed to a user (investigator initials for now)
- Notes are searchable within the case (the search field here is case-scoped, separate from global AI search)
- Notes are also searchable globally via the AI search bar
- Filters: by linked document, by author, by date range
- Sort: newest first, oldest first, by linked document
- Notes are **never deleted** — edits create a new version, old version preserved in audit log
- Notes appear on the Timeline tab interleaved with system events

### 4.7 Tab: Timeline (`/cases/:caseId/timeline`)

```
┌──────────────────────────────────────────────────────────────┐
│  TIMELINE                                                    │
│  Filter: [All ▾] [Notes only] [Signals only] [Documents only]│
│  Author: [All ▾]                                             │
│                                                              │
│  ┌─ Mar 15, 2026 ──────────────────────────────────────────  │
│  │                                                           │
│  │  📝 3:42 PM — TC (Note)                                   │
│  │  Re: deed-2019-04.pdf                                     │
│  │  "Consideration listed as $0..."                          │
│  │                                                           │
│  │  ⚡ 2:15 PM — System                                      │
│  │  Signal SR-005 status changed to REVIEWED                 │
│  │  Note: "Confirmed self-dealing pattern"                   │
│  │                                                           │
│  │  📄 1:30 PM — System                                      │
│  │  OCR completed on 5 documents                             │
│  │                                                           │
│  ├─ Mar 14, 2026 ─────────────────────────────────────────  │
│  │                                                           │
│  │  📝 2:15 PM — TC (Note)                                   │
│  │  "Confirmed John Doe is both grantor and board member..." │
│  │                                                           │
│  │  👤 1:00 PM — System                                      │
│  │  Entity merged: "J. Doe" → "John Doe"                    │
│  │  [View merge details]                                     │
│  │                                                           │
│  ├─ Jan 15, 2026 ─────────────────────────────────────────  │
│  │                                                           │
│  │  📁 10:00 AM — System                                     │
│  │  Case created: "Oak Hills Farm Investigation"             │
│  │                                                           │
│  └───────────────────────────────────────────────────────────│
│  [Load earlier events...]                                    │
└──────────────────────────────────────────────────────────────┘
```

**Event types on timeline:**
- 📁 Case events (created, status change)
- 📄 Document events (uploaded, OCR completed/failed, deleted)
- ⚡ Signal events (detected, triage status change)
- 🔍 Detection events (created, status change)
- 📤 Referral events (created, submitted, acknowledged, closed)
- 📝 Investigator notes (interleaved chronologically)
- 👤 Entity events (created, merged, edited)

**Filters:** By event type, by author. Filters let you strip away the noise — e.g., show "Notes only" to see the investigator's narrative, or "Signals only" to see the detection history.

---

## 5. Entity View — NEW

### 5.1 Entity Browser (`/entities`)

```
┌──────────────────────────────────────────────────────────────┐
│  ENTITIES                                                    │
│                                                              │
│  Type: [All ▾] [Persons] [Organizations] [Properties]        │
│  Case: [All cases ▾]                                         │
│  Search: [Search entities...                            ]    │
│                                                              │
│  ┌──┬─────────────────┬──────────┬───────┬──────┬──────────┐│
│  │  │ Name            │ Type     │ Cases │ Docs │ Signals  ││
│  ├──┼─────────────────┼──────────┼───────┼──────┼──────────┤│
│  │👤│ John Doe        │ Person   │  2    │  7   │ 4 (2🔴)  ││
│  │🏛│ Oak Hills Cons. │ Org      │  1    │  5   │ 2 (1🔴)  ││
│  │🏠│ Parcel 12-345.. │ Property │  1    │  3   │ 1 (1🟡)  ││
│  │🏛│ Shell Corp LLC  │ Org      │  1    │  4   │ 3 (2🔴)  ││
│  │👤│ Jane Smith      │ Person   │  1    │  2   │ 0        ││
│  └──┴─────────────────┴──────────┴───────┴──────┴──────────┘│
└──────────────────────────────────────────────────────────────┘
```

Click any row → `/entities/:type/:id`

### 5.2 Entity Detail — Person (`/entities/person/:id`)

```
┌──────────────────────────────────────────────────────────────┐
│  ← Entities                                                  │
│                                                              │
│  👤 JOHN DOE                                       [Edit ✎]  │
│  Aliases: J. Doe, John R. Doe                                │
│  Roles: Board Member, Grantor, Registered Agent              │
│  Date of Death: Aug 22, 2019                                 │
│  Appears in: 2 cases  |  7 documents  |  4 signals           │
│                                                              │
│  View: [▐List] [Graph]                                       │
│                                                              │
│  ── LIST VIEW ──────────────────────────────────────────────  │
│                                                              │
│  CASES                                                       │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  📁 Oak Hills Farm — board member, grantor               ││
│  │  📁 Shell Corp Network — registered agent                ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  DOCUMENTS (7)                                               │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  📄 deed-2019-04.pdf — grantor (pg. 1, 3) — Oak Hills   ││
│  │  📄 board-roster.pdf — board member — Oak Hills          ││
│  │  📄 articles-of-incorp.pdf — reg. agent — Shell Corp     ││
│  │  📄 990-2020.pdf — officer listed — Oak Hills            ││
│  │  ...                                                     ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  SIGNALS (4)                                                 │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  🔴 SR-005 Self-Dealing — CRITICAL — Oak Hills           ││
│  │  🔴 SR-001 Deceased Signer — CRITICAL — Oak Hills        ││
│  │  🟡 SR-010 Phantom Officer — HIGH — Shell Corp           ││
│  │  🟢 SR-003 Valuation Anomaly — MEDIUM — Oak Hills       ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ORGANIZATIONS                                               │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  🏛 Oak Hills Conservancy — Board Member (2015–present)  ││
│  │  🏛 Shell Corp LLC — Registered Agent (2018–present)     ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  PROPERTIES                                                  │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  🏠 Parcel 12-345678.001 — grantor ($0 consideration)   ││
│  │  🏠 Parcel 45-678901.003 — grantee — Shell Corp         ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  FINANCIAL INSTRUMENTS                                       │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  💰 UCC Filing #2020-1234 — secured party               ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  EXTERNAL SEARCHES                                           │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  🔍 Google News   🔍 Newspapers.com  🔍 Legacy.com      ││
│  │  🔍 Find-a-Grave  🔍 Ohio Courts     🔍 PACER           ││
│  │  🔍 Ohio SOS      🔍 Tax Liens       🔍 LinkedIn        ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  NOTES MENTIONING THIS ENTITY                                │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  📝 Mar 15 — TC — "Consideration listed as $0..."       ││
│  │  📝 Mar 14 — TC — "Confirmed both grantor and board..." ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

**Entity editing:** The [Edit] button allows changing name, aliases, roles, death date, and notes. **All edits are logged immutably** in the audit log with before/after state. There is no way to un-log an edit.

**Entity merging:** When viewing an entity, an [Merge with...] button allows selecting another entity to merge into this one. The merge action:
1. Combines all document links, signals, relationships
2. Moves aliases from the merged entity to the surviving entity
3. Creates an immutable audit log entry recording the merge (who, when, which entities, why)
4. The merged entity is soft-deleted (not hard-deleted) — always recoverable
5. A notification is created: "Entity merged: 'J. Doe' → 'John Doe'"

### 5.3 Entity Detail — Graph View

Toggle from List to Graph shows an interactive relationship visualization:

```
┌──────────────────────────────────────────────────────────────┐
│  View: [List] [▐Graph]                          [Zoom] [Fit] │
│                                                              │
│                        ┌─────────┐                           │
│              ┌─────────│ Oak Hills│──────────┐               │
│              │ board   │ Conserv. │ grantee  │               │
│              │ member  └─────────┘          │               │
│         ┌────┴────┐                    ┌────┴─────┐         │
│         │John Doe │────registered────→│Shell Corp│         │
│         │ (Person)│    agent          │   LLC    │         │
│         └────┬────┘                    └──────────┘         │
│              │ grantor                                        │
│         ┌────┴──────────┐                                    │
│         │Parcel          │                                    │
│         │12-345678.001   │                                    │
│         └───────────────┘                                    │
│                                                              │
│  Click any node to navigate. Drag to rearrange.              │
│  Red edges = flagged relationships (signals)                 │
└──────────────────────────────────────────────────────────────┘
```

**Graph features:**
- Nodes: entities (persons, orgs, properties, financial instruments)
- Edges: relationships with labels (role, transaction type)
- Red/highlighted edges: relationships involved in signals
- Clickable nodes → navigate to that entity's detail
- Draggable, zoomable, pannable (using D3.js or similar)
- Built in Phase D — list view comes first

---

## 6. Signal Triage Queue (`/triage`)

Cross-case by default. Master-detail layout.

```
┌──────────────────────────────────────────────────────────────┐
│  SIGNAL TRIAGE                                               │
│  Queue: 47 │ 12 OPEN │ 28 REVIEWED │ 7 DISMISSED            │
│  Filters: [Severity ▾] [Status ▾] [Case ▾] [Rule ▾]        │
│                                                              │
│  ┌────────────────────────┬─────────────────────────────────┐│
│  │ QUEUE (scrollable)     │ DETAIL                          ││
│  │                        │                                 ││
│  │ 🔴 SR-005 Self-dealing │ SR-005: SELF-DEALING            ││
│  │    Oak Hills Farm      │ Case: Oak Hills Farm [→ view]   ││
│  │    CRITICAL — OPEN     │ Severity: CRITICAL              ││
│  │ ───────────────────    │                                 ││
│  │ 🔴 SR-001 Deceased     │ DESCRIPTION                     ││
│  │    Oak Hills Farm      │ Board member "John Doe"...      ││
│  │    CRITICAL — OPEN     │                                 ││
│  │ ───────────────────    │ LEGAL BASIS                     ││
│  │ 🟡 SR-007 Procurement  │ • IRC §4941 (Self-Dealing)      ││
│  │    FCA Lending         │ • ORC §1702.30 (Fiduciary Duty) ││
│  │    HIGH — OPEN         │                                 ││
│  │ ───────────────────    │ EVIDENCE                        ││
│  │ 🟢 SR-010 Phantom      │ 📄 deed-2019-04.pdf [👁]        ││
│  │    Shell Corp Net      │ 👤 John Doe [→ entity]          ││
│  │    MEDIUM — OPEN       │                                 ││
│  │                        │ CHECKLIST                       ││
│  │                        │ ☐ Pull board minutes            ││
│  │                        │ ☐ Check Form 990 Part VI        ││
│  │                        │                                 ││
│  │                        │ TRIAGE                          ││
│  │                        │ [OPEN] [REVIEWED] [DISMISSED]   ││
│  │ j/k ↑↓  1/2/3 status  │ Note: [                       ] ││
│  │                        │ [Save]  [→ View Case]           ││
│  └────────────────────────┴─────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

**Key behaviors:**
- Cross-case default, filter by case when needed
- After saving triage, auto-advances to next signal
- Evidence document links have [👁] to open embedded PDF viewer
- Entity links navigate to entity detail view
- All filters reflected in URL (bookmarkable)
- Legal basis and investigation checklist on every signal

---

## 7. Referrals View (`/referrals`)

Cross-case referral tracking with pipeline visualization and report generation.

```
┌──────────────────────────────────────────────────────────────┐
│  REFERRALS                                   [+ New Referral]│
│  Filters: [Agency ▾] [Status ▾] [Case ▾]                    │
│                                                              │
│  PIPELINE                                                    │
│  ○ DRAFT(2) ──→ ● SUBMITTED(2) ──→ ● ACKNOWLEDGED(1) ──→ ✓ │
│                                                              │
│  ┌───────────┬────────────────┬──────────────┬──────┬──────┐│
│  │ Agency    │ Case           │ Status       │ Filed│      ││
│  ├───────────┼────────────────┼──────────────┼──────┼──────┤│
│  │ Ohio AG   │ Oak Hills Farm │ ● SUBMITTED  │ 2/15 │[View]││
│  │ IRS       │ Oak Hills Farm │ ○ DRAFT      │ —    │[Edit]││
│  │ FBI       │ Shell Corp Net │ ● SUBMITTED  │ 3/01 │[View]││
│  └───────────┴────────────────┴──────────────┴──────┴──────┘│
│                                                              │
│  [Generate Referral Report]  [Export Raw Data]               │
└──────────────────────────────────────────────────────────────┘
```

**Report Generation** (accessible here and from case referrals tab):
- [Generate Referral Report] → produces a formal Word document with:
  - Case summary and background
  - Evidence inventory with document descriptions
  - Signal summary with legal citations
  - Investigation timeline highlights
  - Investigator notes (relevant ones)
  - Referral submission details
- [Export Raw Data] → JSON/CSV of all case data for external use
- The generated doc is a starting point — investigator polishes externally before submission

---

## 8. Search View (`/search`)

Full search results with AI overview at top.

```
┌──────────────────────────────────────────────────────────────┐
│  SEARCH RESULTS for "who signed the oak hills deed"          │
│  47 results across 3 cases (0.8s)                            │
│  Filter: [All Types ▾] [Case ▾]                              │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ 🤖 AI OVERVIEW                                           ││
│  │                                                          ││
│  │ John Doe appears as the grantor on deed-2019-04.pdf in   ││
│  │ the Oak Hills Farm case. He is also listed as a board    ││
│  │ member of Oak Hills Conservancy (the grantee). The       ││
│  │ system has flagged this as SR-005 (Self-Dealing). The    ││
│  │ deed shows $0 consideration for Parcel 12-345678.001.    ││
│  │                                                          ││
│  │ Sources: deed-2019-04.pdf, board-roster.pdf              ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  📄 deed-2019-04.pdf — Oak Hills Farm — Relevance: 0.95     │
│  "...John Doe, as Grantor, hereby conveys..."               │
│                                                              │
│  ⚡ SR-005: Self-Dealing — Oak Hills Farm — Relevance: 0.91  │
│  "Board member appears as signatory on deed..."             │
│                                                              │
│  👤 John Doe — 2 cases — Relevance: 0.82                    │
│  "Appears in 7 documents across 2 cases."                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 9. Settings View (`/settings`)

Left sub-nav + right content panel.

### 9.1 Sub-navigation

| Section | Content |
|---------|---------|
| Appearance | Theme (Dark/Light/Auto), Accent color, Density |
| Keyboard | Shortcut reference (read-only) |
| Data | OCR and signal processing config |
| Connectors | Data source status and testing |
| External Search | Configure search launcher URLs |
| About | System info, database stats |

### 9.2 Appearance

| Setting | Options | Default | Storage |
|---------|---------|---------|---------|
| Theme | Dark / Light / Auto | Dark | localStorage |
| Accent Color | Blue / Purple / Green | Blue (#0f62fe) | localStorage |
| Density | Comfortable / Compact | Compact | localStorage |

**Light theme CSS variables:**
```css
[data-theme="light"] {
    --bg-ink: #f8f9fa;
    --bg-surface: #ffffff;
    --bg-raised: #f0f1f3;
    --text-primary: #1a1d23;
    --text-secondary: #5a5f6b;
    --border-subtle: #d0d3d9;
    --accent: #0f62fe;
    --danger: #da1e28;
    --warn: #d97706;
}
```

### 9.3 Connectors

Status dashboard for all six data connectors plus a [Test] button for each.

### 9.4 External Search Configuration

```
┌──────────────────────────────────────────────────────────────┐
│  EXTERNAL SEARCH LAUNCHERS                   [+ Add Source]  │
│                                                              │
│  These open in a new browser tab with the entity name        │
│  pre-filled as the search query.                             │
│                                                              │
│  ┌────────────────────┬─────────────────────────────────────┐│
│  │ Google News        │ https://news.google.com/search?q={q}││
│  │ Newspapers.com     │ https://newspapers.com/search?q={q} ││
│  │ Legacy.com         │ https://legacy.com/search?query={q} ││
│  │ Find-a-Grave       │ https://findagrave.com/search?q={q} ││
│  │ Ohio eCourts       │ https://...?name={q}                ││
│  │ PACER              │ https://pacer.uscourts.gov/...      ││
│  │ Tax Liens (Ohio)   │ https://...                         ││
│  └────────────────────┴─────────────────────────────────────┘│
│                                                              │
│  [+ Add Source] lets you add custom URL templates with {q}   │
│  as the query placeholder.                                   │
└──────────────────────────────────────────────────────────────┘
```

Launcher URLs are stored in localStorage (or a settings API). The `{q}` placeholder is replaced with the entity name. This list grows as new case types reveal new sources to check — easily added by the investigator without code changes.

---

## 10. Shared Features

### 10.1 Notes System

**Data model (new backend table):**

```
InvestigatorNote:
    id: UUID (primary key)
    case: FK → Case
    author: CharField (user initials/name)
    content: TextField
    linked_documents: M2M → Document
    linked_signals: M2M → Signal (via signal ID)
    linked_entities: JSONField (list of {type, id} refs)
    created_at: DateTimeField
    updated_at: DateTimeField
```

**Behaviors:**
- Created from the Notes tab or inline from signal triage, document view, entity view
- Searchable within a case (Notes tab search bar) and globally (AI search bar)
- Filterable by: linked document, author, date range
- Sortable by: date, document, author
- Appears on Timeline interleaved with system events
- Edits create a new version; old version preserved in audit log (immutable history)
- Notes carry into referral reports (can be selected during report generation)

### 10.2 Notification System

**Events that trigger notifications:**
- New signal(s) detected on a case
- OCR completed on a document
- Referral status changed (submitted, acknowledged, closed)
- Entity merged
- New detection created
- Bulk upload completed

**Storage:** Derived from AuditLog entries on the frontend, filtered by recency. Or a lightweight `Notification` table if we want read/unread state.

**UI:** Bell icon in header with unread count badge. Dropdown shows recent notifications. Click → navigate to source.

### 10.3 Processing Status Panel

When documents are uploading or being processed, a persistent panel appears at the bottom-right corner:

```
┌─────────────────────────────────────────┐
│  PROCESSING (3 of 12)              [✕]  │
│  ━━━━━━━━━━━━━░░░░░░░░░░ 25%           │
│                                         │
│  ✅ deed-2019-04.pdf — 3 entities found │
│  ✅ 990-2020.pdf — 2 entities found     │
│  ⏳ board-minutes.pdf — extracting...   │
│  ⬜ loan-docs.pdf — queued              │
│  ⬜ scan-batch-3.pdf — queued           │
│  ⬜ ... (7 more)                        │
│                                         │
│  [Collapse]                              │
└─────────────────────────────────────────┘
```

**On completion:**
```
┌─────────────────────────────────────────┐
│  UPLOAD COMPLETE                   [✕]  │
│                                         │
│  12 documents uploaded                  │
│  11 OCR completed successfully          │
│  1 OCR failed (file too large)          │
│  47 entities extracted                  │
│  3 new signals detected                 │
│                                         │
│  [View Documents]  [View Signals]       │
└─────────────────────────────────────────┘
```

**Backend requirement:** Async processing (Celery/Django-Q). Upload returns immediately with `ocr_status: PROCESSING`. Frontend polls `GET /api/cases/:id/documents/` to check status updates. WebSocket is the ideal long-term solution.

### 10.4 Embedded PDF Viewer

Clicking [👁] on any document opens a side panel viewer:

```
┌──────────────────────────────────────────────────────────────┐
│  [Current view content]              │  PDF VIEWER      [✕]  │
│                                      │                       │
│                                      │  deed-2019-04.pdf     │
│                                      │  ┌─────────────────┐  │
│                                      │  │                 │  │
│                                      │  │  [Rendered PDF   │  │
│                                      │  │   page content]  │  │
│                                      │  │                 │  │
│                                      │  │                 │  │
│                                      │  │                 │  │
│                                      │  │                 │  │
│                                      │  └─────────────────┘  │
│                                      │  Page 1 of 4          │
│                                      │  [< Prev] [Next >]    │
│                                      │                       │
│                                      │  [Open externally]    │
│                                      │  [Download]           │
└──────────────────────────────────────────────────────────────┘
```

**Features:**
- Slide-over panel from the right (doesn't navigate away from current view)
- PDF rendered via `<iframe>` with the document's file URL, or a JS PDF library (pdf.js)
- Page navigation
- [Open externally] opens in system viewer
- [Download] saves locally
- Viewer stays open while navigating signals/notes — lets investigator reference evidence while triaging

### 10.5 Report Generation

Two output modes accessible from the Referrals tab or Referrals view:

**Mode 1: Formal Referral Report (Word/PDF)**
Generated via backend endpoint. Contains:
- Cover page with case name, date, agency
- Executive summary (auto-generated from signals + notes)
- Evidence inventory table
- Signal summary with legal citations and investigator notes
- Investigation timeline (key events)
- Appendix: full document list, entity list

The generated document is a **starting point** — the investigator polishes it externally before submitting to the agency.

**Mode 2: Raw Data Export**
JSON and/or CSV export of:
- All case metadata
- All documents (metadata, not files)
- All signals with triage notes
- All detections with evidence snapshots
- All entities with relationships
- All investigator notes
- Full audit log

### 10.6 Investigation Roadmap / Checklist

Each signal type maps to a set of investigation steps. These appear in:
1. The signal detail panel (per-signal checklist)
2. The Dashboard (aggregated top items across all cases)
3. A potential future dedicated "Roadmap" view

**Framing:** "Investigations typically involve these steps:" — not "you should do this." Checklist items can be checked off per-case. State stored in a new `InvestigationChecklistItem` model or locally.

**Checklist items per signal type (examples):**

**SR-001 Deceased Signer:**
- ☐ Search Ohio death records / SSA Death Master File
- ☐ Request certified death certificate
- ☐ Verify signature date vs. date of death
- ☐ Identify notary who witnessed signature
- ☐ Check if power of attorney was in effect

**SR-005 Self-Dealing:**
- ☐ Pull board meeting minutes for vote on transaction
- ☐ Check Form 990 Part VI / Schedule L for disclosure
- ☐ Search county recorder for related party transfers
- ☐ Compare transaction value to fair market value
- ☐ Identify all board members at time of transaction

---

## 11. Keyboard Shortcuts

### Global (available everywhere)

| Keys | Action |
|------|--------|
| `Cmd+K` / `Ctrl+K` | Focus AI search bar |
| `Escape` | Close search / modal / panel |
| `G` then `D` | Go to Dashboard |
| `G` then `C` | Go to Cases |
| `G` then `E` | Go to Entities |
| `G` then `T` | Go to Triage |
| `G` then `R` | Go to Referrals |
| `G` then `S` | Go to Settings |
| `?` | Show keyboard shortcut reference |

### Triage / Signals

| Keys | Action |
|------|--------|
| `J` / `↓` | Next signal |
| `K` / `↑` | Previous signal |
| `1` | Set OPEN |
| `2` | Set REVIEWED |
| `3` | Set DISMISSED |
| `Cmd+S` / `Ctrl+S` | Save triage |
| `Enter` | Open parent case |

### Case List

| Keys | Action |
|------|--------|
| `J` / `↓` | Next case |
| `K` / `↑` | Previous case |
| `Enter` | Open selected case |
| `N` | New case modal |

All single-key shortcuts suppressed in `<input>`, `<textarea>`, `<select>`, `[contenteditable]`.

---

## 12. Backend API Additions Needed

| Endpoint | Method | Purpose | Priority |
|----------|--------|---------|----------|
| `GET /api/signals/` | GET | Cross-case signal list with filters | P0 — Triage view |
| `GET /api/referrals/` | GET | Cross-case referral list with filters | P0 — Referrals view |
| `GET /api/entities/` | GET | Cross-case entity list with type filter | P0 — Entity browser |
| `GET /api/entities/:type/:id/` | GET | Entity detail with all relationships | P0 — Entity detail |
| `POST /api/entities/:type/:id/merge/` | POST | Merge two entities (immutable log) | P1 — Entity editing |
| `PATCH /api/entities/:type/:id/` | PATCH | Edit entity fields (logged) | P1 — Entity editing |
| `GET /api/cases/:id/timeline/` | GET | Audit log entries for case | P1 — Timeline tab |
| `GET /api/cases/:id/notes/` | GET | Investigator notes for case | P1 — Notes tab |
| `POST /api/cases/:id/notes/` | POST | Create note with links | P1 — Notes tab |
| `PATCH /api/cases/:id/notes/:id/` | PATCH | Edit note (versioned) | P1 — Notes tab |
| `GET /api/activity-feed/` | GET | Recent audit log (cross-case) | P1 — Dashboard |
| `POST /api/ai-overview/` | POST | Synthesized search summary | P2 — AI search |
| `POST /api/cases/:id/report/` | POST | Generate referral report doc | P2 — Report gen |
| `GET /api/cases/:id/export/` | GET | Raw data export (JSON) | P2 — Data export |
| `GET /api/stats/` | GET | Aggregated counts for dashboard | P2 — Dashboard KPIs |
| `GET /api/notifications/` | GET | Recent notifications | P2 — Notification bell |

---

## 13. Component Inventory

### Layout Components

| Component | Purpose |
|-----------|---------|
| AppShell | Sidebar + header + search + breadcrumb + notifications + `<Outlet>` |
| Sidebar | Always-expanded nav with badges |
| AISearchBar | Persistent search with dropdown + AI overview |
| Breadcrumb | Dynamic navigation trail |
| NotificationBell | Bell icon + dropdown |
| ProcessingPanel | Bottom-right upload/OCR progress |

### View Components (one per route)

| Component | Route |
|-----------|-------|
| DashboardView | `/` |
| CasesListView | `/cases` |
| CaseDetailView | `/cases/:caseId` |
| EntityBrowserView | `/entities` |
| EntityDetailView | `/entities/:type/:id` |
| TriageView | `/triage` |
| ReferralsView | `/referrals` |
| SearchView | `/search` |
| SettingsView | `/settings` |

### Case Detail Tab Components

| Component | Tab |
|-----------|-----|
| DocumentsTab | Documents |
| SignalsTab | Signals |
| DetectionsTab | Detections |
| ReferralsTab | Referrals |
| NotesTab | Notes |
| TimelineTab | Timeline |

### Entity Components

| Component | Purpose |
|-----------|---------|
| EntityTable | Entity list with type/case filters |
| EntityHeader | Entity detail header with stats |
| EntityListView | List view of relationships |
| EntityGraphView | D3.js relationship graph |
| EntityMergeModal | Merge two entities with confirmation |
| ExternalSearchLaunchers | Grid of search buttons |

### Signal / Triage Components

| Component | Purpose |
|-----------|---------|
| SignalList | Scrollable queue list |
| SignalDetail | Detail panel with legal basis + checklist |
| SignalTriageControls | Status chips + note + save |
| InvestigationChecklist | Per-signal checklist items |
| LegalBasisSection | Statute citations with links |

### Document Components

| Component | Purpose |
|-----------|---------|
| DocumentTable | Sortable/filterable doc table |
| DocumentUpload | Drag-drop upload zone |
| PDFViewer | Slide-over embedded viewer |
| OcrStatusBadge | Status icon (✅ ⏳ ❌) |

### Notes Components

| Component | Purpose |
|-----------|---------|
| NotesList | Filtered/sorted note feed |
| NoteCard | Single note with linked items |
| NoteCreateForm | New note with entity/doc/signal tags |

### Dashboard Components

| Component | Purpose |
|-----------|---------|
| KpiCards | Clickable metric cards |
| RecentActivity | Activity feed widget |
| SeverityChart | Horizontal bar chart |
| RoadmapWidget | Top investigation checklist items |

### Shared UI Primitives

| Component | Status |
|-----------|--------|
| Button | EXISTS |
| FormInput | EXISTS |
| FormSelect | EXISTS |
| FormTextarea | EXISTS |
| StateBlock | EXISTS |
| EmptyState | EXISTS |
| ToastStack | EXISTS |
| DataTable | NEW — reusable sortable table |
| Modal | NEW — overlay dialog |
| TabBar | NEW — horizontal tab navigation |
| Badge | NEW — colored count/status pill |
| SlideOver | NEW — right-side panel overlay (PDF viewer, referral detail) |
| ConfirmDialog | NEW — "Are you sure?" |
| StatusDot | NEW — colored severity indicator |
| Tooltip | NEW — hover information |
| ThemeToggle | NEW — dark/light/auto |

---

## 14. Implementation Phases

### Phase A — Skeleton (2 sessions)
- Install React Router v6
- Create AppShell with always-expanded sidebar
- Breadcrumb component
- Route definitions (all views as placeholders)
- Theme toggle infrastructure (CSS variable swap, dark/light/auto)
- User identity setting (initials + role, stored in localStorage)

### Phase B — View Migration (3 sessions)
- Move CasesPanel → CasesListView (full-width table)
- Move CaseDetailPanel → CaseDetailView with tab routing
- Break CaseDetailPanel into: DocumentsTab, SignalsTab, DetectionsTab, ReferralsTab
- Wire existing API calls to new view structure
- Document upload stays in DocumentsTab (already designed)

### Phase C — Core New Features (4 sessions)
- Signal Triage Queue (cross-case) — needs backend `GET /api/signals/`
- Referrals cross-case view — needs backend `GET /api/referrals/`
- Entity browser + Entity detail (list view) — needs backend entity endpoints
- Notes system (model + tab + create/search/filter) — needs backend notes endpoints
- Timeline tab — needs backend timeline endpoint
- Kanban board for cases
- Notification bell (derived from audit log initially)

### Phase D — Advanced Features (4 sessions)
- AI search bar (quick-jump + full semantic + AI overview)
- Embedded PDF viewer (slide-over panel)
- Processing status panel (async upload/OCR tracking)
- Entity graph view (D3.js visualization)
- Legal basis + investigation checklist on signals
- External search launchers (configurable URL templates)
- Report generation (formal Word/PDF + raw export)
- Dashboard with all widgets including roadmap
- Settings page (all sections)
- Keyboard shortcut expansion (G+D, G+C, etc.)
- Entity merge functionality with immutable logging

### Phase E — Polish & Hardening (2 sessions)
- Light theme CSS variable set
- Command palette overlay
- Performance optimization (React Query if needed)
- Accessibility review
- Error states and edge cases
- Frontend test coverage

**Total estimated: ~15 sessions**

---

*This document is the single reference for all frontend design decisions. Update it as decisions evolve.*
