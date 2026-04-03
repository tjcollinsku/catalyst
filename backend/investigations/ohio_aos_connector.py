"""
Ohio Auditor of State (AOS) connector for Catalyst.

Strategy: Two-step ASP.NET form scraper.

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
    (ASP.NET WebForms — requires ViewState round-trip)

How this works (ASP.NET postback pattern):
    1. GET search.aspx → extract __VIEWSTATE and __EVENTVALIDATION
    2. POST search.aspx with form fields + hidden state → get results HTML
    3. Parse the results table from the response

    This two-step dance is required because ASP.NET WebForms embeds a
    cryptographic token (__VIEWSTATE) in every page load. You cannot POST
    directly without first GETting the page — the server rejects requests
    without a valid ViewState.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# The search form lives at search.aspx (NOT searchresults.aspx)
AOS_SEARCH_URL = "https://ohioauditor.gov/auditsearch/search.aspx"

REQUEST_TIMEOUT = (5, 30)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.5",
}

# ASP.NET form field names (extracted from the actual search page HTML).
# The AOS search form uses simple names (no ContentPlaceHolder prefix).
_FIELD_ENTITY_NAME = "txtQueryString"


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

    This performs a two-step ASP.NET postback:
    1. GET search.aspx to obtain __VIEWSTATE and __EVENTVALIDATION tokens
    2. POST search.aspx with form data to get results

    Args:
        query: Entity name to search for (e.g., "Example Charity").

    Returns:
        List of AuditReport objects.

    Raises:
        AOSError: On network failure, HTTP errors, or missing form tokens.
    """
    if not query or not query.strip():
        raise AOSError("Search query cannot be empty.")

    query = query.strip()
    logger.info("ohio_aos_connector: searching for %r", query)

    session = requests.Session()
    session.headers.update(HEADERS)

    # Step 1: GET the search page to extract ASP.NET hidden fields
    try:
        page_response = session.get(
            AOS_SEARCH_URL,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise AOSError(f"Could not connect to Ohio AOS: {e}") from e

    if not page_response.ok:
        raise AOSError(
            f"Ohio AOS search page returned HTTP {page_response.status_code}",
            status_code=page_response.status_code,
        )

    # Extract ASP.NET hidden fields from the page
    viewstate = _extract_hidden_field(page_response.text, "__VIEWSTATE")
    viewstate_gen = _extract_hidden_field(page_response.text, "__VIEWSTATEGENERATOR")
    event_validation = _extract_hidden_field(page_response.text, "__EVENTVALIDATION")

    if not viewstate:
        # If we can't find ViewState, the page structure may have changed.
        # Log the first 500 chars of the response for debugging.
        logger.warning(
            "ohio_aos_no_viewstate",
            extra={"response_preview": page_response.text[:500]},
        )
        raise AOSError(
            "Could not extract ASP.NET ViewState from Ohio AOS search page. "
            "The page structure may have changed."
        )

    # Step 2: POST the search form with the entity name
    form_data = {
        "__VIEWSTATE": viewstate,
        "__EVENTVALIDATION": event_validation or "",
        _FIELD_ENTITY_NAME: query,
    }
    if viewstate_gen:
        form_data["__VIEWSTATEGENERATOR"] = viewstate_gen

    try:
        search_response = session.post(
            AOS_SEARCH_URL,
            data=form_data,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise AOSError(f"Could not submit search to Ohio AOS: {e}") from e

    if not search_response.ok:
        raise AOSError(
            f"Ohio AOS search returned HTTP {search_response.status_code}",
            status_code=search_response.status_code,
        )

    return _parse_aos_html(search_response.text)


def _extract_hidden_field(html: str, field_name: str) -> str | None:
    """
    Extract value of a hidden input field from ASP.NET HTML.

    ASP.NET WebForms pages contain hidden fields like:
        <input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE"
               value="..." />

    Args:
        html: The full HTML page content.
        field_name: The name/id of the hidden field (e.g., "__VIEWSTATE").

    Returns:
        The field value, or None if not found.
    """
    # Match: name="__VIEWSTATE" ... value="..."
    # The value can be very long (thousands of chars) for ViewState.
    pattern = re.compile(
        rf'name="{re.escape(field_name)}"[^>]*value="([^"]*)"',
        re.IGNORECASE,
    )
    match = pattern.search(html)
    if match:
        return match.group(1)

    # Try alternate order: value="..." ... name="..."
    pattern2 = re.compile(
        rf'value="([^"]*)"[^>]*name="{re.escape(field_name)}"',
        re.IGNORECASE,
    )
    match2 = pattern2.search(html)
    if match2:
        return match2.group(1)

    return None


def _parse_aos_html(html: str) -> list[AuditReport]:
    """
    Parse the HTML table from the AOS search results.

    Expected table columns:
    Entity Name | County | Report Type | Entity Type | Report Period | Release Date

    The results table may be embedded in the same search.aspx page
    (ASP.NET re-renders the page with results after postback).
    """
    reports = []

    row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    cell_pattern = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
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
        if entity_name_raw.lower() in ("entity name", ""):
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
                release_date = datetime.strptime(release_date_str, "%m/%d/%Y").date()
            except ValueError:
                pass

        # Look for PDF link in the entity name cell (typical for AOS)
        # SEC-038: Validate domain to prevent injected URLs.
        pdf_url = None
        link_match = link_pattern.search(cells[0])
        if link_match:
            raw_url = link_match.group(1)
            if raw_url.startswith("/"):
                pdf_url = "https://ohioauditor.gov" + raw_url
            else:
                try:
                    parsed = urlparse(raw_url)
                    if parsed.hostname and parsed.hostname.lower().endswith("ohioauditor.gov"):
                        pdf_url = raw_url
                    else:
                        logger.warning(
                            "aos_pdf_untrusted_domain",
                            extra={
                                "url": raw_url,
                                "domain": parsed.hostname,
                            },
                        )
                except Exception:
                    logger.warning("aos_pdf_invalid_url", extra={"url": raw_url})

        reports.append(
            AuditReport(
                entity_name=entity_name_raw,
                county=county,
                report_type=report_type,
                entity_type=entity_type,
                report_period=report_period,
                release_date=release_date,
                has_findings_for_recovery=has_findings,
                pdf_url=pdf_url,
            )
        )

    return reports
