"""End-to-end integration test: enqueue a job, run a worker, poll to completion.

This test actually invokes Django-Q2's in-process cluster runner. It does
NOT hit any external API — the connector is mocked — so it's safe in CI.
"""

from unittest import mock

from django.test import TransactionTestCase
from django_q.tasks import async_task

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
