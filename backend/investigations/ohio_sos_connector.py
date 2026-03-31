"""
Ohio Secretary of State Business Search connector for Catalyst.

Strategy: bulk file download + local search + staleness warning.

Why not a live scraper?
    The Ohio SOS business search portal (businesssearch.ohiosos.gov) is
    protected by Cloudflare bot detection. A requests-based scraper is blocked
    before it sees any HTML. A browser-automation scraper would be fragile and
    ethically murky for an investigative tool.

Why bulk files?
    The Ohio SOS publishes free monthly CSV exports of all new business filings
    and amendments at publicfiles.ohiosos.gov. These are:
        - Stable direct download URLs (no bot detection)
        - Updated on the second Saturday of each month
        - Sufficient for Catalyst's core use case: does this entity exist?
          When was it formed? Who is the statutory agent?

The staleness design (human-in-the-loop):
    Every search result is accompanied by a StalenessWarning that tells the
    investigator:
        - When the bulk file was downloaded
        - How many days ago that was
        - Whether to manually verify recent filings at businesssearch.ohiosos.gov

    This is intentional. The founding investigation found a deceased person's
    signature on a filing made 153 days after his death — that kind of anomaly
    requires human eyes on the actual filing documents. The staleness warning
    is the system's explicit reminder that automated data has a cutoff and
    human review is required for anything recent.

Future state:
    Multi-state support is planned for Phase 5. Each state connector should
    expose the same public interface (search_entities, fetch_report) so Catalyst
    can query them interchangeably. Ohio is the only state implemented now
    because the founding investigation is Ohio-based.

File URL reference (second Saturday of each month):
    New Nonprofit Corps:   https://publicfiles.ohiosos.gov/free/OnlineBusinessReports/WI0070R.TXT
    New For-Profit Corps:  https://publicfiles.ohiosos.gov/free/OnlineBusinessReports/WI0050R.TXT
    New LLCs (Domestic):   https://publicfiles.ohiosos.gov/free/OnlineBusinessReports/WI0100R.TXT
    New LLCs (Foreign):    https://publicfiles.ohiosos.gov/free/OnlineBusinessReports/WI0090R.TXT
    New LPs (Domestic):    https://publicfiles.ohiosos.gov/free/OnlineBusinessReports/WI0120R.TXT
    Amendments:            https://publicfiles.ohiosos.gov/free/OnlineBusinessReports/WI0250R.TXT
    Dissolutions:          https://publicfiles.ohiosos.gov/free/OnlineBusinessReports/WI0220R.TXT
    Reinstatements:        https://publicfiles.ohiosos.gov/free/OnlineBusinessReports/WI0240R.TXT

Usage:
    from investigations.ohio_sos_connector import (
        fetch_report,
        search_entities,
        load_reports,
        OhioSOSError,
        ReportType,
    )

    # Download and search nonprofit corps filed this month
    records = fetch_report(ReportType.NONPROFIT_CORPS)
    results = search_entities("Example Charity Ministries", records)
    for r in results.matches:
        print(r.charter_number, r.business_name, r.effective_date)
    print(results.staleness_warning)

    # Or load multiple report types at once and search across all
    all_records = load_reports([ReportType.NONPROFIT_CORPS, ReportType.LLC_DOMESTIC])
    results = search_entities("Example Charity", all_records)
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://publicfiles.ohiosos.gov/free/OnlineBusinessReports"

REQUEST_TIMEOUT = (5, 60)  # connect, read — files can be large

HEADERS = {
    "User-Agent": "Catalyst/2.0 (Intelligence Triage Platform; investigative use)",
    "Accept": "text/plain,text/csv,*/*",
}

# Staleness thresholds (days since file was downloaded)
STALENESS_LOW_DAYS = 7  # informational — file is reasonably fresh
STALENESS_MEDIUM_DAYS = 21  # review recommended — over 3 weeks old
# anything above STALENESS_MEDIUM_DAYS is HIGH

MANUAL_SEARCH_URL = "https://businesssearch.ohiosos.gov"


# ---------------------------------------------------------------------------
# Report type enum
# ---------------------------------------------------------------------------


class ReportType(Enum):
    """
    Available Ohio SOS monthly bulk report types.

    Each value is the filename on publicfiles.ohiosos.gov.
    New reports are generated on the second Saturday of each month.
    """

    # New entity filings
    FOREIGN_CORP_FORPROFIT = "WI0010R.TXT"
    FOREIGN_CORP_NONPROFIT = "WI0030R.TXT"
    FOREIGN_CORP_PROFESSIONAL = "WI0040R.TXT"
    CORP_FORPROFIT = "WI0050R.TXT"
    NONPROFIT_CORPS = "WI0070R.TXT"  # most relevant for Catalyst
    CORP_PROFESSIONAL = "WI0080R.TXT"
    LLC_FOREIGN = "WI0090R.TXT"
    LLC_DOMESTIC = "WI0100R.TXT"  # most relevant for Catalyst
    LP_FOREIGN = "WI0110R.TXT"
    LP_DOMESTIC = "WI0120R.TXT"

    # Amendment reports
    MERGERS = "WI0210R.TXT"
    DISSOLUTIONS = "WI0220R.TXT"
    SOS_CANCELLATIONS = "WI0230R.TXT"
    REINSTATEMENTS = "WI0240R.TXT"
    AMENDMENTS = "WI0250R.TXT"  # most relevant for Catalyst

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.value}"

    @property
    def is_amendment(self) -> bool:
        """True for amendment/dissolution/reinstatement reports; False for new entity reports."""
        return self.value.startswith("WI02")


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class OhioSOSError(Exception):
    """
    Raised when the Ohio SOS connector cannot complete an operation.

    Attributes:
        message:     Human-readable description.
        status_code: HTTP status if the error came from a download (or None).
        report_type: The ReportType being fetched when the error occurred (or None).
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        report_type: ReportType | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.report_type = report_type


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EntityRecord:
    """
    A single entity record parsed from an Ohio SOS bulk report file.

    Fields present in ALL report types:
        document_number:   Ohio SOS document/filing number
        charter_number:    Unique entity identifier (called "Charter Number" for
                           corps, "Registration Number" for LLCs/LPs)
        effective_date:    Date the filing became effective (date object or None)
        business_name:     Entity name as registered
        transaction_type:  Filing type description (e.g., "DOMESTIC ARTICLES/NON-PROFIT")
        filing_city:       City from the filer's address
        filing_state:      State from the filer's address
        county:            Ohio county (present in new entity reports)
        report_type:       The ReportType this record came from
        downloaded_at:     When the bulk file was downloaded (UTC datetime)

    Fields present in NEW ENTITY reports only:
        statutory_agent:   Name of the registered statutory agent
        agent_city:        Agent's city
        agent_state:       Agent's state
        business_city:     City where the business operates
        associate_names:   Incorporator/associate names (pipe-separated in raw data)

    Fields present in AMENDMENT reports only:
        (amendment reports have fewer fields — agent info is not included)
    """

    # Core fields (all report types)
    document_number: str
    charter_number: str
    effective_date: date | None
    business_name: str
    transaction_type: str
    filing_city: str
    filing_state: str
    county: str
    report_type: ReportType
    downloaded_at: datetime

    # New entity report fields (None for amendment records)
    statutory_agent: str | None = None
    agent_city: str | None = None
    agent_state: str | None = None
    business_city: str | None = None
    associate_names: str | None = None


