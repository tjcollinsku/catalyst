"""
Tests for the Ohio Auditor of State connector.
"""

import unittest
from datetime import date
from unittest.mock import patch, MagicMock
from investigations.ohio_aos_connector import search_audit_reports, AuditReport, AOSError

MOCK_HTML = """
<html>
<body>
    <table>
        <tr>
            <th>Entity Name</th>
            <th>County</th>
            <th>Report Type</th>
            <th>Entity Type</th>
            <th>Report Period</th>
            <th>Release Date</th>
        </tr>
        <tr>
            <td><a href="/reports/audit1.pdf">Do Good Village</a></td>
            <td>Seneca</td>
            <td>Financial Audit</td>
            <td>Village</td>
            <td>01/01/2021 - 12/31/2022</td>
            <td>02/06/2024</td>
        </tr>
        <tr>
            <td><a href="/reports/audit2.pdf">* Franklin Township</a></td>
            <td>Franklin</td>
            <td>Special Audit</td>
            <td>Township</td>
            <td>01/01/2018 - 12/31/2022</td>
            <td>02/06/2024</td>
        </tr>
    </table>
</body>
</html>
"""


def _make_mock_response(html: str, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.ok = status_code < 400
    mock.status_code = status_code
    mock.text = html
    return mock


class OhioAOSTests(unittest.TestCase):
    @patch("investigations.ohio_aos_connector.requests.get")
    def test_search_audit_reports_success(self, mock_get):
        mock_get.return_value = _make_mock_response(MOCK_HTML)

        results = search_audit_reports("Village")
        self.assertEqual(len(results), 2)

        self.assertEqual(results[0].entity_name, "Do Good Village")
        self.assertFalse(results[0].has_findings_for_recovery)
        self.assertEqual(results[0].release_date, date(2024, 2, 6))
        self.assertEqual(results[0].pdf_url,
                         "https://ohioauditor.gov/reports/audit1.pdf")

        self.assertEqual(results[1].entity_name, "Franklin Township")
        self.assertTrue(results[1].has_findings_for_recovery)
        self.assertEqual(results[1].county, "Franklin")

    @patch("investigations.ohio_aos_connector.requests.get")
    def test_search_audit_reports_empty_query(self, mock_get):
        with self.assertRaises(AOSError):
            search_audit_reports("")

    @patch("investigations.ohio_aos_connector.requests.get")
    def test_search_audit_reports_http_error(self, mock_get):
        mock_get.return_value = _make_mock_response("", 500)
        with self.assertRaises(AOSError):
            search_audit_reports("Village")


if __name__ == "__main__":
    unittest.main()
