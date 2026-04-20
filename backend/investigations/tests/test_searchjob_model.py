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
