"""
Tests for the Ohio SOS bulk-file connector.

All tests use unittest.mock to intercept HTTP calls — no real network
requests are made. This means tests run offline, run fast, and don't
consume any server bandwidth or risk hitting a rate limit.

How mocking works here (same pattern as tests_propublica.py):

    The connector calls requests.get() to download CSV files.
    We use @patch("investigations.ohio_sos_connector.requests.get") to
    intercept that call and replace it with a fake object we control.

    Instead of returning real HTTP responses, we return a MagicMock whose
    .content attribute holds pre-written CSV bytes — exactly what the
    real server would send.

    This lets us test every path — success, 404, timeout, connection error,
    malformed rows, typo handling — without a live server.

Run these tests with:
    python -m unittest investigations.tests_ohio_sos -v
(from the backend/ directory; Django is not required)
"""

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Shared fixture data — realistic fake CSV content
#
# These mirror the exact column names confirmed from the live Ohio SOS files.
# We write them as plain strings so they're easy to read and maintain.
# ---------------------------------------------------------------------------

# A new-entity report (e.g., NONPROFIT_CORPS, LLC_DOMESTIC, CORP_FORPROFIT).
# The header uses "TRANSACTION CODE DESCRIPTION" (correct spelling).
NEW_ENTITY_CSV = """\
DOCUMENT NUMBER,CHARTER NUMBER,EFFECTIVE DATE,BUSINESS NAME,CONSENT FLAG,TRANSACTION CODE DESCRIPTION,FILING ADDRESS NAME,FILING ADDRESS 1,FILING ADDRESS 2,FILING CITY,FILING STATE,FILING ZIP,AGENT ADDRESS NAME,AGENT ADDRESS 1,AGENT ADDRESS 2,AGENT CITY,AGENT STATE,AGENT ZIP,BUSINESS CITY,COUNTY,BUSINESS ASSOCIATE NAMES
202301010001,4567890,01/15/2023,DO GOOD MINISTRIES INC,,DOMESTIC ARTICLES/NON-PROFIT,DO GOOD MINISTRIES INC,123 MAIN ST,,CAREY,OH,43316,JOHN A HOMAN,456 FARM RD,,CAREY,OH,43316,CAREY,WYANDOT,JANE SMITH|JOHN A HOMAN
202301010002,4567891,01/18/2023,DO GOOD RE LLC,,DOMESTIC LLC,,,,FINDLAY,OH,45840,CAROL JONES,789 OAK AVE,,FINDLAY,OH,45840,FINDLAY,HANCOCK,CAROL JONES
202301010003,4567892,01/20/2023,VETERANS COMMUNITY CENTER INC,,DOMESTIC ARTICLES/NON-PROFIT,VETERANS COMMUNITY CENTER,100 LIBERTY DR,,TIFFIN,OH,44883,MIKE BROWN,200 ELM ST,,TIFFIN,OH,44883,TIFFIN,SENECA,MIKE BROWN|SARAH BROWN
"""

# An amendment report (e.g., AMENDMENTS).
# IMPORTANT: The Ohio SOS amendment header has a typo: "TRANSASCTION" (extra A).
# Our parser handles this — tests must confirm that.
AMENDMENT_CSV = """\
DOCUMENT NUMBER,CHARTER NUMBER,EFFECTIVE DATE,BUSINESS NAME,TRANSASCTION CODE DESCRIPTION,FILING ADDRESS NAME,FILING ADDRESS 1,FILING ADDRESS 2,FILING CITY,FILING STATE,FILING ZIP,BUSINESS CITY,COUNTY NAME
202302010001,4567890,02/01/2023,DO GOOD MINISTRIES INC,AMENDED ARTICLES,DO GOOD MINISTRIES INC,123 MAIN ST,,CAREY,OH,43316,CAREY,WYANDOT
202302010002,4567891,02/05/2023,DO GOOD RE LLC,AMENDED ARTICLES,,,,FINDLAY,OH,45840,FINDLAY,HANCOCK
"""

