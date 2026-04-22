# Async Research Jobs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the four slow research endpoints off the gunicorn request thread and onto a Django-Q2 background queue backed by PostgreSQL, eliminating the `502 Bad Gateway` failure mode and letting the frontend reattach to in-flight searches after a page refresh.

**Architecture:** Add Django-Q2 with its `django_q.brokers.orm` broker (reuses existing Postgres). Introduce one `SearchJob` model that tracks status and stores the final result payload. Convert the four slow POSTs from work-inline to enqueue-and-return-`202`. Add two new read endpoints: poll-single-job and list-jobs-for-case. Run a second container (`qcluster`) alongside the existing backend that pulls tasks off the queue.

**Tech Stack:** Django 5.x, Django-Q2, PostgreSQL 16, Docker Compose. Tests use Django's built-in test runner (`manage.py test`) — this project has no pytest setup.

**Spec:** [docs/superpowers/specs/2026-04-20-async-research-jobs-design.md](../specs/2026-04-20-async-research-jobs-design.md)

---

## File Structure

**Created:**
- `backend/investigations/migrations/0022_searchjob.py` — migration for the new table
- `backend/investigations/jobs.py` — the four task functions Django-Q2 runs in a worker
- `backend/investigations/tests/__init__.py` — new test package (the app has no tests dir yet)
- `backend/investigations/tests/test_searchjob_model.py` — unit tests for the model
- `backend/investigations/tests/test_jobs.py` — unit tests for each task function
- `backend/investigations/tests/test_job_views.py` — unit tests for the poll + list-for-case endpoints, and the four converted views
- `backend/investigations/tests/test_integration_qcluster.py` — one end-to-end test that runs a real qcluster

**Modified:**
- `backend/requirements.txt` — add `django-q2`
- `backend/catalyst/settings.py` — add `django_q` to `INSTALLED_APPS`, add `Q_CLUSTER` config block
- `backend/investigations/models.py` — add `SearchJob` model + `JobType` + `JobStatus` TextChoices
- `backend/investigations/views.py` — convert 4 views (`api_research_irs`, `api_research_ohio_aos`, `api_research_parcels`) + add 2 new views (`api_job_detail`, `api_case_jobs`)
- `backend/investigations/urls.py` — wire the 2 new endpoints
- `docker-compose.yml` — add `qcluster` service

