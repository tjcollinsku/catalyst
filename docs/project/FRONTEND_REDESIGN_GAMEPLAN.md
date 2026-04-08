# Catalyst Frontend Redesign — Comprehensive Game Plan

**Created:** 2026-04-02 (Session 26)
**Status:** PLANNING — Not yet started
**Scope:** Full-stack (frontend redesign + backend endpoints + AI integration)
**Design Philosophy:** Modeled after Palantir, Maltego, CrowdStrike, Microsoft Sentinel, NICE Actimize

---

## Design Decisions (Confirmed with Tyler)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary workflow | Both triage + narrative building | Some days scanning signals, other days connecting dots |
| Entity graph | Force-directed (D3.js) + timeline hybrid | Best for discovering unexpected connections in fraud networks |
| Graph location | Overview tab (centerpiece) | First thing investigator/employer sees when opening a case |
| Triage style | Pipeline status bar + filtered list | Splunk SOAR pattern — scales to 29 signal rules without overwhelming |
| Kanban | Rejected | Too many cards with 29 rules; pipeline bar gives same visibility with less clutter |
| AI presence | Inline badges + collapsible AI panel | CrowdStrike Charlotte AI pattern — AI woven throughout, not bolted on |
| Entity profile panel | Summary + expandable drill-down sections | Key facts at top, expandable sections for documents/financials/signals |
| Panel behavior | Slide-in from right, graph resizes smoothly | No overlap, no lost content — most polished interaction |
| Color scheme | Dark theme default + light toggle | "Mission control" analyst feel, with accessibility for daytime use |
| CSS architecture | CSS Modules (per-component) | 3,757-line single file is unsustainable; modules prevent conflicts |
| Build approach | New layout, migrate existing content | Most work but most cohesive result — investigation workspace, not tab collection |
| Timeline layers | Toggle-able (documents, signals, financials, entities) | Maximum power with ability to simplify by hiding layers |
| Escalation columns | 5-stage pipeline (New → Reviewing → Confirmed → Draft → Published) | Full visibility into where every item sits |
| Backend scope | Included in plan | Entity relationship endpoint, AI proxy endpoints, graph data API |
| AI scope | Included in plan | Auto-summarize, suggest connections, draft narratives |

---

## Architecture Overview

### Current State (What Exists)

```
AppShell (sidebar + topbar)
└── Routes
    ├── DashboardView (/)                  — KPI cards, activity feed
    ├── CasesListView (/cases)             — case list + kanban toggle
    ├── CaseDetailView (/cases/:id)        — 7 tab container
    │   ├── OverviewTab                    — KPI cards, coverage audit
    │   ├── DocumentsTab                   — doc list, upload, OCR
    │   ├── FinancialsTab                  — financial snapshots
    │   ├── SignalsTab                     — signal list + re-evaluate
    │   ├── DetectionsTab                  — detection cards
    │   ├── FindingsTab                    — finding CRUD
    │   └── ReferralsTab                   — referral management
    ├── EntityBrowserView (/entities)      — cross-case entity table
    ├── EntityDetailView (/entities/:t/:id)— entity dossier
    ├── TriageView (/triage)               — cross-case signal queue
    ├── ReferralsView (/referrals)         — cross-case referrals
    ├── SearchView (/search)               — global search
    └── SettingsView (/settings)           — preferences
```

**Stats:** 9 views, 7 case tabs, 12 UI components, 28 total components, 3,757 lines CSS, 638 lines API, 336 lines types.

### Target State (What We're Building)

```
AppShell (sidebar + topbar — enhanced with AI panel toggle)
└── Routes
    ├── DashboardView (/)                  — ENHANCED: mini case graph previews
    ├── CasesListView (/cases)             — KEEP: works fine
    ├── CaseDetailView (/cases/:id)        — REDESIGNED: investigation workspace
    │   ├── OverviewTab                    — REBUILT: entity graph + timeline + KPIs
    │   │   ├── KPI Bar (compact, top)
    │   │   ├── EntityGraph (D3 force-directed, main area)
    │   │   │   └── EntityProfilePanel (slide-in right, graph resizes)
    │   │   └── TimelineView (bottom, toggle-able layers)
    │   ├── DocumentsTab                   — ENHANCED: AI extraction badges
    │   ├── FinancialsTab                  — ENHANCED: anomaly highlighting
    │   ├── PipelineTab (NEW — replaces Signals+Detections+Findings)
    │   │   ├── PipelineStatusBar (5 columns with counts)
    │   │   ├── FilteredItemList (signals/detections/findings based on active stage)
    │   │   │   ├── SignalCard (with inline AI badge + quick-actions)
    │   │   │   ├── DetectionCard (with confidence scoring)
    │   │   │   └── FindingCard (with narrative preview)
    │   │   └── ItemDetailPanel (slide-in right — evidence, notes, escalation)
    │   └── ReferralsTab                   — KEEP: works fine
    ├── EntityBrowserView                  — KEEP
    ├── EntityDetailView                   — ENHANCED: mini relationship graph
    ├── TriageView                         — ENHANCED: uses new PipelineStatusBar
    ├── ReferralsView                      — KEEP
    ├── SearchView                         — KEEP
    ├── SettingsView                       — KEEP
    └── AIAssistantPanel (global overlay)  — NEW: collapsible case analysis panel
```

