"""
IRS Tax Exempt Organization connector for Catalyst.

Strategy: bulk file download + local search + staleness warning.

Two data sources, both free and publicly available from the IRS:

    1. Publication 78 (Pub78)
       File: https://apps.irs.gov/pub/epostcard/data-download-pub78.zip
       Format: pipe-delimited text (EIN|Name|City|State|Country|DeductibilityCode)
       Contents: Every organization currently eligible to receive tax-deductible
       charitable contributions. Updated monthly.
       Use case: "Is this org currently deductibility-eligible?"

    2. Exempt Organizations Business Master File (EO BMF)
       Files: https://www.irs.gov/pub/irs-soi/eo1.csv through eo4.csv (by region)
             plus eo_xx.csv per state (e.g., eo_oh.csv for Ohio)
       Format: CSV with ~30 columns
       Contents: All organizations that have received an IRS determination of
       tax-exempt status — active, revoked, and terminated. Includes ruling date,
       NTEE code, filing requirement, subsection, and exemption status.
       Use case: EIN lookup, exemption history, formation timeline.

Why bulk files instead of the TEOS web API?
    The IRS Tax Exempt Organization Search (TEOS) web interface at
    apps.irs.gov/app/eos/ does not expose a documented public REST API.
    The bulk downloads are the official IRS-supported programmatic access method.
    They are stable, free, and require no authentication.

The staleness design (human-in-the-loop):
    Every search result is accompanied by a StalenessWarning that tells the
    investigator when the data was downloaded and whether manual verification
    at apps.irs.gov/app/eos/ is advisable for anything time-sensitive.

    This matters in practice: the founding investigation found a nonprofit
    whose tax-exempt status was relevant to a filing date discrepancy.
    Knowing when an exemption was *granted* versus when a transaction occurred
    is investigatively significant — but bulk files are only as current as
    their last download date.

EO BMF column reference (selected fields):
    EIN                Employer Identification Number (9 digits, no dashes)
    NAME               Organization name
    ICO                In care of name
    STREET             Street address
    CITY               City
    STATE              State abbreviation
    ZIP                ZIP code
    GROUP              Group exemption number
    SUBSECTION         IRC subsection code (3 = 501(c)(3), etc.)
    AFFILIATION        Affiliation code
    CLASSIFICATION     Classification code
    RULING             Ruling date (YYYYMM)
    DEDUCTIBILITY      Deductibility code
    FOUNDATION         Foundation code
    ACTIVITY           Activity codes
    ORGANIZATION       Organization type code
    STATUS             Exemption status code (1=Unconditional, 2=Conditional,
                       6=Church, 7=Government, 12=Revoked)
    TAX_PERIOD         Tax period (YYYYMM) of most recent return filed
    ASSET_CD           Asset code (financial size range)
    INCOME_CD          Income code (revenue size range)
    FILING_REQ_CD      Filing requirement code
    PF_FILING_REQ_CD   Private foundation filing requirement code
    ACCT_PD            Accounting period (month, 1-12)
    ASSET_AMT          Total assets (most recent 990)
    INCOME_AMT         Total income (most recent 990)
    REVENUE_AMT        Total revenue (most recent 990)
    NTEE_CD            NTEE classification code
    SORT_NAME          Sort name / DBA name

EO BMF regional file URLs:
    eo1.csv — northeast states (CT, ME, MA, NH, NJ, NY, PA, RI, VT)
    eo2.csv — mid-Atlantic and southeast (DC, DE, FL, GA, MD, NC, SC, VA, WV, + more)
    eo3.csv — midwest (IL, IN, MI, MN, OH, WI, + more)
    eo4.csv — west and south (AL, AK, AR, AZ, CA, CO, + more)

    State-specific files: eo_oh.csv, eo_il.csv, etc. (lowercase two-letter codes)
    These are subsets of the regional files, included for convenience.

Usage:
    from investigations.irs_connector import (
        fetch_pub78,
        fetch_eo_bmf,
        search_pub78,
        search_eo_bmf,
        lookup_ein,
        IRSError,
        EoBmfRegion,
    )

    # Quick deductibility check by name (Pub78)
    records = fetch_pub78()
    results = search_pub78("Example Charity Ministries", records, state="OH")
    for r in results.matches:
        print(r.ein, r.name, r.deductibility_code)
    print(results.staleness_warning)

    # Full EIN lookup from EO BMF (midwest / Ohio)
    bmf_records = fetch_eo_bmf(EoBmfRegion.MIDWEST)
    result = lookup_ein(123456789, bmf_records)
    if result:
        print(result.name, result.subsection, result.ruling_date, result.status_description)
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pub78 bulk download — pipe-delimited text inside a zip file.
PUB78_URL = "https://apps.irs.gov/pub/epostcard/data-download-pub78.zip"

# EO BMF regional CSV files — full master file split by geography.
EO_BMF_BASE_URL = "https://www.irs.gov/pub/irs-soi"

# Timeout for all HTTP requests (connect, read) in seconds.
REQUEST_TIMEOUT = (10, 60)

# User-Agent so the IRS can identify Catalyst traffic.
HEADERS = {
    "User-Agent": "Catalyst/2.0 (Intelligence Triage Platform; contact: investigator)",
    "Accept": "*/*",
}

# Staleness thresholds (days). Same tier system as Ohio SOS connector.
STALENESS_LOW_DAYS = 7
STALENESS_HIGH_DAYS = 21

# EO BMF status codes → human-readable description.
_BMF_STATUS_MAP = {
    "1": "Unconditional Exemption",
    "2": "Conditional Exemption",
    "6": "Church — 508(c)(1)(A) exemption",
    "7": "Government instrumentality",
    "12": "Revoked",
    "19": "Exempt under 501(c)(3) — private foundation",
    "22": "Exempt under 501(c)(3) — public charity",
    "25": "Exempt under 501(c)(3) — supporting organization",
}

# EO BMF subsection codes → human-readable IRC section.
_BMF_SUBSECTION_MAP = {
    "2": "501(c)(2)",
    "3": "501(c)(3)",
    "4": "501(c)(4)",
    "5": "501(c)(5)",
    "6": "501(c)(6)",
    "7": "501(c)(7)",
    "8": "501(c)(8)",
    "9": "501(c)(9)",
    "10": "501(c)(10)",
    "13": "501(c)(13)",
    "14": "501(c)(14)",
    "19": "501(c)(19)",
    "92": "501(e)",
    "93": "501(f)",
}

# EO BMF deductibility codes.
_BMF_DEDUCTIBILITY_MAP = {
    "1": "Contributions are deductible",
    "2": "Contributions are not deductible",
    "4": "Contributions are deductible by treaty (foreign orgs)",
}


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class IRSError(Exception):
    """
    Raised when the IRS connector cannot complete a request.

    Attributes:
        message:     Human-readable description of what went wrong.
        status_code: HTTP status code if the error came from HTTP (or None).
        ein:         The EIN being looked up, if applicable (or None).
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        ein: int | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.ein = ein


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EoBmfRegion(Enum):
    """
    IRS EO BMF regional file identifiers.

    The IRS splits the master file into four regional CSV files.
    Each value is the filename suffix used in the download URL.

    NORTHEAST:  eo1.csv — CT, ME, MA, NH, NJ, NY, PA, RI, VT + territories
    SOUTHEAST:  eo2.csv — DC, DE, FL, GA, MD, NC, SC, VA, WV + more
    MIDWEST:    eo3.csv — IL, IN, MI, MN, OH, WI + more  ← use for Ohio
    SOUTH_WEST: eo4.csv — AL, AK, AR, AZ, CA, CO, HI, ID, + more

    STATE_OH:   eo_oh.csv — Ohio only (subset of MIDWEST, smaller download)
    """

    NORTHEAST = "eo1.csv"
    SOUTHEAST = "eo2.csv"
    MIDWEST = "eo3.csv"
    SOUTH_WEST = "eo4.csv"
    STATE_OH = "eo_oh.csv"
    STATE_IL = "eo_il.csv"
    STATE_IN = "eo_in.csv"
    STATE_MI = "eo_mi.csv"
    STATE_KY = "eo_ky.csv"
    STATE_PA = "eo_pa.csv"
    STATE_WV = "eo_wv.csv"

    @property
    def url(self) -> str:
        return f"{EO_BMF_BASE_URL}/{self.value}"