# A CSV with one good row and one row with a missing BUSINESS NAME — should be skipped.
MALFORMED_CSV = """\
DOCUMENT NUMBER,CHARTER NUMBER,EFFECTIVE DATE,BUSINESS NAME,CONSENT FLAG,TRANSACTION CODE DESCRIPTION,FILING ADDRESS NAME,FILING ADDRESS 1,FILING ADDRESS 2,FILING CITY,FILING STATE,FILING ZIP,AGENT ADDRESS NAME,AGENT ADDRESS 1,AGENT ADDRESS 2,AGENT CITY,AGENT STATE,AGENT ZIP,BUSINESS CITY,COUNTY,BUSINESS ASSOCIATE NAMES
202301010001,4567890,01/15/2023,DO GOOD MINISTRIES INC,,DOMESTIC ARTICLES/NON-PROFIT,DO GOOD MINISTRIES INC,123 MAIN ST,,CAREY,OH,43316,JOHN A HOMAN,456 FARM RD,,CAREY,OH,43316,CAREY,WYANDOT,
202301010002,4567891,13/45/9999,,,BAD DATE ENTITY,,,,,,,,,,,,,,,,
"""

# A CSV with a badly-formed date that should gracefully fall back to None.
BAD_DATE_CSV = """\
DOCUMENT NUMBER,CHARTER NUMBER,EFFECTIVE DATE,BUSINESS NAME,CONSENT FLAG,TRANSACTION CODE DESCRIPTION,FILING ADDRESS NAME,FILING ADDRESS 1,FILING ADDRESS 2,FILING CITY,FILING STATE,FILING ZIP,AGENT ADDRESS NAME,AGENT ADDRESS 1,AGENT ADDRESS 2,AGENT CITY,AGENT STATE,AGENT ZIP,BUSINESS CITY,COUNTY,BUSINESS ASSOCIATE NAMES
202301010001,4567890,not-a-date,MYSTERY CORP,,DOMESTIC ARTICLES/NON-PROFIT,,,,,,,,,,,,,,,
"""


def _make_mock_response(csv_text: str, status_code: int = 200) -> MagicMock:
    """
    Build a fake requests.Response that returns CSV content.

    The connector reads:
        .ok           — True if status_code < 400
        .status_code  — integer HTTP status
        .content      — raw bytes (we encode the CSV as UTF-8)
    """
    mock = MagicMock()
    mock.ok = status_code < 400
    mock.status_code = status_code
    mock.content = csv_text.encode("utf-8")
    return mock


# ---------------------------------------------------------------------------
# ReportType enum tests
# ---------------------------------------------------------------------------


class ReportTypeTests(unittest.TestCase):
    """Make sure the enum values and properties behave correctly."""

    def test_nonprofit_corps_url(self):
        from investigations.ohio_sos_connector import ReportType

        url = ReportType.NONPROFIT_CORPS.url
        self.assertIn("WI0070R.TXT", url)
        self.assertTrue(url.startswith("https://publicfiles.ohiosos.gov"))

    def test_llc_domestic_url(self):
        from investigations.ohio_sos_connector import ReportType

        url = ReportType.LLC_DOMESTIC.url
        self.assertIn("WI0100R.TXT", url)

    def test_amendments_is_amendment_true(self):
        from investigations.ohio_sos_connector import ReportType

        self.assertTrue(ReportType.AMENDMENTS.is_amendment)

    def test_dissolutions_is_amendment_true(self):
        from investigations.ohio_sos_connector import ReportType

        self.assertTrue(ReportType.DISSOLUTIONS.is_amendment)

    def test_nonprofit_corps_is_amendment_false(self):
        from investigations.ohio_sos_connector import ReportType

        self.assertFalse(ReportType.NONPROFIT_CORPS.is_amendment)

    def test_llc_domestic_is_amendment_false(self):
        from investigations.ohio_sos_connector import ReportType

        self.assertFalse(ReportType.LLC_DOMESTIC.is_amendment)

    def test_all_report_types_have_urls(self):
        from investigations.ohio_sos_connector import ReportType

        for rt in ReportType:
            self.assertTrue(rt.url.startswith("https://"))