**Key structural change:** Signals, Detections, and Findings tabs merge into one **Pipeline tab**. The pipeline status bar shows the 5-stage flow; clicking a stage filters the list below to show items at that stage. This eliminates the "which tab do I look at?" confusion and makes the Signal → Detection → Finding flow a single visual story.

---

## Phase Breakdown

### Phase 1: Foundation (CSS Modules + Layout Infrastructure)

**Goal:** Migrate from single styles.css to CSS Modules. Build the new layout primitives (resizable panels, slide-in panels) that every subsequent phase depends on.

**Why first:** Every other phase needs these building blocks. Doing CSS migration later would mean rewriting styles twice.

#### 1A: CSS Module Migration

**What happens:** Each component gets its own `.module.css` file. The monolithic `styles.css` gets broken apart. Vite supports CSS Modules out of the box — no config needed.

| Task | Files |
|------|-------|
| Create shared design tokens file | `src/styles/tokens.css` (CSS custom properties for colors, spacing, shadows, typography — both dark and light theme values) |
| Create shared utility classes | `src/styles/utilities.css` (layout helpers, sr-only, truncate) |
| Create base/reset styles | `src/styles/base.css` (body, html, scrollbar, selection) |
| Migrate AppShell styles | `src/layouts/AppShell.module.css` |
| Migrate Sidebar styles | `src/components/ui/Sidebar.module.css` |
| Migrate each UI component | `src/components/ui/*.module.css` (12 files) |
| Migrate each view | `src/views/*.module.css` (9 files) |
| Migrate each case tab | `src/components/cases/*.module.css` (7 files) |
| Migrate each panel component | `src/components/*.module.css` (6 files) |
| Delete monolithic styles.css | After all modules verified working |
| Verify tsc + vite build clean | Zero errors, visual regression check |

**Estimated component count:** ~34 CSS module files + 3 shared style files = 37 files

#### 1B: Layout Primitives

**What happens:** Build the reusable panel/layout components that Phase 2-5 need.

| Component | Purpose | Behavior |
|-----------|---------|----------|
| `ResizablePanelLayout` | Two-panel layout where right panel can slide in/out | Graph area + profile panel. Smooth CSS transition on width change. |
| `SlidePanel` | Generic slide-in panel from right edge | Used for entity profile, signal detail, AI panel. Configurable width (300-500px). Close button + click-outside-to-close. |
| `PipelineStatusBar` | Horizontal bar showing 5 stages with counts | Clickable stages. Active stage highlighted. Animated count badges. |
| `CardList` | Filterable, sortable list of cards | Virtualized for performance (100+ signals). Sort by severity/date/confidence. |
| `SeverityBadge` | Consistent severity indicator | CRITICAL (red pulse), HIGH (red), MEDIUM (amber), LOW (blue), INFO (gray). Used everywhere. |
| `ConfidenceMeter` | Visual confidence score (0-100) | Horizontal bar fill + percentage. Color shifts with value. |
| `AIBadge` | Inline AI suggestion indicator | Small icon + one-line suggestion text. Click to expand. Subtle purple accent. |

**New directory structure:**
```
src/
├── styles/
│   ├── tokens.css          — design tokens (colors, spacing, shadows)
│   ├── base.css            — reset, body, scrollbar
│   └── utilities.css       — layout helpers
├── components/
│   ├── ui/                 — existing + new primitives
│   │   ├── ResizablePanelLayout.tsx + .module.css
│   │   ├── SlidePanel.tsx + .module.css
│   │   ├── PipelineStatusBar.tsx + .module.css
│   │   ├── CardList.tsx + .module.css
│   │   ├── SeverityBadge.tsx + .module.css
│   │   ├── ConfidenceMeter.tsx + .module.css
│   │   └── AIBadge.tsx + .module.css
```

**Dependencies:** None — this is the foundation layer.

---

### Phase 2: Entity Relationship Graph (Overview Tab)

**Goal:** Transform the Overview tab from static KPI cards into an interactive investigation map. This is the centerpiece of the entire redesign — the "wow" moment.