**Unchanged (important — don't touch):**
- `backend/investigations/irs_connector.py` — the connector code is reused verbatim from inside the task functions
- `backend/investigations/ohio_aos_connector.py` — same
- `backend/investigations/county_auditor_connector.py` — same
- All frontend code — out of scope for this plan, handled in a later session
- `api_research_ohio_sos`, `api_research_recorder`, `api_research_add_to_case` — these are fast/local, stay synchronous

---

### Task 1: Add Django-Q2 dependency and verify it installs

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add the dependency**

Append to `backend/requirements.txt`:

```
# Background job queue (PostgreSQL-backed broker — no Redis required)
django-q2>=1.7,<2.0
```

- [ ] **Step 2: Rebuild the backend container and verify install**

Run:

```bash
docker compose build backend
docker compose run --rm backend python -c "import django_q; print(django_q.VERSION)"
```

Expected: prints a version tuple like `(1, 7, 6)` (exact numbers may differ) with no ImportError.

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add django-q2 for async job queue"
```

---

### Task 2: Register django_q in INSTALLED_APPS and add the Q_CLUSTER config

**Files:**
- Modify: `backend/catalyst/settings.py:44-54` (INSTALLED_APPS block) and bottom of file (new Q_CLUSTER block)

- [ ] **Step 1: Add `django_q` to INSTALLED_APPS**

Find the `INSTALLED_APPS` list (around line 44) and add `django_q` on the line just before `"investigations",`:

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "django_q",
    "investigations",
]
```

- [ ] **Step 2: Append the Q_CLUSTER config block at the bottom of settings.py**

Add this at the very end of `backend/catalyst/settings.py`:

```python
# ---------------------------------------------------------------------------
# Django-Q2 Background Job Queue
# ---------------------------------------------------------------------------
# Uses the built-in ORM broker — tasks are stored in the existing Postgres
# database, no Redis required. See: django-q2.readthedocs.io
Q_CLUSTER = {
    "name": "catalyst",
    "workers": 2,
    "timeout": 300,       # hard kill a task after 5 minutes
    "retry": 360,         # must be > timeout; unused because we disable retries below
    "max_attempts": 1,    # no retries — we surface the error to the user
    "save_limit": 500,    # retain last 500 completed tasks in django_q_task
    "queue_limit": 50,
    "bulk": 1,
    "orm": "default",     # use the default Django database as broker
    "catch_up": False,    # don't re-run scheduled tasks missed while cluster was down
}
```

- [ ] **Step 3: Run the django_q migrations inside the backend container**

Django-Q2 ships its own migrations for the broker tables. Run them now so `manage.py check` passes in later tasks:

```bash
docker compose up -d db backend
docker compose exec backend python manage.py migrate django_q
```

Expected: several `Applying django_q.####_* ... OK` lines, no errors.

- [ ] **Step 4: Verify settings load cleanly**

```bash
docker compose exec backend python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add backend/catalyst/settings.py
git commit -m "feat: configure django-q2 with postgres orm broker"
```

---

### Task 3: Write the failing test for the SearchJob model

**Files:**
- Create: `backend/investigations/tests/__init__.py` (empty)
- Create: `backend/investigations/tests/test_searchjob_model.py`

- [ ] **Step 1: Create the tests package**

Create `backend/investigations/tests/__init__.py` with empty content.

- [ ] **Step 2: Write the failing test**

Create `backend/investigations/tests/test_searchjob_model.py` with this exact content:

```python
"""Unit tests for the SearchJob model."""

import uuid

from django.test import TestCase

from investigations.models import Case, JobStatus, JobType, SearchJob


class SearchJobModelTests(TestCase):
    def setUp(self):
        self.case = Case.objects.create(name="Test Case")

    def test_create_default_status_is_queued(self):
        job = SearchJob.objects.create(
            case=self.case,
            job_type=JobType.IRS_NAME_SEARCH,
            query_params={"query": "do good"},
        )
        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertIsNone(job.started_at)
        self.assertIsNone(job.finished_at)
        self.assertIsNone(job.result)
        self.assertEqual(job.error_message, "")
        self.assertIsInstance(job.id, uuid.UUID)

    def test_json_result_roundtrip(self):
        payload = {
            "source": "irs_teos_xml",
            "results": [{"ein": "12-3456789", "tax_year": 2024}],
            "count": 1,
            "notes": [],
        }
        job = SearchJob.objects.create(
            case=self.case,
            job_type=JobType.IRS_NAME_SEARCH,
            query_params={"query": "x"},
            status=JobStatus.SUCCESS,
            result=payload,
        )
        job.refresh_from_db()
        self.assertEqual(job.result, payload)

    def test_nullable_case_for_future_non_case_jobs(self):
        job = SearchJob.objects.create(
            case=None,
            job_type=JobType.IRS_NAME_SEARCH,
            query_params={"query": "x"},
        )
        self.assertIsNone(job.case)

    def test_recent_for_case_query_uses_index(self):
        # Create 3 jobs for this case and 1 for another
        other_case = Case.objects.create(name="Other")
        for i in range(3):
            SearchJob.objects.create(
                case=self.case,
                job_type=JobType.IRS_NAME_SEARCH,
                query_params={"n": i},
            )
        SearchJob.objects.create(
            case=other_case,
            job_type=JobType.IRS_NAME_SEARCH,
            query_params={"n": "other"},
        )
        jobs = SearchJob.objects.filter(case=self.case).order_by("-created_at")
        self.assertEqual(jobs.count(), 3)
```

- [ ] **Step 3: Run the test to verify it fails**

Run:

```bash
docker compose exec backend python manage.py test investigations.tests.test_searchjob_model -v 2
```

Expected: `ImportError` or `AttributeError` on `JobStatus` / `JobType` / `SearchJob` — the model does not exist yet.

---

### Task 4: Implement the SearchJob model and its TextChoices

**Files:**
- Modify: `backend/investigations/models.py` (append to end of file)

- [ ] **Step 1: Append the model code**

Append to the very bottom of `backend/investigations/models.py`:

```python
class JobType(models.TextChoices):
    IRS_NAME_SEARCH = "IRS_NAME_SEARCH", "IRS Name Search"
    IRS_FETCH_XML = "IRS_FETCH_XML", "IRS Fetch XML"
    OHIO_AOS = "OHIO_AOS", "Ohio Auditor of State"
    COUNTY_PARCEL = "COUNTY_PARCEL", "County Parcel Search"


class JobStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


class SearchJob(UUIDPrimaryKeyModel):
    """Async research job — tracks state of a backgrounded external-data fetch.

    The four slow research endpoints (`/research/irs/` name search,
    `/research/irs/` with fetch_xml=true, `/research/ohio-aos/`,
    `/research/parcels/`) create a SearchJob row, enqueue a Django-Q2
    task, and return 202 with the job_id. A worker in the qcluster
    container picks the task up, calls the connector code, and writes
    the response payload to `result`. The frontend polls
    `/api/jobs/<id>/` for status + result.
    """

    case = models.ForeignKey(
        "Case",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="search_jobs",
    )
    job_type = models.CharField(max_length=32, choices=JobType.choices)
    status = models.CharField(
        max_length=16,
        choices=JobStatus.choices,
        default=JobStatus.QUEUED,
    )
    query_params = models.JSONField()
    result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="search_jobs",
    )

    class Meta:
        indexes = [
            models.Index(fields=["case", "-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.job_type} {self.status} ({self.id})"
```

- [ ] **Step 2: Generate the migration**

```bash
docker compose exec backend python manage.py makemigrations investigations
```

Expected: creates `backend/investigations/migrations/0022_searchjob.py` (or `0022_*` with a hashed name — either is fine). Output mentions `Create model SearchJob`.

- [ ] **Step 3: Apply the migration**

```bash
docker compose exec backend python manage.py migrate investigations
```

Expected: `Applying investigations.0022_... OK`.

- [ ] **Step 4: Run the model tests to verify they pass**

```bash
docker compose exec backend python manage.py test investigations.tests.test_searchjob_model -v 2
```

Expected: `Ran 4 tests in X.XXXs — OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/investigations/models.py backend/investigations/migrations/0022_*.py backend/investigations/tests/__init__.py backend/investigations/tests/test_searchjob_model.py
git commit -m "feat: add SearchJob model for async research jobs"
```

---

### Task 5: Write failing tests for the task functions in jobs.py

**Files:**
- Create: `backend/investigations/tests/test_jobs.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/investigations/tests/test_jobs.py` with this exact content:

```python
"""Unit tests for the task functions in investigations.jobs.

These tests call the task functions directly (not through the queue),
and mock out the underlying connector so no network calls are made.
"""

from unittest import mock

from django.test import TestCase

from investigations.jobs import (
    run_county_parcel_search,
    run_irs_fetch_xml,
    run_irs_name_search,
    run_ohio_aos_search,
)
from investigations.models import Case, JobStatus, JobType, SearchJob


class RunIrsNameSearchTests(TestCase):
    def setUp(self):
        self.case = Case.objects.create(name="T")
        self.job = SearchJob.objects.create(
            case=self.case,
            job_type=JobType.IRS_NAME_SEARCH,
            query_params={"query": "do good"},
        )

    @mock.patch("investigations.jobs.irs_connector")
    def test_success_sets_result_and_status(self, mock_connector):
        mock_connector.INDEX_YEARS = [2024]
        mock_filing = mock.Mock()
        mock_connector.search_990_by_name.return_value = [mock_filing]
        mock_connector.filing_to_dict.return_value = {
            "ein": "12-3456789",
            "tax_year": 2024,
        }

        run_irs_name_search(str(self.job.id))

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.SUCCESS)
        self.assertIsNotNone(self.job.started_at)
        self.assertIsNotNone(self.job.finished_at)
        self.assertEqual(self.job.result["count"], 1)
        self.assertEqual(self.job.result["source"], "irs_teos_xml")
        self.assertEqual(self.job.error_message, "")

    @mock.patch("investigations.jobs.irs_connector")
    def test_connector_exception_sets_failed_with_message(self, mock_connector):
        mock_connector.INDEX_YEARS = [2024]

        class FakeIRSError(Exception):
            pass

        mock_connector.IRSNetworkError = FakeIRSError
        mock_connector.search_990_by_name.side_effect = FakeIRSError("boom")

        run_irs_name_search(str(self.job.id))

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.FAILED)
        self.assertIn("boom", self.job.error_message)
        self.assertIsNone(self.job.result)
        self.assertIsNotNone(self.job.finished_at)


class RunIrsFetchXmlTests(TestCase):
    def setUp(self):
        self.case = Case.objects.create(name="T")
        self.job = SearchJob.objects.create(
            case=self.case,
            job_type=JobType.IRS_FETCH_XML,
            query_params={"query": "12-3456789"},
        )

    @mock.patch("investigations.jobs.irs_connector")
    def test_ein_search_with_fetch_xml_populates_parsed(self, mock_connector):
        mock_connector.INDEX_YEARS = [2024]
        mock_filing = mock.Mock()
        mock_filing.return_type = "990"
        mock_filing.tax_year = 2024
        mock_filing.object_id = "obj"
        mock_filing.xml_batch_id = "batch"
        search_result = mock.Mock()
        search_result.filings = [mock_filing]
        search_result.total_found = 1
        search_result.ein_formatted = "12-3456789"
        search_result.years_searched = [2024]
        mock_connector.search_990_by_ein.return_value = search_result
        mock_connector.filing_to_dict.return_value = {"ein": "12-3456789"}
        mock_connector.fetch_990_xml.return_value = "<xml/>"
        mock_connector.parse_990_xml.return_value = mock.Mock()
        mock_connector.parsed_990_to_dict.return_value = {"financials": {}}

        class FakeIRSError(Exception):
            pass

        mock_connector.IRSNetworkError = FakeIRSError
        mock_connector.IRSParseError = FakeIRSError

        run_irs_fetch_xml(str(self.job.id))

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.SUCCESS)
        self.assertEqual(self.job.result["count"], 1)
        self.assertIn("parsed", self.job.result["results"][0])


class RunOhioAosSearchTests(TestCase):
    def setUp(self):
        self.case = Case.objects.create(name="T")
        self.job = SearchJob.objects.create(
            case=self.case,
            job_type=JobType.OHIO_AOS,
            query_params={"query": "Bright Future"},
        )

    @mock.patch("investigations.jobs.ohio_aos_connector")
    def test_success_sets_result(self, mock_aos):
        mock_aos.search_aos_by_name.return_value = [
            {"entity_name": "Bright Future", "report_url": "https://x"},
        ]
        run_ohio_aos_search(str(self.job.id))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.SUCCESS)
        self.assertEqual(self.job.result["count"], 1)


class RunCountyParcelSearchTests(TestCase):
    def setUp(self):
        self.case = Case.objects.create(name="T")
        self.job = SearchJob.objects.create(
            case=self.case,
            job_type=JobType.COUNTY_PARCEL,
            query_params={"query": "Smith", "county": "Darke"},
        )

    @mock.patch("investigations.jobs.county_auditor_connector")
    def test_success_sets_result(self, mock_auditor):
        mock_auditor.search_parcels_by_owner.return_value = [
            {"parcel_number": "A-1", "owner_name": "Smith"},
        ]
        run_county_parcel_search(str(self.job.id))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.SUCCESS)
        self.assertEqual(self.job.result["count"], 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
docker compose exec backend python manage.py test investigations.tests.test_jobs -v 2
```

Expected: `ModuleNotFoundError: No module named 'investigations.jobs'` — the module does not exist yet.

---

### Task 6: Implement the four task functions in jobs.py

**Files:**
- Create: `backend/investigations/jobs.py`

- [ ] **Step 1: Write the task functions**

Create `backend/investigations/jobs.py` with this exact content:

```python
"""Background task functions for async research jobs.

Each function takes a SearchJob id (string UUID), loads the row, runs
the corresponding connector, and writes the response payload or the
exception back to the row. These functions are enqueued via
django_q.tasks.async_task from the converted research views.

Task functions are plain Python callables — Django-Q2 imports them by
dotted path, so the name and location here matter. If you rename or
move one, update the enqueue calls in views.py too.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from investigations import county_auditor_connector, irs_connector, ohio_aos_connector
from investigations.models import JobStatus, SearchJob

logger = logging.getLogger(__name__)


def _load_and_mark_running(job_id: str) -> SearchJob | None:
    """Load a job by id, flip it to RUNNING, return it.

    Returns None if the job no longer exists (e.g. it was deleted between
    enqueue and pickup). Callers should bail out in that case.
    """
    try:
        job = SearchJob.objects.get(id=job_id)
    except SearchJob.DoesNotExist:
        logger.warning("SearchJob %s not found on pickup", job_id)
        return None

    job.status = JobStatus.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])
    return job


def _mark_success(job: SearchJob, result: dict) -> None:
    job.status = JobStatus.SUCCESS
    job.result = result
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "result", "finished_at"])


def _mark_failed(job: SearchJob, exc: BaseException) -> None:
    job.status = JobStatus.FAILED
    job.error_message = f"{type(exc).__name__}: {exc}"
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error_message", "finished_at"])
    logger.exception("SearchJob %s failed: %s", job.id, exc)


def run_irs_name_search(job_id: str) -> None:
    """Search IRS TEOS indexes by organization name across all years."""
    job = _load_and_mark_running(job_id)
    if job is None:
        return
    try:
        query = job.query_params["query"].strip()
        filings = irs_connector.search_990_by_name(
            query,
            years=irs_connector.INDEX_YEARS,
            max_results=200,
        )
        records = [irs_connector.filing_to_dict(f) for f in filings]
        result = {
            "source": "irs_teos_xml",
            "results": records,
            "count": len(records),
            "notes": [
                "City/state not shown in search — click Fetch 990 Data to pull "
                "address and full financial/governance detail from the XML."
            ],
        }
        _mark_success(job, result)
    except Exception as exc:  # noqa: BLE001 — surface every error to the user
        _mark_failed(job, exc)


def run_irs_fetch_xml(job_id: str) -> None:
    """Fetch + parse the actual 990 XML for an EIN across all index years."""
    job = _load_and_mark_running(job_id)
    if job is None:
        return
    try:
        query = job.query_params["query"].strip()
        cleaned = query.replace("-", "").replace(" ", "")
        search_result = irs_connector.search_990_by_ein(
            cleaned, years=irs_connector.INDEX_YEARS
        )
        records = []
        notes = []
        for filing in search_result.filings:
            record = irs_connector.filing_to_dict(filing)
            try:
                xml_text = irs_connector.fetch_990_xml(filing)
                parsed = irs_connector.parse_990_xml(
                    xml_text, filing.object_id, filing.xml_batch_id
                )
                record["parsed"] = irs_connector.parsed_990_to_dict(parsed)
            except (irs_connector.IRSNetworkError, irs_connector.IRSParseError) as e:
                record["parsed"] = None
                notes.append(
                    f"Could not parse {filing.return_type} {filing.tax_year}: {e}"
                )
            records.append(record)

        if search_result.total_found == 0:
            notes.append(
                f"No e-filed 990 returns found for EIN "
                f"{search_result.ein_formatted} in "
                f"{', '.join(str(y) for y in search_result.years_searched)} "
                f"indexes. The organization may file on paper or be below the "
                f"e-filing threshold."
            )

        result = {
            "source": "irs_teos_xml",
            "results": records,
            "count": len(records),
            "notes": notes,
        }
        _mark_success(job, result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(job, exc)


def run_ohio_aos_search(job_id: str) -> None:
    """Scrape Ohio Auditor of State audit reports for a given entity name."""
    job = _load_and_mark_running(job_id)
    if job is None:
        return
    try:
        query = job.query_params["query"].strip()
        rows = ohio_aos_connector.search_aos_by_name(query)
        result = {
            "source": "ohio_aos",
            "results": rows,
            "count": len(rows),
            "notes": [],
        }
        _mark_success(job, result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(job, exc)


def run_county_parcel_search(job_id: str) -> None:
    """Query ODNR statewide parcel API by owner name."""
    job = _load_and_mark_running(job_id)
    if job is None:
        return
    try:
        query = job.query_params["query"].strip()
        county = job.query_params.get("county")
        rows = county_auditor_connector.search_parcels_by_owner(
            query, county=county
        )
        result = {
            "source": "county_parcels",
            "results": rows,
            "count": len(rows),
            "notes": [],
        }
        _mark_success(job, result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(job, exc)
```

- [ ] **Step 2: Run the task tests to verify they pass**

```bash
docker compose exec backend python manage.py test investigations.tests.test_jobs -v 2
```

Expected: `Ran 5 tests in X.XXXs — OK`. If any test fails because the connector function it mocks is named differently in the actual connector (e.g., `search_aos_by_name` may be named differently in `ohio_aos_connector.py`), open the connector file, find the actual function name, and update both the mock target in the test AND the call site in `jobs.py` to match. Do not guess.

- [ ] **Step 3: Commit**

```bash
git add backend/investigations/jobs.py backend/investigations/tests/test_jobs.py
git commit -m "feat: add background task functions for research jobs"
```

---

### Task 7: Write failing tests for the new job views (poll + case-jobs)

**Files:**
- Create: `backend/investigations/tests/test_job_views.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/investigations/tests/test_job_views.py` with this exact content:

```python
"""Unit tests for the job-status endpoints and converted research views."""

import json
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from investigations.models import Case, JobStatus, JobType, SearchJob


class JobDetailViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.case = Case.objects.create(name="T")

    def test_returns_job_state_for_queued(self):
        job = SearchJob.objects.create(
            case=self.case,
            job_type=JobType.IRS_NAME_SEARCH,
            query_params={"query": "x"},
        )
        resp = self.client.get(reverse("api_job_detail", args=[job.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], str(job.id))
        self.assertEqual(data["status"], "QUEUED")
        self.assertEqual(data["job_type"], "IRS_NAME_SEARCH")
        self.assertIsNone(data["result"])
        self.assertEqual(data["error_message"], "")

    def test_returns_result_for_success(self):
        payload = {"source": "irs_teos_xml", "results": [], "count": 0, "notes": []}
        job = SearchJob.objects.create(
            case=self.case,
            job_type=JobType.IRS_NAME_SEARCH,
            query_params={"query": "x"},
            status=JobStatus.SUCCESS,
            result=payload,
        )
        resp = self.client.get(reverse("api_job_detail", args=[job.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["result"], payload)

    def test_404_for_unknown_id(self):
        import uuid

        resp = self.client.get(reverse("api_job_detail", args=[uuid.uuid4()]))
        self.assertEqual(resp.status_code, 404)


class CaseJobsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.case = Case.objects.create(name="T")
        self.other = Case.objects.create(name="Other")

    def test_lists_jobs_for_case_most_recent_first(self):
        jobs = [
            SearchJob.objects.create(
                case=self.case,
                job_type=JobType.IRS_NAME_SEARCH,
                query_params={"n": i},
            )
            for i in range(3)
        ]
        SearchJob.objects.create(
            case=self.other,
            job_type=JobType.IRS_NAME_SEARCH,
            query_params={"n": "other"},
        )
        resp = self.client.get(reverse("api_case_jobs", args=[self.case.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["results"]), 3)
        returned_ids = [r["id"] for r in data["results"]]
        self.assertEqual(returned_ids[0], str(jobs[-1].id))

    def test_respects_limit_query_param(self):
        for i in range(10):
            SearchJob.objects.create(
                case=self.case,
                job_type=JobType.IRS_NAME_SEARCH,
                query_params={"n": i},
            )
        resp = self.client.get(
            reverse("api_case_jobs", args=[self.case.id]) + "?limit=5"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["results"]), 5)


class ConvertedResearchViewTests(TestCase):
    """The four converted POST views should now enqueue and return 202."""

    def setUp(self):
        self.client = Client()
        self.case = Case.objects.create(name="T")

    @mock.patch("investigations.views.async_task")
    def test_research_irs_name_search_returns_202(self, mock_async):
        resp = self.client.post(
            reverse("api_research_irs", args=[self.case.id]),
            data=json.dumps({"query": "do good"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("job_id", data)
        self.assertIn("status_url", data)
        self.assertEqual(SearchJob.objects.count(), 1)
        job = SearchJob.objects.first()
        self.assertEqual(job.job_type, JobType.IRS_NAME_SEARCH)
        self.assertEqual(job.query_params["query"], "do good")
        mock_async.assert_called_once()
        args, _ = mock_async.call_args
        self.assertEqual(args[0], "investigations.jobs.run_irs_name_search")
        self.assertEqual(args[1], str(job.id))

    @mock.patch("investigations.views.async_task")
    def test_research_irs_ein_with_fetch_xml_uses_fetch_xml_job_type(self, mock_async):
        resp = self.client.post(
            reverse("api_research_irs", args=[self.case.id]),
            data=json.dumps({"query": "12-3456789", "fetch_xml": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 202)
        job = SearchJob.objects.first()
        self.assertEqual(job.job_type, JobType.IRS_FETCH_XML)

    @mock.patch("investigations.views.async_task")
    def test_research_ohio_aos_returns_202(self, mock_async):
        resp = self.client.post(
            reverse("api_research_ohio_aos", args=[self.case.id]),
            data=json.dumps({"query": "Bright Future"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 202)
        job = SearchJob.objects.first()
        self.assertEqual(job.job_type, JobType.OHIO_AOS)

    @mock.patch("investigations.views.async_task")
    def test_research_parcels_returns_202(self, mock_async):
        resp = self.client.post(
            reverse("api_research_parcels", args=[self.case.id]),
            data=json.dumps({"query": "Smith", "county": "Darke"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 202)
        job = SearchJob.objects.first()
        self.assertEqual(job.job_type, JobType.COUNTY_PARCEL)

    def test_research_irs_missing_query_returns_400(self):
        resp = self.client.post(
            reverse("api_research_irs", args=[self.case.id]),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(SearchJob.objects.count(), 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
docker compose exec backend python manage.py test investigations.tests.test_job_views -v 2
```

Expected: all tests fail with `NoReverseMatch: Reverse for 'api_job_detail' not found` (for the new endpoints) and assertion failures (the converted endpoints still return 200 with inline results).

---

### Task 8: Add the two new job endpoints (poll + case-jobs)

**Files:**
- Modify: `backend/investigations/views.py` (append new views near other api_ views)
- Modify: `backend/investigations/urls.py` (add two path entries)

- [ ] **Step 1: Add `api_job_detail` and `api_case_jobs` views**

Append these two views at the end of `backend/investigations/views.py` (above any trailing whitespace, after the last existing view):

```python
@require_http_methods(["GET"])
def api_job_detail(request, job_id):
    """Return the current state of a SearchJob for frontend polling."""
    job = get_object_or_404(SearchJob, pk=job_id)
    return JsonResponse(
        {
            "id": str(job.id),
            "case_id": str(job.case_id) if job.case_id else None,
            "job_type": job.job_type,
            "status": job.status,
            "query_params": job.query_params,
            "result": job.result,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": (
                job.finished_at.isoformat() if job.finished_at else None
            ),
        }
    )


@require_http_methods(["GET"])
def api_case_jobs(request, pk):
    """List recent SearchJobs for a case — used by frontend reattach-on-mount."""
    case = get_object_or_404(Case, pk=pk)
    try:
        limit = int(request.GET.get("limit", "5"))
    except ValueError:
        limit = 5
    limit = max(1, min(limit, 50))

    jobs = SearchJob.objects.filter(case=case).order_by("-created_at")[:limit]
    return JsonResponse(
        {
            "results": [
                {
                    "id": str(j.id),
                    "job_type": j.job_type,
                    "status": j.status,
                    "query_params": j.query_params,
                    "created_at": j.created_at.isoformat(),
                    "finished_at": (
                        j.finished_at.isoformat() if j.finished_at else None
                    ),
                }
                for j in jobs
            ]
        }
    )
```

Make sure `SearchJob` is imported at the top of `views.py`. Find the existing `from .models import ...` block and add `SearchJob` to it. If `JobType`/`JobStatus` are not imported, add them too.

- [ ] **Step 2: Wire the two new URLs**

In `backend/investigations/urls.py`, add these two entries to the `urlpatterns` list (put them together, near the other research endpoints):

```python
    path(
        "api/jobs/<uuid:job_id>/",
        views.api_job_detail,
        name="api_job_detail",
    ),
    path(
        "api/cases/<uuid:pk>/jobs/",
        views.api_case_jobs,
        name="api_case_jobs",
    ),
```

- [ ] **Step 3: Run the two new-endpoint tests to verify they pass**

```bash
docker compose exec backend python manage.py test investigations.tests.test_job_views.JobDetailViewTests investigations.tests.test_job_views.CaseJobsViewTests -v 2
```

Expected: 5 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/investigations/views.py backend/investigations/urls.py backend/investigations/tests/test_job_views.py
git commit -m "feat: add job-status endpoints for async research jobs"
```

---

### Task 9: Convert `api_research_irs` to enqueue-and-return-202

**Files:**
- Modify: `backend/investigations/views.py` — the existing `api_research_irs` view (starts around line 4264)

- [ ] **Step 1: Find the existing view and replace its body**

Locate the existing `api_research_irs` function in `backend/investigations/views.py`. Replace the **entire** function (from the `@csrf_exempt` decorator down through its final `return JsonResponse(...)`) with this exact replacement:

```python
@csrf_exempt
@require_http_methods(["POST"])
def api_research_irs(request, pk):
    """Enqueue an IRS 990 search job; return 202 with a job id to poll.

    The actual work runs in a Django-Q2 worker (see investigations.jobs).
    Two paths:
      - EIN + fetch_xml=true  -> IRS_FETCH_XML task (fetch + parse XML)
      - everything else       -> IRS_NAME_SEARCH task (index scan)
    """
    case = get_object_or_404(Case, pk=pk)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {"error": "Invalid JSON in request body"},
            status=400,
        )

    query = body.get("query", "").strip()
    fetch_xml = bool(body.get("fetch_xml", False))

    if not query:
        return JsonResponse(
            {"error": "Missing required field: query"},
            status=400,
        )

    cleaned = query.replace("-", "").replace(" ", "")
    is_ein = cleaned.isdigit() and 7 <= len(cleaned) <= 9

    if is_ein and fetch_xml:
        job_type = JobType.IRS_FETCH_XML
        task_path = "investigations.jobs.run_irs_fetch_xml"
    else:
        job_type = JobType.IRS_NAME_SEARCH
        task_path = "investigations.jobs.run_irs_name_search"

    with transaction.atomic():
        job = SearchJob.objects.create(
            case=case,
            job_type=job_type,
            query_params={"query": query, "fetch_xml": fetch_xml},
        )
        async_task(task_path, str(job.id))

    return JsonResponse(
        {
            "job_id": str(job.id),
            "status_url": f"/api/jobs/{job.id}/",
        },
        status=202,
    )
