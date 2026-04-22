# Async Research Frontend + AI Pattern Augmentation — Design

**Date:** 2026-04-21
**Status:** Approved, ready to plan
**Prior art:** [2026-04-20-async-research-jobs-design.md](2026-04-20-async-research-jobs-design.md) (Track 1 consumes the backend this spec shipped)

---

## Problem

Two distinct but sequenced problems.

**Problem 1 — Research tab is broken.** Session 35 moved four slow research
endpoints (IRS name search, IRS `fetch_xml`, Ohio AOS, County Parcel) onto a
Django-Q2 async worker. POSTs now return `202 Accepted + {job_id, status_url}`.
The React frontend still expects a synchronous response shape and throws
`0 is not iterable` on mount. Until the frontend is taught to poll, the async
backend is unreachable from the UI.

**Problem 2 — Signal rules are brittle string-matchers.** The 14 signal rules
are the deterministic baseline of the fraud detection layer. They are good at
narrow numeric checks (purchase-price-vs-assessed, revenue spike,
missing-Schedule-L) and bad at the connective reasoning that actually moves an
investigation forward: "Karen Example on this 990 is the same person as K. S.
Example on this deed," or "you have three deeds on one parcel but no 2019
filing — pull it." Adding more rules does not fix this; every new investigation
pattern would require new hand-written constraints. The investigator needs an
augmentation layer that can read across documents and surface patterns the
rules can't express.

## Goal

Deliver both tracks, in order, with Track 1 unblocking Track 2.

1. Make the Research tab usable again by consuming the `202 + poll` backend
   contract from Session 35.
2. Add an on-demand AI pattern augmentation pass that reads the case and
   produces candidate Findings labeled as AI-generated, triaged through the
   existing Pipeline tab workflow.

## Non-goals

- Rebuilding the Research tab UI. Visual design stays as-is; only the
  fetching layer changes.
- Replacing the rule engine. The 14 rules remain the deterministic baseline.
  AI augments, it does not replace.
- AI as a chat copilot. There is no always-on chat pane in this design.
  (The existing `/ai/summarize/`, `/ai/connections/`, `/ai/ask/` endpoints
  are untouched; they remain triage aids.)
- Agentic / tool-use AI that requests specific documents on its own. That is
  Strategy D in the brainstorm and is deferred until the single-shot Strategy
  B pass proves valuable.
- Automatic re-runs on document upload or finding change. This is strictly
  on-demand — the investigator clicks "Run AI Analysis" when they're ready.
- AI mutating or deleting existing Findings. AI only *adds* Findings.
- Per-entity or per-document AI badges. One unified surface (the Pipeline
  tab) is the AI findings home.
- Touching the two sync research endpoints (Ohio SOS local CSV, Recorder URL
  builder). They already work and stay as-is.

## Principle

**AI highlights patterns and points where they lead. Humans do the accusing.**

Every AI-produced Finding must: cite source documents by ID, carry an
`evidence_weight` of `SPECULATIVE` or `DIRECTIONAL` by default (never
`DOCUMENTED` or `TRACED` — those require human confirmation), include a
plain-language rationale, and suggest a concrete next action
("pull 2019 deed for parcel 12345"). No AI-generated Finding ever asserts
fraud. The referral package exporter already filters on
`status=CONFIRMED`, so AI findings are invisible to the final deliverable
until an investigator confirms them.

---

## Track 1 — Research Tab async wiring

### Architecture

A single new hook, `useAsyncJob`, centralizes the POST → poll → resolve
cycle. The Research tab's four async search surfaces each instantiate the
hook with their endpoint and render state-driven UI (idle / running /
success / failed). Reattach-on-mount reads
`GET /api/cases/<id>/jobs/?limit=5` and resumes polling any in-flight job.

### Components

