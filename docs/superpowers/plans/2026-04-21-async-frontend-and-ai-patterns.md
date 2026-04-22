# Async Research Frontend + AI Pattern Augmentation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the React Research tab to the Session-35 async job backend, then add an on-demand AI pattern-augmentation pass that produces triageable candidate Findings labeled `source=AI`.

**Architecture:** Track 1 builds a single `useAsyncJob` React hook that handles the `202 + poll` contract and retrofits the four async research surfaces. Track 2 adds a new backend module (`ai_pattern_augmentation.py`) that runs on-demand via the existing Django-Q2 infrastructure, calls Claude Sonnet with Strategy-B context (structured data + document excerpts), and writes validated AI Findings into the existing Finding table. The Pipeline tab reuses the Track-1 hook to run the AI pass and renders AI Findings in the same list with a source filter chip.

**Tech Stack:**
- Backend: Python 3.11, Django 4.2, Django-Q2, `ai_proxy.py` (existing Anthropic SDK wrapper)
- Frontend: React 18, TypeScript, Vite, React Testing Library, Vitest
- Tests: pytest (backend), Vitest (frontend)

**Prior art / anchors referenced throughout:**
- Backend async infra: [`backend/investigations/jobs.py`](../../backend/investigations/jobs.py), [`backend/investigations/models.py`](../../backend/investigations/models.py) (`SearchJob`, `JobType`, `JobStatus` at lines 1302–1362), `api_job_detail` + `api_case_jobs` in views.py
- Frontend research surface: [`frontend/src/components/cases/ResearchTab.tsx`](../../frontend/src/components/cases/ResearchTab.tsx) — current sync call sites at lines 84–113
- Finding model: `models.py` lines ~1000–1070 (`FindingSource`, evidence weight, evidence_snapshot JSONField)
- AI wrapper: [`backend/investigations/ai_proxy.py`](../../backend/investigations/ai_proxy.py) (`_call_ai` at line 416, used by `ai_summarize`/`ai_ask`/etc.)

---

## Track 1 — Research Tab async wiring

### Task 1: Add frontend types for async job contract

**Files:**
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Add job types to types.ts**

Append these types to `frontend/src/types.ts`:

```ts
export type JobStatus = "QUEUED" | "RUNNING" | "SUCCESS" | "FAILED";

export type JobType =
    | "IRS_NAME_SEARCH"
    | "IRS_FETCH_XML"
    | "OHIO_AOS"
    | "COUNTY_PARCEL"
    | "AI_PATTERN_ANALYSIS";

export interface SearchJobSummary {
    id: string;
    job_type: JobType;
    status: JobStatus;
    query_params: Record<string, unknown>;
    result: unknown | null;
    error_message: string;
    created_at: string;
    started_at: string | null;
    finished_at: string | null;
}

export interface JobEnqueueResponse {
    job_id: string;
    status_url: string;
}
```

- [ ] **Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (no errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat(frontend): add JobStatus/JobType/SearchJobSummary types"
```

---

### Task 2: Add API client functions for polling and listing jobs

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add `fetchJob` and `fetchCaseJobs` near the bottom of api.ts**

Add these exports. Place them after the research functions (after `fetch990Data`):

```ts
import type { JobEnqueueResponse, SearchJobSummary } from "./types";

export async function fetchJob(
    jobId: string,
    options?: ApiRequestOptions,
): Promise<SearchJobSummary> {
    return request<SearchJobSummary>(
        `/api/jobs/${jobId}/`,
        { method: "GET" },
        { ...options, timeoutMs: options?.timeoutMs ?? 10000 },
    );
}

export async function fetchCaseJobs(
    caseId: string,
    limit = 5,
    options?: ApiRequestOptions,
): Promise<SearchJobSummary[]> {
    return request<SearchJobSummary[]>(
        `/api/cases/${caseId}/jobs/?limit=${limit}`,
        { method: "GET" },
        { ...options, timeoutMs: options?.timeoutMs ?? 10000 },
    );
}
```

If the file already imports from `./types`, fold `JobEnqueueResponse` and `SearchJobSummary` into the existing import block instead of adding a duplicate import.

- [ ] **Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(frontend): add fetchJob and fetchCaseJobs API helpers"
```

---

### Task 3: Write failing tests for `useAsyncJob` hook

**Files:**
- Create: `frontend/src/hooks/useAsyncJob.test.ts`

- [ ] **Step 1: Create the test file**

Create `frontend/src/hooks/useAsyncJob.test.ts` with this content:

```ts
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAsyncJob } from "./useAsyncJob";

const flushTimers = async () => {
    await vi.runAllTimersAsync();
};

describe("useAsyncJob", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.stubGlobal("fetch", vi.fn());
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    function mockPostReturns(jobId: string) {
        (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
            ok: true,
            status: 202,
            json: async () => ({ job_id: jobId, status_url: `/api/jobs/${jobId}/` }),
            headers: new Headers({ "content-type": "application/json" }),
        });
    }

    function mockGetReturns(body: Record<string, unknown>, status = 200) {
        (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
            ok: status < 400,
            status,
            json: async () => body,
            headers: new Headers({ "content-type": "application/json" }),
        });
    }

    it("starts idle", () => {
        const { result } = renderHook(() =>
            useAsyncJob({ postUrl: "/api/cases/abc/research/irs/" }),
        );
        expect(result.current.status).toBe("idle");
        expect(result.current.result).toBeNull();
        expect(result.current.error).toBeNull();
    });

    it("transitions idle → queued → running → success", async () => {
        const { result } = renderHook(() =>
            useAsyncJob({ postUrl: "/api/cases/abc/research/irs/" }),
        );

        mockPostReturns("job-1");
        mockGetReturns({ id: "job-1", status: "RUNNING", result: null, error_message: "" });
        mockGetReturns({
            id: "job-1",
            status: "SUCCESS",
            result: { count: 2, results: [{}, {}] },
            error_message: "",
        });

        await act(async () => {
            await result.current.run({ query: "do good" });
        });
        expect(result.current.status).toBe("queued");

        await act(flushTimers);
        await waitFor(() => expect(result.current.status).toBe("running"));

        await act(flushTimers);
        await waitFor(() => expect(result.current.status).toBe("success"));
        expect((result.current.result as { count: number }).count).toBe(2);
    });

    it("transitions to failed on FAILED status", async () => {
        const { result } = renderHook(() =>
            useAsyncJob({ postUrl: "/api/cases/abc/research/irs/" }),
        );

        mockPostReturns("job-2");
        mockGetReturns({
            id: "job-2",
            status: "FAILED",
            result: null,
            error_message: "Connector raised",
        });

        await act(async () => {
            await result.current.run({ query: "x" });
        });
        await act(flushTimers);
        await waitFor(() => expect(result.current.status).toBe("failed"));
        expect(result.current.error).toBe("Connector raised");
    });

    it("reattach skips POST and starts polling immediately", async () => {
        const { result } = renderHook(() =>
            useAsyncJob({ postUrl: "/api/cases/abc/research/irs/" }),
        );

        mockGetReturns({
            id: "job-3",
            status: "SUCCESS",
            result: { count: 1 },
            error_message: "",
        });

        await act(async () => {
            result.current.reattach("job-3");
        });
        await act(flushTimers);
        await waitFor(() => expect(result.current.status).toBe("success"));

        const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
        expect(calls.some(([url]) => String(url).includes("/api/jobs/job-3/"))).toBe(true);
        expect(calls.some(([_url, init]) => (init as RequestInit | undefined)?.method === "POST")).toBe(false);
    });

    it("clears poll interval on unmount", async () => {
        const { result, unmount } = renderHook(() =>
            useAsyncJob({ postUrl: "/api/cases/abc/research/irs/" }),
        );

        mockPostReturns("job-4");
        mockGetReturns({ id: "job-4", status: "RUNNING", result: null, error_message: "" });

        await act(async () => {
            await result.current.run({ query: "x" });
        });
        await act(flushTimers);

        unmount();

        const callsBefore = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.length;
        await act(flushTimers);
        const callsAfter = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.length;
        expect(callsAfter).toBe(callsBefore);
    });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `cd frontend && npx vitest run src/hooks/useAsyncJob.test.ts`
Expected: FAIL — "Cannot find module './useAsyncJob'" (file does not exist yet).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useAsyncJob.test.ts
git commit -m "test(frontend): add failing tests for useAsyncJob hook"
```

---

### Task 4: Implement `useAsyncJob` hook

**Files:**
- Create: `frontend/src/hooks/useAsyncJob.ts`

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/useAsyncJob.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJob } from "../api";
import type { JobEnqueueResponse, JobStatus, SearchJobSummary } from "../types";