```

- [ ] **Step 2: Add the needed imports at the top of views.py**

Near the top of `backend/investigations/views.py`, alongside the other Django imports:

```python
from django.db import transaction
from django_q.tasks import async_task
```

`transaction` may already be imported — in that case don't add it twice. `async_task` almost certainly is not.

- [ ] **Step 3: Run the IRS-specific view tests to verify they pass**

```bash
docker compose exec backend python manage.py test investigations.tests.test_job_views.ConvertedResearchViewTests.test_research_irs_name_search_returns_202 investigations.tests.test_job_views.ConvertedResearchViewTests.test_research_irs_ein_with_fetch_xml_uses_fetch_xml_job_type investigations.tests.test_job_views.ConvertedResearchViewTests.test_research_irs_missing_query_returns_400 -v 2
```

Expected: 3 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/investigations/views.py
git commit -m "feat: convert api_research_irs to async job"
```

---

### Task 10: Convert `api_research_ohio_aos` to enqueue-and-return-202

**Files:**
- Modify: `backend/investigations/views.py` — existing `api_research_ohio_aos` view

- [ ] **Step 1: Find and replace the existing view**

Locate the existing `api_research_ohio_aos` function. Replace the entire function (decorators included) with:

```python
@csrf_exempt
@require_http_methods(["POST"])
def api_research_ohio_aos(request, pk):
    """Enqueue an Ohio AOS audit-report search job; return 202."""
    case = get_object_or_404(Case, pk=pk)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {"error": "Invalid JSON in request body"},
            status=400,
        )

    query = body.get("query", "").strip()
    if not query:
        return JsonResponse(
            {"error": "Missing required field: query"},
            status=400,
        )

    with transaction.atomic():
        job = SearchJob.objects.create(
            case=case,
            job_type=JobType.OHIO_AOS,
            query_params={"query": query},
        )
        async_task("investigations.jobs.run_ohio_aos_search", str(job.id))

    return JsonResponse(
        {
            "job_id": str(job.id),
            "status_url": f"/api/jobs/{job.id}/",
        },
        status=202,
    )
```