@dataclass
class StalenessWarning:
    """
    Communicates to the investigator that bulk file data has a cutoff date
    and manual verification may be needed for recent filings.

    This is the human-in-the-loop prompt built into every search result.
    It is always returned — even for fresh data — so the investigator is
    never under the impression that the data is comprehensive or real-time.

    Attributes:
        downloaded_at:    When the bulk file was fetched (UTC datetime).
        days_old:         How many days ago the file was downloaded.
        level:            "LOW", "MEDIUM", or "HIGH" based on age thresholds.
        message:          Human-readable warning text for display.
        manual_search_url: URL for manual verification.
    """

    downloaded_at: datetime
    days_old: int
    level: str  # "LOW", "MEDIUM", "HIGH"
    message: str
    manual_search_url: str = MANUAL_SEARCH_URL

    def __str__(self) -> str:
        return self.message


@dataclass
class SearchResult:
    """
    Return value from search_entities().

    Attributes:
        matches:          List of EntityRecord objects matching the query.
        query:            The search string that was used.
        total_searched:   Total number of records searched across all loaded reports.
        staleness_warning: Always present — the human-in-the-loop reminder.
    """

    matches: list[EntityRecord]
    query: str
    total_searched: int
    staleness_warning: StalenessWarning


# ---------------------------------------------------------------------------
# Internal: CSV parsing
# ---------------------------------------------------------------------------

