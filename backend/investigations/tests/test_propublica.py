"""
Tests for the ProPublica Nonprofit Explorer connector.

All tests use unittest.mock to intercept HTTP calls — no real network
requests are made. This means tests run offline, run fast, and don't
consume ProPublica's API quota.

How mocking works here (important concept for a beginner):

    The connector calls requests.get() to make HTTP requests.
    We use @patch("investigations.propublica_connector.requests.get") to
    intercept that call and replace it with a fake object we control.

    The fake object (called a "mock") lets us say:
        "When requests.get() is called, pretend the server responded with
         this JSON body and this status code."

    This way we can test every code path — success, 404, rate limit,
    network error, malformed response — without needing a real server.

Run these tests with:
    python -m unittest investigations.tests_propublica -v
(from the backend/ directory, with Django not required since there are no DB calls)
"""

import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Shared fixture data
# These are realistic fake API responses that mirror ProPublica's actual format.
# ---------------------------------------------------------------------------

SEARCH_RESPONSE = {
    "total_results": 2,
    "organizations": [
        {
            "ein": 123456789,
            "name": "EXAMPLE CHARITY MINISTRIES INC",
            "city": "CAREY",
            "state": "OH",
            "ntee_code": "X20",
            "subsection_code": 3,
        },
        {
            "ein": 987654321,
            "name": "EXAMPLE CHARITY COMMUNITY FUND",
            "city": "FINDLAY",
            "state": "OH",
            "ntee_code": "T30",
            "subsection_code": 3,
        },
    ],
}

ORG_RESPONSE = {
    "organization": {
        "ein": 123456789,
        "name": "EXAMPLE CHARITY MINISTRIES INC",
        "city": "CAREY",
        "state": "OH",
        "ntee_code": "X20",
        "subsection_code": 3,
        "ruling": "200301",
        "classification_codes": "1000",
        "foundation_code": "15",
        "activity_codes": "050",
        "deductibility_code": "1",
    },
    "filings_with_data": [
        {
            "tax_prd": 202212,
            "tax_prd_yr": 2022,
            "formtype": "990",
            "pdf_url": "https://example.com/990_2022.pdf",
            "totrevenue": 1500000,
            "totfuncexpns": 1200000,
            "totassetsend": 800000,
            "totliabend": 50000,
            "pct_compnsatncurrofcr": 0.12,
        },
        {
            "tax_prd": 202112,
            "tax_prd_yr": 2021,
            "formtype": "990",
            "pdf_url": "https://example.com/990_2021.pdf",
            "totrevenue": 1400000,
            "totfuncexpns": 1100000,
            "totassetsend": 750000,
            "totliabend": 45000,
            "pct_compnsatncurrofcr": 0.11,
        },
    ],
    "filings_without_data": [
        {
            "tax_prd": 201812,
            "formtype": "990",
            "pdf_url": "https://example.com/990_2018.pdf",
        },
    ],
}


def _make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """
    Build a fake requests.Response object.

    This helper saves us from repeating boilerplate in every test.
    It creates a MagicMock and sets the attributes that our connector reads:
        .ok           — True if status < 400
        .status_code  — the HTTP status code
        .json()       — the parsed JSON body
    """
    mock = MagicMock()
    mock.ok = status_code < 400
    mock.status_code = status_code
    mock.json.return_value = json_data
    return mock


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