# ---------------------------------------------------------------------------
# Staleness warning
# ---------------------------------------------------------------------------


class StalenessLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class StalenessWarning:
    """
    Always returned alongside search results.

    Tells the investigator how fresh the underlying bulk file is and whether
    manual verification at apps.irs.gov/app/eos/ is advisable.

    Attributes:
        downloaded_at:  UTC datetime when the bulk file was downloaded.
        days_old:       How many days ago that was (relative to now UTC).
        level:          LOW (<7 days), MEDIUM (7-21 days), HIGH (>21 days).
        message:        Human-readable advisory string.
    """

    downloaded_at: datetime
    days_old: int
    level: StalenessLevel
    message: str

    def __str__(self) -> str:
        return self.message

    @classmethod
    def from_download_time(cls, downloaded_at: datetime) -> "StalenessWarning":
        now = datetime.now(tz=timezone.utc)
        # Make sure both are timezone-aware before subtracting
        if downloaded_at.tzinfo is None:
            downloaded_at = downloaded_at.replace(tzinfo=timezone.utc)
        days_old = (now - downloaded_at).days

        if days_old < STALENESS_LOW_DAYS:
            level = StalenessLevel.LOW
            advisory = "Data is recent. Manual verification optional for time-sensitive matters."
        elif days_old <= STALENESS_HIGH_DAYS:
            level = StalenessLevel.MEDIUM
            advisory = "Data is moderately aged. Verify current status at apps.irs.gov/app/eos/ for active investigations."
        else:
            level = StalenessLevel.HIGH
            advisory = (
                "WARNING — DATA IS STALE. IRS bulk files are updated monthly. "
                "This data is over 21 days old. Manually verify all findings at "
                "apps.irs.gov/app/eos/ before relying on exemption status or deductibility."
            )

        message = (
            f"[IRS Bulk Data] Downloaded {downloaded_at.strftime('%Y-%m-%d %H:%M UTC')} "
            f"({days_old} day{'s' if days_old != 1 else ''} ago). "
            f"Staleness: {level.value}. {advisory}"
        )
        return cls(
            downloaded_at=downloaded_at,
            days_old=days_old,
            level=level,
            message=message,
        )


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Pub78Record:
    """
    A single record from IRS Publication 78 (deductibility-eligible orgs).

    This is a lightweight record — it tells you the org is eligible to receive
    deductible contributions and what type of deductibility applies. It does NOT
    contain ruling dates, NTEE codes, or financial data. Use EoBmfRecord for that.

    Attributes:
        ein:               IRS EIN as integer (no dashes).
        name:              Organization name as it appears in IRS records.
        city:              City of the organization's registered address.
        state:             Two-letter state code (e.g., "OH"). Empty for foreign orgs.
        country:           Country code. "US" for domestic orgs.
        deductibility_code: IRS deductibility code. "1" = deductible.
        deductibility_description: Human-readable description of deductibility code.
    """

    ein: int
    name: str
    city: str
    state: str
    country: str
    deductibility_code: str
    deductibility_description: str