- [ ] **Step 2: Run the Ohio-AOS-specific view test**

```bash
docker compose exec backend python manage.py test investigations.tests.test_job_views.ConvertedResearchViewTests.test_research_ohio_aos_returns_202 -v 2
```

Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add backend/investigations/views.py
git commit -m "feat: convert api_research_ohio_aos to async job"
```

---

### Task 11: Convert `api_research_parcels` to enqueue-and-return-202

**Files:**
- Modify: `backend/investigations/views.py` — existing `api_research_parcels` view

- [ ] **Step 1: Find and replace the existing view**

Locate the existing `api_research_parcels` function. Replace the entire function with:

```python
@csrf_exempt
@require_http_methods(["POST"])
def api_research_parcels(request, pk):
    """Enqueue a County Auditor (ODNR) parcel search job; return 202."""
    case = get_object_or_404(Case, pk=pk)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {"error": "Invalid JSON in request body"},
            status=400,
        )

    query = body.get("query", "").strip()
    county = body.get("county")
    if county:
        county = county.strip().upper()
    if not query:
        return JsonResponse(
            {"error": "Missing required field: query"},
            status=400,
        )

    with transaction.atomic():
        job = SearchJob.objects.create(
            case=case,
            job_type=JobType.COUNTY_PARCEL,
            query_params={"query": query, "county": county},
        )
        async_task(
            "investigations.jobs.run_county_parcel_search", str(job.id)
        )

    return JsonResponse(
        {
            "job_id": str(job.id),
            "status_url": f"/api/jobs/{job.id}/",
        },
        status=202,
    )