class SearchOrganizationsTests(unittest.TestCase):
    @patch("investigations.propublica_connector.requests.get")
    def test_returns_list_of_summaries(self, mock_get):
        mock_get.return_value = _make_mock_response(SEARCH_RESPONSE)

        from investigations.propublica_connector import search_organizations

        results = search_organizations("Example Charity Ministries", state="OH")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].ein, 123456789)
        self.assertEqual(results[0].name, "EXAMPLE CHARITY MINISTRIES INC")
        self.assertEqual(results[0].city, "CAREY")
        self.assertEqual(results[0].state, "OH")

    @patch("investigations.propublica_connector.requests.get")
    def test_includes_exempt_status_from_subsection_code(self, mock_get):
        mock_get.return_value = _make_mock_response(SEARCH_RESPONSE)

        from investigations.propublica_connector import search_organizations

        results = search_organizations("Example Charity")

        # subsection_code 3 → "501(c)(3)"
        self.assertEqual(results[0].exempt_status, "501(c)(3)")

    @patch("investigations.propublica_connector.requests.get")
    def test_passes_state_filter_as_query_param(self, mock_get):
        mock_get.return_value = _make_mock_response(SEARCH_RESPONSE)

        from investigations.propublica_connector import search_organizations

        search_organizations("Example Charity", state="oh")  # lowercase — should be uppercased

        # Inspect the params that were passed to requests.get
        call_kwargs = mock_get.call_args
        params = (
            call_kwargs[1].get("params") or call_kwargs[0][1]
            if len(call_kwargs[0]) > 1
            else call_kwargs[1]["params"]
        )
        self.assertIn("state[id]", params)
        self.assertEqual(params["state[id]"], "OH")

    @patch("investigations.propublica_connector.requests.get")
    def test_returns_empty_list_when_no_results(self, mock_get):
        mock_get.return_value = _make_mock_response({"total_results": 0, "organizations": []})

        from investigations.propublica_connector import search_organizations

        results = search_organizations("xyznonexistent")

        self.assertEqual(results, [])

    def test_raises_on_empty_query(self):
        from investigations.propublica_connector import ProPublicaError, search_organizations

        with self.assertRaises(ProPublicaError):
            search_organizations("")

        with self.assertRaises(ProPublicaError):
            search_organizations("   ")

    @patch("investigations.propublica_connector.requests.get")
    def test_raises_propublica_error_on_404(self, mock_get):
        mock_get.return_value = _make_mock_response({}, status_code=404)

        from investigations.propublica_connector import ProPublicaError, search_organizations

        with self.assertRaises(ProPublicaError) as ctx:
            search_organizations("anything")

        self.assertEqual(ctx.exception.status_code, 404)

    @patch("investigations.propublica_connector.requests.get")
    def test_raises_propublica_error_on_rate_limit(self, mock_get):
        mock_get.return_value = _make_mock_response({}, status_code=429)

        from investigations.propublica_connector import ProPublicaError, search_organizations

        with self.assertRaises(ProPublicaError) as ctx:
            search_organizations("anything")

        self.assertEqual(ctx.exception.status_code, 429)

    @patch("investigations.propublica_connector.requests.get")
    def test_raises_propublica_error_on_connection_error(self, mock_get):
        import requests as req

        mock_get.side_effect = req.exceptions.ConnectionError("refused")

        from investigations.propublica_connector import ProPublicaError, search_organizations

        with self.assertRaises(ProPublicaError):
            search_organizations("anything")

    @patch("investigations.propublica_connector.requests.get")
    def test_skips_malformed_org_records_gracefully(self, mock_get):
        # One good record, one missing 'ein' key
        mock_get.return_value = _make_mock_response(
            {
                "total_results": 2,
                "organizations": [
                    {"ein": 123456789, "name": "GOOD ORG", "city": "X", "state": "OH"},
                    {"name": "BAD ORG — no EIN"},  # missing ein — should be skipped
                ],
            }
        )

        from investigations.propublica_connector import search_organizations

        results = search_organizations("anything")

        # Should return the one good record without crashing
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].ein, 123456789)


# ---------------------------------------------------------------------------
# Fetch organization tests
# ---------------------------------------------------------------------------


class FetchOrganizationTests(unittest.TestCase):
    @patch("investigations.propublica_connector.requests.get")
    def test_returns_org_profile(self, mock_get):
        mock_get.return_value = _make_mock_response(ORG_RESPONSE)

        from investigations.propublica_connector import fetch_organization

        profile = fetch_organization(123456789)

        self.assertEqual(profile.ein, 123456789)
        self.assertEqual(profile.name, "EXAMPLE CHARITY MINISTRIES INC")
        self.assertEqual(profile.state, "OH")
        self.assertEqual(profile.ruling_date, "200301")
        self.assertEqual(profile.exempt_status, "501(c)(3)")

    @patch("investigations.propublica_connector.requests.get")
    def test_accepts_string_ein_with_dash(self, mock_get):
        mock_get.return_value = _make_mock_response(ORG_RESPONSE)

        from investigations.propublica_connector import fetch_organization

        # "12-3456789" should normalize to 123456789
        profile = fetch_organization("12-3456789")
        self.assertEqual(profile.ein, 123456789)

    @patch("investigations.propublica_connector.requests.get")
    def test_raises_on_empty_organization_body(self, mock_get):
        mock_get.return_value = _make_mock_response({"organization": {}, "filings_with_data": []})

        from investigations.propublica_connector import ProPublicaError, fetch_organization

        with self.assertRaises(ProPublicaError):
            fetch_organization(123456789)

    def test_raises_on_invalid_ein(self):
        from investigations.propublica_connector import ProPublicaError, fetch_organization

        with self.assertRaises(ProPublicaError):
            fetch_organization(-1)

        with self.assertRaises(ProPublicaError):
            fetch_organization("not-a-number")

    @patch("investigations.propublica_connector.requests.get")
    def test_raw_org_dict_preserved(self, mock_get):
        mock_get.return_value = _make_mock_response(ORG_RESPONSE)

        from investigations.propublica_connector import fetch_organization

        profile = fetch_organization(123456789)

        # organization_raw should contain the original dict for fields we
        # didn't explicitly model
        self.assertIn("foundation_code", profile.organization_raw)
        self.assertEqual(profile.organization_raw["foundation_code"], "15")


# ---------------------------------------------------------------------------
# Fetch filings tests
# ---------------------------------------------------------------------------