**`frontend/src/hooks/useAsyncJob.ts`** (new)
- **What it does:** Encapsulates the 202 + poll contract.
- **Interface:** `useAsyncJob(options: { postUrl, pollUrl?: (id) => string })` returns
  `{ status: 'idle' | 'queued' | 'running' | 'success' | 'failed', result, error, run(body), reattach(jobId), cancel() }`.
- **Depends on:** `fetch`, React hooks, existing CSRF helper.
- **Behavior:**
  - `run(body)` POSTs, reads `{job_id, status_url}`, transitions to `queued`, starts polling.
  - Polls every 2000 ms. Transitions to `running` on first `RUNNING` response.
  - Resolves to `success` with `result` payload when `status=SUCCESS`.
  - Resolves to `failed` with `error_message` when `status=FAILED`.
  - Cleans up poll interval on unmount or `cancel()`.
  - `reattach(jobId)` skips the POST and starts polling directly.

**`frontend/src/components/cases/ResearchTab.tsx`** (modified)
- Each of the four async searches (IRS name, IRS fetch_xml, Ohio AOS, County
  Parcel) swaps its current fetch call for a `useAsyncJob` instance.
- Adds spinner + status line during `queued` / `running`:
  > "Searching IRS filings… (typically 20–90 seconds)"
- Existing result rendering (the table / list layer) reads from
  `result` once `status=success`. Zero visual change in the success path.
- On tab mount, calls `GET /api/cases/<id>/jobs/?limit=5`. For any returned
  job where `status in (QUEUED, RUNNING)`, calls `hook.reattach(job.id)` on
  the matching surface so the user doesn't lose work by switching tabs.
- Existing `0 is not iterable` crash: root-caused during implementation.
  Most likely the current code destructures a paginated response shape
  that changed; fixed as part of the same pass.

**Ohio SOS and Recorder panels:** untouched. Still synchronous.

### Data flow

```
User clicks "Search IRS"
        ↓
useAsyncJob.run({name: "Do Good Foundation"})
        ↓
POST /api/cases/<id>/research/irs/    →   202 {job_id: "abc..."}
        ↓
poll GET /api/jobs/abc/  every 2s
        ↓
   status=QUEUED → RUNNING → SUCCESS
        ↓
result = {filings: [...]}  ←  SearchJob.result
        ↓
existing IRS result renderer
```

### Testing

- Hook unit tests (Vitest): POST happy path, POST error, poll SUCCESS, poll
  FAILED, poll times out / aborts, unmount during poll cleans up, `reattach`
  bypasses POST.
- ResearchTab integration: mock the four endpoints, click each search
  button, assert spinner → result transition. Mock `/cases/<id>/jobs/` with
  a RUNNING job on mount, assert that the hook reattaches and renders the
  running spinner without re-POSTing.

---

## Track 2 — AI Pattern Augmentation

### Architecture

A new backend module, `ai_pattern_augmentation.py`, assembles a structured
case context payload (Strategy B: structured data + document excerpts),
calls Claude Sonnet once with prompt caching, parses a strict JSON response,
validates document references, and writes Findings with `source=AI` inside
a single transaction. The pass is triggered on-demand via a new endpoint
that rides on the Session-35 async job infrastructure.

### Components

**`investigations/ai_pattern_augmentation.py`** (new)
- **What it does:** End-to-end orchestration of one AI pattern pass for one
  case.
- **Entry point:** `analyze_case(case_id: UUID) -> dict` — called by a
  Django-Q2 task function (see below).
- **Depends on:** `ai_proxy.py` (for the Claude call), `models.py`
  (Case, Person, Organization, Property, Finding, Document,
  FinancialSnapshot, Relationship), `json`, `logging`.