const POLL_INTERVAL_MS = 2000;

export type UseAsyncJobStatus = "idle" | "queued" | "running" | "success" | "failed";

export interface UseAsyncJobReturn<TResult> {
    status: UseAsyncJobStatus;
    jobId: string | null;
    result: TResult | null;
    error: string | null;
    run: (body: Record<string, unknown>) => Promise<void>;
    reattach: (jobId: string) => void;
    cancel: () => void;
}

export interface UseAsyncJobOptions {
    postUrl: string;
}

function getCSRFToken(): string {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : "";
}

export function useAsyncJob<TResult = unknown>(
    options: UseAsyncJobOptions,
): UseAsyncJobReturn<TResult> {
    const [status, setStatus] = useState<UseAsyncJobStatus>("idle");
    const [jobId, setJobId] = useState<string | null>(null);
    const [result, setResult] = useState<TResult | null>(null);
    const [error, setError] = useState<string | null>(null);

    const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
    const mounted = useRef(true);

    useEffect(() => {
        mounted.current = true;
        return () => {
            mounted.current = false;
            if (pollTimer.current !== null) {
                clearInterval(pollTimer.current);
                pollTimer.current = null;
            }
        };
    }, []);

    const stopPolling = useCallback(() => {
        if (pollTimer.current !== null) {
            clearInterval(pollTimer.current);
            pollTimer.current = null;
        }
    }, []);

    const applyJobState = useCallback(
        (job: SearchJobSummary) => {
            if (!mounted.current) return;
            const jobStatus = job.status as JobStatus;
            if (jobStatus === "QUEUED") {
                setStatus("queued");
            } else if (jobStatus === "RUNNING") {
                setStatus("running");
            } else if (jobStatus === "SUCCESS") {
                setStatus("success");
                setResult(job.result as TResult);
                stopPolling();
            } else if (jobStatus === "FAILED") {
                setStatus("failed");
                setError(job.error_message || "Job failed");
                stopPolling();
            }
        },
        [stopPolling],
    );

    const startPolling = useCallback(
        (id: string) => {
            stopPolling();
            const tick = async () => {
                try {
                    const job = await fetchJob(id);
                    applyJobState(job);
                } catch (e) {
                    if (!mounted.current) return;
                    setStatus("failed");
                    setError(e instanceof Error ? e.message : "Poll failed");
                    stopPolling();
                }
            };
            pollTimer.current = setInterval(tick, POLL_INTERVAL_MS);
            void tick();
        },
        [applyJobState, stopPolling],
    );

    const run = useCallback(
        async (body: Record<string, unknown>) => {
            setStatus("queued");
            setResult(null);
            setError(null);
            try {
                const res = await fetch(options.postUrl, {
                    method: "POST",
                    credentials: "include",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": getCSRFToken(),
                    },
                    body: JSON.stringify(body),
                });
                if (!res.ok) {
                    throw new Error(`Enqueue failed: ${res.status}`);
                }
                const enqueue = (await res.json()) as JobEnqueueResponse;
                setJobId(enqueue.job_id);
                startPolling(enqueue.job_id);
            } catch (e) {
                setStatus("failed");
                setError(e instanceof Error ? e.message : "Enqueue failed");
            }
        },
        [options.postUrl, startPolling],
    );

    const reattach = useCallback(
        (id: string) => {
            setStatus("queued");
            setResult(null);
            setError(null);
            setJobId(id);
            startPolling(id);
        },
        [startPolling],
    );

    const cancel = useCallback(() => {
        stopPolling();
        setStatus("idle");
    }, [stopPolling]);

    return { status, jobId, result, error, run, reattach, cancel };
}
```

- [ ] **Step 2: Run tests**

Run: `cd frontend && npx vitest run src/hooks/useAsyncJob.test.ts`
Expected: PASS (all 5 tests).

- [ ] **Step 3: Verify typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useAsyncJob.ts
git commit -m "feat(frontend): implement useAsyncJob hook with poll + reattach"
```

---

### Task 5: Retrofit ResearchTab to use `useAsyncJob` for the four async sources

**Files:**
- Modify: `frontend/src/components/cases/ResearchTab.tsx`
- Modify: `frontend/src/components/cases/ResearchTab.module.css` (optional — spinner classes)

**Context:** Current code at ResearchTab.tsx:84–113 calls `searchParcels` / `searchOhioAOS` / `searchIRS` directly and awaits a synchronous `ResearchResult`. After Session 35 these endpoints return `202 + {job_id}` instead, so the awaited value no longer has `.results`, `.count`, `.notes` fields — that is the `0 is not iterable` crash. After this task, those three sources go through `useAsyncJob`; Ohio SOS and Recorder stay synchronous.

- [ ] **Step 1: Replace the inside of the `ResearchTab` component**

Open `frontend/src/components/cases/ResearchTab.tsx` and make these changes:

**1a. Update the imports at the top of the file** — replace the current imports block (lines 1–5) with:

```tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { CaseDetailContext } from "../../views/CaseDetailView";
import {
    ResearchResult,
    Fetch990Result,
    searchOhioSOS,
    searchRecorder,
    addResearchToCase,
    fetch990Data,
    fetchCaseJobs,
} from "../../api";
import { useAsyncJob } from "../../hooks/useAsyncJob";
import type { SearchJobSummary } from "../../types";
import styles from "./ResearchTab.module.css";
```

Note: removed `useState` extra import line, `useCallback`, etc. are merged. Removed `searchParcels`, `searchOhioAOS`, `searchIRS` imports — we no longer call them directly.

**1b. Inside the component**, replace the existing `loading` / `error` / `results` state block (around lines 60–63) with three hooks — one per async source — plus the sync results state that recorder/SOS use:

```tsx
const irsJob = useAsyncJob<ResearchResult>({
    postUrl: `/api/cases/${caseId}/research/irs/`,
});
const aosJob = useAsyncJob<ResearchResult>({
    postUrl: `/api/cases/${caseId}/research/ohio-aos/`,
});
const parcelsJob = useAsyncJob<ResearchResult>({
    postUrl: `/api/cases/${caseId}/research/parcels/`,
});

const [syncResults, setSyncResults] = useState<ResearchResult | null>(null);
const [syncLoading, setSyncLoading] = useState(false);
const [syncError, setSyncError] = useState<string | null>(null);
```

**1c. Replace the `handleSearch` callback** with this version that branches on source:

```tsx
const handleSearch = useCallback(async () => {
    if (!query.trim()) {
        pushToast("error", "Please enter a search query");
        return;
    }

    if (activeSource === "irs") {
        await irsJob.run({ query });
        return;
    }
    if (activeSource === "ohio-aos") {
        await aosJob.run({ query });
        return;
    }
    if (activeSource === "parcels") {
        const searchType = query.match(/^\d{4}-\d{4}-\d{4}$/) ? "parcel" : "owner";
        await parcelsJob.run({ query, search_type: searchType, county });
        return;
    }

    // sync sources
    setSyncLoading(true);
    setSyncError(null);
    setSyncResults(null);
    try {
        let result: ResearchResult;
        if (activeSource === "ohio-sos") {
            result = await searchOhioSOS(caseId, query);
        } else if (activeSource === "recorder") {
            if (!county.trim()) {
                pushToast("error", "Please select a county for recorder search");
                setSyncLoading(false);
                return;
            }
            result = await searchRecorder(caseId, county, query);
        } else {
            throw new Error("Unknown source");
        }
        if (result.error) {
            setSyncError(result.error);
        } else {
            setSyncResults(result);
            setAddedRows(new Set());
        }
    } catch (err) {
        const message = err instanceof Error ? err.message : "Search failed";
        setSyncError(message);
        pushToast("error", message);
    } finally {
        setSyncLoading(false);
    }
}, [activeSource, caseId, county, query, pushToast, irsJob, aosJob, parcelsJob]);
```

