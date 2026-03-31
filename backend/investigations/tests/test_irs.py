"""
Tests for irs_connector.py.

All tests are pure unittest — no Django, no network, no real IRS data.
HTTP calls are intercepted with unittest.mock.patch so the test suite
can run without credentials, internet access, or IRS rate limits.

Test coverage:
    EoBmfRegionTests        — all region enum values have well-formed URLs
    StalenessWarningTests   — LOW/MEDIUM/HIGH tiers, naive datetime, str(), HIGH message
    ParsePub78Tests         — pipe-delimited parsing, bad EINs, short lines, empty names
    ParseEoBmfTests         — CSV parsing, ruling date splitting, revoked flag, safe_int
    FetchPub78Tests         — zip extraction, non-zip response, 404, connection error, timeout
    FetchEoBmfTests         — CSV response, 404, connection error, timeout, custom URL
    SearchPub78Tests        — name match, state filter, case-insensitive, no match, empty query/records
    SearchEoBmfTests        — name match, state filter, include_revoked=False, empty query/records
    LookupEinTests          — found, not found, string EIN normalization, synthetic staleness
    SearchOhioNonprofitsTests — integration of fetch+search, IRSError propagation
    IRSErrorTests           — status_code and ein attributes
"""

import io
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from investigations.irs_connector import (
    EoBmfRecord,
    EoBmfRegion,
    IRSError,
    Pub78Record,
    StalenessLevel,
    StalenessWarning,
    _parse_eo_bmf,
    _parse_pub78,
    _safe_int,
    fetch_eo_bmf,
    fetch_pub78,
    lookup_ein,
    search_eo_bmf,
    search_ohio_nonprofits,
    search_pub78,
)

# ---------------------------------------------------------------------------
# Helpers — build fake HTTP responses
# ---------------------------------------------------------------------------