- **Behavior:**
  1. Load case and all related entities/findings/snapshots/relationships.
  2. Build a document manifest: assign each Document a short ID
     (`Doc-1`, `Doc-2`, …) for that run. Persist the mapping in-memory only.
     For each doc, include `doc_type`, `filename`, and either the first
     2000 chars of extracted text OR — if `ai_extraction.py` has already
     produced a summary — that summary.
  3. Assemble the context JSON (see *Context schema* below).
  4. Call Claude Sonnet via `ai_proxy.py` with a system prompt that codifies
     the guardrails and a user prompt containing the context JSON. Use
     prompt caching on the case context so repeat runs within the cache
     window are cheap.
  5. Parse the model's response as JSON. On parse failure, log and return
     an empty result — never 500 the job.
  6. For each returned pattern: validate that every cited `doc_ref` resolves
     to a real Document in this case. Drop patterns with any invalid
     citation and log the drop.
  7. In a single transaction, create a Finding for each surviving pattern:
     `source=AI`, `status=NEW`, `evidence_weight` from AI output,
     `rule_id=None`, `title` + `description` + `narrative` from AI,
     `evidence_snapshot` stores the raw AI rationale + doc_refs +
     suggested_action.
  8. Link each Finding to cited entities via `FindingEntity` and cited
     documents via `FindingDocument`.
  9. Return `{findings_created: N, patterns_dropped: M, tokens_used: X}`.

**`investigations/jobs.py`** (modified)
- Adds `run_ai_pattern_analysis(case_id)` task function that wraps
  `ai_pattern_augmentation.analyze_case` in the same SearchJob write-back
  pattern as the four existing research tasks. The AI pass reuses the
  existing async job infrastructure wholesale — no new worker, no new
  broker, no new polling contract.

**`investigations/models.py`** (modified)
- `Finding.source` gains a third choice: `AI`.
  Current: `AUTO | MANUAL`. New: `AUTO | MANUAL | AI`.
- `SearchJob.job_type` gains a new choice: `AI_PATTERN_ANALYSIS`.
- Both are one-line migrations with no data changes.

**`investigations/views.py` + `urls.py`** (modified)
- New endpoint: `POST /api/cases/<uuid>/ai/analyze-patterns/`
  - Creates a SearchJob with `job_type=AI_PATTERN_ANALYSIS`.
  - Enqueues `run_ai_pattern_analysis(case_id, job_id)` on django-q2.
  - Returns `202 Accepted {job_id, status_url}` — identical contract to
    research jobs, so the frontend can reuse `useAsyncJob`.
  - Rejects with 409 if a prior AI job for this case is still `QUEUED` or
    `RUNNING` (one at a time per case).

**`frontend/src/components/cases/PipelineTab.tsx`** (modified)
- New button in the tab header: **"Run AI Analysis"**.
  - Uses the same `useAsyncJob` hook from Track 1, pointed at the new AI
    endpoint.
  - Disabled while running. Button shows spinner + "Analyzing…".
  - On completion, shows "Last run: <relative time> · <N> patterns found"
    and refetches the findings list.
- New filter chip row above findings: **`All` · `Rules` · `AI` · `Manual`**.
  Pure frontend filter on `source` field. Default `All`.
- AI Findings render with a distinctive badge (**🤖 AI Finding** or the
  non-emoji equivalent, depending on theme). The card body shows:
  - The AI's rationale (from `evidence_snapshot`).
  - Cited documents as clickable links that open the document workspace.
  - The suggested next action as a callout line.
  - The same triage actions as other Findings: `Confirm` · `Needs Evidence`
    · `Dismiss`.
- Confirming an AI Finding flips `status=CONFIRMED`. Nothing else changes.
  The referral-package exporter, which already filters on
  `status=CONFIRMED`, picks up confirmed AI findings with no further work.

### Context schema (the payload to Claude)