**1d. Add a `useEffect` after `handleSearch` to reattach in-flight jobs on mount.** Paste this block:

```tsx
useEffect(() => {
    let cancelled = false;
    (async () => {
        try {
            const jobs = await fetchCaseJobs(caseId, 5);
            if (cancelled) return;
            const latest: Partial<Record<SearchJobSummary["job_type"], SearchJobSummary>> = {};
            for (const job of jobs) {
                if (!latest[job.job_type]) latest[job.job_type] = job;
            }
            const reattachIfLive = (
                job: SearchJobSummary | undefined,
                hook: { reattach: (id: string) => void },
            ) => {
                if (!job) return;
                if (job.status === "QUEUED" || job.status === "RUNNING") {
                    hook.reattach(job.id);
                }
            };
            reattachIfLive(latest.IRS_NAME_SEARCH ?? latest.IRS_FETCH_XML, irsJob);
            reattachIfLive(latest.OHIO_AOS, aosJob);
            reattachIfLive(latest.COUNTY_PARCEL, parcelsJob);
        } catch {
            // Non-fatal — the user can simply re-run the search.
        }
    })();
    return () => {
        cancelled = true;
    };
    // Intentionally only on mount (hooks are stable refs from useAsyncJob)
    // eslint-disable-next-line react-hooks/exhaustive-deps
}, [caseId]);
```

**1e. Derive a single `displayResults`, `loading`, and `error`** the rest of the render code can consume. Add this just before `renderResults`:

```tsx
const activeJob = useMemo(() => {
    if (activeSource === "irs") return irsJob;
    if (activeSource === "ohio-aos") return aosJob;
    if (activeSource === "parcels") return parcelsJob;
    return null;
}, [activeSource, irsJob, aosJob, parcelsJob]);

const loading =
    activeJob !== null
        ? activeJob.status === "queued" || activeJob.status === "running"
        : syncLoading;

const error = activeJob !== null ? activeJob.error : syncError;

const results: ResearchResult | null =
    activeJob !== null
        ? activeJob.status === "success"
            ? activeJob.result
            : null
        : syncResults;
```

**1f. Update `setResults`/`setLoading`/`setError` references** in the rest of the component. The `handleAddToCase` and `handleFetch990` callbacks only read `pushToast` and `activeSource` — leave them alone. If there are any stale references to the old `results`/`loading`/`error` state setters (e.g. inside reset logic), delete them.

**1g. Add a status line** above the results area when a job is queued/running. Find the existing `{loading && (...)}` spinner block (or equivalent) and replace with:

```tsx
{loading && (
    <div className={styles.loadingRow} role="status" aria-live="polite">
        <span className={styles.spinner} aria-hidden="true" />
        <span>
            {activeJob?.status === "queued" && "Queued…"}
            {activeJob?.status === "running" && "Searching… (typically 20–90 seconds)"}
            {activeJob === null && "Searching…"}
        </span>
    </div>
)}
```

