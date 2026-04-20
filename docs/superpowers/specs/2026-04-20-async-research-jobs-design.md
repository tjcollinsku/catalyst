# Async Research Jobs — Design

**Date:** 2026-04-20
**Status:** Approved, ready for implementation planning
**Author:** Tyler Collins (with Claude)

## Problem

The four slow research endpoints in Catalyst (`/api/cases/<uuid>/research/irs/`
name search, IRS `fetch_xml=true`, `/research/ohio-aos/`, `/research/parcels/`)
run their work inline on the gunicorn request thread. The IRS name-search path
streams 50–90 MB index CSVs for seven years from `apps.irs.gov` and can legitimately
take 30–120 seconds.

Gunicorn's default worker timeout is 30 seconds. When a worker exceeds it, the
worker is killed; nginx receives no response and returns `502 Bad Gateway` to
the browser. This was reproduced on 2026-04-20 with query `"do good"` on the
local Docker stack.

Raising the gunicorn timeout is a band-aid. It does not address the real issue:
long-running external-data fetches should not occupy a request thread. This
spec addresses that structurally.

## Non-goals

- Redesigning the Research tab results UI (collapsible per-entity cards, 7-year
  toggle, download buttons). Separate future work.
- Making the batch OCR endpoint async. Same-shaped problem but different
  scaling profile (CPU-bound, in-container); separate future work.
- Adding a job history / "recent searches" panel. We persist the data needed
  for it, but UI work is deferred.
- Multi-user authorization on job results. `created_by` field exists on the
  model for future use; no enforcement in v1.

## Architecture

Add **Django-Q2** as the job queue, using **PostgreSQL as the broker** (not
Redis). Introduces one new queue worker container alongside the existing
`backend` service. No new infrastructure services.

A `SearchJob` model in Postgres tracks every job's state and stores the final
result payload. The four slow research endpoints are converted from
work-inline to enqueue-and-return-`202 Accepted`. The frontend polls a new
job-status endpoint every 2 seconds. On Research tab mount, the frontend
queries a case-jobs endpoint to reattach to any running or recently-completed
job for the current case.

### Why Django-Q2 with the Postgres broker (vs. Celery + Redis)

- Zero new infrastructure — reuses existing Postgres
- Real job queue semantics (retries, failure tracking, scheduled tasks)
- Can swap in Redis later with a config change if traffic ever warrants it
- Lighter cognitive load in a portfolio project — fewer moving parts to
  explain in an interview

## Components

### New

- **`SearchJob` Django model** (schema below)
- **`backend/investigations/jobs.py`** — plain Python task functions that
  Django-Q2 invokes. One function per job type:
  - `run_irs_name_search(job_id)`
  - `run_irs_fetch_xml(job_id)`
  - `run_ohio_aos_search(job_id)`
  - `run_county_parcel_search(job_id)`
- **New API endpoints:**
  - `GET /api/jobs/<uuid>/` — poll single job status + result
  - `GET /api/cases/<uuid>/jobs/?limit=5` — list recent jobs for a case (for
    reattach-on-mount)
- **New container** in `docker-compose.yml` — runs `python manage.py qcluster`.
  Same image as `backend`, different command.
- **New entries** in `requirements.txt` (`django-q2`), `INSTALLED_APPS`
  (`django_q`), and a `Q_CLUSTER` settings block.

### Changed

- **4 existing POST views** in `views.py` converted from work-inline to
  enqueue-and-return-202:
  - `api_research_irs` (name-search path + EIN-with-`fetch_xml` path)
  - `api_research_ohio_aos`
  - `api_research_parcels`

### Unchanged

- Fast endpoints stay synchronous: IRS EIN-only search (no `fetch_xml`),
  County Recorder URL builder, Ohio SOS local CSV lookup, health check,
  document CRUD, everything else. No point queueing work that finishes
  in <1 second.
- Existing response *shapes* for each research endpoint are preserved
  verbatim — the frontend just receives them via the poll endpoint instead
  of directly from the POST.

## Data model

### `SearchJob`

| Field            | Type                        | Notes |
|------------------|-----------------------------|-------|
| `id`             | UUID primary key            | Stable ID for polling |
| `case`           | FK → `Case`, nullable       | Nullable so future non-case jobs fit |
| `job_type`       | CharField(choices)          | `IRS_NAME_SEARCH`, `IRS_FETCH_XML`, `OHIO_AOS`, `COUNTY_PARCEL` |
| `status`         | CharField(choices)          | `QUEUED`, `RUNNING`, `SUCCESS`, `FAILED` |
| `query_params`   | JSONField                   | Exact request body that kicked the job off |
| `result`         | JSONField, nullable         | Response payload the old sync endpoint returned |
| `error_message`  | TextField(blank=True)       | Exception string if `status=FAILED` |
| `created_at`     | DateTimeField auto_now_add  | — |
| `started_at`     | DateTimeField, nullable     | Set when worker picks the job up |
| `finished_at`    | DateTimeField, nullable     | Set on `SUCCESS` or `FAILED` |
| `created_by`     | FK → User, nullable         | Unused in v1; placeholder for multi-user future |