class FetchFilingsTests(unittest.TestCase):
    @patch("investigations.propublica_connector.requests.get")
    def test_returns_combined_filings_list(self, mock_get):
        mock_get.return_value = _make_mock_response(ORG_RESPONSE)

        from investigations.propublica_connector import fetch_filings

        filings = fetch_filings(123456789)

        # 2 filings_with_data + 1 filing_without_data = 3 total
        self.assertEqual(len(filings), 3)

    @patch("investigations.propublica_connector.requests.get")
    def test_filings_sorted_most_recent_first(self, mock_get):
        mock_get.return_value = _make_mock_response(ORG_RESPONSE)

        from investigations.propublica_connector import fetch_filings

        filings = fetch_filings(123456789)

        tax_periods = [f.tax_period for f in filings]
        self.assertEqual(tax_periods, sorted(tax_periods, reverse=True))

    @patch("investigations.propublica_connector.requests.get")
    def test_filing_financial_fields_parsed(self, mock_get):
        mock_get.return_value = _make_mock_response(ORG_RESPONSE)

        from investigations.propublica_connector import fetch_filings

        filings = fetch_filings(123456789)

        most_recent = filings[0]
        self.assertEqual(most_recent.tax_year, 2022)
        self.assertEqual(most_recent.form_type, "990")
        self.assertEqual(most_recent.total_revenue, 1500000.0)
        self.assertEqual(most_recent.total_expenses, 1200000.0)
        self.assertEqual(most_recent.total_assets_eoy, 800000.0)
        self.assertEqual(most_recent.pdf_url, "https://example.com/990_2022.pdf")

    @patch("investigations.propublica_connector.requests.get")
    def test_filing_without_data_has_pdf_url_only(self, mock_get):
        mock_get.return_value = _make_mock_response(ORG_RESPONSE)

        from investigations.propublica_connector import fetch_filings

        filings = fetch_filings(123456789)

        # The 2018 filing (oldest) has no financial data
        oldest = filings[-1]
        self.assertEqual(oldest.tax_year, 2018)
        self.assertIsNone(oldest.total_revenue)
        self.assertEqual(oldest.pdf_url, "https://example.com/990_2018.pdf")

    @patch("investigations.propublica_connector.requests.get")
    def test_pdf_urls_are_all_strings_or_none(self, mock_get):
        mock_get.return_value = _make_mock_response(ORG_RESPONSE)

        from investigations.propublica_connector import fetch_filings

        filings = fetch_filings(123456789)

        for f in filings:
            self.assertTrue(
                f.pdf_url is None or isinstance(f.pdf_url, str),
                f"Expected pdf_url to be str or None, got {type(f.pdf_url)}",
            )

    @patch("investigations.propublica_connector.requests.get")
    def test_returns_empty_list_when_no_filings(self, mock_get):
        mock_get.return_value = _make_mock_response(
            {
                "organization": ORG_RESPONSE["organization"],
                "filings_with_data": [],
                "filings_without_data": [],
            }
        )

        from investigations.propublica_connector import fetch_filings

        filings = fetch_filings(123456789)

        self.assertEqual(filings, [])


# ---------------------------------------------------------------------------
# EIN validation tests
# ---------------------------------------------------------------------------


class EINValidationTests(unittest.TestCase):
    def test_string_ein_without_dash_accepted(self):
        from investigations.propublica_connector import _validate_ein

        self.assertEqual(_validate_ein("123456789"), 123456789)

    def test_string_ein_with_dash_accepted(self):
        from investigations.propublica_connector import _validate_ein

        self.assertEqual(_validate_ein("12-3456789"), 123456789)

    def test_integer_ein_accepted(self):
        from investigations.propublica_connector import _validate_ein

        self.assertEqual(_validate_ein(123456789), 123456789)

    def test_negative_ein_raises(self):
        from investigations.propublica_connector import ProPublicaError, _validate_ein

        with self.assertRaises(ProPublicaError):
            _validate_ein(-1)

    def test_non_numeric_string_raises(self):
        from investigations.propublica_connector import ProPublicaError, _validate_ein

        with self.assertRaises(ProPublicaError):
            _validate_ein("not-an-ein")


# ---------------------------------------------------------------------------
# Exempt status derivation tests
# ---------------------------------------------------------------------------


class ExemptStatusTests(unittest.TestCase):
    def test_subsection_3_returns_501c3(self):
        from investigations.propublica_connector import _derive_exempt_status

        self.assertEqual(_derive_exempt_status(3), "501(c)(3)")

    def test_subsection_4_returns_501c4(self):
        from investigations.propublica_connector import _derive_exempt_status

        self.assertEqual(_derive_exempt_status(4), "501(c)(4)")

    def test_unknown_subsection_returns_generic(self):
        from investigations.propublica_connector import _derive_exempt_status

        self.assertEqual(_derive_exempt_status(99), "501(c)(99)")

    def test_none_returns_none(self):
        from investigations.propublica_connector import _derive_exempt_status

        self.assertIsNone(_derive_exempt_status(None))


if __name__ == "__main__":
    unittest.main()