- [ ] **Step 2: Run typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Run the frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS. (Pre-existing tests should not regress; `useAsyncJob` tests from Task 4 pass.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/cases/ResearchTab.tsx frontend/src/components/cases/ResearchTab.module.css
git commit -m "feat(frontend): ResearchTab consumes async job contract with reattach"
```

---

### Task 6: Smoke-test Track 1 in a running dev environment

- [ ] **Step 1: Start backend + worker + frontend**

Run in one shell (from repo root):

```bash
docker compose up -d backend qcluster db
cd frontend && npm run dev
```

- [ ] **Step 2: Manual smoke test**

In a browser:
1. Open an existing case in the frontend.
2. Click Research tab. Expected: tab loads with no `0 is not iterable` console error.
3. Run an IRS name search for "do good". Expected: spinner with "Searching… (typically 20–90 seconds)"; eventually results render.
4. While the search is running, navigate away and back to the Research tab. Expected: spinner picks up again (reattach) — no second POST.
5. Confirm results render correctly. Confirm Fetch 990 Data (sync `/fetch-990s/` endpoint) and Ohio SOS still work — these are unchanged.

- [ ] **Step 3: If any of those fail, fix inline and re-run before continuing.**

- [ ] **Step 4: Update STATUS.md**

Open `STATUS.md`. Move "Research tab frontend" out of "In active refactor" into the "Working" table with:

> Research tab frontend | React consumes the 202 + poll contract with reattach-on-mount. Spinner, error rendering, in-flight job pickup all working. | useAsyncJob hook shared with AI analysis.

Remove the "Recently completed (Session 35)" frontend caveat line about the research tab wiring being deferred.

- [ ] **Step 5: Commit**

```bash
git add STATUS.md
git commit -m "docs: mark research tab async wiring as working"
```

---

## Track 2 — AI Pattern Augmentation (backend)

### Task 7: Extend `FindingSource` and `JobType` enums

**Files:**
- Modify: `backend/investigations/models.py`
- Create: `backend/investigations/migrations/0XXX_ai_source_and_jobtype.py` (auto-generated)

- [ ] **Step 1: Update `FindingSource`**

In `backend/investigations/models.py`, find `class FindingSource` (line 129) and change to:

```python
class FindingSource(models.TextChoices):
    AUTO = "AUTO", "Auto-detected by signal rules"
    MANUAL = "MANUAL", "Manually created by investigator"
    AI = "AI", "AI-flagged pattern"
```

- [ ] **Step 2: Update `JobType`**

In the same file, find `class JobType` (line 1302) and add the new choice:

```python
class JobType(models.TextChoices):
    IRS_NAME_SEARCH = "IRS_NAME_SEARCH", "IRS Name Search"
    IRS_FETCH_XML = "IRS_FETCH_XML", "IRS Fetch XML"
    OHIO_AOS = "OHIO_AOS", "Ohio Auditor of State"
    COUNTY_PARCEL = "COUNTY_PARCEL", "County Parcel Search"
    AI_PATTERN_ANALYSIS = "AI_PATTERN_ANALYSIS", "AI Pattern Analysis"
```

- [ ] **Step 3: Generate and verify the migration**

Run: `docker compose exec backend python manage.py makemigrations investigations`
Expected: Creates a migration file that alters `Finding.source` choices and `SearchJob.job_type` choices. Both are choice-only changes — no schema change on disk.

- [ ] **Step 4: Apply migration**

Run: `docker compose exec backend python manage.py migrate investigations`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/investigations/models.py backend/investigations/migrations/
git commit -m "feat(models): add AI FindingSource and AI_PATTERN_ANALYSIS JobType"
```

---

### Task 8: Write failing tests for context builder

**Files:**
- Create: `tests/test_ai_pattern_context.py`

- [ ] **Step 1: Create the test file**

Create `tests/test_ai_pattern_context.py`:

```python
"""Tests for ai_pattern_augmentation.build_context."""
from __future__ import annotations

import pytest
from django.utils import timezone

from investigations import ai_pattern_augmentation
from investigations.models import (
    Case,
    Document,
    FinancialSnapshot,
    Organization,
    Person,
    PersonOrganization,
)


@pytest.fixture
def seeded_case(db):
    case = Case.objects.create(name="Test Case", status="ACTIVE")
    person = Person.objects.create(name="Karen Example")
    org = Organization.objects.create(name="Example Foundation", ein="12-3456789")
    PersonOrganization.objects.create(person=person, organization=org, role_type="OFFICER")
    FinancialSnapshot.objects.create(
        org=org, tax_year=2021, revenue=500000, expenses=400000, net_assets=100000,
    )
    doc = Document.objects.create(
        case=case,
        filename="2021_990.pdf",
        sha256_hash="a" * 64,
        doc_type="FORM_990",
        extracted_text="Part VII lists Karen Example as president..." * 100,
    )
    return {"case": case, "person": person, "org": org, "doc": doc}


def test_build_context_includes_case_and_entities(seeded_case):
    ctx = ai_pattern_augmentation.build_context(seeded_case["case"])
    assert ctx["case"]["name"] == "Test Case"
    assert any(p["name"] == "Karen Example" for p in ctx["entities"]["persons"])
    assert any(o["ein"] == "12-3456789" for o in ctx["entities"]["organizations"])


def test_build_context_includes_financials(seeded_case):
    ctx = ai_pattern_augmentation.build_context(seeded_case["case"])
    assert any(f["tax_year"] == 2021 and f["revenue"] == 500000 for f in ctx["financial_snapshots"])


def test_build_context_assigns_doc_refs(seeded_case):
    ctx = ai_pattern_augmentation.build_context(seeded_case["case"])
    docs = ctx["documents"]
    assert len(docs) >= 1
    assert docs[0]["ref"] == "Doc-1"
    assert docs[0]["filename"] == "2021_990.pdf"
    assert "text_excerpt" in docs[0]


def test_build_context_truncates_document_text(seeded_case):
    ctx = ai_pattern_augmentation.build_context(seeded_case["case"])
    for d in ctx["documents"]:
        assert len(d["text_excerpt"]) <= 2000


def test_build_context_returns_doc_ref_map(seeded_case):
    ctx, doc_ref_map = ai_pattern_augmentation.build_context_with_refs(seeded_case["case"])
    assert len(doc_ref_map) == len(ctx["documents"])
    assert all(ref.startswith("Doc-") for ref in doc_ref_map.keys())
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `docker compose exec backend pytest tests/test_ai_pattern_context.py -v`
Expected: FAIL — `ModuleNotFoundError` or `AttributeError` (module does not exist yet).

- [ ] **Step 3: Commit**

```bash
git add tests/test_ai_pattern_context.py
git commit -m "test(ai): failing tests for ai pattern context builder"
```

---

### Task 9: Implement context builder

**Files:**
- Create: `backend/investigations/ai_pattern_augmentation.py`

- [ ] **Step 1: Create the module with the context builder only**

Create `backend/investigations/ai_pattern_augmentation.py`:

```python
"""AI Pattern Augmentation — single-pass case-level pattern detector.

Reads a Case with its entities, findings, financial snapshots, and document
excerpts; asks Claude to highlight patterns the rule engine cannot see;
writes each returned pattern as a Finding with source=AI.

The module is deliberately small — orchestration only. Claude-calling logic
lives in ai_proxy.py; database writes use the existing Finding machinery.

See docs/superpowers/specs/2026-04-21-async-frontend-and-ai-patterns-design.md
"""
from __future__ import annotations

import logging
from typing import Any

from django.db.models import Prefetch

from investigations.models import (
    Case,
    Document,
    FinancialSnapshot,
    Finding,
    Organization,
    Person,
    Property,
    Relationship,
)

logger = logging.getLogger(__name__)

MAX_EXCERPT_CHARS = 2000
MAX_DOCUMENTS = 60  # hard cap to keep the prompt bounded


def build_context(case: Case) -> dict[str, Any]:
    """Return the JSON-serializable context payload we send to Claude."""
    ctx, _ = build_context_with_refs(case)
    return ctx


def build_context_with_refs(case: Case) -> tuple[dict[str, Any], dict[str, str]]:
    """Return (context payload, {doc_ref: document_uuid_str}).

    The ref map is used on the way back to validate cited `Doc-N` references.
    """
    persons = list(Person.objects.filter(documents__case=case).distinct())
    orgs = list(Organization.objects.filter(documents__case=case).distinct())
    properties = list(Property.objects.filter(persontransactions__case=case).distinct()) \
        if hasattr(Property, "persontransactions") else list(Property.objects.none())

    snapshots = list(FinancialSnapshot.objects.filter(org__in=orgs))
    relationships = list(
        Relationship.objects.filter(from_person__in=persons)
        | Relationship.objects.filter(to_person__in=persons)
    ) if hasattr(Relationship, "from_person") else []

    existing_findings = list(Finding.objects.filter(case=case))

    docs = list(Document.objects.filter(case=case).order_by("created_at")[:MAX_DOCUMENTS])
    doc_ref_map: dict[str, str] = {}
    doc_entries: list[dict[str, Any]] = []
    for i, d in enumerate(docs, start=1):
        ref = f"Doc-{i}"
        doc_ref_map[ref] = str(d.id)
        excerpt = (d.extracted_text or "")[:MAX_EXCERPT_CHARS]
        doc_entries.append({
            "ref": ref,
            "doc_type": d.doc_type or "",
            "filename": d.filename,
            "text_excerpt": excerpt,
        })

    ctx: dict[str, Any] = {
        "case": {
            "id": str(case.id),
            "name": case.name,
            "status": case.status,
        },
        "entities": {
            "persons": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "aliases": list(getattr(p, "aliases", []) or []),
                    "role_tags": list(getattr(p, "role_tags", []) or []),
                }
                for p in persons
            ],
            "organizations": [
                {
                    "id": str(o.id),
                    "name": o.name,
                    "ein": o.ein or "",
                    "org_type": getattr(o, "org_type", "") or "",
                }
                for o in orgs
            ],
            "properties": [
                {
                    "id": str(pr.id),
                    "parcel_number": pr.parcel_number or "",
                    "address": getattr(pr, "address", "") or "",
                    "assessed_value": float(pr.assessed_value or 0),
                    "purchase_price": float(pr.purchase_price or 0),
                }
                for pr in properties
            ],
        },
        "financial_snapshots": [
            {
                "org_id": str(s.org_id),
                "tax_year": s.tax_year,
                "revenue": float(s.revenue or 0),
                "expenses": float(s.expenses or 0),
                "net_assets": float(s.net_assets or 0),
            }
            for s in snapshots
        ],
        "relationships": [],  # populated below if the model supports it
        "existing_findings": [
            {
                "rule_id": f.rule_id or "",
                "title": f.title,
                "status": f.status,
                "evidence_weight": f.evidence_weight,
                "source": f.source,
            }
            for f in existing_findings
        ],
        "documents": doc_entries,
    }
    return ctx, doc_ref_map
```

Note: the `properties` and `relationships` queries guard with `hasattr` because the current schema uses `PropertyTransaction` and `Relationship` in idiosyncratic ways. If the query pattern here misses related rows for a case, subsequent tasks will surface it — we ship the simpler version first.

- [ ] **Step 2: Run the context tests**

Run: `docker compose exec backend pytest tests/test_ai_pattern_context.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/investigations/ai_pattern_augmentation.py
git commit -m "feat(ai): add build_context for AI pattern augmentation"
```

---

### Task 10: Write failing tests for response parsing and validation

**Files:**
- Create: `tests/test_ai_pattern_parse.py`

- [ ] **Step 1: Create the test file**

Create `tests/test_ai_pattern_parse.py`:

```python
"""Tests for parse_response and validate_patterns in ai_pattern_augmentation."""
from __future__ import annotations

import json
from investigations import ai_pattern_augmentation


def test_parse_response_happy_path():
    raw = json.dumps({
        "patterns": [
            {
                "title": "Name variant",
                "description": "K. S. Example ≈ Karen Example",
                "rationale": "Overlapping city and last name",
                "evidence_weight": "DIRECTIONAL",
                "entity_refs": ["uuid-a"],
                "doc_refs": ["Doc-1", "Doc-2"],
                "suggested_action": "Pull 2020 990",
            }
        ]
    })
    parsed = ai_pattern_augmentation.parse_response(raw)
    assert len(parsed) == 1
    assert parsed[0]["title"] == "Name variant"


