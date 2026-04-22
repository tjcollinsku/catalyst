"""Unit tests for the task functions in investigations.jobs.

These tests call the task functions directly (not through the queue),
and mock out the underlying connector so no network calls are made.
"""

import datetime
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
    def test_success_serializes_audit_report_dataclass(self, mock_aos):
        report = mock.Mock()
        report.entity_name = "Bright Future"
        report.county = "Franklin"
        report.report_type = "Financial"
        report.entity_type = "Nonprofit"
        report.report_period = "2023"
        report.release_date = datetime.date(2024, 1, 15)
        report.has_findings_for_recovery = True
        report.pdf_url = "https://x"
        mock_aos.search_audit_reports.return_value = [report]

        run_ohio_aos_search(str(self.job.id))

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.SUCCESS)
        self.assertEqual(self.job.result["count"], 1)
        row = self.job.result["results"][0]
        self.assertEqual(row["entity_name"], "Bright Future")
        self.assertEqual(row["release_date"], "2024-01-15")
        self.assertTrue(row["has_findings_for_recovery"])

    @mock.patch("investigations.jobs.ohio_aos_connector")
    def test_null_release_date_serializes_to_none(self, mock_aos):
        report = mock.Mock()
        report.entity_name = "X"
        report.county = "Y"
        report.report_type = ""
        report.entity_type = ""
        report.report_period = ""
        report.release_date = None
        report.has_findings_for_recovery = False
        report.pdf_url = None
        mock_aos.search_audit_reports.return_value = [report]

        run_ohio_aos_search(str(self.job.id))

        self.job.refresh_from_db()
        self.assertIsNone(self.job.result["results"][0]["release_date"])


class RunCountyParcelSearchTests(TestCase):
    def setUp(self):
        self.case = Case.objects.create(name="T")

    def _make_job(self, **params):
        return SearchJob.objects.create(
            case=self.case,
            job_type=JobType.COUNTY_PARCEL,
            query_params={"query": "Smith", **params},
        )

    @mock.patch("investigations.jobs.county_auditor_connector")
    def test_owner_search_success_serializes_records(self, mock_auditor):
        # Ensure OhioCounty enum lookup returns the expected enum value
        mock_enum = mock.MagicMock()
        mock_enum.__getitem__.return_value = "DARKE_ENUM"
        mock_auditor.OhioCounty = mock_enum

        record = mock.Mock()
        record.pin = "A-1"
        record.owner1 = "SMITH"
        record.owner2 = ""
        record.county = "Darke"
        record.calc_acres = "1.5"
        record.assr_acres = "1.5"
        record.aud_link = "https://x"
        result_obj = mock.Mock()
        result_obj.records = [record]
        result_obj.note = ""
        mock_auditor.search_parcels_by_owner.return_value = result_obj

        job = self._make_job(county="DARKE", search_type="owner")
        run_county_parcel_search(str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.SUCCESS)
        self.assertEqual(job.result["count"], 1)
        row = job.result["results"][0]
        self.assertEqual(row["acres_calc"], "1.5")
        self.assertEqual(row["acres_desc"], "1.5")

    @mock.patch("investigations.jobs.county_auditor_connector")
    def test_pin_search_calls_search_parcels_by_pin(self, mock_auditor):
        mock_enum = mock.MagicMock()
        mock_enum.__getitem__.return_value = "X"
        mock_auditor.OhioCounty = mock_enum
        result_obj = mock.Mock(records=[], note="")
        mock_auditor.search_parcels_by_pin.return_value = result_obj

        job = self._make_job(county="DARKE", search_type="parcel")
        run_county_parcel_search(str(job.id))

        mock_auditor.search_parcels_by_pin.assert_called_once()
        mock_auditor.search_parcels_by_owner.assert_not_called()

    @mock.patch("investigations.jobs.county_auditor_connector")
    def test_no_county_passes_none(self, mock_auditor):
        result_obj = mock.Mock(records=[], note="")
        mock_auditor.search_parcels_by_owner.return_value = result_obj

        job = self._make_job()
        run_county_parcel_search(str(job.id))

        mock_auditor.search_parcels_by_owner.assert_called_once()
        _, kwargs = mock_auditor.search_parcels_by_owner.call_args
        self.assertIsNone(kwargs.get("county"))

    @mock.patch("investigations.jobs.county_auditor_connector")
    def test_invalid_county_marks_failed(self, mock_auditor):
        mock_enum = mock.MagicMock()
        mock_enum.__getitem__.side_effect = KeyError("NOT_A_COUNTY")
        mock_auditor.OhioCounty = mock_enum

        job = self._make_job(county="NOT_A_COUNTY")
        run_county_parcel_search(str(job.id))

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIn("county", job.error_message.lower())