# Column names as they appear in the actual Ohio SOS TXT files.
# Confirmed by inspecting the live files.
_NEW_ENTITY_COLUMNS = [
    "DOCUMENT NUMBER",
    "CHARTER NUMBER",
    "EFFECTIVE DATE",
    "BUSINESS NAME",
    "CONSENT FLAG",
    "TRANSACTION CODE DESCRIPTION",
    "FILING ADDRESS NAME",
    "FILING ADDRESS 1",
    "FILING ADDRESS 2",
    "FILING CITY",
    "FILING STATE",
    "FILING ZIP",
    "AGENT ADDRESS NAME",
    "AGENT ADDRESS 1",
    "AGENT ADDRESS 2",
    "AGENT CITY",
    "AGENT STATE",
    "AGENT ZIP",
    "BUSINESS CITY",
    "COUNTY",
    "BUSINESS ASSOCIATE NAMES",
]

_AMENDMENT_COLUMNS = [
    "DOCUMENT NUMBER",
    "CHARTER NUMBER",
    "EFFECTIVE DATE",
    "BUSINESS NAME",
    "TRANSASCTION CODE DESCRIPTION",  # note: typo in Ohio SOS header is intentional
    "FILING ADDRESS NAME",
    "FILING ADDRESS 1",
    "FILING ADDRESS 2",
    "FILING CITY",
    "FILING STATE",
    "FILING ZIP",
    "BUSINESS CITY",
    "COUNTY NAME",
]


def _parse_date(raw: str) -> date | None:
    """Parse MM/DD/YYYY date strings from Ohio SOS files. Returns None on failure."""
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    logger.warning("ohio_sos: could not parse date %r", raw)
    return None