def test_parse_response_malformed_returns_empty():
    assert ai_pattern_augmentation.parse_response("not json") == []
    assert ai_pattern_augmentation.parse_response("{}") == []
    assert ai_pattern_augmentation.parse_response('{"patterns": "not a list"}') == []


def test_validate_patterns_drops_invalid_doc_refs():
    patterns = [
        {
            "title": "ok",
            "description": "d",
            "rationale": "r",
            "evidence_weight": "DIRECTIONAL",
            "entity_refs": [],
            "doc_refs": ["Doc-1"],
            "suggested_action": "a",
        },
        {
            "title": "bad",
            "description": "d",
            "rationale": "r",
            "evidence_weight": "DIRECTIONAL",
            "entity_refs": [],
            "doc_refs": ["Doc-99"],
            "suggested_action": "a",
        },
    ]
    doc_ref_map = {"Doc-1": "uuid-real"}
    kept, dropped = ai_pattern_augmentation.validate_patterns(patterns, doc_ref_map)
    assert len(kept) == 1
    assert kept[0]["title"] == "ok"
    assert dropped == 1


def test_validate_patterns_coerces_weight():
    patterns = [
        {
            "title": "ok",
            "description": "d",
            "rationale": "r",
            "evidence_weight": "DOCUMENTED",  # not allowed from AI
            "entity_refs": [],
            "doc_refs": ["Doc-1"],
            "suggested_action": "a",
        }
    ]
    kept, _ = ai_pattern_augmentation.validate_patterns(patterns, {"Doc-1": "x"})
    assert kept[0]["evidence_weight"] == "DIRECTIONAL"


def test_validate_patterns_requires_required_fields():
    patterns = [{"title": "no-body"}]
    kept, dropped = ai_pattern_augmentation.validate_patterns(patterns, {})
    assert kept == []
    assert dropped == 1
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `docker compose exec backend pytest tests/test_ai_pattern_parse.py -v`
Expected: FAIL — `AttributeError: module 'investigations.ai_pattern_augmentation' has no attribute 'parse_response'`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ai_pattern_parse.py
git commit -m "test(ai): failing tests for parse_response and validate_patterns"
```

---

### Task 11: Implement `parse_response` and `validate_patterns`

**Files:**
- Modify: `backend/investigations/ai_pattern_augmentation.py`

- [ ] **Step 1: Append these functions to the module**

Add to `backend/investigations/ai_pattern_augmentation.py`:

```python
import json

ALLOWED_AI_WEIGHTS = {"SPECULATIVE", "DIRECTIONAL"}
REQUIRED_PATTERN_FIELDS = (
    "title",
    "description",
    "rationale",
    "evidence_weight",
    "doc_refs",
    "suggested_action",
)


def parse_response(raw: str) -> list[dict[str, Any]]:
    """Parse Claude's response to a list of pattern dicts. Never raises."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("AI pattern response was not valid JSON")
        return []
    if not isinstance(data, dict):
        return []
    patterns = data.get("patterns")
    if not isinstance(patterns, list):
        return []
    return [p for p in patterns if isinstance(p, dict)]


def validate_patterns(
    patterns: list[dict[str, Any]],
    doc_ref_map: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:
    """Keep only patterns with real doc_refs and required fields.

    Coerces any evidence_weight that isn't SPECULATIVE or DIRECTIONAL down
    to DIRECTIONAL. Returns (kept, dropped_count).
    """
    kept: list[dict[str, Any]] = []
    dropped = 0
    for p in patterns:
        if not all(field in p for field in REQUIRED_PATTERN_FIELDS):
            dropped += 1
            continue
        doc_refs = p.get("doc_refs") or []
        if not isinstance(doc_refs, list) or not doc_refs:
            dropped += 1
            continue
        if any(ref not in doc_ref_map for ref in doc_refs):
            dropped += 1
            logger.info("Dropping AI pattern with unknown doc_ref: %s", doc_refs)
            continue
        weight = p.get("evidence_weight", "")
        if weight not in ALLOWED_AI_WEIGHTS:
            logger.info("Coercing AI evidence_weight %s → DIRECTIONAL", weight)
            p["evidence_weight"] = "DIRECTIONAL"
        kept.append(p)
    return kept, dropped
```

- [ ] **Step 2: Run tests**

Run: `docker compose exec backend pytest tests/test_ai_pattern_parse.py -v`
Expected: PASS (5 tests).

- [ ] **Step 3: Commit**

```bash
git add backend/investigations/ai_pattern_augmentation.py
git commit -m "feat(ai): add parse_response and validate_patterns"
```

---

### Task 12: Write failing tests for `analyze_case` end-to-end

**Files:**
- Create: `tests/test_ai_pattern_analyze.py`

- [ ] **Step 1: Create the test file**

Create `tests/test_ai_pattern_analyze.py`:

```python
"""End-to-end tests for ai_pattern_augmentation.analyze_case with mocked Claude."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from investigations import ai_pattern_augmentation
from investigations.models import Case, Document, Finding, FindingSource


@pytest.fixture
def case_with_docs(db):
    case = Case.objects.create(name="AI Test Case", status="ACTIVE")
    Document.objects.create(
        case=case, filename="a.pdf", sha256_hash="a" * 64,
        doc_type="FORM_990", extracted_text="some text",
    )
    Document.objects.create(
        case=case, filename="b.pdf", sha256_hash="b" * 64,
        doc_type="DEED", extracted_text="more text",
    )
    return case


def _mock_ai_response(patterns):
    return json.dumps({"patterns": patterns})


@patch("investigations.ai_pattern_augmentation.call_claude")
def test_analyze_case_writes_findings(mock_call, case_with_docs):
    mock_call.return_value = _mock_ai_response([
        {
            "title": "Name variant pattern",
            "description": "Looks like same person",
            "rationale": "Matching context",
            "evidence_weight": "DIRECTIONAL",
            "entity_refs": [],
            "doc_refs": ["Doc-1"],
            "suggested_action": "Pull related deed",
        }
    ])
    result = ai_pattern_augmentation.analyze_case(case_with_docs.id)
    assert result["findings_created"] == 1
    assert result["patterns_dropped"] == 0
    findings = Finding.objects.filter(case=case_with_docs, source=FindingSource.AI)
    assert findings.count() == 1
    f = findings.first()
    assert f.title == "Name variant pattern"
    assert f.evidence_weight == "DIRECTIONAL"
    assert f.status == "NEW"
    assert "rationale" in f.evidence_snapshot
    assert f.evidence_snapshot["suggested_action"] == "Pull related deed"


@patch("investigations.ai_pattern_augmentation.call_claude")
def test_analyze_case_drops_invalid_doc_refs(mock_call, case_with_docs):
    mock_call.return_value = _mock_ai_response([
        {
            "title": "good",
            "description": "d", "rationale": "r", "evidence_weight": "DIRECTIONAL",
            "entity_refs": [], "doc_refs": ["Doc-1"], "suggested_action": "a",
        },
        {
            "title": "bad",
            "description": "d", "rationale": "r", "evidence_weight": "DIRECTIONAL",
            "entity_refs": [], "doc_refs": ["Doc-99"], "suggested_action": "a",
        },
    ])
    result = ai_pattern_augmentation.analyze_case(case_with_docs.id)
    assert result["findings_created"] == 1
    assert result["patterns_dropped"] == 1


@patch("investigations.ai_pattern_augmentation.call_claude")
def test_analyze_case_handles_malformed_ai_response(mock_call, case_with_docs):
    mock_call.return_value = "not json"
    result = ai_pattern_augmentation.analyze_case(case_with_docs.id)
    assert result["findings_created"] == 0