@dataclass
class EoBmfRecord:
    """
    A single record from the IRS Exempt Organizations Business Master File.

    This is the authoritative IRS record for an exempt organization. It contains
    everything Catalyst needs: formation date (ruling), current status, exemption
    type, and financial size indicators.

    Attributes:
        ein:              IRS EIN as integer.
        name:             Organization name.
        city:             City.
        state:            State abbreviation.
        zip_code:         ZIP code.
        subsection:       IRC subsection code string (e.g., "3" for 501(c)(3)).
        subsection_description: Human-readable IRC section (e.g., "501(c)(3)").
        ruling_date:      Date IRS ruling was issued, as "YYYYMM" string.
                          This is the *exemption grant date* — critical for
                          SR-002 (entity named in a document before it existed).
        ruling_year:      Four-digit ruling year (int) or None.
        ruling_month:     Two-digit ruling month (int) or None.
        status_code:      IRS exemption status code string.
        status_description: Human-readable status (e.g., "Unconditional Exemption").
        is_revoked:       True if status_code == "12" (revoked).
        deductibility_code: Deductibility code.
        deductibility_description: Human-readable deductibility.
        ntee_code:        National Taxonomy of Exempt Entities code (e.g., "B99").
        foundation_code:  IRS foundation status code.
        filing_req_code:  Filing requirement code.
        tax_period:       Tax period (YYYYMM) of most recent filed return.
        asset_amount:     Total assets from most recent 990 (int or None).
        income_amount:    Total income from most recent 990 (int or None).
        revenue_amount:   Total revenue from most recent 990 (int or None).
        sort_name:        DBA / sort name if different from legal name.
        raw:              The full raw CSV row as a dict.
    """

    ein: int
    name: str
    city: str
    state: str
    zip_code: str
    subsection: str
    subsection_description: str
    ruling_date: str | None
    ruling_year: int | None
    ruling_month: int | None
    status_code: str
    status_description: str
    is_revoked: bool
    deductibility_code: str
    deductibility_description: str
    ntee_code: str | None
    foundation_code: str | None
    filing_req_code: str | None
    tax_period: str | None
    asset_amount: int | None
    income_amount: int | None
    revenue_amount: int | None
    sort_name: str | None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Pub78SearchResult:
    """Returned by search_pub78(). Always includes a staleness warning."""

    matches: list[Pub78Record]
    query: str
    total_searched: int
    staleness_warning: StalenessWarning