#### 2A: Backend — Entity Relationship Endpoint

**What happens:** New API endpoint that returns nodes (entities) and edges (relationships) for a case, ready for D3 to consume.

**Endpoint:** `GET /api/cases/<uuid>/graph/`

**Response shape:**
```json
{
  "nodes": [
    {
      "id": "uuid",
      "type": "person",           // person | organization | property | financial_instrument
      "label": "Jay Brunswick",
      "metadata": {
        "role_tags": ["PRESIDENT"],
        "signal_count": 4,
        "detection_count": 2,
        "doc_count": 7
      }
    }
  ],
  "edges": [
    {
      "source": "uuid-person",
      "target": "uuid-org",
      "relationship": "OFFICER_OF",    // OFFICER_OF, SIGNED, OWNS, TRANSFERRED_TO, etc.
      "label": "President",
      "weight": 3,                     // number of documents supporting this connection
      "documents": ["uuid-doc-1", "uuid-doc-2"]
    }
  ],
  "stats": {
    "total_nodes": 15,
    "total_edges": 22,
    "node_types": { "person": 5, "organization": 3, "property": 4, "financial_instrument": 3 }
  }
}
```

**Backend work required:**
| Task | Detail |
|------|--------|
| Build `api_case_graph()` view | Queries Person, Organization, Property, FinancialInstrument for the case |
| Derive edges from junction tables | `PersonOrganization` → OFFICER_OF edges. `PersonDocument` + `OrgDocument` → CO_APPEARS_IN edges. `PropertyTransaction` → TRANSFERRED_TO/FROM edges. `Relationship` model → direct edges. |
| Add signal/detection counts per entity | Annotate each node with how many signals reference it |
| Add edge weight calculation | Count supporting documents per relationship |
| Wire URL pattern | `path("api/cases/<uuid:pk>/graph/", ...)` |
| Add to api.ts | `fetchCaseGraph(caseId)` function + TypeScript types |

#### 2B: Frontend — Force-Directed Graph Component

**What happens:** D3.js force-directed graph renders on the Overview tab. Entities are nodes, relationships are edges. Click a node to highlight its connections and open the profile panel.

| Component | Purpose |
|-----------|---------|
| `EntityGraph.tsx` | Main D3 canvas. Renders nodes + edges. Handles zoom, pan, click, hover. |
| `EntityGraph.module.css` | Graph container, node styling, edge styling, hover effects |
| `graphHelpers.ts` | D3 force simulation config, node color/size by type, edge styling by relationship type |

**Node visual encoding:**
- Shape: Circle (person), Square (organization), Diamond (property), Triangle (financial instrument)
- Size: Proportional to signal count (more signals = bigger node = "this entity is interesting")
- Color: By entity type (blue=person, green=org, orange=property, purple=financial)
- Border: Red glow if entity has HIGH/CRITICAL signals
- Label: Entity name, truncated to ~20 chars

**Edge visual encoding:**
- Thickness: By weight (more supporting documents = thicker line)
- Color: Gray default, red if the relationship triggered a signal
- Style: Solid for confirmed relationships, dashed for AI-suggested
- Label: Relationship type on hover
- Arrowhead: Direction of relationship (Brunswick → Example Charity = officer direction)

**Interactions:**
- **Click node:** Highlight node + all connected edges + connected nodes. Dim everything else. Open EntityProfilePanel on right.
- **Click edge:** Show edge detail tooltip (relationship type, supporting documents, dates).
- **Hover node:** Show tooltip with name, type, signal count.
- **Drag node:** Reposition node. Simulation adjusts. Node stays where dropped.
- **Zoom/Pan:** Mouse wheel to zoom, click-drag on background to pan.
- **Double-click node:** Navigate to full EntityDetailView for that entity.

**npm dependency:** `d3` (already available in our React artifact environment, but need to install for the actual project: `npm install d3 @types/d3`)

#### 2C: Frontend — Entity Profile Panel

**What happens:** When you click an entity on the graph, a panel slides in from the right. The graph smoothly resizes to make room. Panel shows entity summary + expandable drill-down sections.

| Component | Purpose |
|-----------|---------|
| `EntityProfilePanel.tsx` | Profile panel content — summary header + expandable sections |
| `EntityProfilePanel.module.css` | Panel layout, section styling, expand/collapse animations |

