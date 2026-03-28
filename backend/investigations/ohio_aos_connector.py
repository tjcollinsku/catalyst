"""
Ohio Auditor of State (AOS) connector for Catalyst.

Strategy: Stateless HTML scraper (mocked for testing).

The Ohio Auditor of State publishes audit reports for all public entities
(counties, cities, villages, townships, school districts). Crucially, these
reports denote whether an audit resulted in a "Finding for Recovery" — a
legal determination that public money was spent illegally, collected improperly,
or misappropriated, and must be repaid.

Investigative context:
    Public corruption investigations frequently intersect with the AOS.
    If a nonprofit or contractor is doing business with a village or township,
    an AOS finding against that village may name the contractor.

Data Source:
    https://ohioauditor.gov/auditsearch/search.aspx
    (HTML search results table)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
import urllib.parse
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# URL for search (assuming a GET parameter-based search for simplicity)
AOS_SEARCH_URL = "https://ohioauditor.gov/auditsearch/searchresults.aspx"

REQUEST_TIMEOUT = (5, 30)
HEADERS = {
    "User-Agent": "Catalyst/2.0 (Intelligence Triage Platform; contact: investigator)",
}


class AOSError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class AuditReport:
    """A single audit report from the Ohio Auditor of State."""
    entity_name: str
    county: str
    report_type: str
    entity_type: str
    report_period: str
    release_date: datetime.date | None
    has_findings_for_recovery: bool
    pdf_url: str | None


def search_audit_reports(query: str) -> list[AuditReport]:
    """
    Search the Ohio Auditor of State database for audit reports.

    Args:
        query: Entity name to search for (e.g., "Example Charity").

    Returns:
        List of AuditReport objects.
    """
    if not query or not query.strip():
        raise AOSError("Search query cannot be empty.")

    params = {"q": query.strip()}
    logger.info("ohio_aos_connector: searching for %r", query)

    try:
        response = requests.get(
            AOS_SEARCH_URL,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise AOSError(f"Could not connect to Ohio AOS: {e}") from e

    if not response.ok:
        raise AOSError(
            f"Ohio AOS returned HTTP {response.status_code}",
            status_code=response.status_code,
        )

    return _parse_aos_html(response.text)


def _parse_aos_html(html: str) -> list[AuditReport]:
    """
    Parse the HTML table from the AOS search results.

    Expected table columns:
    Entity Name | County | Report Type | Entity Type | Report Period | Release Date
    """
    reports = []

    # We use a robust regex to find table rows.
    # A real implementation might use BeautifulSoup, but regex avoids a new dependency
    # and is sufficient for a targeted scraper where we control the mock.

    row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    cell_pattern = re.compile(
        r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
    link_pattern = re.compile(r"href=['\"]([^'\"]+\.pdf)['\"]", re.IGNORECASE)

    for row_match in row_pattern.finditer(html):
        row_html = row_match.group(1)
        cells = cell_pattern.findall(row_html)

        if len(cells) < 6:
            continue

        def clean_cell(text):
            text = re.sub(r"<[^>]+>", "", text)
            text = text.replace("&nbsp;", " ").replace("&amp;", "&")
            return text.strip()

        entity_name_raw = clean_cell(cells[0])

        # Skip header rows
        if entity_name_raw.lower() == "entity name":
            continue

        # "* Denotes Findings for Recovery"
        has_findings = False
        if entity_name_raw.startswith("*"):
            has_findings = True
            entity_name_raw = entity_name_raw.lstrip("*").strip()

        county = clean_cell(cells[1])
        report_type = clean_cell(cells[2])
        entity_type = clean_cell(cells[3])
        report_period = clean_cell(cells[4])
        release_date_str = clean_cell(cells[5])

        release_date = None
        if release_date_str:
            try:
                # typically MM/DD/YYYY
                release_date = datetime.strptime(
                    release_date_str, "%m/%d/%Y").date()
            except ValueError:
                pass

        # Look for PDF link in the entity name cell (typical for AOS)
        pdf_url = None
        link_match = link_pattern.search(cells[0])
        if link_match:
            pdf_url = link_match.group(1)
            if pdf_url.startswith("/"):
                pdf_url = "https://ohioauditor.gov" + pdf_url

        reports.append(AuditReport(
            entity_name=entity_name_raw,
            county=county,
            report_type=report_type,
            entity_type=entity_type,
            report_period=report_period,
            release_date=release_date,
            has_findings_for_recovery=has_findings,
            pdf_url=pdf_url,
        ))

    return reports