@dataclass
class EoBmfSearchResult:
    """Returned by search_eo_bmf(). Always includes a staleness warning."""

    matches: list[EoBmfRecord]
    query: str
    total_searched: int
    staleness_warning: StalenessWarning


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------


def _download(url: str) -> bytes:
    """
    Download a file from the given URL and return the raw bytes.
    Raises IRSError on network failure or non-200 HTTP status.
    """
    logger.info("irs_connector: downloading %s", url)
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            stream=True,
        )
    except requests.exceptions.ConnectionError as e:
        raise IRSError(f"Could not connect to IRS data server: {e}") from e
    except requests.exceptions.Timeout:
        raise IRSError(f"Request to IRS timed out after {REQUEST_TIMEOUT[1]}s: {url}")
    except requests.exceptions.RequestException as e:
        raise IRSError(f"Unexpected request error fetching {url}: {e}") from e

    if response.status_code == 404:
        raise IRSError(
            f"IRS data file not found (404): {url}",
            status_code=404,
        )
    if not response.ok:
        raise IRSError(
            f"IRS server returned HTTP {response.status_code}: {url}",
            status_code=response.status_code,
        )

    content = response.content
    logger.info("irs_connector: downloaded %s (%.1f KB)", url, len(content) / 1024)
    return content


# ---------------------------------------------------------------------------
# Pub78 — fetch and parse
# ---------------------------------------------------------------------------


def fetch_pub78(url: str = PUB78_URL) -> tuple[list[Pub78Record], StalenessWarning]:
    """
    Download and parse the IRS Publication 78 bulk data file.

    The Pub78 file is a zip archive containing a pipe-delimited text file.
    Fields: EIN | Name | City | State | Country | DeductibilityCode

    Args:
        url: Override the default Pub78 download URL (useful for testing).

    Returns:
        (records, staleness_warning) tuple where records is a list of
        Pub78Record objects and staleness_warning reflects the download time.

    Raises:
        IRSError: On network failure, bad HTTP status, or parse error.

    Example:
        records, warning = fetch_pub78()
        print(f"Loaded {len(records)} Pub78 records. {warning}")
    """
    raw_bytes = _download(url)
    downloaded_at = datetime.now(tz=timezone.utc)

    # Pub78 is delivered as a .zip containing a single pipe-delimited .txt file.
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            # Find the text file inside the zip
            txt_names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            if not txt_names:
                raise IRSError("Pub78 zip file contains no .txt data file.")
            with zf.open(txt_names[0]) as txt_file:
                text_content = txt_file.read().decode("utf-8", errors="replace")
    except zipfile.BadZipFile as e:
        raise IRSError(f"Pub78 download is not a valid zip file: {e}") from e

    records = _parse_pub78(text_content)
    staleness = StalenessWarning.from_download_time(downloaded_at)

    logger.info(
        "irs_connector fetch_pub78: parsed %d records, staleness=%s",
        len(records),
        staleness.level.value,
    )
    return records, staleness