def _parse_records(
    text: str,
    report_type: ReportType,
    downloaded_at: datetime,
) -> list[EntityRecord]:
    """
    Parse raw CSV text from an Ohio SOS bulk file into EntityRecord objects.

    Handles both new entity report format and amendment report format.
    Skips rows that don't parse cleanly rather than raising — bulk files
    occasionally contain malformed rows.
    """
    records: list[EntityRecord] = []
    reader = csv.DictReader(io.StringIO(text))

    is_amendment = report_type.is_amendment

    for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        try:
            # Normalize keys — strip whitespace, handle the typo in amendment headers
            row = {k.strip(): v.strip() for k, v in row.items() if k}

            # Handle the typo: "TRANSASCTION" vs "TRANSACTION"
            tx_desc = (
                row.get("TRANSACTION CODE DESCRIPTION")
                or row.get("TRANSASCTION CODE DESCRIPTION")
                or ""
            )

            county = row.get("COUNTY") or row.get("COUNTY NAME") or ""

            effective_date = _parse_date(row.get("EFFECTIVE DATE", ""))

            if is_amendment:
                record = EntityRecord(
                    document_number=row.get("DOCUMENT NUMBER", ""),
                    charter_number=row.get("CHARTER NUMBER", ""),
                    effective_date=effective_date,
                    business_name=row.get("BUSINESS NAME", ""),
                    transaction_type=tx_desc,
                    filing_city=row.get("FILING CITY", ""),
                    filing_state=row.get("FILING STATE", ""),
                    county=county,
                    report_type=report_type,
                    downloaded_at=downloaded_at,
                    # Amendment reports don't include agent info
                    statutory_agent=None,
                    agent_city=None,
                    agent_state=None,
                    business_city=row.get("BUSINESS CITY", ""),
                    associate_names=None,
                )
            else:
                record = EntityRecord(
                    document_number=row.get("DOCUMENT NUMBER", ""),
                    charter_number=row.get("CHARTER NUMBER", ""),
                    effective_date=effective_date,
                    business_name=row.get("BUSINESS NAME", ""),
                    transaction_type=tx_desc,
                    filing_city=row.get("FILING CITY", ""),
                    filing_state=row.get("FILING STATE", ""),
                    county=county,
                    report_type=report_type,
                    downloaded_at=downloaded_at,
                    statutory_agent=row.get("AGENT ADDRESS NAME") or None,
                    agent_city=row.get("AGENT CITY") or None,
                    agent_state=row.get("AGENT STATE") or None,
                    business_city=row.get("BUSINESS CITY") or None,
                    associate_names=row.get("BUSINESS ASSOCIATE NAMES") or None,
                )

            if record.business_name:  # skip completely empty rows
                records.append(record)

        except Exception as e:
            logger.warning(
                "ohio_sos: skipping malformed row %d in %s: %s",
                row_num,
                report_type.value,
                e,
            )

    return records


# ---------------------------------------------------------------------------
# Internal: staleness calculation
# ---------------------------------------------------------------------------


def _build_staleness_warning(downloaded_at: datetime) -> StalenessWarning:
    """
    Build a StalenessWarning based on how old the downloaded file is.

    The warning is tiered:
        LOW    (< 7 days):  file is reasonably fresh, informational note only
        MEDIUM (7-21 days): approaching next monthly update, review recommended
        HIGH   (> 21 days): file is stale — manual verification strongly advised
    """
    now = datetime.now(tz=timezone.utc)
    if downloaded_at.tzinfo is None:
        downloaded_at = downloaded_at.replace(tzinfo=timezone.utc)

    days_old = (now - downloaded_at).days
    date_str = downloaded_at.strftime("%B %d, %Y")

    if days_old < STALENESS_LOW_DAYS:
        level = "LOW"
        message = (
            f"Data from Ohio SOS bulk file downloaded {date_str} ({days_old} days ago). "
            f"File is reasonably current. Any filings after {date_str} will not appear here. "
            f"Manual verification: {MANUAL_SEARCH_URL}"
        )
    elif days_old <= STALENESS_MEDIUM_DAYS:
        level = "MEDIUM"
        message = (
            f"Data from Ohio SOS bulk file downloaded {date_str} ({days_old} days ago). "
            f"A newer monthly file may be available. Filings after {date_str} are not captured. "
            f"RECOMMENDED: Manually verify recent activity at {MANUAL_SEARCH_URL}"
        )
    else:
        level = "HIGH"
        message = (
            f"DATA MAY BE STALE — Ohio SOS bulk file downloaded {date_str} ({days_old} days ago). "
            f"Ohio SOS publishes new files on the second Saturday of each month. "
            f"This file is more than {STALENESS_MEDIUM_DAYS} days old. "
            f"Any filings, amendments, or dissolutions since {date_str} are NOT reflected here. "
            f"MANUAL VERIFICATION REQUIRED: {MANUAL_SEARCH_URL}"
        )

    return StalenessWarning(
        downloaded_at=downloaded_at,
        days_old=days_old,
        level=level,
        message=message,
    )


