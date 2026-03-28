"""
ProPublica Nonprofit Explorer API connector for Catalyst.

Provides three operations:

    1. search_organizations(query, state)
       Search for nonprofits by name or keyword, optionally filtered by state.
       Returns a list of lightweight OrganizationSummary objects.

    2. fetch_organization(ein)
       Fetch the full profile for a single organization by EIN.
       Returns an OrganizationProfile with all available IRS metadata.

    3. fetch_filings(ein)
       Fetch the list of 990 filings for an organization by EIN.
       Returns a list of Filing objects, each with financial totals and a PDF URL.
       These PDF URLs can be fed directly into Catalyst's document intake pipeline.

Design principles:

    - Stateless: no Django imports, no DB writes. This module only fetches and
      returns structured data. Persisting to the DB is the caller's job.
      This makes the connector easy to test and reuse outside the upload pipeline.

    - Explicit errors: network failures, bad EINs, and rate limits raise
      ProPublicaError with a clear message. The caller decides how to handle them.

    - No retries built in: the connector makes one attempt. If you need retry
      logic (e.g., for rate limiting), wrap the call in a retry decorator at
      the call site. Keeping retries out of the connector keeps it simple.

    - Rate limiting awareness: ProPublica doesn't publish a hard rate limit,
      but their terms ask for reasonable use. We add a configurable delay
      between calls when fetching multiple filings in a loop.

API reference: https://projects.propublica.org/nonprofits/api
No API key required. Free for non-commercial and research use.

Usage:
    from investigations.propublica_connector import (
        search_organizations,
        fetch_organization,
        fetch_filings,
        ProPublicaError,
    )

    # Find an org by name
    results = search_organizations("Do Good Ministries", state="OH")
    for org in results:
        print(org.ein, org.name, org.city)

    # Get full profile by EIN
    profile = fetch_organization(123456789)
    print(profile.name, profile.exempt_status, profile.ruling_date)

    # Get all 990 filings
    filings = fetch_filings(123456789)
    for f in filings:
        print(f.tax_year, f.form_type, f.total_revenue, f.pdf_url)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://projects.propublica.org/nonprofits/api/v2"

# Timeout for all HTTP requests (connect timeout, read timeout) in seconds.
# ProPublica's API is generally fast, but we don't want to hang indefinitely.
REQUEST_TIMEOUT = (5, 30)

# Polite delay between consecutive API calls (seconds).
# Used when making multiple requests in a loop (e.g., fetching filings for
# several EINs). Set to 0 to disable.
POLITE_DELAY = 0.5

# User-Agent header so ProPublica can identify Catalyst traffic.
HEADERS = {
    "User-Agent": "Catalyst/2.0 (Intelligence Triage Platform; contact: investigator)",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class ProPublicaError(Exception):
    """
    Raised when the ProPublica connector cannot complete a request.

    Attributes:
        message:     Human-readable description of what went wrong.
        status_code: HTTP status code if the error came from the API (or None).
        ein:         The EIN being looked up, if applicable (or None).
    """
    def __init__(self, message: str, status_code: int | None = None, ein: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.ein = ein


# ---------------------------------------------------------------------------
# Data structures
#
# Why dataclasses instead of dicts?
# Dicts work, but they give you no autocomplete, no type checking, and no
# documentation of what fields exist. Dataclasses make the contract explicit:
# you know exactly what fields the connector returns, and what type each is.
# ---------------------------------------------------------------------------

@dataclass
class OrganizationSummary:
    """
    Lightweight org record returned by search_organizations().
    Contains just enough to identify the org and decide whether to fetch more.

    Attributes:
        ein:           IRS Employer Identification Number (integer, no dashes).
        name:          Organization name as it appears in IRS records (usually ALL CAPS).
        city:          City of the organization's registered address.
        state:         Two-letter state code (e.g., "OH").
        ntee_code:     National Taxonomy of Exempt Entities code (e.g., "B99").
        subsection:    IRC subsection code (3 = 501(c)(3), 4 = 501(c)(4), etc.).
        exempt_status: Human-readable exemption status string (e.g., "501(c)(3)").
    """
    ein: int
    name: str
    city: str
    state: str
    ntee_code: str | None = None
    subsection: int | None = None
    exempt_status: str | None = None


@dataclass
class OrganizationProfile:
    """
    Full org profile returned by fetch_organization().

    Attributes:
        ein:              IRS EIN (integer).
        name:             Organization name.
        city:             City.
        state:            State code.
        ntee_code:        NTEE classification code.
        subsection:       IRC subsection code.
        exempt_status:    Exemption status string.
        ruling_date:      Date IRS ruling was issued, as "YYYYMM" string (e.g., "200301").
                          None if not available.
        classification:   IRS classification code string.
        foundation_code:  IRS foundation status code.
        activity_codes:   IRS activity codes string.
        deductibility:    Deductibility code.
        organization_raw: The full raw dict from the API, in case you need a field
                          not explicitly modeled here.
    """
    ein: int
    name: str
    city: str
    state: str
    ntee_code: str | None = None
    subsection: int | None = None
    exempt_status: str | None = None
    ruling_date: str | None = None
    classification: str | None = None
    foundation_code: str | None = None
    activity_codes: str | None = None
    deductibility: str | None = None
    organization_raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Filing:
    """
    A single 990 filing record returned by fetch_filings().

    Attributes:
        tax_period:          Tax period end date as YYYYMM integer (e.g., 202212).
        tax_year:            Four-digit tax year (e.g., 2022).
        form_type:           "990", "990EZ", or "990PF".
        pdf_url:             Direct URL to the filing PDF (or None if unavailable).
                             Feed this into Catalyst's document intake pipeline.
        total_revenue:       Total revenue for the year (float or None).
        total_expenses:      Total functional expenses (float or None).
        total_assets_eoy:    Total assets at end of year (float or None).
        total_liabilities_eoy: Total liabilities at end of year (float or None).
        officer_compensation_pct: Officer compensation as % of total expenses (float or None).
        filing_raw:          The full raw dict from the API.
    """
    tax_period: int
    tax_year: int
    form_type: str
    pdf_url: str | None = None
    total_revenue: float | None = None
    total_expenses: float | None = None
    total_assets_eoy: float | None = None
    total_liabilities_eoy: float | None = None
    officer_compensation_pct: float | None = None
    filing_raw: dict = field(default_factory=dict, repr=False)


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, params: dict | None = None) -> dict:
    """
    Make a GET request to the ProPublica API and return the parsed JSON body.

    Raises ProPublicaError on:
        - Network/connection errors
        - Non-200 HTTP status codes
        - Invalid JSON response
    """
    try:
        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.ConnectionError as e:
        raise ProPublicaError(
            f"Could not connect to ProPublica API: {e}"
        ) from e
    except requests.exceptions.Timeout:
        raise ProPublicaError(
            f"Request to ProPublica API timed out after {REQUEST_TIMEOUT[1]}s: {url}"
        )
    except requests.exceptions.RequestException as e:
        raise ProPublicaError(f"Unexpected request error: {e}") from e

    if response.status_code == 404:
        raise ProPublicaError(
            f"ProPublica returned 404 — resource not found: {url}",
            status_code=404,
        )
    if response.status_code == 429:
        raise ProPublicaError(
            "ProPublica API rate limit exceeded. Wait before retrying.",
            status_code=429,
        )
    if not response.ok:
        raise ProPublicaError(
            f"ProPublica API returned HTTP {response.status_code}: {url}",
            status_code=response.status_code,
        )

    try:
        return response.json()
    except ValueError as e:
        raise ProPublicaError(
            f"ProPublica API returned non-JSON response: {e}"
        ) from e


# ---------------------------------------------------------------------------
# Public API — Search
# ---------------------------------------------------------------------------

def search_organizations(
    query: str,
    state: str | None = None,
    page: int = 0,
) -> list[OrganizationSummary]:
    """
    Search for nonprofits by name or keyword.

    Args:
        query: Search term — org name, keyword, or partial name.
               Example: "Do Good Ministries"
        state: Optional two-letter state code to narrow results.
               Example: "OH"
        page:  Zero-indexed page number for pagination (25 results per page).

    Returns:
        List of OrganizationSummary objects. Empty list if no results found.

    Raises:
        ProPublicaError: On network failure or API error.

    Example:
        results = search_organizations("Do Good Ministries", state="OH")
        # [OrganizationSummary(ein=123456789, name='DO GOOD MINISTRIES INC', ...)]
    """
    if not query or not query.strip():
        raise ProPublicaError("Search query cannot be empty.")

    params: dict = {"q": query.strip(), "page": page}
    if state:
        params["state[id]"] = state.upper().strip()

    url = f"{BASE_URL}/search.json"
    logger.info("propublica_search query=%r state=%r page=%d", query, state, page)

    data = _get(url, params=params)

    organizations = data.get("organizations") or []
    results = []
    for org in organizations:
        try:
            results.append(OrganizationSummary(
                ein=int(org["ein"]),
                name=org.get("name") or "",
                city=org.get("city") or "",
                state=org.get("state") or "",
                ntee_code=org.get("ntee_code"),
                subsection=org.get("subsection_code"),
                exempt_status=_derive_exempt_status(org.get("subsection_code")),
            ))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("propublica_search: skipping malformed org record: %s — %r", e, org)

    logger.info("propublica_search: returned %d results", len(results))
    return results


# ---------------------------------------------------------------------------
# Public API — Organization profile
# ---------------------------------------------------------------------------

def fetch_organization(ein: int) -> OrganizationProfile:
    """
    Fetch the full IRS profile for an organization by EIN.

    Args:
        ein: IRS Employer Identification Number as an integer (no dashes).
             Example: 123456789

    Returns:
        OrganizationProfile with all available IRS metadata.

    Raises:
        ProPublicaError: On network failure, 404 (EIN not found), or API error.

    Example:
        profile = fetch_organization(123456789)
        print(profile.name, profile.ruling_date)
    """
    ein = _validate_ein(ein)
    url = f"{BASE_URL}/organizations/{ein}.json"
    logger.info("propublica_fetch_org ein=%d", ein)

    data = _get(url)
    org = data.get("organization") or {}

    if not org:
        raise ProPublicaError(
            f"ProPublica returned empty organization record for EIN {ein}.",
            ein=ein,
        )

    profile = OrganizationProfile(
        ein=int(org.get("ein", ein)),
        name=org.get("name") or "",
        city=org.get("city") or "",
        state=org.get("state") or "",
        ntee_code=org.get("ntee_code"),
        subsection=org.get("subsection_code"),
        exempt_status=_derive_exempt_status(org.get("subsection_code")),
        ruling_date=str(org["ruling"]) if org.get("ruling") else None,
        classification=str(org["classification_codes"]) if org.get("classification_codes") else None,
        foundation_code=str(org["foundation_code"]) if org.get("foundation_code") else None,
        activity_codes=str(org["activity_codes"]) if org.get("activity_codes") else None,
        deductibility=str(org["deductibility_code"]) if org.get("deductibility_code") else None,
        organization_raw=org,
    )

    logger.info("propublica_fetch_org: found %r (EIN %d)", profile.name, ein)
    return profile


# ---------------------------------------------------------------------------
# Public API — Filings list
# ---------------------------------------------------------------------------

def fetch_filings(ein: int) -> list[Filing]:
    """
    Fetch the list of available 990 filings for an organization.

    Returns both filings_with_data (structured financial data extracted by
    ProPublica) and filings_without_data (PDF links only, no extracted fields).
    All filings are returned in a single flat list, sorted by tax year descending
    (most recent first).

    Args:
        ein: IRS EIN as an integer.

    Returns:
        List of Filing objects. The pdf_url field on each Filing can be passed
        directly to Catalyst's document intake pipeline.

    Raises:
        ProPublicaError: On network failure, 404, or API error.

    Example:
        filings = fetch_filings(123456789)
        for f in filings:
            print(f.tax_year, f.form_type, f.total_revenue, f.pdf_url)
    """
    ein = _validate_ein(ein)
    url = f"{BASE_URL}/organizations/{ein}.json"
    logger.info("propublica_fetch_filings ein=%d", ein)

    data = _get(url)

    filings: list[Filing] = []

    # --- Filings with extracted financial data -------------------------------
    for raw in (data.get("filings_with_data") or []):
        try:
            filings.append(_parse_filing_with_data(raw))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(
                "propublica_fetch_filings: skipping malformed filing_with_data: %s — %r", e, raw
            )

    # --- Filings without extracted data (PDF links only) --------------------
    for raw in (data.get("filings_without_data") or []):
        try:
            filings.append(_parse_filing_without_data(raw))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(
                "propublica_fetch_filings: skipping malformed filing_without_data: %s — %r", e, raw
            )

    # Sort most recent first
    filings.sort(key=lambda f: f.tax_period, reverse=True)

    logger.info(
        "propublica_fetch_filings: EIN %d — %d filings (%d with data, %d without)",
        ein,
        len(filings),
        sum(1 for f in filings if f.total_revenue is not None),
        sum(1 for f in filings if f.total_revenue is None),
    )
    return filings


# ---------------------------------------------------------------------------
# Internal parsing helpers
# ---------------------------------------------------------------------------

def _parse_filing_with_data(raw: dict) -> Filing:
    """Parse a filing record from the filings_with_data list."""
    tax_period = int(raw["tax_prd"])
    tax_year = int(raw.get("tax_prd_yr") or str(tax_period)[:4])

    return Filing(
        tax_period=tax_period,
        tax_year=tax_year,
        form_type=str(raw.get("formtype") or "990"),
        pdf_url=raw.get("pdf_url") or None,
        total_revenue=_safe_float(raw.get("totrevenue")),
        total_expenses=_safe_float(raw.get("totfuncexpns")),
        total_assets_eoy=_safe_float(raw.get("totassetsend")),
        total_liabilities_eoy=_safe_float(raw.get("totliabend")),
        officer_compensation_pct=_safe_float(raw.get("pct_compnsatncurrofcr")),
        filing_raw=raw,
    )


def _parse_filing_without_data(raw: dict) -> Filing:
    """
    Parse a filing record from the filings_without_data list.
    These have a pdf_url and tax period but no extracted financial fields.
    """
    # filings_without_data uses different field names than filings_with_data
    tax_period = int(raw.get("tax_prd") or raw.get("taxperiod") or 0)
    tax_year = int(str(tax_period)[:4]) if tax_period else 0

    return Filing(
        tax_period=tax_period,
        tax_year=tax_year,
        form_type=str(raw.get("formtype") or raw.get("form_type") or "990"),
        pdf_url=raw.get("pdf_url") or None,
        filing_raw=raw,
    )


def _safe_float(value) -> float | None:
    """Convert a value to float, returning None if conversion fails or value is None."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _validate_ein(ein: int) -> int:
    """
    Validate that an EIN is a plausible integer.
    EINs are 9-digit numbers. We accept them with or without dashes and
    normalize to integer.
    """
    # Accept string EINs like "12-3456789" or "123456789"
    if isinstance(ein, str):
        ein = ein.replace("-", "").strip()
        try:
            ein = int(ein)
        except ValueError:
            raise ProPublicaError(f"Invalid EIN format: {ein!r}")

    if not isinstance(ein, int) or ein <= 0:
        raise ProPublicaError(f"EIN must be a positive integer, got: {ein!r}")

    return ein