**Panel layout (350px wide):**
```
┌─────────────────────────────┐
│ ✕ Close                     │
│                             │
│ 👤 Jay Brunswick            │
│ Person · President          │
│ ● 4 signals  ● 2 detections│
│                             │
│ ▼ Organizations (2)         │
│   Example Charity In His Name Inc   │
│   Example Township Vol Fire Co        │
│                             │
│ ▼ Documents (7)             │
│   FY2019_990.pdf            │
│   FY2020_990.pdf            │
│   ... (clickable → doc tab) │
│                             │
│ ▼ Signals (4)               │
│   SR-003 Rapid Flip — HIGH  │
│   SR-012 Family Net — MED   │
│   ... (clickable → pipeline)│
│                             │
│ ▼ Financial Summary         │
│   Total compensation: $0    │
│   Orgs total revenue: $282K │
│                             │
│ ▼ AI Insights               │
│   "Appears in 4 docs across │
│    2 orgs. Possible related │
│    party pattern detected." │
│                             │
│ [View Full Profile →]       │
└─────────────────────────────┘
```

**Each section is expandable/collapsible.** Default: Organizations and Signals expanded, others collapsed.

#### 2D: Frontend — Overview Tab Rebuild

**What happens:** Rebuild OverviewTab to center on the graph, with KPIs as a compact row above and timeline below.

**Layout:**
```
┌──────────────────────────────────────────────────────────────────┐
│  Cases: 1  │  Documents: 30  │  Entities: 15  │  Signals: 12   │  ← KPI bar (compact)
├──────────────────────────────────────────────────────────────────┤
│                                              │                   │
│                                              │  Entity Profile   │
│          Entity Relationship Graph           │  Panel            │
│          (D3 force-directed)                 │  (slide-in)       │
│                                              │                   │
│                                              │                   │
├──────────────────────────────────────────────────────────────────┤
│  Timeline  [📄 Docs] [⚡ Signals] [💰 Financial] [👤 Entities]  │  ← layer toggles
│  ──●────────●──●─────────●────●──────────●────────────●──────── │
│  2019      2020        2021              2022         2023       │
└──────────────────────────────────────────────────────────────────┘
```

---

### Phase 3: Timeline View

**Goal:** Interactive timeline below the entity graph showing when events occurred, with toggle-able layers and synchronized filtering with the graph.

#### 3A: Timeline Component

| Component | Purpose |
|-----------|---------|
| `TimelineView.tsx` | D3 or custom SVG timeline. Horizontal axis = time. Events rendered as markers. |
| `TimelineView.module.css` | Timeline rail, markers, layer toggles, brush selection |
| `timelineHelpers.ts` | Date parsing, layer filtering, event clustering |

**Layers (each toggle-able):**
| Layer | Icon | Data Source | Marker Style |
|-------|------|-------------|--------------|
| Documents | 📄 | `documents[].uploaded_at` | Blue circle |
| Signals | ⚡ | `signals[].detected_at` | Red/amber/green triangle (by severity) |
| Financial Events | 💰 | `financial_snapshots[].tax_year` | Green diamond |
| Entity Appearances | 👤 | First document date per entity | Purple square |

**Interactions:**
- **Brush selection:** Click-drag on timeline to select a date range. Graph filters to show only entities/edges active in that range.
- **Click marker:** Show tooltip with event details. If it's a document, offer "View Document" link.
- **Zoom:** Scroll to zoom timeline in/out (year → month → day granularity).
- **Hover marker:** Highlight corresponding node on graph (if entity-related).

#### 3B: Graph ↔ Timeline Synchronization

**What happens:** Selecting on the graph filters the timeline; selecting on the timeline filters the graph. Two-way sync.

| Action | Graph Effect | Timeline Effect |
|--------|-------------|----------------|
| Click node on graph | Node + connections highlight | Timeline highlights events involving that entity |
| Brush date range on timeline | Graph dims entities not active in range | Timeline zooms to selected range |
| Click timeline marker | Corresponding entity highlights on graph | Marker expands with detail |
| Clear selection | Graph resets to full view | Timeline resets to full range |

**Implementation:** Shared React state (context or lifted state in OverviewTab) manages `selectedEntityId`, `selectedDateRange`, `highlightedNodes[]`. Both components read and write to this state.

---

### Phase 4: Pipeline Triage (Signal → Detection → Finding)

**Goal:** Replace the separate Signals, Detections, and Findings tabs with a unified Pipeline tab showing the entire 5-stage workflow in one view.

#### 4A: Pipeline Status Bar

**What happens:** Horizontal bar at the top of the Pipeline tab showing counts per stage. Click a stage to filter.