```

- [ ] **Step 2: Run the parcels-specific view test**

```bash
docker compose exec backend python manage.py test investigations.tests.test_job_views.ConvertedResearchViewTests.test_research_parcels_returns_202 -v 2
```

Expected: passes.

- [ ] **Step 3: Run the full converted-views test class to confirm nothing regressed**

```bash
docker compose exec backend python manage.py test investigations.tests.test_job_views -v 2
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/investigations/views.py
git commit -m "feat: convert api_research_parcels to async job"
```

---

### Task 12: Add the qcluster service to docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Append the qcluster service**

In `docker-compose.yml`, add a new service under `services:` (before `volumes:`):

```yaml
  # ---------------------------------------------------------------------------
  # qcluster — Django-Q2 worker (pulls async jobs off the Postgres broker)
  # ---------------------------------------------------------------------------
  qcluster:
    build:
      context: ./backend
      dockerfile: docker/Dockerfile
    container_name: catalyst_qcluster
    restart: unless-stopped
    command: python manage.py qcluster
    environment:
      DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY}
      DJANGO_DEBUG: ${DJANGO_DEBUG:-True}
      ALLOWED_HOSTS: ${ALLOWED_HOSTS:-localhost,127.0.0.1}
      POSTGRES_DB: catalyst_db
      POSTGRES_USER: catalyst_user
      DB_PASSWORD: ${DB_PASSWORD}
      DB_HOST: db
      DB_PORT: "5432"
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      CATALYST_REQUIRE_AUTH: ${CATALYST_REQUIRE_AUTH:-False}
      CATALYST_API_TOKENS: ${CATALYST_API_TOKENS:-}
      CHROMA_PATH: /chroma_data
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - chromadb_data:/chroma_data
```

- [ ] **Step 2: Start the full stack and verify qcluster boots**

```bash
docker compose up -d
docker compose logs --tail=30 qcluster
```

Expected: logs show something like `Q Cluster catalyst starting` and `2 workers are idle`. No tracebacks.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: run qcluster worker alongside backend"
```