def _derive_exempt_status(subsection_code: int | None) -> str | None:
    """
    Convert a numeric IRC subsection code to a human-readable exempt status string.
    ProPublica returns subsection_code as an integer (e.g., 3 for 501(c)(3)).
    """
    if subsection_code is None:
        return None
    _map = {
        3: "501(c)(3)",
        4: "501(c)(4)",
        5: "501(c)(5)",
        6: "501(c)(6)",
        7: "501(c)(7)",
        8: "501(c)(8)",
        9: "501(c)(9)",
        19: "501(c)(19)",
    }
    return _map.get(int(subsection_code), f"501(c)({subsection_code})")


# ---------------------------------------------------------------------------
# Convenience: fetch everything about an org in one call
# ---------------------------------------------------------------------------

def fetch_full_profile(ein: int, polite_delay: float = POLITE_DELAY) -> tuple[OrganizationProfile, list[Filing]]:
    """
    Convenience wrapper: fetch both the org profile and its filings in one call.

    Makes two API requests (one for profile, one already included in the same
    endpoint — so this is actually just one HTTP call under the hood, since
    filings come back in the same organization endpoint response).

    Args:
        ein:          IRS EIN as integer.
        polite_delay: Seconds to sleep after the call (default: POLITE_DELAY).
                      Set to 0 to disable in tests.

    Returns:
        (OrganizationProfile, list[Filing]) tuple.

    Raises:
        ProPublicaError: On any failure.
    """
    ein = _validate_ein(ein)
    url = f"{BASE_URL}/organizations/{ein}.json"
    logger.info("propublica_fetch_full_profile ein=%d", ein)

    data = _get(url)
    org_raw = data.get("organization") or {}

    if not org_raw:
        raise ProPublicaError(
            f"ProPublica returned empty organization record for EIN {ein}.",
            ein=ein,
        )

    profile = OrganizationProfile(
        ein=int(org_raw.get("ein", ein)),
        name=org_raw.get("name") or "",
        city=org_raw.get("city") or "",
        state=org_raw.get("state") or "",
        ntee_code=org_raw.get("ntee_code"),
        subsection=org_raw.get("subsection_code"),
        exempt_status=_derive_exempt_status(org_raw.get("subsection_code")),
        ruling_date=str(org_raw["ruling"]) if org_raw.get("ruling") else None,
        classification=str(org_raw["classification_codes"]) if org_raw.get("classification_codes") else None,
        foundation_code=str(org_raw["foundation_code"]) if org_raw.get("foundation_code") else None,
        activity_codes=str(org_raw["activity_codes"]) if org_raw.get("activity_codes") else None,
        deductibility=str(org_raw["deductibility_code"]) if org_raw.get("deductibility_code") else None,
        organization_raw=org_raw,
    )

    filings: list[Filing] = []
    for raw in (data.get("filings_with_data") or []):
        try:
            filings.append(_parse_filing_with_data(raw))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("fetch_full_profile: skipping filing: %s", e)

    for raw in (data.get("filings_without_data") or []):
        try:
            filings.append(_parse_filing_without_data(raw))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("fetch_full_profile: skipping filing: %s", e)

    filings.sort(key=lambda f: f.tax_period, reverse=True)

    if polite_delay > 0:
        time.sleep(polite_delay)

    return profile, filings