@patch("investigations.ai_pattern_augmentation.call_claude")
def test_analyze_case_links_cited_documents(mock_call, case_with_docs):
    mock_call.return_value = _mock_ai_response([
        {
            "title": "links",
            "description": "d", "rationale": "r", "evidence_weight": "SPECULATIVE",
            "entity_refs": [], "doc_refs": ["Doc-1", "Doc-2"],
            "suggested_action": "a",
        }
    ])
    ai_pattern_augmentation.analyze_case(case_with_docs.id)
    f = Finding.objects.filter(case=case_with_docs, source=FindingSource.AI).first()
    assert f is not None
    # FindingDocument rows exist for each cited doc
    assert f.findingdocument_set.count() == 2
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `docker compose exec backend pytest tests/test_ai_pattern_analyze.py -v`
Expected: FAIL — `AttributeError: module has no attribute 'analyze_case'` (and `call_claude`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_ai_pattern_analyze.py
git commit -m "test(ai): failing tests for analyze_case end-to-end"
```

---

### Task 13: Implement `call_claude` and `analyze_case`

**Files:**
- Modify: `backend/investigations/ai_pattern_augmentation.py`

- [ ] **Step 1: Append the Claude call wrapper and orchestrator**

Add these to `backend/investigations/ai_pattern_augmentation.py`:

```python
from django.db import transaction

from investigations import ai_proxy
from investigations.models import (
    FindingDocument,
    FindingEntity,
    FindingSource,
)

SYSTEM_PROMPT = """\
You are a pattern-detection assistant for a public-records fraud
investigator. You are NOT an accuser. You highlight patterns across the
documents and entities you are shown and point toward what the
investigator should pull next. You never assert fraud; never use the words
"fraud", "crime", "illegal", or "guilty". Describe patterns, not verdicts.

Every pattern you return must:
  - cite at least one document by its Doc-N reference,
  - carry an `evidence_weight` of either `SPECULATIVE` or `DIRECTIONAL`
    (never `DOCUMENTED` or `TRACED` — those require human confirmation),
  - include a plain-language `rationale`,
  - include a concrete `suggested_action` (what to pull or check next).

Prioritize patterns the brittle rule engine cannot see: entity
disambiguation (same person with different name spellings), timeline
anomalies across documents, missing documents a pattern implies should
exist, narrative inconsistencies between filings.

Respond with strict JSON only, matching this schema:
{
  "patterns": [
    {
      "title": "...",
      "description": "...",
      "rationale": "...",
      "evidence_weight": "SPECULATIVE" | "DIRECTIONAL",
      "entity_refs": ["uuid", ...],
      "doc_refs": ["Doc-1", ...],
      "suggested_action": "..."
    }
  ]
}
If you find no patterns, return {"patterns": []}. No prose outside JSON.
"""


def call_claude(context: dict[str, Any]) -> str:
    """Single Claude call with the pattern-detection system prompt.

    Thin wrapper so tests can mock this function. Uses the existing
    ai_proxy._call_ai under the hood.
    """
    user_message = (
        "Here is the case. Return patterns as strict JSON per the schema in "
        "the system prompt.\n\n" + json.dumps(context)
    )
    return ai_proxy._call_ai(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        max_tokens=4096,
    )


def analyze_case(case_id: Any) -> dict[str, Any]:
    """Run the AI pattern pass for one case. Returns a summary dict."""
    case = Case.objects.get(pk=case_id)
    context, doc_ref_map = build_context_with_refs(case)
    raw = call_claude(context)
    patterns = parse_response(raw)
    kept, dropped = validate_patterns(patterns, doc_ref_map)

    created = 0
    with transaction.atomic():
        for p in kept:
            finding = Finding.objects.create(
                case=case,
                rule_id=None,
                title=p["title"][:200],
                description=p["description"],
                narrative=p.get("rationale", ""),
                severity="INFORMATIONAL",
                status="NEW",
                evidence_weight=p["evidence_weight"],
                source=FindingSource.AI,
                evidence_snapshot={
                    "rationale": p["rationale"],
                    "suggested_action": p["suggested_action"],
                    "doc_refs": p["doc_refs"],
                    "entity_refs": p.get("entity_refs", []),
                },
            )
            for ref in p["doc_refs"]:
                doc_id = doc_ref_map.get(ref)
                if doc_id:
                    FindingDocument.objects.create(
                        finding=finding,
                        document_id=doc_id,
                    )
            for entity_id in p.get("entity_refs", []):
                # Skip invalid UUIDs silently — AI may fabricate these.
                try:
                    FindingEntity.objects.create(
                        finding=finding,
                        entity_id=entity_id,
                    )
                except Exception:
                    logger.info("Skipping invalid entity_ref %s", entity_id)
            created += 1

    return {
        "findings_created": created,
        "patterns_dropped": dropped,
        "case_id": str(case.id),
    }
```

Note on the `Finding.objects.create` call — field names (`narrative`, `severity`, `status`, `evidence_weight`, `source`) match the model at `models.py:1015–1055`. If `FindingEntity` requires a richer link shape in this codebase than a bare `entity_id`, that will surface in the test — fix inline by inspecting `models.py:1075` and adjusting.

- [ ] **Step 2: Run tests**

Run: `docker compose exec backend pytest tests/test_ai_pattern_analyze.py -v`
Expected: PASS (4 tests). If `FindingEntity` signature errors out, open `models.py:1075` and adjust the create call to match (then re-run).

- [ ] **Step 3: Run all AI-related tests together**

Run: `docker compose exec backend pytest tests/test_ai_pattern_context.py tests/test_ai_pattern_parse.py tests/test_ai_pattern_analyze.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/investigations/ai_pattern_augmentation.py
git commit -m "feat(ai): implement analyze_case with Claude call and Finding writes"
```

---

### Task 14: Add the Django-Q task function for AI pattern analysis

**Files:**
- Modify: `backend/investigations/jobs.py`

- [ ] **Step 1: Append the new task function**

At the bottom of `backend/investigations/jobs.py`, add:

```python
# ---------------------------------------------------------------------------
# AI Pattern Analysis
# ---------------------------------------------------------------------------


def run_ai_pattern_analysis(job_id: str) -> None:
    job = _load_and_mark_running(job_id)
    if job is None:
        return
    try:
        from investigations import ai_pattern_augmentation

        case_id = job.query_params["case_id"]
        summary = ai_pattern_augmentation.analyze_case(case_id)
        _mark_success(job, summary)
    except Exception as exc:  # noqa: BLE001 — surface every error to the user
        _mark_failed(job, exc)
```

- [ ] **Step 2: Run the existing jobs tests to confirm no regression**

Run: `docker compose exec backend pytest tests/test_jobs.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/investigations/jobs.py
git commit -m "feat(ai): add run_ai_pattern_analysis background task"
```

---

### Task 15: Write failing test for the `/ai/analyze-patterns/` endpoint

**Files:**
- Create: `tests/test_ai_pattern_view.py`

- [ ] **Step 1: Create the test file**

Create `tests/test_ai_pattern_view.py`:

```python
"""Tests for POST /api/cases/<id>/ai/analyze-patterns/ endpoint."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.test import Client

from investigations.models import Case, JobStatus, JobType, SearchJob


@pytest.fixture
def client():
    return Client(enforce_csrf_checks=False)


@pytest.fixture
def case(db):
    return Case.objects.create(name="Endpoint Test Case", status="ACTIVE")


def test_post_enqueues_job_and_returns_202(client, case):
    resp = client.post(
        f"/api/cases/{case.id}/ai/analyze-patterns/",
        data="{}",
        content_type="application/json",
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert body["status_url"] == f"/api/jobs/{body['job_id']}/"
    job = SearchJob.objects.get(id=body["job_id"])
    assert job.job_type == JobType.AI_PATTERN_ANALYSIS
    assert job.query_params["case_id"] == str(case.id)


def test_post_returns_409_when_prior_job_running(client, case):
    SearchJob.objects.create(
        case=case,
        job_type=JobType.AI_PATTERN_ANALYSIS,
        status=JobStatus.RUNNING,
        query_params={"case_id": str(case.id)},
    )
    resp = client.post(
        f"/api/cases/{case.id}/ai/analyze-patterns/",
        data="{}",
        content_type="application/json",
    )
    assert resp.status_code == 409


def test_post_allows_after_prior_job_finished(client, case):
    SearchJob.objects.create(
        case=case,
        job_type=JobType.AI_PATTERN_ANALYSIS,
        status=JobStatus.SUCCESS,
        query_params={"case_id": str(case.id)},
        result={"findings_created": 0, "patterns_dropped": 0},
    )
    resp = client.post(
        f"/api/cases/{case.id}/ai/analyze-patterns/",
        data="{}",
        content_type="application/json",
    )
    assert resp.status_code == 202
```

- [ ] **Step 2: Run, confirm failure**

Run: `docker compose exec backend pytest tests/test_ai_pattern_view.py -v`
Expected: FAIL — 404 Not Found (URL not registered).

- [ ] **Step 3: Commit**

```bash
git add tests/test_ai_pattern_view.py
git commit -m "test(ai): failing tests for /ai/analyze-patterns endpoint"
```

---

### Task 16: Add the endpoint and URL route

**Files:**
- Modify: `backend/investigations/views.py`
- Modify: `backend/investigations/urls.py`

- [ ] **Step 1: Add the view function in views.py**

Near the other `api_research_*` views (anywhere around line 4070–4130 in views.py), paste this:

```python
@csrf_exempt
@require_http_methods(["POST"])
def api_ai_analyze_patterns(request, pk):
    """Enqueue an AI pattern analysis job; return 202 with job id to poll.

    Rejects with 409 if a prior AI_PATTERN_ANALYSIS job for this case is
    still QUEUED or RUNNING.
    """
    case = get_object_or_404(Case, pk=pk)

    in_flight = SearchJob.objects.filter(
        case=case,
        job_type=JobType.AI_PATTERN_ANALYSIS,
        status__in=[JobStatus.QUEUED, JobStatus.RUNNING],
    ).exists()
    if in_flight:
        return JsonResponse(
            {"error": "An AI analysis job is already running for this case."},
            status=409,
        )

    with transaction.atomic():
        job = SearchJob.objects.create(
            case=case,
            job_type=JobType.AI_PATTERN_ANALYSIS,
            query_params={"case_id": str(case.id)},
        )
        async_task("investigations.jobs.run_ai_pattern_analysis", str(job.id))

    return JsonResponse(
        {
            "job_id": str(job.id),
            "status_url": f"/api/jobs/{job.id}/",
        },
        status=202,
    )
```

If `JobStatus` / `JobType` / `SearchJob` / `async_task` aren't already imported at the top of views.py, add them — check the existing `api_research_irs` imports (views.py line ~4080) for the pattern; they should already be imported since that function uses them.

- [ ] **Step 2: Add the URL route**

In `backend/investigations/urls.py`, add this entry alongside the other `api_research_*` paths (around line 90):

```python
    path(
        "api/cases/<uuid:pk>/ai/analyze-patterns/",
        views.api_ai_analyze_patterns,
        name="api_ai_analyze_patterns",
    ),
```

- [ ] **Step 3: Run the view tests**

Run: `docker compose exec backend pytest tests/test_ai_pattern_view.py -v`
Expected: PASS (3 tests).

- [ ] **Step 4: Run the full backend test suite as a regression check**

Run: `docker compose exec backend pytest -x -q`
Expected: all PASS (no existing tests broken).

- [ ] **Step 5: Commit**

```bash
git add backend/investigations/views.py backend/investigations/urls.py
git commit -m "feat(ai): add POST /api/cases/<id>/ai/analyze-patterns endpoint"
```

---

## Track 2 — AI Pattern Augmentation (frontend)

### Task 17: Add AI pattern API client function

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add `runAiPatternAnalysis` to api.ts**

Append near the other AI helpers:

```ts
export async function enqueueAiPatternAnalysis(
    caseId: string,
    options?: ApiRequestOptions,
): Promise<JobEnqueueResponse> {
    return request<JobEnqueueResponse>(
        `/api/cases/${caseId}/ai/analyze-patterns/`,
        { method: "POST", body: "{}" },
        { ...options, timeoutMs: options?.timeoutMs ?? 10000 },
    );
}
```

Make sure `JobEnqueueResponse` is imported in the existing types import block.

- [ ] **Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(frontend): add enqueueAiPatternAnalysis API helper"
```

---

### Task 18: Add source filter chip and AI badge to PipelineTab

**Files:**
- Modify: `frontend/src/components/cases/PipelineTab.tsx`
- Modify: `frontend/src/components/cases/PipelineTab.module.css` (new class names)

**Context:** The exact structure of `PipelineTab.tsx` wasn't inspected while planning (it was rewritten in Session 33). This task's shape is: add a filter chip row, an AI badge, and a "Run AI Analysis" button. The executor reads the current file and inserts the pieces idiomatically.

- [ ] **Step 1: Read the current PipelineTab**

Run: `cat frontend/src/components/cases/PipelineTab.tsx | head -200`
Identify:
- Where the Finding list is rendered.
- Where the tab header / toolbar is.
- What prop shape a Finding has (especially the `source` field — should be `"AUTO" | "MANUAL" | "AI"`).

- [ ] **Step 2: Add the filter chip row above the findings list**

```tsx
type SourceFilter = "ALL" | "AUTO" | "AI" | "MANUAL";

const [sourceFilter, setSourceFilter] = useState<SourceFilter>("ALL");

const filteredFindings = useMemo(() => {
    if (sourceFilter === "ALL") return findings;
    return findings.filter((f) => f.source === sourceFilter);
}, [findings, sourceFilter]);
```

And render (inside the tab body, above the list):

```tsx
<div className={styles.filterRow} role="toolbar" aria-label="Filter findings by source">
    {(["ALL", "AUTO", "AI", "MANUAL"] as SourceFilter[]).map((f) => (
        <button
            key={f}
            className={`${styles.chip} ${sourceFilter === f ? styles.chipActive : ""}`}
            onClick={() => setSourceFilter(f)}
            aria-pressed={sourceFilter === f}
        >
            {f === "ALL" ? "All" : f === "AUTO" ? "Rules" : f === "AI" ? "AI" : "Manual"}
        </button>
    ))}
</div>
```

- [ ] **Step 3: Add an "AI Finding" badge on each AI-sourced finding card**

Inside the Finding renderer:

```tsx
{finding.source === "AI" && (
    <span className={styles.aiBadge} title="AI-flagged pattern — review and confirm or dismiss">
        AI Finding
    </span>
)}
```

And render the AI-specific detail strip when source is AI:

```tsx
{finding.source === "AI" && finding.evidence_snapshot && (
    <div className={styles.aiDetail}>
        <p className={styles.aiRationale}>{finding.evidence_snapshot.rationale}</p>
        {finding.evidence_snapshot.suggested_action && (
            <p className={styles.aiAction}>
                <strong>Suggested next step:</strong> {finding.evidence_snapshot.suggested_action}
            </p>
        )}
    </div>
)}
```

- [ ] **Step 4: Add CSS for the new classes**

Append to `PipelineTab.module.css`:

```css
.filterRow {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
}

.chip {
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    border: 1px solid var(--color-border);
    background: var(--color-bg);
    cursor: pointer;
}

.chipActive {
    background: var(--color-accent);
    color: var(--color-accent-contrast);
    border-color: var(--color-accent);
}

.aiBadge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    background: var(--color-accent-soft, #e0f2ff);
    color: var(--color-accent, #0369a1);
    font-size: 0.75rem;
    font-weight: 600;
    margin-left: 0.5rem;
}

.aiDetail {
    margin-top: 0.5rem;
    padding: 0.5rem 0.75rem;
    border-left: 3px solid var(--color-accent, #0369a1);
    background: var(--color-bg-alt, #f8fafc);
}

.aiRationale { margin: 0 0 0.25rem 0; font-style: italic; }
.aiAction    { margin: 0; font-size: 0.875rem; }
```

- [ ] **Step 5: Verify build**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/cases/PipelineTab.tsx frontend/src/components/cases/PipelineTab.module.css
git commit -m "feat(frontend): add source filter chips and AI badge to PipelineTab"
```

---

### Task 19: Add "Run AI Analysis" button to PipelineTab

**Files:**
- Modify: `frontend/src/components/cases/PipelineTab.tsx`

- [ ] **Step 1: Wire the hook**

Near the top of the component:

```tsx
import { useAsyncJob } from "../../hooks/useAsyncJob";
import { enqueueAiPatternAnalysis, fetchCaseJobs } from "../../api";

const aiJob = useAsyncJob<{ findings_created: number; patterns_dropped: number }>({
    postUrl: `/api/cases/${caseId}/ai/analyze-patterns/`,
});
```

- [ ] **Step 2: Render the button**

Inside the tab header/toolbar area, alongside any existing actions:

```tsx
<div className={styles.aiRunControls}>
    <button
        onClick={() => aiJob.run({})}
        disabled={aiJob.status === "queued" || aiJob.status === "running"}
        className={styles.runAiButton}
    >
        {aiJob.status === "queued" || aiJob.status === "running"
            ? "Analyzing…"
            : "Run AI Analysis"}
    </button>
    {aiJob.status === "success" && aiJob.result && (
        <span className={styles.aiResultHint}>
            AI added {aiJob.result.findings_created} finding
            {aiJob.result.findings_created === 1 ? "" : "s"}
            {aiJob.result.patterns_dropped > 0 &&
                ` (${aiJob.result.patterns_dropped} dropped for invalid citations)`}
        </span>
    )}
    {aiJob.status === "failed" && (
        <span className={styles.aiResultError} role="alert">
            AI analysis failed: {aiJob.error}
        </span>
    )}
</div>
```

- [ ] **Step 3: Refetch findings on AI job success**

Wherever the findings list is refreshed (likely via a parent-provided callback or a local loader), add a `useEffect`:

```tsx
useEffect(() => {
    if (aiJob.status === "success") {
        // existing refetch, e.g. refreshFindings();
        refreshFindings?.();
    }
}, [aiJob.status, refreshFindings]);
```

If no `refreshFindings` callback is available at this level, add one via props from the parent view (`CaseDetailView`) and have it re-call the findings fetch. Keep the change small — the rest of Pipeline already reloads findings in many places.

- [ ] **Step 4: Add button CSS**

Append to `PipelineTab.module.css`:

```css
.aiRunControls { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; }
.runAiButton {
    padding: 0.5rem 1rem;
    border-radius: 6px;
    border: 1px solid var(--color-accent, #0369a1);
    background: var(--color-accent, #0369a1);
    color: white;
    cursor: pointer;
}
.runAiButton[disabled] { opacity: 0.6; cursor: not-allowed; }
.aiResultHint  { color: var(--color-text-muted, #64748b); font-size: 0.875rem; }
.aiResultError { color: var(--color-error, #b91c1c); font-size: 0.875rem; }
```

- [ ] **Step 5: Verify build + smoke test**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`

Then in a browser with the stack running:
1. Open a case with a few documents.
2. Click Pipeline tab → "Run AI Analysis".
3. Confirm: button disables with "Analyzing…", eventually shows "AI added N finding(s)", findings list refreshes, AI findings show the badge + rationale + suggested action.
4. Confirm filter chips toggle visibility as expected.
5. Click Confirm on an AI finding — confirm it flips status.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/cases/PipelineTab.tsx frontend/src/components/cases/PipelineTab.module.css
git commit -m "feat(frontend): add Run AI Analysis button to PipelineTab"
```

---

### Task 20: Update STATUS.md and CLAUDE.md

**Files:**
- Modify: `STATUS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: STATUS.md**

Add a new row to the **Working** table:

> AI pattern augmentation (on-demand) | Claude-powered second pass that reads case context + document excerpts and surfaces candidate Findings labeled `source=AI`. Triaged in Pipeline tab via Confirm/Needs Evidence/Dismiss. | Never asserts fraud — highlights patterns and suggests next actions. Investigator has the final say.

If "Frontend consuming async job 202 + poll" is in the Planned list, mark it done (strike-through + DONE note).

- [ ] **Step 2: CLAUDE.md**

- Bump "API endpoints" total (currently 45) to reflect the new `/ai/analyze-patterns/` endpoint — should become 46.
- Add an entry to the **Session History** section for this session (Session 36):

```
- Session 36: **Async research frontend wired + AI pattern augmentation shipped.**
  Track 1: built the `useAsyncJob` React hook and retrofitted ResearchTab so the
  four async research surfaces (IRS name, IRS fetch_xml, Ohio AOS, County Parcel)
  consume the `202 + poll` contract from Session 35, with reattach-on-mount
  resuming in-flight jobs. Killed the `0 is not iterable` crash.
  Track 2: added `ai_pattern_augmentation.py` — on-demand Claude Sonnet pass that
  reads case structured data + per-document 2K-char excerpts (Strategy B) and
  writes candidate Findings as `source=AI`, `evidence_weight=SPECULATIVE|DIRECTIONAL`.
  Hard guardrails in the system prompt: never assert fraud, always cite docs by
  `Doc-N`, always include a suggested next action. Doc-ref validator drops AI
  patterns that cite non-existent documents; evidence-weight coercer prevents
  AI from claiming `DOCUMENTED`/`TRACED`. PipelineTab gains a source filter chip
  (`All | Rules | AI | Manual`) and a "Run AI Analysis" button that reuses
  `useAsyncJob`. AI findings triage through the same confirm/dismiss flow —
  referral package exporter already filters on `status=CONFIRMED` so no exporter
  changes were needed.
```

- Update the "AI" section in the endpoints table to include:

```
POST   /api/cases/<uuid>/ai/analyze-patterns/   → Run AI pattern augmentation pass (async, returns 202 + job_id)
```

- [ ] **Step 3: Commit**

```bash
git add STATUS.md CLAUDE.md
git commit -m "docs: record Session 36 (async frontend + AI pattern augmentation)"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage:**
- Track 1 architecture (useAsyncJob + retrofit) → Tasks 1–6 ✅
- Track 2 context builder (Strategy B) → Tasks 8–9 ✅
- Track 2 response parsing + validation (malformed JSON, bad doc refs, weight coercion) → Tasks 10–11 ✅
- Track 2 Finding writer (source=AI, FindingDocument/FindingEntity links, transaction) → Tasks 12–13 ✅
- AI_PATTERN_ANALYSIS job type + task function → Tasks 7, 14 ✅
- POST endpoint with 409 for in-flight job → Tasks 15–16 ✅
- PipelineTab filter chips + AI badge → Task 18 ✅
- "Run AI Analysis" button reusing useAsyncJob → Task 19 ✅
- Reattach-on-mount for Research tab → Task 5 step 1d ✅
- System prompt guardrails → Task 13 (SYSTEM_PROMPT constant) ✅
- Documentation updates → Task 20 ✅

**Placeholder scan:** No TBD, TODO, or "add appropriate error handling" phrases. Every code block is concrete and paste-ready.

**Type consistency:** `JobStatus`/`JobType`/`SearchJobSummary` naming matches across `types.ts`, `api.ts`, hook, and backend migration. `FindingSource.AI` matches `source === "AI"` on the frontend filter. `evidence_snapshot.rationale` / `evidence_snapshot.suggested_action` used consistently between backend writer (Task 13) and frontend renderer (Task 18).

**Scope check:** Two clearly sequenced tracks in one plan. Track 1 is short and unblocks Track 2. They share the `useAsyncJob` hook. Keeping them in one plan matches how the spec was written and how they'll land in one branch.

---

Plan complete and saved to [docs/superpowers/plans/2026-04-21-async-frontend-and-ai-patterns.md](docs/superpowers/plans/2026-04-21-async-frontend-and-ai-patterns.md).