**Index:** `(case, -created_at)` for the reattach query.

**Design notes:**
- No `progress` field in v1 (UX is a simple spinner; adding progress would
  tempt us into building progress UI). Easy one-column migration if we want
  it later.
- `result` as JSONField — cleaner than per-job-type result tables for
  heterogeneous payload shapes. Largest expected payload (IRS name search,
  up to 200 filings) is well under 1 MB; JSONB handles this comfortably.
- No TTL / cleanup cron in v1. Rows accumulate. Acceptable for a solo-user
  tool for months. Add cleanup later if/when it matters.

## Flow

### Request kickoff
1. Frontend `POST /api/cases/<uuid>/research/irs/` with `{query: "do good"}`
2. View wraps in `transaction.atomic()`:
   - Creates `SearchJob` row with `status=QUEUED`, `query_params`, `job_type`
   - Calls `django_q.tasks.async_task("investigations.jobs.run_irs_name_search", job.id)`
3. View returns `202 Accepted` with body:
   ```json
   {"job_id": "<uuid>", "status_url": "/api/jobs/<uuid>/"}
   ```
4. Total latency: ~20 ms.

### Worker execution (separate container)
5. `qcluster` worker picks up the queued task, loads the `SearchJob` row,
   sets `status=RUNNING`, `started_at=now()`.
6. Worker calls the same connector code that used to run inline
   (e.g. `irs_connector.search_990_by_name(...)`). Connector code is
   unchanged.
7. On success: worker writes response payload to `job.result`, sets
   `status=SUCCESS`, `finished_at=now()`.
8. On exception: worker catches, writes exception string to
   `job.error_message`, sets `status=FAILED`, `finished_at=now()`.

### Frontend polling
9. Frontend receives the 202, begins polling `GET /api/jobs/<id>/` every 2 s.
10. While `status ∈ {QUEUED, RUNNING}` — spinner remains visible.
11. On `status=SUCCESS` — frontend renders `job.result` using the existing
    results component (no shape changes).
12. On `status=FAILED` — frontend shows `job.error_message` in the existing
    red "Search Error" box.

### Reattach on mount
13. Research tab mount fires `GET /api/cases/<uuid>/jobs/?limit=5`.
14. If any returned job is `RUNNING`, or `SUCCESS` within last 15 minutes,
    and matches the currently-selected data source, frontend silently
    hydrates the results view with that job. (Silent hydrate — no
    "restore?" prompt, less friction.)

## Error handling

| Failure mode | Behavior |
|---|---|
| IRS server 5xx / timeout | Worker catches `IRSNetworkError`, job → `FAILED` with error string; frontend shows in existing red error box |
| Worker crashes mid-job | Django-Q2 marks task failed; job → `FAILED` with `error_message="worker crashed"` |
| Enqueue call fails (broker unreachable) | `transaction.atomic()` rolls back the SearchJob row; view returns 500; frontend shows "Could not start search" |
| User double-clicks Search | Each click creates a new SearchJob. Acceptable in v1; dedup deferred |
| User navigates away mid-job | Job continues in worker, completes, result sits in DB; reattach logic picks it up on return |
| Worker container down | Jobs sit in `QUEUED`. Frontend spinner continues; messaging escalates at 60 s / 180 s. No auto-timeout at the backend — legitimate IRS searches can take ~2 min |

**Retry policy:** Django-Q2 retries are **disabled** for these tasks. Retrying
a partially-failed IRS search wastes work; surface the error and let the user
retry manually.

**Hard task timeout:** 300 seconds. Protects against a hung IRS connection
silently consuming a worker forever.

**Worker concurrency:** 2 workers in the qcluster. Two searches can run
simultaneously. More than enough for a solo user.

## Testing

### Unit tests (fast, in CI)
- `SearchJob` model: state transitions, JSON field round-trip
- Each task function in `jobs.py`: called directly (not through queue), with
  the connector mocked. Assert the SearchJob row ends in the correct state
  with the correct `result` / `error_message` for success and failure paths.
- Converted views: POST → assert 202 + correct SearchJob row + `async_task`
  was called (mocked). One test per converted endpoint.
- Poll endpoint: GET `/api/jobs/<id>/` returns correct shape for each of
  the four status values.

### Integration test (one)
- Spin up a qcluster in a test fixture
- Enqueue a task that returns a canned result without hitting the IRS
- Poll with condition-based wait (not `time.sleep`) until `status=SUCCESS`
- Assert result

### Not testing
- Actual IRS server calls — flaky for CI, already covered by existing
  mocked-HTTP connector tests
- Frontend polling behavior — separate frontend session

### Test hygiene
- No `time.sleep()` in tests. Condition-based polling only:
  `while job.status == QUEUED: job.refresh_from_db()` with a max iteration count.

## Open items (deferred)

- Frontend progress display (requires `progress` column)
- Job cancel endpoint
- Job history panel on Research tab
- TTL / cleanup cron for old `SearchJob` rows
- Applying the same pattern to batch OCR (`/documents/process-pending/`)