def _make_response(content: bytes, status_code: int = 200) -> MagicMock:
    """Build a minimal mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.content = content
    return resp


def _make_pub78_zip(lines: list[str]) -> bytes:
    """Build a zip file containing a pipe-delimited pub78 text file."""
    text_bytes = "\n".join(lines).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data-download-pub78.txt", text_bytes)
    return buf.getvalue()


def _make_eo_bmf_csv(rows: list[dict], extra_fields: list[str] | None = None) -> bytes:
    """Build a minimal EO BMF CSV with the standard header columns."""
    header_fields = [
        "EIN",
        "NAME",
        "ICO",
        "STREET",
        "CITY",
        "STATE",
        "ZIP",
        "GROUP",
        "SUBSECTION",
        "AFFILIATION",
        "CLASSIFICATION",
        "RULING",
        "DEDUCTIBILITY",
        "FOUNDATION",
        "ACTIVITY",
        "ORGANIZATION",
        "STATUS",
        "TAX_PERIOD",
        "ASSET_CD",
        "INCOME_CD",
        "FILING_REQ_CD",
        "PF_FILING_REQ_CD",
        "ACCT_PD",
        "ASSET_AMT",
        "INCOME_AMT",
        "REVENUE_AMT",
        "NTEE_CD",
        "SORT_NAME",
    ]
    if extra_fields:
        header_fields += extra_fields

    lines = [",".join(header_fields)]
    for row in rows:
        line = ",".join(str(row.get(f, "")) for f in header_fields)
        lines.append(line)
    return "\n".join(lines).encode("utf-8")


def _sample_bmf_row(**overrides) -> dict:
    """Return a minimal valid EO BMF row dict."""
    base = {
        "EIN": "341234567",
        "NAME": "DO GOOD MINISTRIES INC",
        "CITY": "TIFFIN",
        "STATE": "OH",
        "ZIP": "44883",
        "SUBSECTION": "3",
        "RULING": "200301",
        "DEDUCTIBILITY": "1",
        "FOUNDATION": "15",
        "STATUS": "1",
        "TAX_PERIOD": "202212",
        "ASSET_AMT": "500000",
        "INCOME_AMT": "750000",
        "REVENUE_AMT": "750000",
        "NTEE_CD": "X20",
        "SORT_NAME": "",
        "FILING_REQ_CD": "1",
    }
    base.update(overrides)
    return base


def _sample_pub78_line(
    ein="341234567",
    name="DO GOOD MINISTRIES INC",
    city="TIFFIN",
    state="OH",
    country="US",
    code="1",
) -> str:
    return f"{ein}|{name}|{city}|{state}|{country}|{code}"


# ---------------------------------------------------------------------------
# EoBmfRegionTests
# ---------------------------------------------------------------------------


class EoBmfRegionTests(unittest.TestCase):
    """Every EoBmfRegion value should produce a well-formed URL."""

    def test_all_regions_have_url(self):
        for region in EoBmfRegion:
            url = region.url
            self.assertTrue(
                url.startswith("https://www.irs.gov/pub/irs-soi/"),
                f"{region.name} URL should start with IRS SOI base: {url}",
            )
            self.assertTrue(
                url.endswith(".csv"),
                f"{region.name} URL should end with .csv: {url}",
            )

    def test_state_oh_url(self):
        self.assertEqual(
            EoBmfRegion.STATE_OH.url,
            "https://www.irs.gov/pub/irs-soi/eo_oh.csv",
        )

    def test_midwest_url(self):
        self.assertEqual(
            EoBmfRegion.MIDWEST.url,
            "https://www.irs.gov/pub/irs-soi/eo3.csv",
        )

    def test_all_four_regions_are_numbered(self):
        numbered = {
            EoBmfRegion.NORTHEAST,
            EoBmfRegion.SOUTHEAST,
            EoBmfRegion.MIDWEST,
            EoBmfRegion.SOUTH_WEST,
        }
        for region in numbered:
            self.assertRegex(region.value, r"^eo\d\.csv$")


# ---------------------------------------------------------------------------
# StalenessWarningTests
# ---------------------------------------------------------------------------


class StalenessWarningTests(unittest.TestCase):
    def _warning(self, days_ago: int) -> StalenessWarning:
        dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
        return StalenessWarning.from_download_time(dt)

    def test_low_staleness_under_7_days(self):
        w = self._warning(3)
        self.assertEqual(w.level, StalenessLevel.LOW)

    def test_low_staleness_exactly_0_days(self):
        w = self._warning(0)
        self.assertEqual(w.level, StalenessLevel.LOW)

    def test_medium_staleness_at_7_days(self):
        w = self._warning(7)
        self.assertEqual(w.level, StalenessLevel.MEDIUM)

    def test_medium_staleness_at_21_days(self):
        w = self._warning(21)
        self.assertEqual(w.level, StalenessLevel.MEDIUM)

    def test_high_staleness_over_21_days(self):
        w = self._warning(22)
        self.assertEqual(w.level, StalenessLevel.HIGH)

    def test_high_staleness_message_contains_warning(self):
        w = self._warning(30)
        self.assertIn("WARNING", str(w))
        self.assertIn("STALE", str(w))

    def test_str_returns_message(self):
        w = self._warning(5)
        self.assertEqual(str(w), w.message)

    def test_days_old_is_correct(self):
        w = self._warning(10)
        self.assertEqual(w.days_old, 10)

    def test_naive_datetime_treated_as_utc(self):
        # A naive datetime (no tzinfo) should not raise — treated as UTC.
        naive_dt = datetime.utcnow() - timedelta(days=5)
        w = StalenessWarning.from_download_time(naive_dt)
        self.assertEqual(w.level, StalenessLevel.LOW)

    def test_message_contains_irs_label(self):
        w = self._warning(2)
        self.assertIn("IRS Bulk Data", w.message)


# ---------------------------------------------------------------------------
# ParsePub78Tests
# ---------------------------------------------------------------------------


class ParsePub78Tests(unittest.TestCase):
    """Tests for the internal _parse_pub78() function."""

    def test_parses_valid_line(self):
        line = _sample_pub78_line()
        records = _parse_pub78(line)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r.ein, 341234567)
        self.assertEqual(r.name, "DO GOOD MINISTRIES INC")
        self.assertEqual(r.city, "TIFFIN")
        self.assertEqual(r.state, "OH")
        self.assertEqual(r.country, "US")
        self.assertEqual(r.deductibility_code, "1")
        self.assertEqual(r.deductibility_description, "Contributions are deductible")

    def test_skips_line_with_too_few_fields(self):
        lines = "341234567|INCOMPLETE|CITY"
        records = _parse_pub78(lines)
        self.assertEqual(records, [])

    def test_skips_line_with_bad_ein(self):
        lines = "NOTANEIN|DO GOOD MINISTRIES INC|TIFFIN|OH|US|1"
        records = _parse_pub78(lines)
        self.assertEqual(records, [])

    def test_skips_line_with_empty_name(self):
        lines = "341234567||TIFFIN|OH|US|1"
        records = _parse_pub78(lines)
        self.assertEqual(records, [])

    def test_skips_blank_lines(self):
        text = "\n\n" + _sample_pub78_line() + "\n\n"
        records = _parse_pub78(text)
        self.assertEqual(len(records), 1)

    def test_parses_multiple_records(self):
        lines = "\n".join(
            [
                _sample_pub78_line(ein="341234567", name="ORG A"),
                _sample_pub78_line(ein="341234568", name="ORG B"),
                _sample_pub78_line(ein="341234569", name="ORG C"),
            ]
        )
        records = _parse_pub78(lines)
        self.assertEqual(len(records), 3)

    def test_unknown_deductibility_code(self):
        line = _sample_pub78_line(code="9")
        records = _parse_pub78(line)
        self.assertEqual(records[0].deductibility_description, "Code 9")

    def test_deductibility_code_2_not_deductible(self):
        line = _sample_pub78_line(code="2")
        records = _parse_pub78(line)
        self.assertEqual(records[0].deductibility_description, "Contributions are not deductible")


# ---------------------------------------------------------------------------
# ParseEoBmfTests
# ---------------------------------------------------------------------------


class ParseEoBmfTests(unittest.TestCase):
    """Tests for the internal _parse_eo_bmf() function."""

    def _parse(self, rows: list[dict]) -> list[EoBmfRecord]:
        csv_bytes = _make_eo_bmf_csv(rows)
        return _parse_eo_bmf(csv_bytes.decode("utf-8"))

    def test_parses_valid_row(self):
        records = self._parse([_sample_bmf_row()])
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r.ein, 341234567)
        self.assertEqual(r.name, "DO GOOD MINISTRIES INC")
        self.assertEqual(r.city, "TIFFIN")
        self.assertEqual(r.state, "OH")
        self.assertEqual(r.subsection, "3")
        self.assertEqual(r.subsection_description, "501(c)(3)")
        self.assertEqual(r.ruling_date, "200301")
        self.assertEqual(r.ruling_year, 2003)
        self.assertEqual(r.ruling_month, 1)
        self.assertEqual(r.status_code, "1")
        self.assertEqual(r.status_description, "Unconditional Exemption")
        self.assertFalse(r.is_revoked)
        self.assertEqual(r.ntee_code, "X20")
        self.assertEqual(r.asset_amount, 500000)
        self.assertEqual(r.income_amount, 750000)
        self.assertEqual(r.revenue_amount, 750000)

    def test_revoked_org_flag(self):
        records = self._parse([_sample_bmf_row(STATUS="12")])
        self.assertTrue(records[0].is_revoked)
        self.assertEqual(records[0].status_description, "Revoked")

    def test_ruling_date_split_correctly(self):
        records = self._parse([_sample_bmf_row(RULING="199806")])
        r = records[0]
        self.assertEqual(r.ruling_year, 1998)
        self.assertEqual(r.ruling_month, 6)

    def test_empty_ruling_date_gives_none(self):
        records = self._parse([_sample_bmf_row(RULING="")])
        self.assertIsNone(records[0].ruling_date)
        self.assertIsNone(records[0].ruling_year)
        self.assertIsNone(records[0].ruling_month)

    def test_skips_row_with_bad_ein(self):
        records = self._parse([_sample_bmf_row(EIN="BADEIN")])
        self.assertEqual(records, [])

    def test_skips_row_with_empty_ein(self):
        records = self._parse([_sample_bmf_row(EIN="")])
        self.assertEqual(records, [])

    def test_skips_row_with_empty_name(self):
        records = self._parse([_sample_bmf_row(NAME="")])
        self.assertEqual(records, [])

    def test_empty_ntee_gives_none(self):
        records = self._parse([_sample_bmf_row(NTEE_CD="")])
        self.assertIsNone(records[0].ntee_code)

    def test_multiple_rows(self):
        rows = [
            _sample_bmf_row(EIN="111111111", NAME="ORG A"),
            _sample_bmf_row(EIN="222222222", NAME="ORG B"),
        ]
        records = self._parse(rows)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].name, "ORG A")
        self.assertEqual(records[1].name, "ORG B")

    def test_deductibility_description_code_1(self):
        records = self._parse([_sample_bmf_row(DEDUCTIBILITY="1")])
        self.assertEqual(records[0].deductibility_description, "Contributions are deductible")

    def test_deductibility_description_code_2(self):
        records = self._parse([_sample_bmf_row(DEDUCTIBILITY="2")])
        self.assertEqual(records[0].deductibility_description, "Contributions are not deductible")

    def test_safe_int_empty_asset_amount(self):
        records = self._parse([_sample_bmf_row(ASSET_AMT="")])
        self.assertIsNone(records[0].asset_amount)

    def test_subsection_description_maps_correctly(self):
        for code, expected in [("3", "501(c)(3)"), ("4", "501(c)(4)"), ("6", "501(c)(6)")]:
            records = self._parse([_sample_bmf_row(SUBSECTION=code)])
            self.assertEqual(records[0].subsection_description, expected)


# ---------------------------------------------------------------------------
# FetchPub78Tests
# ---------------------------------------------------------------------------


class FetchPub78Tests(unittest.TestCase):
    """Tests for fetch_pub78() — mocks HTTP, tests zip extraction."""

    def _make_zip_response(self, lines: list[str]) -> MagicMock:
        return _make_response(_make_pub78_zip(lines))

    @patch("investigations.irs_connector.requests.get")
    def test_successful_fetch_returns_records(self, mock_get):
        mock_get.return_value = self._make_zip_response(
            [
                _sample_pub78_line(ein="341234567", name="DO GOOD MINISTRIES INC"),
                _sample_pub78_line(ein="341234568", name="ANOTHER ORG"),
            ]
        )
        records, warning = fetch_pub78()
        self.assertEqual(len(records), 2)
        self.assertIsInstance(warning, StalenessWarning)

    @patch("investigations.irs_connector.requests.get")
    def test_staleness_warning_level_is_low_for_fresh_download(self, mock_get):
        mock_get.return_value = self._make_zip_response([_sample_pub78_line()])
        _records, warning = fetch_pub78()
        self.assertEqual(warning.level, StalenessLevel.LOW)

    @patch("investigations.irs_connector.requests.get")
    def test_404_raises_irs_error(self, mock_get):
        mock_get.return_value = _make_response(b"", status_code=404)
        with self.assertRaises(IRSError) as ctx:
            fetch_pub78()
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("investigations.irs_connector.requests.get")
    def test_500_raises_irs_error(self, mock_get):
        mock_get.return_value = _make_response(b"server error", status_code=500)
        with self.assertRaises(IRSError) as ctx:
            fetch_pub78()
        self.assertEqual(ctx.exception.status_code, 500)

    @patch("investigations.irs_connector.requests.get")
    def test_not_a_zip_raises_irs_error(self, mock_get):
        mock_get.return_value = _make_response(b"this is not a zip file")
        with self.assertRaises(IRSError):
            fetch_pub78()

    @patch("investigations.irs_connector.requests.get")
    def test_connection_error_raises_irs_error(self, mock_get):
        import requests as req

        mock_get.side_effect = req.exceptions.ConnectionError("refused")
        with self.assertRaises(IRSError) as ctx:
            fetch_pub78()
        self.assertIn("connect", str(ctx.exception).lower())

    @patch("investigations.irs_connector.requests.get")
    def test_timeout_raises_irs_error(self, mock_get):
        import requests as req

        mock_get.side_effect = req.exceptions.Timeout()
        with self.assertRaises(IRSError) as ctx:
            fetch_pub78()
        self.assertIn("timed out", str(ctx.exception).lower())

    @patch("investigations.irs_connector.requests.get")
    def test_empty_zip_raises_irs_error(self, mock_get):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass  # empty zip — no .txt file inside
        mock_get.return_value = _make_response(buf.getvalue())
        with self.assertRaises(IRSError) as ctx:
            fetch_pub78()
        self.assertIn("no .txt", str(ctx.exception).lower())

    @patch("investigations.irs_connector.requests.get")
    def test_custom_url_is_used(self, mock_get):
        mock_get.return_value = self._make_zip_response([_sample_pub78_line()])
        fetch_pub78(url="https://example.com/custom-pub78.zip")
        call_args = mock_get.call_args
        self.assertIn("example.com", call_args[0][0])


# ---------------------------------------------------------------------------
# FetchEoBmfTests
# ---------------------------------------------------------------------------


class FetchEoBmfTests(unittest.TestCase):
    """Tests for fetch_eo_bmf() — mocks HTTP, tests CSV parsing."""

    def _make_csv_response(self, rows: list[dict]) -> MagicMock:
        return _make_response(_make_eo_bmf_csv(rows))

    @patch("investigations.irs_connector.requests.get")
    def test_successful_fetch_returns_records(self, mock_get):
        mock_get.return_value = self._make_csv_response([_sample_bmf_row()])
        records, warning = fetch_eo_bmf(EoBmfRegion.STATE_OH)
        self.assertEqual(len(records), 1)
        self.assertIsInstance(warning, StalenessWarning)

    @patch("investigations.irs_connector.requests.get")
    def test_default_region_is_state_oh(self, mock_get):
        mock_get.return_value = self._make_csv_response([_sample_bmf_row()])
        fetch_eo_bmf()
        call_url = mock_get.call_args[0][0]
        self.assertIn("eo_oh.csv", call_url)

    @patch("investigations.irs_connector.requests.get")
    def test_midwest_region_uses_eo3_url(self, mock_get):
        mock_get.return_value = self._make_csv_response([_sample_bmf_row()])
        fetch_eo_bmf(EoBmfRegion.MIDWEST)
        call_url = mock_get.call_args[0][0]
        self.assertIn("eo3.csv", call_url)

    @patch("investigations.irs_connector.requests.get")
    def test_custom_url_is_used(self, mock_get):
        mock_get.return_value = self._make_csv_response([_sample_bmf_row()])
        fetch_eo_bmf(url="https://example.com/custom-bmf.csv")
        call_url = mock_get.call_args[0][0]
        self.assertIn("example.com", call_url)

    @patch("investigations.irs_connector.requests.get")
    def test_404_raises_irs_error(self, mock_get):
        mock_get.return_value = _make_response(b"", status_code=404)
        with self.assertRaises(IRSError) as ctx:
            fetch_eo_bmf()
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("investigations.irs_connector.requests.get")
    def test_connection_error_raises_irs_error(self, mock_get):
        import requests as req

        mock_get.side_effect = req.exceptions.ConnectionError("refused")
        with self.assertRaises(IRSError):
            fetch_eo_bmf()

    @patch("investigations.irs_connector.requests.get")
    def test_timeout_raises_irs_error(self, mock_get):
        import requests as req

        mock_get.side_effect = req.exceptions.Timeout()
        with self.assertRaises(IRSError):
            fetch_eo_bmf()

    @patch("investigations.irs_connector.requests.get")
    def test_staleness_level_is_low_for_fresh_download(self, mock_get):
        mock_get.return_value = self._make_csv_response([_sample_bmf_row()])
        _records, warning = fetch_eo_bmf()
        self.assertEqual(warning.level, StalenessLevel.LOW)


# ---------------------------------------------------------------------------
# SearchPub78Tests
# ---------------------------------------------------------------------------


class SearchPub78Tests(unittest.TestCase):
    """Tests for search_pub78()."""

    def _make_records(self) -> tuple[list[Pub78Record], StalenessWarning]:
        lines = "\n".join(
            [
                _sample_pub78_line(ein="111111111", name="DO GOOD MINISTRIES INC", state="OH"),
                _sample_pub78_line(ein="222222222", name="COMMUNITY IMPROVEMENT CORP", state="OH"),
                _sample_pub78_line(ein="333333333", name="TOLEDO ARTS COUNCIL", state="OH"),
                _sample_pub78_line(ein="444444444", name="DO GOOD FOUNDATION", state="IL"),
            ]
        )
        records = _parse_pub78(lines)
        warning = StalenessWarning.from_download_time(
            datetime.now(tz=timezone.utc) - timedelta(days=2)
        )
        return records, warning

    def test_finds_by_name_substring(self):
        records, warning = self._make_records()
        result = search_pub78("do good", records, warning)
        self.assertEqual(len(result.matches), 2)

    def test_case_insensitive_match(self):
        records, warning = self._make_records()
        result = search_pub78("DO GOOD", records, warning)
        self.assertEqual(len(result.matches), 2)
        result2 = search_pub78("do good", records, warning)
        self.assertEqual(len(result2.matches), 2)

    def test_state_filter_narrows_results(self):
        records, warning = self._make_records()
        result = search_pub78("do good", records, warning, state="OH")
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].ein, 111111111)

    def test_state_filter_il_finds_one(self):
        records, warning = self._make_records()
        result = search_pub78("do good", records, warning, state="IL")
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].ein, 444444444)

    def test_no_match_returns_empty_list(self):
        records, warning = self._make_records()
        result = search_pub78("NONEXISTENT ORG XYZ", records, warning)
        self.assertEqual(result.matches, [])

    def test_result_preserves_query(self):
        records, warning = self._make_records()
        result = search_pub78("do good", records, warning)
        self.assertEqual(result.query, "do good")

    def test_total_searched_reflects_pool(self):
        records, warning = self._make_records()
        result = search_pub78("do good", records, warning, state="OH")
        # 3 OH records, 1 IL record — state filter gives pool of 3
        self.assertEqual(result.total_searched, 3)

    def test_empty_query_raises_irs_error(self):
        records, warning = self._make_records()
        with self.assertRaises(IRSError):
            search_pub78("", records, warning)

    def test_whitespace_query_raises_irs_error(self):
        records, warning = self._make_records()
        with self.assertRaises(IRSError):
            search_pub78("   ", records, warning)

    def test_empty_records_raises_irs_error(self):
        warning = StalenessWarning.from_download_time(datetime.now(tz=timezone.utc))
        with self.assertRaises(IRSError):
            search_pub78("do good", [], warning)

    def test_staleness_warning_always_present(self):
        records, warning = self._make_records()
        result = search_pub78("anything", records, warning)
        self.assertIsInstance(result.staleness_warning, StalenessWarning)

    def test_synthetic_staleness_when_none_passed(self):
        records, _warning = self._make_records()
        result = search_pub78("do good", records, staleness_warning=None)
        # Should not raise — should generate a synthetic HIGH warning
        self.assertIsInstance(result.staleness_warning, StalenessWarning)
        self.assertEqual(result.staleness_warning.level, StalenessLevel.HIGH)


# ---------------------------------------------------------------------------
# SearchEoBmfTests
# ---------------------------------------------------------------------------


class SearchEoBmfTests(unittest.TestCase):
    """Tests for search_eo_bmf()."""

    def _make_records(self) -> tuple[list[EoBmfRecord], StalenessWarning]:
        csv_bytes = _make_eo_bmf_csv(
            [
                _sample_bmf_row(EIN="111111111", NAME="DO GOOD MINISTRIES INC", STATE="OH"),
                _sample_bmf_row(EIN="222222222", NAME="VETERANS CENTER INC", STATE="OH"),
                _sample_bmf_row(EIN="333333333", NAME="DO GOOD FOUNDATION", STATE="IL"),
                _sample_bmf_row(EIN="444444444", NAME="REVOKED ORG", STATE="OH", STATUS="12"),
            ]
        )
        records = _parse_eo_bmf(csv_bytes.decode("utf-8"))
        warning = StalenessWarning.from_download_time(
            datetime.now(tz=timezone.utc) - timedelta(days=2)
        )
        return records, warning

    def test_finds_by_name_substring(self):
        records, warning = self._make_records()
        result = search_eo_bmf("do good", records, warning)
        self.assertEqual(len(result.matches), 2)

    def test_case_insensitive(self):
        records, warning = self._make_records()
        result = search_eo_bmf("DO GOOD", records, warning)
        self.assertEqual(len(result.matches), 2)

    def test_state_filter(self):
        records, warning = self._make_records()
        result = search_eo_bmf("do good", records, warning, state="OH")
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].ein, 111111111)

    def test_include_revoked_true_by_default(self):
        records, warning = self._make_records()
        result = search_eo_bmf("revoked", records, warning)
        self.assertEqual(len(result.matches), 1)
        self.assertTrue(result.matches[0].is_revoked)

    def test_include_revoked_false_excludes_revoked(self):
        records, warning = self._make_records()
        result = search_eo_bmf("revoked", records, warning, include_revoked=False)
        self.assertEqual(result.matches, [])

    def test_no_match_returns_empty_list(self):
        records, warning = self._make_records()
        result = search_eo_bmf("nonexistent xyz", records, warning)
        self.assertEqual(result.matches, [])

    def test_empty_query_raises_irs_error(self):
        records, warning = self._make_records()
        with self.assertRaises(IRSError):
            search_eo_bmf("", records, warning)

    def test_empty_records_raises_irs_error(self):
        warning = StalenessWarning.from_download_time(datetime.now(tz=timezone.utc))
        with self.assertRaises(IRSError):
            search_eo_bmf("do good", [], warning)

    def test_staleness_warning_always_present(self):
        records, warning = self._make_records()
        result = search_eo_bmf("anything", records, warning)
        self.assertIsInstance(result.staleness_warning, StalenessWarning)

    def test_synthetic_staleness_when_none_passed(self):
        records, _ = self._make_records()
        result = search_eo_bmf("do good", records, staleness_warning=None)
        self.assertEqual(result.staleness_warning.level, StalenessLevel.HIGH)

    def test_result_preserves_query(self):
        records, warning = self._make_records()
        result = search_eo_bmf("veterans", records, warning)
        self.assertEqual(result.query, "veterans")

    def test_total_searched_counts_pool_not_matches(self):
        records, warning = self._make_records()
        result = search_eo_bmf("do good", records, warning, state="OH")
        # 3 OH records in pool, 1 match
        self.assertEqual(result.total_searched, 3)
        self.assertEqual(len(result.matches), 1)


# ---------------------------------------------------------------------------
# LookupEinTests
# ---------------------------------------------------------------------------


class LookupEinTests(unittest.TestCase):
    """Tests for lookup_ein()."""

    def _make_records(self) -> tuple[list[EoBmfRecord], StalenessWarning]:
        csv_bytes = _make_eo_bmf_csv(
            [
                _sample_bmf_row(EIN="341234567", NAME="DO GOOD MINISTRIES INC"),
                _sample_bmf_row(EIN="341234568", NAME="VETERANS CENTER INC", STATUS="12"),
            ]
        )
        records = _parse_eo_bmf(csv_bytes.decode("utf-8"))
        warning = StalenessWarning.from_download_time(datetime.now(tz=timezone.utc))
        return records, warning

    def test_found_returns_record(self):
        records, warning = self._make_records()
        result, w = lookup_ein(341234567, records, warning)
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "DO GOOD MINISTRIES INC")

    def test_not_found_returns_none(self):
        records, warning = self._make_records()
        result, w = lookup_ein(999999999, records, warning)
        self.assertIsNone(result)

    def test_staleness_warning_always_returned(self):
        records, warning = self._make_records()
        _result, w = lookup_ein(341234567, records, warning)
        self.assertIsInstance(w, StalenessWarning)

    def test_string_ein_with_dash_is_normalized(self):
        records, warning = self._make_records()
        result, _w = lookup_ein("34-1234567", records, warning)
        self.assertIsNotNone(result)
        self.assertEqual(result.ein, 341234567)

    def test_string_ein_without_dash_is_normalized(self):
        records, warning = self._make_records()
        result, _w = lookup_ein("341234567", records, warning)
        self.assertIsNotNone(result)

    def test_found_revoked_org(self):
        records, warning = self._make_records()
        result, _w = lookup_ein(341234568, records, warning)
        self.assertIsNotNone(result)
        self.assertTrue(result.is_revoked)

    def test_ruling_date_accessible_on_result(self):
        records, warning = self._make_records()
        result, _w = lookup_ein(341234567, records, warning)
        self.assertEqual(result.ruling_date, "200301")
        self.assertEqual(result.ruling_year, 2003)

    def test_synthetic_staleness_when_none_passed(self):
        records, _ = self._make_records()
        _result, w = lookup_ein(341234567, records, None)
        self.assertIsInstance(w, StalenessWarning)
        self.assertEqual(w.level, StalenessLevel.HIGH)


# ---------------------------------------------------------------------------
# SearchOhioNonprofitsTests
# ---------------------------------------------------------------------------


class SearchOhioNonprofitsTests(unittest.TestCase):
    """Tests for search_ohio_nonprofits() convenience wrapper."""

    @patch("investigations.irs_connector.requests.get")
    def test_returns_matching_records(self, mock_get):
        csv_bytes = _make_eo_bmf_csv(
            [
                _sample_bmf_row(EIN="111111111", NAME="DO GOOD MINISTRIES INC", STATE="OH"),
                _sample_bmf_row(EIN="222222222", NAME="COMMUNITY FOUNDATION", STATE="OH"),
            ]
        )
        mock_get.return_value = _make_response(csv_bytes)
        result = search_ohio_nonprofits("do good")
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].ein, 111111111)

    @patch("investigations.irs_connector.requests.get")
    def test_no_match_returns_empty_list(self, mock_get):
        csv_bytes = _make_eo_bmf_csv([_sample_bmf_row()])
        mock_get.return_value = _make_response(csv_bytes)
        result = search_ohio_nonprofits("nonexistent xyz")
        self.assertEqual(result.matches, [])

    @patch("investigations.irs_connector.requests.get")
    def test_uses_state_oh_url(self, mock_get):
        csv_bytes = _make_eo_bmf_csv([_sample_bmf_row()])
        mock_get.return_value = _make_response(csv_bytes)
        search_ohio_nonprofits("do good")
        call_url = mock_get.call_args[0][0]
        self.assertIn("eo_oh.csv", call_url)

    @patch("investigations.irs_connector.requests.get")
    def test_include_revoked_true_by_default(self, mock_get):
        csv_bytes = _make_eo_bmf_csv(
            [
                _sample_bmf_row(EIN="111111111", NAME="REVOKED ORG", STATE="OH", STATUS="12"),
            ]
        )
        mock_get.return_value = _make_response(csv_bytes)
        result = search_ohio_nonprofits("revoked")
        self.assertEqual(len(result.matches), 1)

    @patch("investigations.irs_connector.requests.get")
    def test_include_revoked_false_excludes_revoked(self, mock_get):
        csv_bytes = _make_eo_bmf_csv(
            [
                _sample_bmf_row(EIN="111111111", NAME="REVOKED ORG", STATE="OH", STATUS="12"),
            ]
        )
        mock_get.return_value = _make_response(csv_bytes)
        result = search_ohio_nonprofits("revoked", include_revoked=False)
        self.assertEqual(result.matches, [])

    @patch("investigations.irs_connector.requests.get")
    def test_network_error_propagates_as_irs_error(self, mock_get):
        import requests as req

        mock_get.side_effect = req.exceptions.ConnectionError("down")
        with self.assertRaises(IRSError):
            search_ohio_nonprofits("anything")

    @patch("investigations.irs_connector.requests.get")
    def test_staleness_warning_present_in_result(self, mock_get):
        csv_bytes = _make_eo_bmf_csv([_sample_bmf_row()])
        mock_get.return_value = _make_response(csv_bytes)
        result = search_ohio_nonprofits("do good")
        self.assertIsInstance(result.staleness_warning, StalenessWarning)


# ---------------------------------------------------------------------------
# IRSErrorTests
# ---------------------------------------------------------------------------


class IRSErrorTests(unittest.TestCase):
    def test_status_code_stored(self):
        err = IRSError("not found", status_code=404)
        self.assertEqual(err.status_code, 404)

    def test_ein_stored(self):
        err = IRSError("bad ein", ein=341234567)
        self.assertEqual(err.ein, 341234567)

    def test_status_code_defaults_to_none(self):
        err = IRSError("network down")
        self.assertIsNone(err.status_code)

    def test_ein_defaults_to_none(self):
        err = IRSError("network down")
        self.assertIsNone(err.ein)

    def test_is_exception(self):
        with self.assertRaises(IRSError):
            raise IRSError("test error")

    def test_message_accessible_via_str(self):
        err = IRSError("something went wrong")
        self.assertIn("something went wrong", str(err))


# ---------------------------------------------------------------------------
# SafeIntTests
# ---------------------------------------------------------------------------


class SafeIntTests(unittest.TestCase):
    def test_integer_input(self):
        self.assertEqual(_safe_int(500000), 500000)

    def test_string_integer(self):
        self.assertEqual(_safe_int("750000"), 750000)

    def test_float_string(self):
        self.assertEqual(_safe_int("1234.0"), 1234)

    def test_empty_string_returns_none(self):
        self.assertIsNone(_safe_int(""))

    def test_none_returns_none(self):
        self.assertIsNone(_safe_int(None))

    def test_non_numeric_string_returns_none(self):
        self.assertIsNone(_safe_int("not a number"))

    def test_zero_is_valid(self):
        self.assertEqual(_safe_int(0), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