def _parse_pub78(text: str) -> list[Pub78Record]:
    """
    Parse the pipe-delimited Pub78 text content into a list of Pub78Records.

    Format: EIN|Name|City|State|Country|DeductibilityCode
    No header row. Some lines may be malformed; those are skipped with a warning.
    """
    records: list[Pub78Record] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 6:
            logger.debug(
                "irs_connector _parse_pub78: skipping short line %d (%d parts): %r",
                line_no,
                len(parts),
                line[:80],
            )
            continue
        ein_str, name, city, state, country, deductibility_code = (
            parts[0].strip(),
            parts[1].strip(),
            parts[2].strip(),
            parts[3].strip(),
            parts[4].strip(),
            parts[5].strip(),
        )
        try:
            ein = int(ein_str)
        except ValueError:
            logger.debug(
                "irs_connector _parse_pub78: skipping line %d — bad EIN %r",
                line_no,
                ein_str,
            )
            continue
        if not name:
            continue

        records.append(
            Pub78Record(
                ein=ein,
                name=name,
                city=city,
                state=state,
                country=country,
                deductibility_code=deductibility_code,
                deductibility_description=_BMF_DEDUCTIBILITY_MAP.get(
                    deductibility_code, f"Code {deductibility_code}"
                ),
            )
        )

    return records


# ---------------------------------------------------------------------------
# EO BMF — fetch and parse
# ---------------------------------------------------------------------------


def fetch_eo_bmf(
    region: EoBmfRegion = EoBmfRegion.STATE_OH,
    url: str | None = None,
) -> tuple[list[EoBmfRecord], StalenessWarning]:
    """
    Download and parse an IRS EO BMF regional or state-level CSV file.

    The EO BMF is the authoritative IRS master file of all exempt organizations.
    It includes current status, ruling date, NTEE code, financial size indicators,
    and filing requirements.

    Args:
        region: Which regional/state file to download. Defaults to STATE_OH
                (Ohio-only file — smallest download, sufficient for Ohio
                investigations). Use MIDWEST for all midwest states.
        url:    Override the download URL entirely (useful for testing).

    Returns:
        (records, staleness_warning) tuple.

    Raises:
        IRSError: On network failure, bad HTTP status, or parse error.

    Example:
        records, warning = fetch_eo_bmf(EoBmfRegion.STATE_OH)
        print(f"Loaded {len(records)} EO BMF records. {warning}")
    """
    target_url = url or region.url
    raw_bytes = _download(target_url)
    downloaded_at = datetime.now(tz=timezone.utc)

    try:
        text_content = raw_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        raise IRSError(f"Could not decode EO BMF file content: {e}") from e

    records = _parse_eo_bmf(text_content)
    staleness = StalenessWarning.from_download_time(downloaded_at)

    logger.info(
        "irs_connector fetch_eo_bmf: region=%s, parsed %d records, staleness=%s",
        region.value,
        len(records),
        staleness.level.value,
    )
    return records, staleness


def _parse_eo_bmf(text: str) -> list[EoBmfRecord]:
    """
    Parse the EO BMF CSV content into a list of EoBmfRecord objects.

    The EO BMF CSV has a header row. Column names are uppercase.
    Many fields may be empty strings — we normalize those to None.
    """
    records: list[EoBmfRecord] = []
    reader = csv.DictReader(io.StringIO(text))

    for row_no, row in enumerate(reader, start=2):  # row 1 is the header
        ein_str = (row.get("EIN") or "").strip()
        if not ein_str:
            continue
        try:
            ein = int(ein_str)
        except ValueError:
            logger.debug(
                "irs_connector _parse_eo_bmf: skipping row %d — bad EIN %r",
                row_no,
                ein_str,
            )
            continue

        name = (row.get("NAME") or "").strip()
        if not name:
            continue

        ruling_raw = (row.get("RULING") or "").strip()
        ruling_year: int | None = None
        ruling_month: int | None = None
        if len(ruling_raw) == 6:
            try:
                ruling_year = int(ruling_raw[:4])
                ruling_month = int(ruling_raw[4:])
            except ValueError:
                pass

        subsection = (row.get("SUBSECTION") or "").strip()
        status_code = (row.get("STATUS") or "").strip()

        records.append(
            EoBmfRecord(
                ein=ein,
                name=name,
                city=(row.get("CITY") or "").strip(),
                state=(row.get("STATE") or "").strip(),
                zip_code=(row.get("ZIP") or "").strip(),
                subsection=subsection,
                subsection_description=_BMF_SUBSECTION_MAP.get(
                    subsection, f"501(c)({subsection})" if subsection else "Unknown"
                ),
                ruling_date=ruling_raw or None,
                ruling_year=ruling_year,
                ruling_month=ruling_month,
                status_code=status_code,
                status_description=_BMF_STATUS_MAP.get(status_code, f"Code {status_code}"),
                is_revoked=(status_code == "12"),
                deductibility_code=(row.get("DEDUCTIBILITY") or "").strip(),
                deductibility_description=_BMF_DEDUCTIBILITY_MAP.get(
                    (row.get("DEDUCTIBILITY") or "").strip(),
                    f"Code {(row.get('DEDUCTIBILITY') or '').strip()}",
                ),
                ntee_code=(row.get("NTEE_CD") or "").strip() or None,
                foundation_code=(row.get("FOUNDATION") or "").strip() or None,
                filing_req_code=(row.get("FILING_REQ_CD") or "").strip() or None,
                tax_period=(row.get("TAX_PERIOD") or "").strip() or None,
                asset_amount=_safe_int(row.get("ASSET_AMT")),
                income_amount=_safe_int(row.get("INCOME_AMT")),
                revenue_amount=_safe_int(row.get("REVENUE_AMT")),
                sort_name=(row.get("SORT_NAME") or "").strip() or None,
                raw=dict(row),
            )
        )

    return records