```
┌──────────────────────────────────────────────────────────────────┐
│  ● NEW (12)  →  🔍 REVIEWING (5)  →  ✓ CONFIRMED (3)  →  📝 DRAFT (2)  →  📋 PUBLISHED (1)  │
└──────────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Click a stage → list below filters to show only items at that stage
- Active stage has highlighted background + bold text
- Counts update in real-time when items move between stages
- Arrow connectors between stages show the flow direction
- "All" option to show everything

**Mapping from current models to pipeline stages:**
| Pipeline Stage | Model | Status Value |
|----------------|-------|-------------|
| NEW | Signal | `OPEN` |
| REVIEWING | Signal | `UNDER_REVIEW` (new status needed) |
| CONFIRMED | Detection | `CONFIRMED` |
| DRAFT | Finding | `DRAFT` |
| PUBLISHED | Finding | `REVIEWED` or `INCLUDED_IN_MEMO` |

**Backend change needed:** Add `UNDER_REVIEW` to `SignalStatus` choices. Currently only has OPEN, CONFIRMED, DISMISSED.

#### 4B: Signal Cards (Pipeline Stage: NEW + REVIEWING)

**What happens:** Each signal appears as a card in the filtered list with quick-action buttons and inline AI badges.

```
┌─ SR-003 Rapid Property Flip ─────────── HIGH ── 2 days ago ─┐
│                                                               │
│  123 Main St transferred twice within 90 days.                │
│  Trigger doc: FY2020_990_DoGood.pdf                          │
│                                                               │
│  🤖 AI: "Pattern matches rapid asset flipping commonly seen   │
│      in nonprofit self-dealing schemes. Cross-reference with  │
│      SR-018 (Related Party TX)."                              │
│                                                               │
│  [📄 View Doc]  [🔍 Start Review]  [✓ Confirm]  [✕ Dismiss] │
└───────────────────────────────────────────────────────────────┘
```

**Quick-action buttons:**
| Button | Action | Result |
|--------|--------|--------|
| View Doc | Opens PDF viewer or navigates to document | — |
| Start Review | Changes signal status to UNDER_REVIEW | Card moves to REVIEWING column |
| Confirm | Escalates signal → creates Detection | Card moves to CONFIRMED column |
| Dismiss | Changes signal status to DISMISSED | Card disappears from active view |

**Clicking the card body** (not a button) opens the detail panel on the right with full evidence, investigator notes textarea, and the escalation form.

#### 4C: Detection Cards (Pipeline Stage: CONFIRMED)

```
┌─ RELATED_PARTY_TX ──────────── HIGH ── Confidence: 92% ─────┐
│                                                               │
│  Multiple transactions between Example Charity Inc and entities       │
│  controlled by the same officers.                             │
│                                                               │
│  Evidence: FY2019_990.pdf, FY2020_990.pdf, Deed_123Main.pdf  │
│  Entities: Jay Brunswick, Example Charity Inc, Example Township Fire Co         │
│                                                               │
│  Severity ████████░░  HIGH        Confidence █████████░ 92%   │
│                                                               │
│  [📝 Draft Finding]  [↩ Revert to Signal]                    │
└───────────────────────────────────────────────────────────────┘
```

**New: Dual-axis scoring** — Severity (how bad) + Confidence (how certain). Visual bars for each.

#### 4D: Finding Cards (Pipeline Stage: DRAFT + PUBLISHED)

```
┌─ Finding: Self-Dealing Property Transfers ── DRAFT ──────────┐
│                                                               │
│  Investigation revealed a pattern of property transfers       │
│  between Example Charity In His Name Inc and entities controlled...   │
│  [Read more →]                                                │
│                                                               │
│  Linked: 3 detections, 5 documents, 4 entities                │
│  Legal refs: ORC §1702.30, IRC §4941                          │
│                                                               │
│  [✏️ Edit Narrative]  [📋 Publish]  [🗑 Delete]               │
└───────────────────────────────────────────────────────────────┘
```

#### 4E: Item Detail Panel

**What happens:** Click any card body to open a detail slide-in panel on the right (same pattern as entity profile panel). Panel shows full evidence, notes, and escalation controls.

**Panel sections (for a Signal):**
1. **Header:** Rule ID, severity badge, status, detected date
2. **Summary:** Full detected_summary text
3. **Trigger Document:** Document name + "View" button + extraction preview
4. **Trigger Entity:** Entity name + link to graph node
5. **AI Analysis:** AI-generated explanation of why this signal matters
6. **Related Signals:** Other signals involving the same entities/documents
7. **Investigator Notes:** Editable textarea (auto-saves)
8. **Actions:** Escalate / Dismiss / Change severity
9. **Audit Trail:** Who created, reviewed, when

---

### Phase 5: AI Integration

**Goal:** AI-powered assistance at every stage — summarize evidence, suggest connections, draft narratives. All AI calls go through Django backend (API key security).

#### 5A: Backend — AI Proxy Endpoints

| Endpoint | Purpose | Request | Response |
|----------|---------|---------|----------|
| `POST /api/cases/<uuid>/ai/summarize/` | Summarize evidence for a signal or entity | `{ target_type: "signal"/"entity", target_id: "uuid" }` | `{ summary: "...", confidence: 0.85 }` |
| `POST /api/cases/<uuid>/ai/connections/` | Suggest entity connections | `{ entity_id: "uuid" }` | `{ suggestions: [{ from, to, relationship, reasoning, confidence }] }` |
| `POST /api/cases/<uuid>/ai/narrative/` | Draft finding narrative | `{ detection_ids: ["uuid", ...], tone: "formal"/"technical" }` | `{ narrative: "...", key_points: [...], legal_refs: [...] }` |
| `POST /api/cases/<uuid>/ai/ask/` | Free-form case question | `{ question: "What connects Jay Brunswick to the property transfers?" }` | `{ answer: "...", sources: [{ doc_id, excerpt }] }` |

**Backend implementation pattern:**
- Each endpoint gathers relevant case data (documents, entities, signals, financials)
- Builds a structured prompt with the evidence
- Calls Claude API via existing backend integration
- Returns structured JSON response
- Caches results for 10 minutes (same question = cached answer)
- Rate limiting: 10 AI calls per minute per case

#### 5B: Frontend — Inline AI Badges

**What happens:** Signal cards, detection cards, and entity profiles show a small AI badge with a one-line insight. The insight is fetched on component mount (with caching).

| Component | File |
|-----------|------|
| `AIBadge` | Already defined in Phase 1B |
| AI badge integration into SignalCard | In each card component |
| AI badge integration into EntityProfilePanel | In profile panel |

**Badge behavior:**
- Shows a 🤖 icon + one-line summary
- Click to expand to full AI analysis
- Loading state: subtle shimmer animation while AI responds
- Error state: "AI unavailable" text (doesn't break the card)
- Cache: Badge content cached per item, refreshes when item changes

#### 5C: Frontend — AI Assistant Panel

**What happens:** Global collapsible panel accessible from the topbar. Case-aware — when you're in a case, AI has full context about that case's documents, entities, and signals.

| Component | Purpose |
|-----------|---------|
| `AIAssistantPanel.tsx` | Collapsible sidebar panel with chat-like interface |
| `AIAssistantPanel.module.css` | Panel styling, message bubbles, input area |

**Panel layout:**
```
┌──────────── AI Assistant ──────── ✕ ─┐
│                                       │
│  🤖 I'm analyzing the Example Charity case.  │
│     Ask me anything about the         │
│     evidence or entities.             │
│                                       │
│  You: What connects Jay Brunswick     │
│       to the property transfers?      │
│                                       │
│  🤖 Jay Brunswick appears as          │
│     President of Example Charity Inc in       │
│     FY2019 and FY2020 990 filings.   │
│     Three properties were             │
│     transferred to entities where...  │
│     [View sources →]                  │
│                                       │
│  ┌─────────────────────────────────┐ │
│  │ Ask about this case...          │ │
│  └─────────────────────────────────┘ │
│                                       │
│  Quick actions:                       │
│  [Summarize case] [Find connections]  │
│  [Draft narrative] [Coverage gaps]    │
└───────────────────────────────────────┘
```

**Features:**
- **Case-aware context:** AI automatically knows which case you're viewing
- **Source linking:** AI responses include clickable links to source documents and entities
- **Quick action buttons:** Pre-built prompts for common investigation tasks
- **Conversation history:** Messages persist during session (not across sessions)
- **Draft narrative mode:** AI writes a Finding narrative, presents for editing, then you can save directly as a new Finding

---

### Phase 6: Polish and Demo-Ready Finish

**Goal:** Bring everything to portfolio-quality. Animations, loading states, responsive design, dark/light theme refinement.

#### 6A: Theme System Overhaul

| Task | Detail |
|------|--------|
| Expand design tokens | Add tokens for graph colors, timeline colors, AI panel colors, severity colors |
| Dark theme refinement | Deep charcoal backgrounds (#1a1a2e), subtle borders (#2d2d44), bright accents |
| Light theme refinement | Clean whites/light grays, darker text, same accent colors but adjusted for contrast |
| Theme toggle | Existing useTheme hook + new tokens. Toggle in topbar and settings. |
| Transition animation | Smooth 200ms color transition when switching themes |

#### 6B: Animations and Micro-interactions

| Animation | Where | Implementation |
|-----------|-------|---------------|
| Graph node entrance | Overview graph | Nodes fade in with scale-up on initial load |
| Edge draw | Overview graph | Edges animate along path from source to target |
| Panel slide-in | Entity profile, detail panel | CSS transform + transition (300ms ease-out) |
| Graph resize | When panel opens/closes | CSS transition on width (300ms ease-out) |
| Pipeline count update | Status bar | Count animates up/down when items move stages |
| Card hover | All cards | Subtle lift (translateY -2px) + shadow increase |
| AI typing indicator | AI panel + badges | Three-dot pulse animation while AI responds |
| Severity pulse | CRITICAL severity badges | Subtle red pulse animation (attention-drawing) |
| Timeline brush | Timeline selection | Smooth highlight of selected range |
| Toast notifications | Global | Slide-in from top-right, auto-dismiss after 5s |

#### 6C: Loading and Empty States

| State | Component | Display |
|-------|-----------|---------|
| Graph loading | EntityGraph | Skeleton shimmer in graph area + "Building investigation map..." |
| Graph empty (no entities) | EntityGraph | Illustration + "Upload documents to populate the investigation map" |
| Timeline loading | TimelineView | Horizontal shimmer bar |
| Timeline empty | TimelineView | "No events to display. Upload documents to build a timeline." |
| Pipeline loading | PipelineTab | Skeleton cards (3 placeholder cards) |
| Pipeline empty (no signals) | PipelineTab | "No signals detected. Upload documents and run signal analysis." |
| AI panel loading | AIAssistantPanel | Typing indicator animation |
| AI panel error | AIAssistantPanel | "Unable to reach AI service. Check your API key in settings." |

#### 6D: Accessibility

| Feature | Implementation |
|---------|---------------|
| Graph keyboard navigation | Tab to move between nodes, Enter to select, Escape to deselect |
| Screen reader support for graph | ARIA labels on nodes/edges, live region for selection changes |
| Color-blind safe palette | Severity uses shape + color (not color alone). Tested with deuteranopia simulator. |
| Focus management for panels | Focus trapped in open panel, returns to trigger on close |
| Reduced motion | `prefers-reduced-motion` disables graph animations, panel slides become instant |

---

## New Backend Endpoints Summary

| # | Endpoint | Method | Purpose | Phase |
|---|----------|--------|---------|-------|
| 1 | `/api/cases/<uuid>/graph/` | GET | Entity nodes + relationship edges for D3 graph | 2A |
| 2 | `/api/cases/<uuid>/ai/summarize/` | POST | AI evidence summary for signal or entity | 5A |
| 3 | `/api/cases/<uuid>/ai/connections/` | POST | AI-suggested entity connections | 5A |
| 4 | `/api/cases/<uuid>/ai/narrative/` | POST | AI-drafted finding narrative | 5A |
| 5 | `/api/cases/<uuid>/ai/ask/` | POST | Free-form AI case question | 5A |

**Backend model changes:**
| Change | Detail | Phase |
|--------|--------|-------|
| Add `UNDER_REVIEW` to SignalStatus | New status for the "Reviewing" pipeline stage | 4A |
| Add AI response cache model (optional) | Cache AI responses to reduce API costs | 5A |

---

## New Frontend Files Summary

| Phase | New Files | Modified Files |
|-------|-----------|---------------|
| 1A (CSS Modules) | ~37 .module.css files, 3 shared style files | All .tsx files (import changes) |
| 1B (Layout Primitives) | 7 new components + 7 .module.css | — |
| 2 (Graph) | EntityGraph.tsx, EntityProfilePanel.tsx, graphHelpers.ts, OverviewTab rebuild | api.ts, types.ts |
| 3 (Timeline) | TimelineView.tsx, timelineHelpers.ts | OverviewTab.tsx |
| 4 (Pipeline) | PipelineTab.tsx, SignalCard.tsx, DetectionCard.tsx, FindingCard.tsx, ItemDetailPanel.tsx | App.tsx (routes), CaseDetailView.tsx (tabs), api.ts, types.ts |
| 5 (AI) | AIAssistantPanel.tsx, aiHelpers.ts | AppShell.tsx (panel toggle), multiple card components (badge integration) |
| 6 (Polish) | — | tokens.css (expanded), multiple components (animations, states) |

**Estimated total new files:** ~60 files
**Estimated total modified files:** ~25 files

---

## npm Dependencies to Add

| Package | Purpose | Phase |
|---------|---------|-------|
| `d3` | Force-directed graph + timeline rendering | 2 |
| `@types/d3` | TypeScript types for D3 | 2 |

That's it. We keep the dependency footprint minimal. D3 is the only new package — everything else (CSS Modules, React context, animations) uses what we already have.

---

## Build Order and Dependencies

```
Phase 1A: CSS Module Migration
    ↓  (no dependency — can start immediately)