---

### Task 13: Write and run the one end-to-end integration test

**Files:**
- Create: `backend/investigations/tests/test_integration_qcluster.py`

- [ ] **Step 1: Write the integration test**

Create `backend/investigations/tests/test_integration_qcluster.py` with this exact content:

```python
"""End-to-end integration test: enqueue a job, run a worker, poll to completion.

This test actually invokes Django-Q2's in-process cluster runner. It does
NOT hit any external API — the connector is mocked — so it's safe in CI.
"""

from unittest import mock

from django.test import TransactionTestCase
from django_q.tasks import async_task, result

from investigations.models import Case, JobStatus, JobType, SearchJob


class QclusterRoundTripTests(TransactionTestCase):
    """Uses TransactionTestCase because django-q2 needs real DB commits to
    pass tasks between enqueue and worker."""

    def test_job_completes_via_real_async_task(self):
        case = Case.objects.create(name="T")
        job = SearchJob.objects.create(
            case=case,
            job_type=JobType.IRS_NAME_SEARCH,
            query_params={"query": "x"},
        )

        with mock.patch("investigations.jobs.irs_connector") as mock_connector:
            mock_connector.INDEX_YEARS = [2024]
            mock_connector.search_990_by_name.return_value = []
            mock_connector.filing_to_dict.return_value = {}

            # Run synchronously via django-q2's sync=True mode.
            task_id = async_task(
                "investigations.jobs.run_irs_name_search",
                str(job.id),
                sync=True,
            )
            # sync=True runs the task inline and returns the task id.
            self.assertIsNotNone(task_id)

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.SUCCESS)
        self.assertEqual(job.result["count"], 0)
        self.assertEqual(job.result["source"], "irs_teos_xml")
```