```json
{
  "case": {"id": "...", "name": "...", "status": "ACTIVE"},
  "entities": {
    "persons": [{"id": "...", "name": "...", "aliases": [...], "role_tags": [...]}],
    "organizations": [{"id": "...", "name": "...", "ein": "...", "org_type": "..."}],
    "properties": [{"id": "...", "parcel_number": "...", "address": "...",
                    "assessed_value": 0, "purchase_price": 0}]
  },
  "financial_snapshots": [
    {"org_id": "...", "tax_year": 2021, "revenue": 0, "expenses": 0, "net_assets": 0}
  ],
  "relationships": [
    {"from_type": "Person", "from_id": "...", "to_type": "Organization",
     "to_id": "...", "relationship": "OFFICER"}
  ],
  "existing_findings": [
    {"rule_id": "SR-003", "title": "...", "status": "NEW",
     "evidence_weight": "DIRECTIONAL", "source": "AUTO"}
  ],
  "documents": [
    {"ref": "Doc-1", "doc_type": "FORM_990", "filename": "2021_990.pdf",
     "text_excerpt": "...first 2000 chars or ai summary..."}
  ]
}
```

### Expected model response (strict JSON)

```json
{
  "patterns": [
    {
      "title": "Name variant across 990 and deed",
      "description": "Karen Example on the 2021 990 appears to match K. S. Example on the 2019 deed for parcel 12345.",
      "rationale": "Same last name, same city, overlapping timeframe. The deed is signed in a capacity consistent with the officer role on the 990.",
      "evidence_weight": "DIRECTIONAL",
      "entity_refs": ["person-uuid-1", "person-uuid-2"],
      "doc_refs": ["Doc-3", "Doc-7"],
      "suggested_action": "Pull the 2020 990 to check if K.S. Example was still listed as an officer at the time of the deed."
    }
  ]
}
```

### System prompt (the guardrails)

Canonical text, stored as a module-level constant in
`ai_pattern_augmentation.py` (paraphrased here for the spec):

> You are a pattern-detection assistant for a public-records fraud
> investigator. You are **not** an accuser. You highlight patterns across
> the documents and entities you are shown and point toward what the
> investigator should pull next. You never assert fraud, never use the
> words "fraud," "crime," "illegal," "guilty." You describe patterns.
>
> Every pattern you return must: cite at least one document by its `Doc-N`
> reference, carry an `evidence_weight` of either `SPECULATIVE` or
> `DIRECTIONAL` (never `DOCUMENTED` or `TRACED` — those require human
> confirmation), include a plain-language rationale, and suggest a
> concrete next action.
>
> Prioritize patterns the brittle rule engine cannot see: entity
> disambiguation (same person, different name spelling), timeline anomalies
> across documents, missing documents a pattern implies should exist,
> narrative inconsistencies between filings.
>
> Respond with strict JSON in the schema provided. No prose outside JSON.
> If you find no patterns, return `{"patterns": []}`.

### Data flow

```
Investigator clicks "Run AI Analysis" on Pipeline tab
        ↓
POST /api/cases/<id>/ai/analyze-patterns/   →  202 {job_id}
        ↓
Django-Q2 worker picks up the task
        ↓
ai_pattern_augmentation.analyze_case(case_id):
    load case + entities + findings + snapshots + relationships
    build document manifest with Doc-N refs
    assemble context JSON
    call Claude Sonnet (prompt cached)
    parse response, validate doc_refs
    transaction: create Finding + FindingEntity + FindingDocument rows
        ↓
SearchJob.result = {findings_created, patterns_dropped, tokens_used}
        ↓
frontend poll sees status=SUCCESS
        ↓
PipelineTab refetches findings, new AI findings render with badge
        ↓
investigator confirms / dismisses / promotes like any other Finding
```

### Failure modes and mitigations