Phase 1B: Layout Primitives
    ↓  (depends on 1A for tokens.css)
Phase 2A: Backend graph endpoint
Phase 2B: Entity Graph component      ←── depends on 1B (ResizablePanelLayout) + 2A (data)
Phase 2C: Entity Profile Panel         ←── depends on 1B (SlidePanel) + 2B (click handler)
Phase 2D: Overview Tab rebuild         ←── depends on 2B + 2C
    ↓
Phase 3A: Timeline component           ←── depends on 1B + 2D (shared state)
Phase 3B: Graph ↔ Timeline sync        ←── depends on 2B + 3A
    ↓
Phase 4A: Pipeline Status Bar          ←── depends on 1B
Phase 4B-D: Pipeline Cards             ←── depends on 4A + 1B (CardList, SlidePanel)
Phase 4E: Item Detail Panel            ←── depends on 4B-D
    ↓
Phase 5A: Backend AI endpoints         ←── independent (can parallel with Phase 4)
Phase 5B: Inline AI badges             ←── depends on 5A + Phase 4 cards
Phase 5C: AI Assistant Panel           ←── depends on 5A + 1B (SlidePanel)
    ↓
Phase 6: Polish                        ←── depends on everything above
```

**Parallelization opportunities:**
- Phase 2A (backend) can run in parallel with Phase 1B (frontend)
- Phase 5A (backend AI) can run in parallel with Phase 4 (frontend pipeline)

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| D3 graph performance with 100+ nodes | Medium | High | Implement node clustering for large graphs. Virtualize if needed. Test with Example Charity case data (15+ entities). |
| AI API cost with frequent calls | Medium | Medium | Cache responses for 10 min. Batch requests. Rate limit 10/min/case. |
| CSS Module migration breaks existing styles | Low | High | Migrate one component at a time. Visual regression check after each. Keep old styles.css as fallback until fully migrated. |
| Graph ↔ Timeline sync complexity | Medium | Medium | Start with one-way sync (graph → timeline), add reverse later if needed. |
| Scope creep | High | High | Each phase has a clear "done" definition. Ship each phase before starting next. |

---

## Definition of Done (Per Phase)

| Phase | Done When |
|-------|-----------|
| 1 | All components use CSS Modules. `styles.css` deleted. `tsc --noEmit` + `vite build` clean. Visual parity with current UI. |
| 2 | Entity graph renders on Overview tab with real case data. Click node → profile panel slides in, graph resizes. All entity types displayed with correct shapes/colors. |
| 3 | Timeline renders below graph with all 4 layers. Brush selection on timeline filters graph. Click graph node highlights timeline events. |
| 4 | Pipeline tab replaces Signals+Detections+Findings tabs. Status bar shows accurate counts. Quick-action buttons work (confirm/dismiss/escalate). Signal → Detection → Finding flow completes end-to-end in UI. |
| 5 | AI badges appear on signal cards and entity profiles. AI panel opens from topbar. "Summarize," "Suggest connections," and "Draft narrative" all return useful results. |
| 6 | Dark and light themes polished. Animations smooth. Loading/empty states for all async content. Keyboard navigable. Employer-ready. |

---

## Estimated Effort

| Phase | Estimated Sessions | Complexity |
|-------|-------------------|------------|
| 1A: CSS Migration | 2-3 sessions | Medium (repetitive but important) |
| 1B: Layout Primitives | 1-2 sessions | Medium |
| 2: Entity Graph | 3-4 sessions | High (D3 + backend) |
| 3: Timeline | 2-3 sessions | High (D3 + sync logic) |
| 4: Pipeline Triage | 2-3 sessions | Medium-High |
| 5: AI Integration | 2-3 sessions | High (backend + frontend + prompt engineering) |
| 6: Polish | 2-3 sessions | Medium |
| **Total** | **14-21 sessions** | |

---

## What This Delivers

When complete, Catalyst will have:

1. **An interactive investigation map** that visualizes the fraud network — click any person, org, property, or financial instrument to see how it connects to everything else
2. **A synchronized timeline** showing how the fraud evolved over time, with toggle-able layers for different event types
3. **A unified triage pipeline** that shows Signal → Detection → Finding as a single visual flow, with quick-action buttons for rapid investigation
4. **AI assistance woven throughout** — inline insights on every card, plus a conversational AI panel for deep case analysis and narrative drafting
5. **A polished, demo-ready UI** with dark/light themes, smooth animations, and professional visual design that stands out in a portfolio

This puts Catalyst in the same visual and functional category as Palantir, Maltego, and CrowdStrike — but purpose-built for nonprofit fraud investigation.