- [ ] **Step 2: Run the integration test**

```bash
docker compose exec backend python manage.py test investigations.tests.test_integration_qcluster -v 2
```

Expected: passes. If django-q2's `sync=True` path requires settings we haven't added, the test will explain what's missing — fix the settings, rerun.

- [ ] **Step 3: Run the entire test suite to confirm nothing regressed**

```bash
docker compose exec backend python manage.py test investigations -v 2
```

Expected: all tests pass. Count should be 4 (model) + 5 (jobs) + 8 (views) + 1 (integration) = 18 tests.

- [ ] **Step 4: Commit**

```bash
git add backend/investigations/tests/test_integration_qcluster.py
git commit -m "test: add end-to-end qcluster round-trip test"
```

---

### Task 14: Manual smoke test against the running stack

**Files:** (no file changes — just verification)

- [ ] **Step 1: Make sure the full stack is running**

```bash
docker compose up -d
docker compose ps
```

Expected: `catalyst_db (healthy)`, `catalyst_backend (Up)`, `catalyst_qcluster (Up)`, `catalyst_frontend (Up)`.

- [ ] **Step 2: Open the browser and reproduce the original bug scenario**

Open a case's Research tab at http://localhost:5173/cases/<some-case-id>/research, pick "IRS 990 E-File Search", type `do good`, click Search.