# ---------------------------------------------------------------------------
# Public API — Fetch a single report
# ---------------------------------------------------------------------------


def fetch_report(report_type: ReportType) -> list[EntityRecord]:
    """
    Download and parse a single Ohio SOS monthly bulk report.

    Makes one HTTP GET request to publicfiles.ohiosos.gov and parses the
    returned CSV into a list of EntityRecord objects. The download timestamp
    is captured and stored on every record — this is what drives the
    staleness warning in search results.

    Args:
        report_type: A ReportType enum value specifying which file to download.

    Returns:
        List of EntityRecord objects parsed from the file.
        Empty list if the file is empty or contains no valid rows.

    Raises:
        OhioSOSError: On network failure, timeout, or non-200 response.

    Example:
        records = fetch_report(ReportType.NONPROFIT_CORPS)
        print(f"Downloaded {len(records)} nonprofit filings")
    """
    url = report_type.url
    logger.info("ohio_sos_fetch: downloading %s from %s", report_type.name, url)

    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ConnectionError as e:
        raise OhioSOSError(
            f"Could not connect to Ohio SOS file server: {e}",
            report_type=report_type,
        ) from e
    except requests.exceptions.Timeout:
        raise OhioSOSError(
            f"Download timed out after {REQUEST_TIMEOUT[1]}s: {url}",
            report_type=report_type,
        )
    except requests.exceptions.RequestException as e:
        raise OhioSOSError(
            f"Unexpected error downloading {url}: {e}",
            report_type=report_type,
        ) from e

    if not response.ok:
        raise OhioSOSError(
            f"Ohio SOS file server returned HTTP {response.status_code}: {url}",
            status_code=response.status_code,
            report_type=report_type,
        )

    downloaded_at = datetime.now(tz=timezone.utc)

    # Try UTF-8 first; fall back to latin-1 which handles most Windows-1252 artifacts
    try:
        text = response.content.decode("utf-8")
    except UnicodeDecodeError:
        text = response.content.decode("latin-1")

    records = _parse_records(text, report_type, downloaded_at)
    logger.info(
        "ohio_sos_fetch: parsed %d records from %s",
        len(records),
        report_type.name,
    )
    return records


# ---------------------------------------------------------------------------
# Public API — Load multiple reports
# ---------------------------------------------------------------------------


def load_reports(report_types: list[ReportType]) -> list[EntityRecord]:
    """
    Download and parse multiple Ohio SOS report types, returning a combined
    flat list of all records.

    Useful for searching across entity types in a single call. For example,
    loading both NONPROFIT_CORPS and LLC_DOMESTIC gives you all new Ohio
    nonprofits and LLCs filed in the current monthly window.

    Args:
        report_types: List of ReportType values to download.

    Returns:
        Combined list of EntityRecord objects from all requested report types.
        Reports that fail to download are logged and skipped — the function
        returns whatever it successfully fetched.

    Example:
        records = load_reports([ReportType.NONPROFIT_CORPS, ReportType.LLC_DOMESTIC])
        print(f"Loaded {len(records)} total records across 2 report types")
    """
    all_records: list[EntityRecord] = []
    for report_type in report_types:
        try:
            records = fetch_report(report_type)
            all_records.extend(records)
        except OhioSOSError as e:
            logger.error(
                "ohio_sos_load_reports: failed to fetch %s: %s",
                report_type.name,
                e,
            )
    return all_records


# ---------------------------------------------------------------------------
# Public API — Search
# ---------------------------------------------------------------------------