# ---------------------------------------------------------------------------
# Search — Pub78
# ---------------------------------------------------------------------------


def search_pub78(
    query: str,
    records: list[Pub78Record],
    staleness_warning: StalenessWarning | None = None,
    state: str | None = None,
) -> Pub78SearchResult:
    """
    Case-insensitive substring search across Pub78 records by organization name.

    Args:
        query:            Search term. Cannot be empty.
        records:          List of Pub78Record objects (from fetch_pub78()).
        staleness_warning: Pass the StalenessWarning from fetch_pub78(). If None,
                           a synthetic warning is generated (treat as HIGH staleness).
        state:            Optional two-letter state filter applied before name matching.

    Returns:
        Pub78SearchResult with matching records and always a staleness warning.

    Raises:
        IRSError: If query is empty or records list is empty.

    Example:
        records, warning = fetch_pub78()
        result = search_pub78("Example Charity Ministries", records, warning, state="OH")
        for r in result.matches:
            print(r.ein, r.name, r.deductibility_description)
    """
    if not query or not query.strip():
        raise IRSError("Search query cannot be empty.")
    if not records:
        raise IRSError("Records list is empty — call fetch_pub78() first.")

    if staleness_warning is None:
        # Generate a synthetic HIGH-staleness warning since we don't know when
        # the data was downloaded.
        from datetime import timedelta

        fake_dt = datetime.now(tz=timezone.utc) - timedelta(days=30)
        staleness_warning = StalenessWarning.from_download_time(fake_dt)

    q = query.strip().lower()
    state_filter = state.strip().upper() if state else None

    pool = records
    if state_filter:
        pool = [r for r in pool if r.state.upper() == state_filter]

    matches = [r for r in pool if q in r.name.lower()]

    return Pub78SearchResult(
        matches=matches,
        query=query,
        total_searched=len(pool),
        staleness_warning=staleness_warning,
    )


# ---------------------------------------------------------------------------
# Search — EO BMF
# ---------------------------------------------------------------------------


def search_eo_bmf(
    query: str,
    records: list[EoBmfRecord],
    staleness_warning: StalenessWarning | None = None,
    state: str | None = None,
    include_revoked: bool = True,
) -> EoBmfSearchResult:
    """
    Case-insensitive substring search across EO BMF records by organization name.

    Args:
        query:            Search term. Cannot be empty.
        records:          List of EoBmfRecord objects (from fetch_eo_bmf()).
        staleness_warning: Pass the StalenessWarning from fetch_eo_bmf(). If None,
                           a synthetic HIGH-staleness warning is generated.
        state:            Optional two-letter state filter applied before name matching.
        include_revoked:  If False, exclude records where is_revoked is True.
                          Default True — revoked orgs are investigatively relevant.

    Returns:
        EoBmfSearchResult with matching records and always a staleness warning.

    Raises:
        IRSError: If query is empty or records list is empty.

    Example:
        records, warning = fetch_eo_bmf(EoBmfRegion.STATE_OH)
        result = search_eo_bmf("Example Charity Ministries", records, warning, state="OH")
        for r in result.matches:
            print(r.ein, r.name, r.ruling_date, r.status_description)
    """
    if not query or not query.strip():
        raise IRSError("Search query cannot be empty.")
    if not records:
        raise IRSError("Records list is empty — call fetch_eo_bmf() first.")

    if staleness_warning is None:
        from datetime import timedelta

        fake_dt = datetime.now(tz=timezone.utc) - timedelta(days=30)
        staleness_warning = StalenessWarning.from_download_time(fake_dt)

    q = query.strip().lower()
    state_filter = state.strip().upper() if state else None

    pool = records
    if state_filter:
        pool = [r for r in pool if r.state.upper() == state_filter]
    if not include_revoked:
        pool = [r for r in pool if not r.is_revoked]

    matches = [r for r in pool if q in r.name.lower()]

    return EoBmfSearchResult(
        matches=matches,
        query=query,
        total_searched=len(pool),
        staleness_warning=staleness_warning,
    )