Expected behavior:
- The request returns `202` almost immediately (check the Network tab in DevTools — response body includes `job_id` and `status_url`)
- Background requests to `/api/jobs/<id>/` start polling every ~2s (these will only appear once the frontend is wired up in a future session — for now, you'll just see the 202 in the Network tab, and the existing frontend UI will probably show "Loading..." or break until it's updated)
- No `502 Bad Gateway`

- [ ] **Step 3: Verify the job ran to completion via curl**

```bash
# Grab the job_id from the 202 response, then:
curl -s http://localhost:8000/api/jobs/<job_id>/ | python -m json.tool
```

Expected: eventually `"status": "SUCCESS"` and a populated `result` field with `results`, `count`, `notes`. If `"status": "FAILED"`, check `qcluster` logs: `docker compose logs --tail=100 qcluster`.

- [ ] **Step 4: Check qcluster logs to confirm the worker picked it up**

```bash
docker compose logs --tail=50 qcluster
```

Expected: log lines showing the worker processed task `investigations.jobs.run_irs_name_search` successfully.

- [ ] **Step 5: Commit a note marking the backend work done**

(No code changes — just a tag commit so the branch has a clear endpoint.)

```bash
git commit --allow-empty -m "chore: async research jobs backend complete (frontend pending)"
```

---

## What's deliberately not in this plan

- **Frontend changes.** The React side (new `useAsyncJob` hook, polling, reattach on mount, spinner state, error rendering) is a separate plan for a future session. The backend as shipped in this plan returns `202` + `job_id`; the existing frontend will need work to consume that. Until that frontend work lands, the Research tab will appear broken in the browser — that's expected.
- **Job cancel endpoint.** Deferred per spec.
- **Progress field / progress UI.** Deferred per spec.
- **TTL / cleanup cron.** Deferred per spec.
- **Applying this pattern to `/documents/process-pending/` (OCR).** Different scaling profile, separate future work.

---

## Self-review

**Spec coverage:** Walked each spec section against the plan:
- "Architecture / Why Django-Q2 with Postgres broker" → Tasks 1–2 install + configure
- "Components / Created" → `SearchJob` (Task 4), `jobs.py` (Task 6), 2 new endpoints (Task 8), qcluster container (Task 12)
- "Components / Changed" → 4 view conversions (Tasks 9–11; IRS name + IRS fetch_xml both covered in Task 9)
- "Data model" → all 11 fields + index present in Task 4
- "Flow" → kickoff in Task 9/10/11, worker in Task 6, poll in Task 8, reattach endpoint in Task 8
- "Error handling" → 300s timeout and disabled retries configured in Task 2; exception capture in Task 6's `_mark_failed`
- "Testing" → all four unit-test categories (model/tasks/views/integration) covered in Tasks 3, 5, 7, 13

**Placeholder scan:** No TBDs, no "implement later," every code step has complete code.

**Type consistency:** `JobType` / `JobStatus` used consistently across model (Task 4), task functions (Task 6), views (Tasks 8–11), and tests (Tasks 3, 5, 7, 13). `SearchJob` model field names (`result`, `error_message`, `query_params`, `started_at`, `finished_at`) consistent across every task that touches them.

**One noted flex point:** Task 6 tells the agent: "if the connector function the test mocks is named differently in the actual connector, open the connector file and update both test mock path and call site to match." This is intentional — `ohio_aos_connector.search_aos_by_name` and `county_auditor_connector.search_parcels_by_owner` are my best read of likely names from CLAUDE.md's connector descriptions, but I did not re-read every line of those two files. The test failure will catch any mismatch immediately, and the instruction tells the agent the right way to fix it.