def search_entities(
    query: str,
    records: list[EntityRecord],
    *,
    fuzzy: bool = False,
) -> SearchResult:
    """
    Search a list of EntityRecord objects by business name.

    Two matching modes:
        Exact (default): case-insensitive substring match.
            "example charity" matches "EXAMPLE CHARITY MINISTRIES INC"
            Fast, predictable, no false positives.

        Fuzzy (opt-in): uses entity_normalization.normalize_org_name() to
            strip legal designators before comparing. Catches:
            "Example Charity Ministries" matching "EXAMPLE CHARITY MINISTRIES INC"
            Slightly slower on large datasets.

    A StalenessWarning is always included in the result. It is derived from
    the most recent downloaded_at timestamp in the records list, which means
    the warning accurately reflects when the data was actually pulled.

    Args:
        query:   Name or partial name to search for.
        records: List of EntityRecord objects (from fetch_report or load_reports).
        fuzzy:   If True, normalize both query and record names before comparing.

    Returns:
        SearchResult with matches, total searched count, and staleness warning.

    Raises:
        OhioSOSError: If query is empty or records is empty.

    Example:
        records = fetch_report(ReportType.NONPROFIT_CORPS)
        result = search_entities("Example Charity Ministries", records)
        for match in result.matches:
            print(match.charter_number, match.business_name)
        print(result.staleness_warning)
    """
    if not query or not query.strip():
        raise OhioSOSError("Search query cannot be empty.")

    if not records:
        raise OhioSOSError("No records to search. Call fetch_report() or load_reports() first.")

    query = query.strip()

    # Determine most recent download time for the staleness warning
    most_recent_download = max(r.downloaded_at for r in records)
    staleness_warning = _build_staleness_warning(most_recent_download)

    if fuzzy:
        from .entity_normalization import normalize_org_name

        normalized_query = normalize_org_name(query)
        matches = [r for r in records if normalized_query in normalize_org_name(r.business_name)]
    else:
        query_lower = query.lower()
        matches = [r for r in records if query_lower in r.business_name.lower()]

    logger.info(
        "ohio_sos_search: query=%r fuzzy=%s — %d/%d matches",
        query,
        fuzzy,
        len(matches),
        len(records),
    )

    return SearchResult(
        matches=matches,
        query=query,
        total_searched=len(records),
        staleness_warning=staleness_warning,
    )


# ---------------------------------------------------------------------------
# Convenience: the two most useful report types for Catalyst investigations
# ---------------------------------------------------------------------------

# These are the report types that cover the entities most likely to appear
# in a Catalyst investigation based on the founding Example Charity Inc. case:
#   - Nonprofits (Example Charity Ministries, Example Example Example Example Veterans Center)
#   - Domestic LLCs (Example Charity RE LLC, Example Hmains LLP)
#   - Amendments (changes in officers, registered agents, addresses)

CATALYST_DEFAULT_REPORTS = [
    ReportType.NONPROFIT_CORPS,
    ReportType.LLC_DOMESTIC,
    ReportType.AMENDMENTS,
    ReportType.CORP_FORPROFIT,
]


def search_ohio(
    query: str,
    report_types: list[ReportType] | None = None,
    fuzzy: bool = False,
) -> SearchResult:
    """
    One-call convenience function: download the default report types and
    search across all of them.

    This is the simplest way to use the connector for a typical Catalyst
    investigation workflow. It downloads fresh data on every call.

    Args:
        query:        Entity name or partial name to search for.
        report_types: Which report types to include. Defaults to
                      CATALYST_DEFAULT_REPORTS (nonprofits, LLCs, amendments,
                      for-profit corps).
        fuzzy:        Whether to use normalized fuzzy matching.

    Returns:
        SearchResult with matches and staleness warning.

    Example:
        result = search_ohio("Example Charity Ministries")
        for match in result.matches:
            print(match.charter_number, match.business_name, match.effective_date)
        print(result.staleness_warning)
    """
    if report_types is None:
        report_types = CATALYST_DEFAULT_REPORTS

    records = load_reports(report_types)
    return search_entities(query, records, fuzzy=fuzzy)