| Failure | Mitigation |
|---------|-----------|
| Model returns malformed JSON | Parse in try/except. Log. Job completes with `findings_created=0` and `error_message` set. Never 500. |
| Model hallucinates `Doc-N` that doesn't exist | Validate every cited `doc_ref` against the manifest. Drop the pattern. Log the drop. |
| Model returns `evidence_weight=DOCUMENTED` or `TRACED` | Coerce down to `DIRECTIONAL` before persisting. Log the coercion. |
| Token cost spikes on large cases | Hard cap context at 150K input tokens. If a case exceeds that, truncate document excerpts proportionally and log a warning. Output `max_tokens` capped at 4K. |
| Two AI jobs fired back-to-back on the same case | `POST /ai/analyze-patterns/` returns `409 Conflict` if a prior job is `QUEUED` or `RUNNING`. |
| AI pass runs while a rule pass is also running | No conflict — both only write new Findings, and Finding creation is transactional. |
| Model produces the same pattern on every run, creating duplicates | V1 accepts the duplication (investigator dismisses dupes). Deduplication is a V2 concern once we see what real output looks like. |

### Cost envelope

- Case with 50 documents × 2K chars ≈ ~100K input tokens.
- Sonnet input at list pricing: ~$0.30 for first run.
- With prompt caching on the case context, repeat runs within the 5-minute
  cache window are ~10× cheaper (~$0.03 each).
- Output capped at 4K tokens (~$0.06 max per run).
- **Expected per-case per-session cost: ~$0.30–0.40 for first run,
  pennies for follow-ups.**

### Testing

**Backend unit (`tests/test_ai_pattern_augmentation.py`):**
- Context builder: asserts entity fields, snapshot fields, doc manifest
  shape for a fixture case.
- Response parser: happy-path JSON, malformed JSON, missing required
  fields.
- Doc-ref validator: valid refs pass, invalid refs dropped, mixed valid/invalid
  keeps only valid.
- Evidence-weight coercion: `DOCUMENTED` and `TRACED` get coerced to
  `DIRECTIONAL`.
- Finding writer: asserts row counts, source=AI, status=NEW, evidence_snapshot
  contents, FindingEntity + FindingDocument links.

**Backend integration (`tests/test_ai_pattern_views.py`):**
- `POST /ai/analyze-patterns/` returns 202 + job_id on happy path.
- Returns 409 when a prior AI job is still RUNNING for the same case.
- Using Django-Q2 `sync=True` and a mocked `ai_proxy.ai_call`, fire the
  endpoint and assert that Findings are written to the DB with the correct
  source and links.

**Frontend (`frontend/src/components/cases/PipelineTab.test.tsx`):**
- Button disabled while job running; enabled on success.
- Filter chip row filters the rendered list by `source`.
- AI finding card renders rationale + cited doc links + suggested action.
- Confirming an AI finding flips status and the card updates in place.

---

## Sequencing

1. **Track 1 first.** It's short, unblocks a user-facing crash, and builds
   the `useAsyncJob` hook that Track 2's "Run AI Analysis" button reuses.
2. **Track 2 after Track 1 lands.** The backend work (model choice,
   `ai_pattern_augmentation.py`, endpoint) can be built and tested
   standalone; the frontend work depends on Track 1's hook.

---

## Open decisions deferred to implementation

- Whether to name the `source=AI` badge "AI Finding" vs "AI-flagged" vs
  "AI Suggestion" — decide during the frontend task, after seeing real
  output.
- Whether the "Last run: 3 min ago" timestamp is stored on the Case model
  or derived by querying the most recent AI SearchJob. Leaning toward
  derived (no schema change) but will confirm during implementation.
- Exact prompt-caching boundary — cache the system prompt + case context,
  or just the system prompt. Will tune after first real-case run.

---

## What lands at the end

- Research tab works again. The four async searches show spinners, resolve
  to results, and survive tab navigation via reattach-on-mount.
- Pipeline tab has a "Run AI Analysis" button that produces candidate
  Findings labeled `source=AI`, each carrying rationale + cited documents +
  suggested next action, each triageable through the existing
  confirm/dismiss flow.
- Referral package exporter picks up confirmed AI findings with zero code
  changes, because it already filters on `status=CONFIRMED`.
- Rules engine untouched. The 14 rules still run. AI is a second pass, not
  a replacement. Adding new rules in future investigations continues to
  work, and AI augments whatever rule set is present.