# ---------------------------------------------------------------------------
# EIN lookup — exact match from EO BMF
# ---------------------------------------------------------------------------


def lookup_ein(
    ein: int,
    records: list[EoBmfRecord],
    staleness_warning: StalenessWarning | None = None,
) -> tuple[EoBmfRecord | None, StalenessWarning]:
    """
    Look up a single EIN in the EO BMF records list.

    This is the primary EIN verification function. Given an EIN from a 990
    filing, a UCC filing, or a deed — confirm that the organization exists,
    when its exemption was granted, and whether it is currently active or revoked.

    Why this matters for signal detection:
        SR-002 checks whether an entity named in a document predates the
        entity's IRS formation/ruling date. lookup_ein() provides the ruling_year
        and ruling_month needed to evaluate that signal.

    Args:
        ein:              IRS EIN as integer (no dashes).
        records:          List of EoBmfRecord objects (from fetch_eo_bmf()).
        staleness_warning: Pass the StalenessWarning from fetch_eo_bmf().

    Returns:
        (EoBmfRecord, StalenessWarning) if found.
        (None, StalenessWarning) if not found.

    Example:
        records, warning = fetch_eo_bmf(EoBmfRegion.STATE_OH)
        record, w = lookup_ein(123456789, records, warning)
        if record:
            print(record.name, record.ruling_date, record.is_revoked)
        else:
            print("EIN not found in IRS EO BMF.")
        print(w)
    """
    if isinstance(ein, str):
        ein = int(ein.replace("-", "").strip())

    if staleness_warning is None:
        from datetime import timedelta

        fake_dt = datetime.now(tz=timezone.utc) - timedelta(days=30)
        staleness_warning = StalenessWarning.from_download_time(fake_dt)

    for record in records:
        if record.ein == ein:
            logger.info(
                "irs_connector lookup_ein: found EIN %d — %r (%s)",
                ein,
                record.name,
                record.status_description,
            )
            return record, staleness_warning

    logger.info("irs_connector lookup_ein: EIN %d not found in records", ein)
    return None, staleness_warning


# ---------------------------------------------------------------------------
# Convenience wrapper — fetch and search in one call
# ---------------------------------------------------------------------------


def search_ohio_nonprofits(
    query: str,
    include_revoked: bool = True,
) -> EoBmfSearchResult:
    """
    Convenience function: download the Ohio EO BMF file and search by name.

    Makes one HTTP request to the IRS. Returns matching Ohio nonprofits
    with a staleness warning. This is the simplest entry point for Ohio
    investigations — no setup required.

    Args:
        query:           Organization name search term.
        include_revoked: Include revoked orgs (default True — they are
                         investigatively relevant).

    Returns:
        EoBmfSearchResult with matches and staleness warning.

    Raises:
        IRSError: On network failure or empty query.

    Example:
        result = search_ohio_nonprofits("Example Charity Ministries")
        for r in result.matches:
            print(r.ein, r.name, r.ruling_date, r.is_revoked)
    """
    records, warning = fetch_eo_bmf(EoBmfRegion.STATE_OH)
    return search_eo_bmf(
        query=query,
        records=records,
        staleness_warning=warning,
        state="OH",
        include_revoked=include_revoked,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_int(value) -> int | None:
    """Convert a value to int, returning None if conversion fails or value is None/empty."""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    try:
        return int(float(v))  # handles "1234.0" style strings
    except (ValueError, TypeError):
        return None