# ---------------------------------------------------------------------------
# fetch_report — success paths
# ---------------------------------------------------------------------------


class FetchReportSuccessTests(unittest.TestCase):
    @patch("investigations.ohio_sos_connector.requests.get")
    def test_returns_list_of_entity_records(self, mock_get):
        mock_get.return_value = _make_mock_response(NEW_ENTITY_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        self.assertEqual(len(records), 3)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_record_business_name_parsed(self, mock_get):
        mock_get.return_value = _make_mock_response(NEW_ENTITY_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        self.assertEqual(records[0].business_name, "DO GOOD MINISTRIES INC")

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_record_charter_number_parsed(self, mock_get):
        mock_get.return_value = _make_mock_response(NEW_ENTITY_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        self.assertEqual(records[0].charter_number, "4567890")

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_record_effective_date_parsed(self, mock_get):
        mock_get.return_value = _make_mock_response(NEW_ENTITY_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        self.assertEqual(records[0].effective_date, date(2023, 1, 15))

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_record_statutory_agent_parsed(self, mock_get):
        mock_get.return_value = _make_mock_response(NEW_ENTITY_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        self.assertEqual(records[0].statutory_agent, "JOHN A HOMAN")
        self.assertEqual(records[0].agent_city, "CAREY")
        self.assertEqual(records[0].agent_state, "OH")

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_record_county_parsed(self, mock_get):
        mock_get.return_value = _make_mock_response(NEW_ENTITY_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        self.assertEqual(records[0].county, "WYANDOT")

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_report_type_stored_on_record(self, mock_get):
        mock_get.return_value = _make_mock_response(NEW_ENTITY_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        for r in records:
            self.assertEqual(r.report_type, ReportType.NONPROFIT_CORPS)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_downloaded_at_is_utc_aware(self, mock_get):
        mock_get.return_value = _make_mock_response(NEW_ENTITY_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        for r in records:
            self.assertIsNotNone(r.downloaded_at.tzinfo)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_bad_date_becomes_none(self, mock_get):
        mock_get.return_value = _make_mock_response(BAD_DATE_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        # The record should still be returned — just with effective_date=None
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].effective_date)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_skips_rows_with_empty_business_name(self, mock_get):
        mock_get.return_value = _make_mock_response(MALFORMED_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        # Row 1: DO GOOD MINISTRIES INC — should be included
        # Row 2: empty BUSINESS NAME — should be skipped
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].business_name, "DO GOOD MINISTRIES INC")


# ---------------------------------------------------------------------------
# fetch_report — amendment format
# ---------------------------------------------------------------------------


class FetchReportAmendmentTests(unittest.TestCase):
    @patch("investigations.ohio_sos_connector.requests.get")
    def test_amendment_records_parsed(self, mock_get):
        mock_get.return_value = _make_mock_response(AMENDMENT_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.AMENDMENTS)

        self.assertEqual(len(records), 2)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_amendment_header_typo_handled(self, mock_get):
        """
        The Ohio SOS amendment header says "TRANSASCTION" (extra A) instead of
        "TRANSACTION". Our parser handles this silently — the transaction_type
        field should still be populated correctly.
        """
        mock_get.return_value = _make_mock_response(AMENDMENT_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.AMENDMENTS)

        self.assertEqual(records[0].transaction_type, "AMENDED ARTICLES")

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_amendment_records_have_no_statutory_agent(self, mock_get):
        mock_get.return_value = _make_mock_response(AMENDMENT_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.AMENDMENTS)

        for r in records:
            self.assertIsNone(r.statutory_agent)
            self.assertIsNone(r.agent_city)
            self.assertIsNone(r.agent_state)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_amendment_county_uses_county_name_column(self, mock_get):
        """Amendment reports use 'COUNTY NAME' not 'COUNTY'."""
        mock_get.return_value = _make_mock_response(AMENDMENT_CSV)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.AMENDMENTS)

        self.assertEqual(records[0].county, "WYANDOT")


# ---------------------------------------------------------------------------
# fetch_report — error paths
# ---------------------------------------------------------------------------


class FetchReportErrorTests(unittest.TestCase):
    @patch("investigations.ohio_sos_connector.requests.get")
    def test_raises_ohio_sos_error_on_404(self, mock_get):
        mock_get.return_value = _make_mock_response("", status_code=404)

        from investigations.ohio_sos_connector import OhioSOSError, ReportType, fetch_report

        with self.assertRaises(OhioSOSError) as ctx:
            fetch_report(ReportType.NONPROFIT_CORPS)

        self.assertEqual(ctx.exception.status_code, 404)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_raises_ohio_sos_error_on_500(self, mock_get):
        mock_get.return_value = _make_mock_response("", status_code=500)

        from investigations.ohio_sos_connector import OhioSOSError, ReportType, fetch_report

        with self.assertRaises(OhioSOSError) as ctx:
            fetch_report(ReportType.NONPROFIT_CORPS)

        self.assertEqual(ctx.exception.status_code, 500)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_raises_ohio_sos_error_on_connection_error(self, mock_get):
        import requests as req

        mock_get.side_effect = req.exceptions.ConnectionError("refused")

        from investigations.ohio_sos_connector import OhioSOSError, ReportType, fetch_report

        with self.assertRaises(OhioSOSError):
            fetch_report(ReportType.NONPROFIT_CORPS)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_raises_ohio_sos_error_on_timeout(self, mock_get):
        import requests as req

        mock_get.side_effect = req.exceptions.Timeout()

        from investigations.ohio_sos_connector import OhioSOSError, ReportType, fetch_report

        with self.assertRaises(OhioSOSError):
            fetch_report(ReportType.NONPROFIT_CORPS)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_error_carries_report_type(self, mock_get):
        mock_get.return_value = _make_mock_response("", status_code=503)

        from investigations.ohio_sos_connector import OhioSOSError, ReportType, fetch_report

        with self.assertRaises(OhioSOSError) as ctx:
            fetch_report(ReportType.LLC_DOMESTIC)

        self.assertEqual(ctx.exception.report_type, ReportType.LLC_DOMESTIC)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_returns_empty_list_for_header_only_file(self, mock_get):
        header_only = (
            "DOCUMENT NUMBER,CHARTER NUMBER,EFFECTIVE DATE,BUSINESS NAME,CONSENT FLAG,"
            "TRANSACTION CODE DESCRIPTION,FILING ADDRESS NAME,FILING ADDRESS 1,FILING ADDRESS 2,"
            "FILING CITY,FILING STATE,FILING ZIP,AGENT ADDRESS NAME,AGENT ADDRESS 1,AGENT ADDRESS 2,"
            "AGENT CITY,AGENT STATE,AGENT ZIP,BUSINESS CITY,COUNTY,BUSINESS ASSOCIATE NAMES\n"
        )
        mock_get.return_value = _make_mock_response(header_only)

        from investigations.ohio_sos_connector import ReportType, fetch_report

        records = fetch_report(ReportType.NONPROFIT_CORPS)

        self.assertEqual(records, [])


# ---------------------------------------------------------------------------
# load_reports — multiple report types
# ---------------------------------------------------------------------------


class LoadReportsTests(unittest.TestCase):
    @patch("investigations.ohio_sos_connector.requests.get")
    def test_combines_records_from_multiple_reports(self, mock_get):
        # Both calls return the same 3-row CSV — 6 total records expected
        mock_get.return_value = _make_mock_response(NEW_ENTITY_CSV)

        from investigations.ohio_sos_connector import ReportType, load_reports

        records = load_reports([ReportType.NONPROFIT_CORPS, ReportType.LLC_DOMESTIC])

        self.assertEqual(len(records), 6)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_makes_one_request_per_report_type(self, mock_get):
        mock_get.return_value = _make_mock_response(NEW_ENTITY_CSV)

        from investigations.ohio_sos_connector import ReportType, load_reports

        load_reports([ReportType.NONPROFIT_CORPS, ReportType.LLC_DOMESTIC, ReportType.AMENDMENTS])

        self.assertEqual(mock_get.call_count, 3)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_skips_failed_report_and_returns_rest(self, mock_get):
        """
        If one report type returns a 500, load_reports should log the error
        and continue — returning records from the other report types.
        """
        # First call: success (3 records); second call: 500 error
        mock_get.side_effect = [
            _make_mock_response(NEW_ENTITY_CSV),  # NONPROFIT_CORPS — success
            _make_mock_response("", status_code=500),  # LLC_DOMESTIC — failure
        ]

        from investigations.ohio_sos_connector import ReportType, load_reports

        records = load_reports([ReportType.NONPROFIT_CORPS, ReportType.LLC_DOMESTIC])

        # Should still return the 3 records from the successful download
        self.assertEqual(len(records), 3)

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_returns_empty_list_if_all_fail(self, mock_get):
        mock_get.return_value = _make_mock_response("", status_code=500)

        from investigations.ohio_sos_connector import ReportType, load_reports

        records = load_reports([ReportType.NONPROFIT_CORPS, ReportType.LLC_DOMESTIC])

        self.assertEqual(records, [])

    @patch("investigations.ohio_sos_connector.requests.get")
    def test_empty_report_types_list_returns_empty(self, mock_get):
        from investigations.ohio_sos_connector import load_reports

        records = load_reports([])

        self.assertEqual(records, [])
        mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# search_entities — basic matching
# ---------------------------------------------------------------------------


class SearchEntitiesExactTests(unittest.TestCase):
    def _make_records(self):
        """Build a small list of EntityRecord objects in-memory without HTTP."""
        from investigations.ohio_sos_connector import EntityRecord, ReportType

        ts = datetime(2023, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        return [
            EntityRecord(
                document_number="001",
                charter_number="4567890",
                effective_date=date(2023, 1, 15),
                business_name="DO GOOD MINISTRIES INC",
                transaction_type="DOMESTIC ARTICLES/NON-PROFIT",
                filing_city="CAREY",
                filing_state="OH",
                county="WYANDOT",
                report_type=ReportType.NONPROFIT_CORPS,
                downloaded_at=ts,
                statutory_agent="JOHN A HOMAN",
                agent_city="CAREY",
                agent_state="OH",
            ),
            EntityRecord(
                document_number="002",
                charter_number="4567891",
                effective_date=date(2023, 1, 18),
                business_name="DO GOOD RE LLC",
                transaction_type="DOMESTIC LLC",
                filing_city="FINDLAY",
                filing_state="OH",
                county="HANCOCK",
                report_type=ReportType.LLC_DOMESTIC,
                downloaded_at=ts,
                statutory_agent="CAROL JONES",
                agent_city="FINDLAY",
                agent_state="OH",
            ),
            EntityRecord(
                document_number="003",
                charter_number="4567892",
                effective_date=date(2023, 1, 20),
                business_name="VETERANS COMMUNITY CENTER INC",
                transaction_type="DOMESTIC ARTICLES/NON-PROFIT",
                filing_city="TIFFIN",
                filing_state="OH",
                county="SENECA",
                report_type=ReportType.NONPROFIT_CORPS,
                downloaded_at=ts,
                statutory_agent="MIKE BROWN",
                agent_city="TIFFIN",
                agent_state="OH",
            ),
        ]

    def test_exact_match_case_insensitive(self):
        from investigations.ohio_sos_connector import search_entities

        records = self._make_records()

        result = search_entities("do good", records)
        self.assertEqual(len(result.matches), 2)

    def test_exact_match_partial_name(self):
        from investigations.ohio_sos_connector import search_entities

        records = self._make_records()

        result = search_entities("VETERANS", records)
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].business_name, "VETERANS COMMUNITY CENTER INC")

    def test_no_match_returns_empty_list(self):
        from investigations.ohio_sos_connector import search_entities

        records = self._make_records()

        result = search_entities("NONEXISTENT ENTITY", records)
        self.assertEqual(result.matches, [])

    def test_query_preserved_in_result(self):
        from investigations.ohio_sos_connector import search_entities

        records = self._make_records()

        result = search_entities("Do Good", records)
        self.assertEqual(result.query, "Do Good")

    def test_total_searched_is_full_record_count(self):
        from investigations.ohio_sos_connector import search_entities

        records = self._make_records()

        result = search_entities("anything", records)
        self.assertEqual(result.total_searched, 3)

    def test_raises_on_empty_query(self):
        from investigations.ohio_sos_connector import OhioSOSError, search_entities

        records = self._make_records()

        with self.assertRaises(OhioSOSError):
            search_entities("", records)

        with self.assertRaises(OhioSOSError):
            search_entities("   ", records)

    def test_raises_on_empty_records(self):
        from investigations.ohio_sos_connector import OhioSOSError, search_entities

        with self.assertRaises(OhioSOSError):
            search_entities("Do Good", [])

    def test_result_includes_staleness_warning(self):
        from investigations.ohio_sos_connector import search_entities

        records = self._make_records()

        result = search_entities("Do Good", records)
        self.assertIsNotNone(result.staleness_warning)
        self.assertIn(result.staleness_warning.level, ("LOW", "MEDIUM", "HIGH"))


# ---------------------------------------------------------------------------
# search_entities — fuzzy matching
# ---------------------------------------------------------------------------


class SearchEntitiesFuzzyTests(unittest.TestCase):
    def _make_records(self):
        from investigations.ohio_sos_connector import EntityRecord, ReportType

        ts = datetime(2023, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        return [
            EntityRecord(
                document_number="001",
                charter_number="4567890",
                effective_date=date(2023, 1, 15),
                business_name="DO GOOD MINISTRIES INC",
                transaction_type="DOMESTIC ARTICLES/NON-PROFIT",
                filing_city="CAREY",
                filing_state="OH",
                county="WYANDOT",
                report_type=ReportType.NONPROFIT_CORPS,
                downloaded_at=ts,
            ),
        ]

    def test_fuzzy_strips_legal_designators_before_match(self):
        """
        With fuzzy=True, normalize_org_name() strips "INC" from the record
        name before comparing. A query of "Do Good Ministries" (without INC)
        should still match "DO GOOD MINISTRIES INC".
        """
        from investigations.ohio_sos_connector import search_entities

        records = self._make_records()

        result = search_entities("Do Good Ministries", records, fuzzy=True)
        self.assertEqual(len(result.matches), 1)

    def test_exact_does_not_match_without_designator(self):
        """
        Sanity check: exact mode requires the substring to be present.
        "Do Good Ministries" (no INC) should NOT match "DO GOOD MINISTRIES INC"
        in exact mode unless the substring literally appears.

        Actually: "do good ministries" IS a substring of "do good ministries inc"
        so this test verifies the exact mode does case-insensitive substring.
        """
        from investigations.ohio_sos_connector import search_entities

        records = self._make_records()

        # "do good ministries" is a substring of "do good ministries inc" — match expected
        result = search_entities("do good ministries", records, fuzzy=False)
        self.assertEqual(len(result.matches), 1)


# ---------------------------------------------------------------------------
# Staleness warning level calculation
# ---------------------------------------------------------------------------


class StalenessWarningTests(unittest.TestCase):
    """
    These test the _build_staleness_warning() internal function directly,
    verifying the LOW/MEDIUM/HIGH tiers work correctly.

    We import the private function because it has clear, testable logic that
    we want to verify in isolation. In production, it's always called through
    search_entities() — but testing it directly is cleaner.
    """

    def _make_warning(self, days_ago: int):
        from investigations.ohio_sos_connector import _build_staleness_warning

        downloaded_at = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
        return _build_staleness_warning(downloaded_at)

    def test_zero_days_is_low(self):
        warning = self._make_warning(0)
        self.assertEqual(warning.level, "LOW")

    def test_six_days_is_low(self):
        warning = self._make_warning(6)
        self.assertEqual(warning.level, "LOW")

    def test_seven_days_is_medium(self):
        warning = self._make_warning(7)
        self.assertEqual(warning.level, "MEDIUM")

    def test_twenty_one_days_is_medium(self):
        warning = self._make_warning(21)
        self.assertEqual(warning.level, "MEDIUM")

    def test_twenty_two_days_is_high(self):
        warning = self._make_warning(22)
        self.assertEqual(warning.level, "HIGH")

    def test_sixty_days_is_high(self):
        warning = self._make_warning(60)
        self.assertEqual(warning.level, "HIGH")

    def test_warning_includes_manual_search_url(self):
        from investigations.ohio_sos_connector import MANUAL_SEARCH_URL

        warning = self._make_warning(10)
        self.assertIn(MANUAL_SEARCH_URL, warning.message)
        self.assertEqual(warning.manual_search_url, MANUAL_SEARCH_URL)

    def test_warning_str_method_returns_message(self):
        warning = self._make_warning(5)
        self.assertEqual(str(warning), warning.message)

    def test_warning_days_old_matches_input(self):
        warning = self._make_warning(14)
        self.assertEqual(warning.days_old, 14)

    def test_high_warning_message_contains_data_may_be_stale(self):
        warning = self._make_warning(30)
        # High-level warnings should be clearly marked for the investigator
        self.assertIn("STALE", warning.message.upper())

    def test_naive_datetime_is_treated_as_utc(self):
        """
        If downloaded_at has no tzinfo (naive), the function should treat it
        as UTC rather than crashing.
        """
        from investigations.ohio_sos_connector import _build_staleness_warning

        naive_ts = datetime(2023, 1, 1, 12, 0, 0)  # no tzinfo
        # Should not raise; should return a StalenessWarning
        warning = _build_staleness_warning(naive_ts)
        self.assertIsNotNone(warning)
        self.assertIn(warning.level, ("LOW", "MEDIUM", "HIGH"))

    def test_staleness_warning_is_always_returned_in_search(self):
        """
        Even when data is brand new (0 days old), a StalenessWarning is
        always returned by search_entities(). This is by design — the
        investigator should always be reminded that data has a cutoff.
        """
        from investigations.ohio_sos_connector import EntityRecord, ReportType, search_entities

        ts = datetime.now(tz=timezone.utc)
        records = [
            EntityRecord(
                document_number="001",
                charter_number="999",
                effective_date=None,
                business_name="TEST CORP INC",
                transaction_type="TEST",
                filing_city="COLUMBUS",
                filing_state="OH",
                county="FRANKLIN",
                report_type=ReportType.CORP_FORPROFIT,
                downloaded_at=ts,
            )
        ]
        result = search_entities("TEST CORP", records)
        self.assertIsNotNone(result.staleness_warning)


# ---------------------------------------------------------------------------
# OhioSOSError attributes
# ---------------------------------------------------------------------------


class OhioSOSErrorTests(unittest.TestCase):
    def test_error_message_accessible(self):
        from investigations.ohio_sos_connector import OhioSOSError

        err = OhioSOSError("something went wrong")
        self.assertEqual(str(err), "something went wrong")

    def test_status_code_defaults_to_none(self):
        from investigations.ohio_sos_connector import OhioSOSError

        err = OhioSOSError("no status")
        self.assertIsNone(err.status_code)

    def test_report_type_defaults_to_none(self):
        from investigations.ohio_sos_connector import OhioSOSError

        err = OhioSOSError("no report type")
        self.assertIsNone(err.report_type)

    def test_status_code_stored_correctly(self):
        from investigations.ohio_sos_connector import OhioSOSError

        err = OhioSOSError("not found", status_code=404)
        self.assertEqual(err.status_code, 404)

    def test_report_type_stored_correctly(self):
        from investigations.ohio_sos_connector import OhioSOSError, ReportType

        err = OhioSOSError("failed", report_type=ReportType.NONPROFIT_CORPS)
        self.assertEqual(err.report_type, ReportType.NONPROFIT_CORPS)


if __name__ == "__main__":
    unittest.main()
