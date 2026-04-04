"""
IRS Form 990 XML connector for Catalyst.

Strategy: Index CSV lookup → HTTP range-request extraction from ZIP → XML parsing.

Data source: IRS TEOS (Tax Exempt Organization Search) bulk downloads.
    - Index CSVs:  apps.irs.gov/pub/epostcard/990/xml/{YEAR}/index_{YEAR}.csv
    - XML ZIPs:    apps.irs.gov/pub/epostcard/990/xml/{YEAR}/{BATCH_ID}.zip

Each ZIP contains thousands of individual 990 XML files (~5-100KB each).
Instead of downloading entire 100MB ZIPs, we use HTTP range requests to
read only the ZIP central directory and then extract a single file (~5KB
of network traffic per filing).

This replaces the old bulk-CSV approach (Publication 78 + EO BMF) which:
    - Downloaded 50MB+ CSV files that Railway's IP got blocked from
    - Only provided summary data (no governance, no compensation detail)
    - Had no Part IV/VI/VII data needed by signal rules

The XML approach gives us:
    - Part I:   Full financials (revenue, expenses, assets)
    - Part IV:  Checklist of required schedules (related-party flags)
    - Part VI:  Governance (conflict policy, board independence, whistleblower)
    - Part VII: Officer compensation table (name, title, hours, pay)
    - Schedules: L (related-party transactions), etc.

All hosted on IRS servers (apps.irs.gov), publicly accessible, no auth needed,
updated monthly, supports HTTP range requests.

Usage:
    from investigations.irs_connector import (
        search_990_by_ein,
        fetch_990_xml,
        parse_990_xml,
        IRSError,
    )

    # Find all filings for an EIN
    filings = search_990_by_ein("12-3456789")
    for f in filings:
        print(f.tax_year, f.return_type, f.taxpayer_name)

    # Fetch and parse the actual XML
    xml_text = fetch_990_xml(filings[0])
    parsed = parse_990_xml(xml_text)
    print(parsed.financials.total_revenue)
    print(parsed.governance.conflict_of_interest_policy)
    print(parsed.officers[0].name, parsed.officers[0].compensation)
"""

from __future__ import annotations

import csv
import io
import logging
import struct
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

IRS_BASE_URL = "https://apps.irs.gov/pub/epostcard/990/xml"

# Which years to search (most recent first). Add new years as IRS publishes them.
INDEX_YEARS = [2025, 2024, 2023, 2022, 2021, 2020, 2019]

# HTTP settings
REQUEST_TIMEOUT = (10, 60)  # (connect, read) seconds
USER_AGENT = "Catalyst-Nonprofit-Research/1.0 (nonprofit fraud investigation tool)"
POLITE_DELAY = 0.3  # seconds between requests to IRS servers

# Cache: in-memory index cache to avoid re-downloading during a session.
# Key: year (int), Value: list of IndexRecord
_index_cache: dict[int, list[IndexRecord]] = {}
_zip_directory_cache: dict[str, ZipDirectory] = {}

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IRSError(Exception):
    """Base exception for IRS connector errors."""

    pass


class IRSNetworkError(IRSError):
    """Network-level failure talking to IRS servers."""

    pass


class IRSParseError(IRSError):
    """Failed to parse XML or index data."""

    pass


class IRSNotFoundError(IRSError):
    """No filing found for the given EIN/criteria."""

    pass


# ---------------------------------------------------------------------------
# Data Classes — Index
# ---------------------------------------------------------------------------


@dataclass
class IndexRecord:
    """One row from the IRS yearly index CSV."""

    return_id: str
    filing_type: str  # "EFILE"
    ein: str  # 9 digits, no dashes
    tax_period: str  # "YYYYMM"
    sub_date: str  # submission year
    taxpayer_name: str
    return_type: str  # "990", "990EZ", "990PF"
    dln: str
    object_id: str  # Key for ZIP extraction
    xml_batch_id: str  # e.g., "2024_TEOS_XML_01A"
    index_year: int = 0  # Which yearly index this came from

    @property
    def tax_year(self) -> int:
        """Extract tax year from tax_period (first 4 digits)."""
        try:
            return int(self.tax_period[:4])
        except (ValueError, IndexError):
            return 0

    @property
    def ein_formatted(self) -> str:
        """EIN with dash: 12-3456789."""
        ein = self.ein.zfill(9)
        return f"{ein[:2]}-{ein[2:]}"

    @property
    def zip_url(self) -> str:
        """Full URL to the ZIP file containing this XML."""
        year = self.xml_batch_id.split("_")[0]
        return f"{IRS_BASE_URL}/{year}/{self.xml_batch_id}.zip"

    @property
    def xml_filename(self) -> str:
        """Filename inside the ZIP."""
        return f"{self.object_id}_public.xml"


# ---------------------------------------------------------------------------
# Data Classes — Parsed 990
# ---------------------------------------------------------------------------


@dataclass
class FinancialData:
    """Part I financials + Part X balance sheet."""

    # Part I — Revenue (current year)
    total_contributions: Optional[int] = None
    program_service_revenue: Optional[int] = None
    investment_income: Optional[int] = None
    other_revenue: Optional[int] = None
    total_revenue: Optional[int] = None

    # Part I — Revenue (prior year, for trend analysis)
    py_total_revenue: Optional[int] = None
    py_total_expenses: Optional[int] = None

    # Part I — Expenses
    grants_paid: Optional[int] = None
    salaries_and_compensation: Optional[int] = None
    professional_fundraising: Optional[int] = None
    other_expenses: Optional[int] = None
    total_expenses: Optional[int] = None

    # Part I — Bottom line
    revenue_less_expenses: Optional[int] = None

    # Part X — Balance Sheet
    total_assets_boy: Optional[int] = None
    total_assets_eoy: Optional[int] = None
    total_liabilities_boy: Optional[int] = None
    total_liabilities_eoy: Optional[int] = None
    net_assets_boy: Optional[int] = None
    net_assets_eoy: Optional[int] = None

    # Cash position (for SR-019 CASH_HEAVY)
    cash_non_interest_bearing_eoy: Optional[int] = None
    savings_and_temp_investments_eoy: Optional[int] = None


@dataclass
class GovernanceData:
    """Part IV checklist + Part VI governance indicators."""

    # Part IV — Checklist of Required Schedules
    schedule_b_required: Optional[bool] = None  # Major donors
    political_campaign_activity: Optional[bool] = None
    lobbying_activities: Optional[bool] = None
    subject_to_proxy_tax: Optional[bool] = None
    donor_advised_fund: Optional[bool] = None
    conservation_easements: Optional[bool] = None
    report_land_building_equipment: Optional[bool] = None
    schedule_l_required: Optional[bool] = None  # Related-party transactions
    loan_outstanding: Optional[bool] = None  # Loans to/from officers
    grant_to_related_person: Optional[bool] = None  # Grants to related persons
    business_rln_with_org_member: Optional[bool] = None  # Business with board members
    business_rln_with_family: Optional[bool] = None  # Business with family
    business_rln_with_35_ctrl: Optional[bool] = None  # Business with 35% controllers
    deductible_noncash_contrib: Optional[bool] = None
    schedule_j_required: Optional[bool] = None  # Compensation > $150K
    tax_exempt_bonds: Optional[bool] = None
    # Unrelated business income
    unrelated_business_income: Optional[bool] = None

    # Part VI Section A — Governing Body
    voting_members_governing_body: Optional[int] = None
    independent_voting_members: Optional[int] = None
    family_or_business_relationship: Optional[bool] = None
    delegation_of_mgmt_duties: Optional[bool] = None
    material_diversion_or_misuse: Optional[bool] = None
    members_or_stockholders: Optional[bool] = None
    election_of_board_members: Optional[bool] = None

    # Part VI Section B — Policies
    conflict_of_interest_policy: Optional[bool] = None  # Line 12a — SR-012
    annual_disclosure_covered: Optional[bool] = None  # Line 12b
    regular_monitoring_enforced: Optional[bool] = None  # Line 12c
    whistleblower_policy: Optional[bool] = None  # Line 13
    document_retention_policy: Optional[bool] = None  # Line 14
    compensation_process_ceo: Optional[bool] = None  # Line 15a
    compensation_process_other: Optional[bool] = None  # Line 15b

    # Part VI — Minutes and transparency
    minutes_of_governing_body: Optional[bool] = None
    minutes_of_committees: Optional[bool] = None
    form990_provided_to_governing_body: Optional[bool] = None


@dataclass
class OfficerCompensation:
    """One row from Part VII — Officers, Directors, Trustees, Key Employees."""

    name: str = ""
    title: str = ""
    average_hours_per_week: Optional[float] = None
    average_hours_related_org: Optional[float] = None
    reportable_comp_from_org: Optional[int] = None
    reportable_comp_from_related: Optional[int] = None
    other_compensation: Optional[int] = None
    is_former: bool = False
    is_officer: bool = False
    is_highest_compensated: bool = False
    is_key_employee: bool = False

    @property
    def total_compensation(self) -> int:
        """Sum of all compensation columns."""
        return (
            (self.reportable_comp_from_org or 0)
            + (self.reportable_comp_from_related or 0)
            + (self.other_compensation or 0)
        )


@dataclass
class Parsed990:
    """Complete parsed Form 990 result."""

    # Header
    ein: str = ""
    taxpayer_name: str = ""
    tax_year: int = 0
    tax_period_begin: str = ""  # "YYYY-MM-DD"
    tax_period_end: str = ""  # "YYYY-MM-DD"
    return_type: str = ""  # "990", "990EZ", "990PF"
    formation_year: Optional[int] = None
    state: str = ""
    mission: str = ""
    website: str = ""

    # Sections
    financials: FinancialData = field(default_factory=FinancialData)
    governance: GovernanceData = field(default_factory=GovernanceData)
    officers: list[OfficerCompensation] = field(default_factory=list)

    # Compensation summary
    total_reportable_comp_from_org: Optional[int] = None
    individuals_over_100k: Optional[int] = None
    total_comp_greater_than_150k: Optional[bool] = None

    # Employees
    num_employees: Optional[int] = None
    num_volunteers: Optional[int] = None

    # Metadata
    source_object_id: str = ""
    source_batch_id: str = ""
    parse_quality: float = 1.0  # 0.0–1.0


@dataclass
class SearchResult:
    """Result from search_990_by_ein with all filings found."""

    ein: str
    ein_formatted: str
    filings: list[IndexRecord]
    years_searched: list[int]
    total_found: int


# ---------------------------------------------------------------------------
# ZIP Directory Cache
# ---------------------------------------------------------------------------


@dataclass
class ZipFileEntry:
    """One file entry from a ZIP central directory."""

    filename: str
    compressed_size: int
    uncompressed_size: int
    local_header_offset: int
    compression_method: int  # 8 = deflate, 0 = stored


@dataclass
class ZipDirectory:
    """Parsed ZIP central directory for a batch."""

    entries: dict[str, ZipFileEntry]  # filename -> entry
    fetched_at: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Index Operations
# ---------------------------------------------------------------------------


def _normalize_ein(ein: str) -> str:
    """Strip dashes and spaces, zero-pad to 9 digits."""
    cleaned = ein.replace("-", "").replace(" ", "").strip()
    return cleaned.zfill(9)


def _stream_search_index(
    year: int,
    *,
    ein_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    max_results: int = 200,
) -> list[IndexRecord]:
    """
    Stream-download an IRS yearly index CSV and filter on-the-fly.

    CRITICAL: We never load the full CSV into memory. The index files
    are 50-90MB with ~700K+ rows. On Railway (512MB-1GB containers),
    loading the whole thing causes OOM or timeouts.

    Instead we:
      1. Stream the HTTP response line-by-line
      2. Check each row against the filter (EIN or name)
      3. Keep only matching rows (typically <20 per org)
      4. Stop early once max_results is reached

    Memory usage: ~O(matches) instead of O(all_rows).
    """
    url = f"{IRS_BASE_URL}/{year}/index_{year}.csv"
    logger.info("Streaming IRS index: %s", url)

    try:
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            stream=True,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise IRSNetworkError(f"Failed to download index for {year}: {e}") from e

    matches: list[IndexRecord] = []
    header: list[str] = []
    line_buf = ""

    for chunk in resp.iter_content(chunk_size=64 * 1024, decode_unicode=True):
        if chunk is None:
            continue
        line_buf += chunk
        lines = line_buf.split("\n")
        # Keep last partial line in buffer
        line_buf = lines[-1]

        for line in lines[:-1]:
            line = line.strip()
            if not line:
                continue

            if not header:
                header = [h.strip().strip('"') for h in line.split(",")]
                continue

            # Fast pre-filter before full CSV parse
            if ein_filter and ein_filter not in line:
                continue
            if name_filter and name_filter not in line.upper():
                continue

            # Parse matching row
            try:
                vals = next(csv.reader(io.StringIO(line)))
                row = dict(zip(header, vals))
            except Exception:
                continue

            try:
                record = IndexRecord(
                    return_id=row.get("RETURN_ID", ""),
                    filing_type=row.get("FILING_TYPE", ""),
                    ein=row.get("EIN", "").strip(),
                    tax_period=row.get("TAX_PERIOD", ""),
                    sub_date=row.get("SUB_DATE", ""),
                    taxpayer_name=row.get("TAXPAYER_NAME", ""),
                    return_type=row.get("RETURN_TYPE", ""),
                    dln=row.get("DLN", ""),
                    object_id=row.get("OBJECT_ID", ""),
                    xml_batch_id=row.get("XML_BATCH_ID", ""),
                    index_year=year,
                )
            except Exception as e:
                logger.warning("Skipping row: %s", e)
                continue

            # Confirm match (full CSV parse may differ)
            if ein_filter and record.ein != ein_filter:
                continue
            if name_filter:
                if name_filter not in record.taxpayer_name.upper():
                    continue

            matches.append(record)
            if len(matches) >= max_results:
                resp.close()
                break

        if len(matches) >= max_results:
            break

    logger.info(
        "Found %d matches in %d index (streamed)",
        len(matches),
        year,
    )
    return matches


def search_990_by_ein(
    ein: str,
    years: Optional[list[int]] = None,
    return_types: Optional[list[str]] = None,
) -> SearchResult:
    """
    Search IRS index CSVs for all 990 filings by a given EIN.

    Uses streaming search — never loads full index into memory.

    Args:
        ein: EIN with or without dash
        years: Which index years to search (default: all)
        return_types: Filter by return type (e.g., ["990"])

    Returns:
        SearchResult with matching filings, newest first.
    """
    normalized_ein = _normalize_ein(ein)
    search_years = years or INDEX_YEARS

    logger.info(
        "Searching for EIN %s across years %s",
        normalized_ein,
        search_years,
    )

    all_filings: list[IndexRecord] = []
    seen_object_ids: set[str] = set()

    for year in search_years:
        try:
            matches = _stream_search_index(year, ein_filter=normalized_ein)
        except IRSNetworkError as e:
            logger.warning(
                "Could not load index for %d: %s",
                year,
                e,
            )
            continue

        for record in matches:
            if record.object_id not in seen_object_ids:
                if return_types:
                    if record.return_type not in return_types:
                        continue
                all_filings.append(record)
                seen_object_ids.add(record.object_id)

        time.sleep(POLITE_DELAY)

    all_filings.sort(
        key=lambda r: (r.tax_year, r.sub_date),
        reverse=True,
    )

    result = SearchResult(
        ein=normalized_ein,
        ein_formatted=(f"{normalized_ein[:2]}-{normalized_ein[2:]}"),
        filings=all_filings,
        years_searched=search_years,
        total_found=len(all_filings),
    )

    logger.info(
        "Found %d filings for EIN %s",
        result.total_found,
        result.ein_formatted,
    )
    return result


def search_990_by_name(
    name: str,
    state: Optional[str] = None,
    years: Optional[list[int]] = None,
    max_results: int = 50,
) -> list[IndexRecord]:
    """
    Search IRS index CSVs by org name (case-insensitive).

    Uses streaming search — never loads full index into memory.
    Only searches most recent 2 years by default to limit time.

    Args:
        name: Organization name to search for.
        state: Ignored (not in index CSV).
        years: Years to search (default: most recent 2).
        max_results: Max results to return.

    Returns:
        Matching IndexRecords, sorted by tax year desc.
    """
    search_years = years or INDEX_YEARS[:2]
    name_upper = name.upper().strip()

    logger.info(
        "Searching for name '%s' across years %s",
        name,
        search_years,
    )

    results: list[IndexRecord] = []
    seen_eins: set[str] = set()

    for year in search_years:
        try:
            matches = _stream_search_index(
                year,
                name_filter=name_upper,
                max_results=max_results,
            )
        except IRSNetworkError as e:
            logger.warning(
                "Could not load index for %d: %s",
                year,
                e,
            )
            continue

        for record in matches:
            if record.ein not in seen_eins:
                results.append(record)
                seen_eins.add(record.ein)
                if len(results) >= max_results:
                    break

        if len(results) >= max_results:
            break
        time.sleep(POLITE_DELAY)

    results.sort(
        key=lambda r: (r.tax_year, r.sub_date),
        reverse=True,
    )
    logger.info(
        "Found %d orgs matching '%s'",
        len(results),
        name,
    )
    return results


# ---------------------------------------------------------------------------
# ZIP Range-Request Extraction
# ---------------------------------------------------------------------------


def _fetch_zip_directory(zip_url: str) -> ZipDirectory:
    """
    Download and parse the central directory of a remote ZIP file.

    ZIP files store their table of contents (central directory) at the END
    of the file. We can read it with just two small HTTP range requests:
      1. Last 256KB to find the End of Central Directory record
      2. The central directory itself (typically 1-2MB)

    This tells us the filename, offset, and size of every file in the ZIP
    without downloading the entire 100MB archive.
    """
    cache_key = zip_url
    if cache_key in _zip_directory_cache:
        return _zip_directory_cache[cache_key]

    logger.info("Fetching ZIP directory: %s", zip_url)

    # Step 1: Get file size
    try:
        head_resp = requests.head(
            zip_url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        head_resp.raise_for_status()
        file_size = int(head_resp.headers.get("content-length", 0))
    except requests.RequestException as e:
        raise IRSNetworkError(f"Failed to get ZIP size: {e}") from e

    if file_size == 0:
        raise IRSNetworkError(f"ZIP file has zero size: {zip_url}")

    # Step 2: Download last 256KB to find End of Central Directory (EOCD)
    eocd_range_start = max(0, file_size - 262144)
    try:
        resp = requests.get(
            zip_url,
            headers={
                "Range": f"bytes={eocd_range_start}-{file_size - 1}",
                "User-Agent": USER_AGENT,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise IRSNetworkError(f"Failed to read ZIP EOCD: {e}") from e

    data = resp.content

    # Find EOCD signature (PK\x05\x06)
    eocd_pos = data.rfind(b"PK\x05\x06")
    if eocd_pos < 0:
        raise IRSParseError("Could not find ZIP End of Central Directory")

    # Parse EOCD
    num_entries = struct.unpack("<H", data[eocd_pos + 10 : eocd_pos + 12])[0]
    cd_size = struct.unpack("<I", data[eocd_pos + 12 : eocd_pos + 16])[0]
    cd_offset = struct.unpack("<I", data[eocd_pos + 16 : eocd_pos + 20])[0]

    logger.info(
        "ZIP has %d entries, central directory at offset %d (size %d)",
        num_entries,
        cd_offset,
        cd_size,
    )

    # Step 3: Download the central directory
    # Check if we already have it in our EOCD download
    local_cd_start = cd_offset - eocd_range_start
    if local_cd_start >= 0 and local_cd_start + cd_size <= len(data):
        cd_data = data[local_cd_start : local_cd_start + cd_size]
    else:
        # Need a separate request for the central directory
        time.sleep(POLITE_DELAY)
        try:
            resp = requests.get(
                zip_url,
                headers={
                    "Range": f"bytes={cd_offset}-{cd_offset + cd_size - 1}",
                    "User-Agent": USER_AGENT,
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            cd_data = resp.content
        except requests.RequestException as e:
            raise IRSNetworkError(f"Failed to read ZIP central directory: {e}") from e

    # Step 4: Parse all central directory entries
    entries: dict[str, ZipFileEntry] = {}
    pos = 0
    for _ in range(num_entries):
        if pos + 46 > len(cd_data) or cd_data[pos : pos + 4] != b"PK\x01\x02":
            break

        compression_method = struct.unpack("<H", cd_data[pos + 10 : pos + 12])[0]
        comp_size = struct.unpack("<I", cd_data[pos + 20 : pos + 24])[0]
        uncomp_size = struct.unpack("<I", cd_data[pos + 24 : pos + 28])[0]
        fname_len = struct.unpack("<H", cd_data[pos + 28 : pos + 30])[0]
        extra_len = struct.unpack("<H", cd_data[pos + 30 : pos + 32])[0]
        comment_len = struct.unpack("<H", cd_data[pos + 32 : pos + 34])[0]
        local_offset = struct.unpack("<I", cd_data[pos + 42 : pos + 46])[0]

        filename = cd_data[pos + 46 : pos + 46 + fname_len].decode("utf-8", errors="replace")

        entries[filename] = ZipFileEntry(
            filename=filename,
            compressed_size=comp_size,
            uncompressed_size=uncomp_size,
            local_header_offset=local_offset,
            compression_method=compression_method,
        )

        pos += 46 + fname_len + extra_len + comment_len

    logger.info("Parsed %d ZIP entries", len(entries))

    directory = ZipDirectory(entries=entries)
    _zip_directory_cache[cache_key] = directory
    return directory


def fetch_990_xml(filing: IndexRecord) -> str:
    """
    Fetch a single 990 XML file from an IRS ZIP archive.

    Falls back to full ZIP download if compression method is not standard
    DEFLATE (e.g., if IRS uses DEFLATE64 which Python's zlib cannot handle).

    Args:
        filing: An IndexRecord from search_990_by_ein().

    Returns:
        The raw XML text of the 990 filing.
    """
    zip_url = filing.zip_url
    target_filename = filing.xml_filename

    logger.info("Fetching XML for %s from %s", filing.object_id, zip_url)

    # Get ZIP directory to check compression method
    directory = _fetch_zip_directory(zip_url)

    if target_filename not in directory.entries:
        raise IRSNotFoundError(
            f"File {target_filename} not found in ZIP. ZIP has {len(directory.entries)} entries."
        )

    entry = directory.entries[target_filename]
    logger.info(
        "Found %s: compressed=%d, uncompressed=%d, offset=%d, compression=%d",
        target_filename,
        entry.compressed_size,
        entry.uncompressed_size,
        entry.local_header_offset,
        entry.compression_method,
    )

    # If compression method is standard DEFLATE (8) or STORED (0),
    # use range request to download only what we need
    if entry.compression_method in (0, 8):
        return _fetch_990_xml_ranged(filing, entry)

    # For unsupported compression methods (e.g., DEFLATE64/9),
    # fall back to downloading the entire ZIP
    logger.info(
        "Compression method %d not supported by zlib, downloading full ZIP",
        entry.compression_method,
    )
    return _fetch_990_xml_full_zip(zip_url, target_filename)


def _fetch_990_xml_ranged(filing: IndexRecord, entry: ZipFileEntry) -> str:
    """Fetch XML using HTTP range requests (efficient for DEFLATE/STORED)."""
    zip_url = filing.zip_url

    # Read local file header + compressed data
    # Local header is 30 bytes + filename length + extra field length
    # We over-read by 300 bytes to cover filename and extra fields
    read_size = 30 + 300 + entry.compressed_size
    range_start = entry.local_header_offset
    range_end = range_start + read_size - 1

    time.sleep(POLITE_DELAY)
    try:
        resp = requests.get(
            zip_url,
            headers={
                "Range": f"bytes={range_start}-{range_end}",
                "User-Agent": USER_AGENT,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise IRSNetworkError(f"Failed to read XML from ZIP: {e}") from e

    data = resp.content

    # Verify local file header signature
    if data[:4] != b"PK\x03\x04":
        raise IRSParseError("Invalid local file header signature")

    # Parse local file header to find where compressed data starts
    fname_len = struct.unpack("<H", data[26:28])[0]
    extra_len = struct.unpack("<H", data[28:30])[0]
    data_start = 30 + fname_len + extra_len

    compressed_data = data[data_start : data_start + entry.compressed_size]

    # Decompress
    if entry.compression_method == 8:  # DEFLATE
        try:
            xml_bytes = zlib.decompress(compressed_data, -15)  # raw deflate
        except zlib.error as e:
            raise IRSParseError(f"Failed to decompress XML: {e}") from e
    elif entry.compression_method == 0:  # STORED (no compression)
        xml_bytes = compressed_data
    else:
        raise IRSParseError(f"Unsupported compression method: {entry.compression_method}")

    xml_text = xml_bytes.decode("utf-8", errors="replace")
    logger.info("Extracted %d chars of XML for %s", len(xml_text), filing.object_id)
    return xml_text


def _fetch_990_xml_full_zip(zip_url: str, target_filename: str) -> str:
    """
    Fetch XML by downloading the entire ZIP file.

    This is a fallback for compression methods not supported by Python's zlib
    (e.g., DEFLATE64). Downloads the full 400+ MB ZIP and extracts using
    Python's zipfile module (which will also fail) or system unzip.
    """
    import subprocess
    import tempfile

    logger.info("Downloading full ZIP file from %s", zip_url)

    time.sleep(POLITE_DELAY)
    try:
        resp = requests.get(
            zip_url,
            headers={"User-Agent": USER_AGENT},
            timeout=180,
            stream=True,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise IRSNetworkError(f"Failed to download ZIP: {e}") from e

    # Write to temporary file and extract with system unzip
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                tmp_zip.write(chunk)
        tmp_zip_path = tmp_zip.name

    try:
        # Use system unzip to extract (supports DEFLATE64)
        result = subprocess.run(
            ["unzip", "-p", tmp_zip_path, target_filename],
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")
            raise IRSParseError(f"unzip failed: {stderr_text}")

        xml_bytes = result.stdout
        xml_text = xml_bytes.decode("utf-8", errors="replace")
        logger.info("Extracted %d chars of XML using unzip", len(xml_text))
        return xml_text

    finally:
        # Clean up temp file
        try:
            import os

            os.unlink(tmp_zip_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# XML Parsing
# ---------------------------------------------------------------------------

# IRS e-file namespace
IRS_NS = "{http://www.irs.gov/efile}"


def _tag(name: str) -> str:
    """Build a namespaced tag."""
    return f"{IRS_NS}{name}"


def _text(elem, tag_name: str, default: str = "") -> str:
    """Get text content of a child element, or default."""
    if elem is None:
        return default
    child = elem.find(_tag(tag_name))
    if child is not None and child.text:
        return child.text.strip()
    return default


def _int(elem, tag_name: str) -> Optional[int]:
    """Get integer content of a child element, or None."""
    text = _text(elem, tag_name)
    if not text:
        return None
    try:
        # Handle decimal values (e.g., "1234.00" in some filings)
        return int(float(text))
    except (ValueError, TypeError):
        return None


def _bool(elem, tag_name: str) -> Optional[bool]:
    """Get boolean content of a child element, or None."""
    text = _text(elem, tag_name).lower()
    if not text:
        return None
    if text in ("true", "1", "x", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    return None


def _float(elem, tag_name: str) -> Optional[float]:
    """Get float content of a child element, or None."""
    text = _text(elem, tag_name)
    if not text:
        return None
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _grp_int(elem, grp_tag: str, val_tag: str) -> Optional[int]:
    """Get integer from a nested group element (e.g., TotalRevenueGrp/TotalRevenueAmt)."""
    if elem is None:
        return None
    grp = elem.find(_tag(grp_tag))
    if grp is None:
        return None
    return _int(grp, val_tag)


def parse_990_xml(
    xml_text: str, source_object_id: str = "", source_batch_id: str = ""
) -> Parsed990:
    """
    Parse a Form 990 XML file into structured Catalyst data.

    Handles 990, 990EZ, and 990PF return types with graceful degradation
    (990EZ and 990PF have fewer fields — we extract what's available).

    Args:
        xml_text: Raw XML string from fetch_990_xml().
        source_object_id: IRS OBJECT_ID for provenance tracking.
        source_batch_id: IRS XML_BATCH_ID for provenance tracking.

    Returns:
        Parsed990 with all available financial, governance, and compensation data.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise IRSParseError(f"Invalid XML: {e}") from e

    result = Parsed990(
        source_object_id=source_object_id,
        source_batch_id=source_batch_id,
    )

    # --- Return Header ---
    header = root.find(_tag("ReturnHeader"))
    if header is not None:
        result.tax_period_end = _text(header, "TaxPeriodEndDt")
        result.tax_period_begin = _text(header, "TaxPeriodBeginDt")
        result.return_type = _text(header, "ReturnTypeCd")
        result.tax_year = _int(header, "TaxYr") or 0

        filer = header.find(_tag("Filer"))
        if filer is not None:
            result.ein = _text(filer, "EIN")
            biz_name = filer.find(_tag("BusinessName"))
            if biz_name is not None:
                result.taxpayer_name = _text(biz_name, "BusinessNameLine1Txt")

    # --- Find the main return document ---
    return_data = root.find(_tag("ReturnData"))
    if return_data is None:
        result.parse_quality = 0.0
        return result

    # Determine which form type we have
    irs990 = return_data.find(_tag("IRS990"))
    irs990ez = return_data.find(_tag("IRS990EZ"))
    irs990pf = return_data.find(_tag("IRS990PF"))

    if irs990 is not None:
        _parse_990_full(irs990, result)
    elif irs990ez is not None:
        _parse_990ez(irs990ez, result)
    elif irs990pf is not None:
        _parse_990pf(irs990pf, result)
    else:
        logger.warning("No recognized IRS990/990EZ/990PF element in XML")
        result.parse_quality = 0.1

    return result


def _parse_990_full(elem, result: Parsed990) -> None:
    """Parse a full Form 990 (the most detailed version)."""
    fin = result.financials
    gov = result.governance

    # --- Header fields ---
    result.formation_year = _int(elem, "FormationYr")
    result.state = _text(elem, "LegalDomicileStateCd")
    result.mission = _text(elem, "ActivityOrMissionDesc") or _text(elem, "MissionDesc")
    result.website = _text(elem, "WebsiteAddressTxt")

    # --- Part I: Revenue (Current Year) ---
    fin.total_contributions = _int(elem, "CYContributionsGrantsAmt")
    fin.program_service_revenue = _int(elem, "CYProgramServiceRevenueAmt")
    fin.investment_income = _int(elem, "CYInvestmentIncomeAmt")
    fin.other_revenue = _int(elem, "CYOtherRevenueAmt")
    fin.total_revenue = _int(elem, "CYTotalRevenueAmt")

    # Prior year for trend analysis
    fin.py_total_revenue = _int(elem, "PYTotalRevenueAmt")
    fin.py_total_expenses = _int(elem, "PYTotalExpensesAmt")

    # --- Part I: Expenses ---
    fin.grants_paid = _int(elem, "CYGrantsAndSimilarPaidAmt")
    fin.salaries_and_compensation = _int(elem, "CYSalariesCompEmpBnftPaidAmt")
    fin.professional_fundraising = _int(elem, "CYTotalProfFndrsngExpnsAmt")
    fin.other_expenses = _int(elem, "CYOtherExpensesAmt")
    fin.total_expenses = _int(elem, "CYTotalExpensesAmt")
    fin.revenue_less_expenses = _int(elem, "CYRevenuesLessExpensesAmt")

    # --- Part X: Balance Sheet ---
    fin.total_assets_boy = _int(elem, "TotalAssetsBOYAmt")
    fin.total_assets_eoy = _int(elem, "TotalAssetsEOYAmt")
    fin.total_liabilities_boy = _int(elem, "TotalLiabilitiesBOYAmt")
    fin.total_liabilities_eoy = _int(elem, "TotalLiabilitiesEOYAmt")
    fin.net_assets_boy = _int(elem, "NetAssetsOrFundBalancesBOYAmt")
    fin.net_assets_eoy = _int(elem, "NetAssetsOrFundBalancesEOYAmt")

    # Cash position
    fin.cash_non_interest_bearing_eoy = _grp_int(elem, "CashNonInterestBearingGrp", "EOYAmt")
    fin.savings_and_temp_investments_eoy = _grp_int(elem, "SavingsAndTempCashInvstGrp", "EOYAmt")

    # --- Employee counts ---
    result.num_employees = _int(elem, "TotalEmployeeCnt")
    result.num_volunteers = _int(elem, "TotalVolunteersCnt")

    # --- Part IV: Checklist of Required Schedules ---
    gov.schedule_b_required = _bool(elem, "ScheduleBRequiredInd")
    gov.political_campaign_activity = _bool(elem, "PoliticalCampaignActyInd")
    gov.donor_advised_fund = _bool(elem, "DonorAdvisedFundInd")
    gov.conservation_easements = _bool(elem, "ConservationEasementsInd")
    gov.report_land_building_equipment = _bool(elem, "ReportLandBuildingEquipmentInd")
    gov.schedule_j_required = _bool(elem, "ScheduleJRequiredInd")
    gov.tax_exempt_bonds = _bool(elem, "TaxExemptBondsInd")
    gov.loan_outstanding = _bool(elem, "LoanOutstandingInd")
    gov.grant_to_related_person = _bool(elem, "GrantToRelatedPersonInd")
    gov.business_rln_with_org_member = _bool(elem, "BusinessRlnWithOrgMemInd")
    gov.business_rln_with_family = _bool(elem, "BusinessRlnWithFamMemInd")
    gov.business_rln_with_35_ctrl = _bool(elem, "BusinessRlnWith35CtrlEntInd")
    gov.deductible_noncash_contrib = _bool(elem, "DeductibleNonCashContriInd")
    gov.unrelated_business_income = _bool(elem, "UnrelatedBusIncmOverLimitInd")
    gov.subject_to_proxy_tax = _bool(elem, "SubjectToProxyTaxInd")
    gov.lobbying_activities = (
        _bool(elem, "LobbyingActivitiesInd")
        if elem.find(_tag("LobbyingActivitiesInd")) is not None
        else None
    )

    # --- Part VI Section A: Governing Body ---
    gov.voting_members_governing_body = _int(elem, "GoverningBodyVotingMembersCnt")
    gov.independent_voting_members = _int(elem, "IndependentVotingMemberCnt")
    gov.family_or_business_relationship = _bool(elem, "FamilyOrBusinessRlnInd")
    gov.delegation_of_mgmt_duties = _bool(elem, "DelegationOfMgmtDutiesInd")
    gov.material_diversion_or_misuse = _bool(elem, "MaterialDiversionOrMisuseInd")
    gov.members_or_stockholders = _bool(elem, "MembersOrStockholdersInd")
    gov.election_of_board_members = _bool(elem, "ElectionOfBoardMembersInd")

    # Also check the VotingMembersGoverningBodyCnt / VotingMembersIndependentCnt
    # (some filings use these instead)
    if gov.voting_members_governing_body is None:
        gov.voting_members_governing_body = _int(elem, "VotingMembersGoverningBodyCnt")
    if gov.independent_voting_members is None:
        gov.independent_voting_members = _int(elem, "VotingMembersIndependentCnt")

    # --- Part VI Section B: Policies ---
    gov.conflict_of_interest_policy = _bool(elem, "ConflictOfInterestPolicyInd")
    gov.annual_disclosure_covered = _bool(elem, "AnnualDisclosureCoveredPrsnInd")
    gov.regular_monitoring_enforced = _bool(elem, "RegularMonitoringEnfrcInd")
    gov.whistleblower_policy = _bool(elem, "WhistleblowerPolicyInd")
    gov.document_retention_policy = _bool(elem, "DocumentRetentionPolicyInd")
    gov.compensation_process_ceo = _bool(elem, "CompensationProcessCEOInd")
    gov.compensation_process_other = _bool(elem, "CompensationProcessOtherInd")
    gov.minutes_of_governing_body = _bool(elem, "MinutesOfGoverningBodyInd")
    gov.minutes_of_committees = _bool(elem, "MinutesOfCommitteesInd")
    gov.form990_provided_to_governing_body = _bool(elem, "Form990ProvidedToGvrnBodyInd")

    # --- Part VII: Officer/Director/Trustee Compensation ---
    result.total_reportable_comp_from_org = _int(elem, "TotalReportableCompFromOrgAmt")
    result.individuals_over_100k = _int(elem, "IndivRcvdGreaterThan100KCnt")
    result.total_comp_greater_than_150k = _bool(elem, "TotalCompGreaterThan150KInd")

    for grp in elem.findall(_tag("Form990PartVIISectionAGrp")):
        officer = OfficerCompensation()
        # Name can be in PersonNm or BusinessName
        person_nm = grp.find(_tag("PersonNm"))
        if person_nm is not None and person_nm.text:
            officer.name = person_nm.text.strip()
        else:
            biz_nm = grp.find(_tag("BusinessName"))
            if biz_nm is not None:
                officer.name = _text(biz_nm, "BusinessNameLine1Txt")

        officer.title = _text(grp, "TitleTxt")
        officer.average_hours_per_week = _float(grp, "AverageHoursPerWeekRt")
        officer.average_hours_related_org = _float(grp, "AverageHoursPerWeekRltdOrgRt")
        officer.reportable_comp_from_org = _int(grp, "ReportableCompFromOrgAmt")
        officer.reportable_comp_from_related = _int(grp, "ReportableCompFromRltdOrgAmt")
        officer.other_compensation = _int(grp, "OtherCompensationAmt")
        officer.is_former = _bool(grp, "FormerOfcrDirectorTrusteeInd") or False
        officer.is_officer = _bool(grp, "OfficerInd") or False
        officer.is_highest_compensated = _bool(grp, "HighestCompensatedEmployeeInd") or False
        officer.is_key_employee = _bool(grp, "KeyEmployeeInd") or False

        result.officers.append(officer)

    # --- Parse quality score ---
    # Count how many key fields we got
    key_fields = [
        fin.total_revenue,
        fin.total_expenses,
        fin.total_assets_eoy,
        gov.conflict_of_interest_policy,
        gov.voting_members_governing_body,
    ]
    filled = sum(1 for f in key_fields if f is not None)
    result.parse_quality = filled / len(key_fields)


def _parse_990ez(elem, result: Parsed990) -> None:
    """Parse Form 990-EZ (simplified version with fewer fields)."""
    fin = result.financials
    gov = result.governance

    result.formation_year = _int(elem, "FormationYr")
    result.state = _text(elem, "LegalDomicileStateCd") or _text(elem, "StateAbbreviationCd")
    result.mission = _text(elem, "PrimaryExemptPurposeTxt")
    result.website = _text(elem, "WebsiteAddressTxt")

    # Revenue
    fin.total_contributions = _int(elem, "ContributionsGiftsGrantsEtcAmt")
    fin.program_service_revenue = _int(elem, "ProgramServiceRevenueAmt")
    fin.investment_income = _int(elem, "InvestmentIncomeAmt")
    fin.total_revenue = _int(elem, "TotalRevenueAmt")

    # Expenses
    fin.salaries_and_compensation = _int(elem, "SalariesOtherCompEmplBnftAmt")
    fin.total_expenses = _int(elem, "TotalExpensesAmt")
    fin.revenue_less_expenses = _int(elem, "ExcessOrDeficitForYearAmt")

    # Balance Sheet
    fin.total_assets_boy = (
        _int(elem, "Form990TotalAssetsGrp/BOYAmt")
        if elem.find(_tag("Form990TotalAssetsGrp"))
        else None
    )
    fin.total_assets_eoy = _int(elem, "TotalAssetsEOYAmt")
    fin.total_liabilities_eoy = (
        _int(elem, "SumOfTotalLiabilitiesGrp/EOYAmt")
        if elem.find(_tag("SumOfTotalLiabilitiesGrp"))
        else None
    )
    fin.net_assets_eoy = _int(elem, "NetAssetsOrFundBalancesEOYAmt")

    # 990-EZ has fewer governance fields
    gov.schedule_b_required = (
        _bool(elem, "ScheduleBRequiredInd")
        if elem.find(_tag("ScheduleBRequiredInd")) is not None
        else _bool(elem, "ScheduleBNotRequiredInd")
    )
    # Invert ScheduleBNotRequired
    if gov.schedule_b_required is None:
        not_required = _bool(elem, "ScheduleBNotRequiredInd")
        if not_required is not None:
            gov.schedule_b_required = not not_required

    # Officers from Part IV of 990-EZ
    for grp in elem.findall(_tag("OfficerDirectorTrusteeEmplGrp")):
        officer = OfficerCompensation()
        person_nm = grp.find(_tag("PersonNm"))
        if person_nm is not None and person_nm.text:
            officer.name = person_nm.text.strip()
        officer.title = _text(grp, "TitleTxt")
        officer.average_hours_per_week = _float(grp, "AverageHrsPerWkDevotedToPosRt")
        officer.reportable_comp_from_org = _int(grp, "CompensationAmt")
        officer.is_officer = True
        result.officers.append(officer)

    result.parse_quality = 0.6  # 990-EZ has less data


def _parse_990pf(elem, result: Parsed990) -> None:
    """Parse Form 990-PF (private foundation)."""
    fin = result.financials

    result.mission = _text(elem, "ActivityOrMissionDesc")

    # Financials from AnalysisOfRevenueAndExpenses
    analysis = elem.find(_tag("AnalysisOfRevenueAndExpenses"))
    if analysis is not None:
        fin.total_contributions = _int(analysis, "ContriRcvdRevAndExpnssAmt")
        fin.investment_income = _int(analysis, "DividendsRevAndExpnssAmt")
        fin.total_revenue = _int(analysis, "TotalRevAndExpnssAmt")
        fin.salaries_and_compensation = _int(analysis, "CompOfcrDirTrstRevAndExpnssAmt")
        fin.total_expenses = _int(analysis, "TotOprExpensesRevAndExpnssAmt")
        fin.revenue_less_expenses = _int(analysis, "ExcessRevenueOverExpensesAmt")

    # Balance Sheet
    balance = elem.find(_tag("Form990PFBalanceSheetsGrp"))
    if balance is not None:
        fin.total_assets_boy = _grp_int(balance, "TotalAssetsBOYGrp", "BOYAmt")
        fin.total_assets_eoy = _grp_int(balance, "TotalAssetsEOYGrp", "EOYAmt")

    # FMV of assets
    fmv = _int(elem, "FMVAssetsEOYAmt")
    if fmv and not fin.total_assets_eoy:
        fin.total_assets_eoy = fmv

    # Officers from OfficerDirTrstKeyEmplInfoGrp
    info_grp = elem.find(_tag("OfficerDirTrstKeyEmplInfoGrp"))
    if info_grp is not None:
        for officer_grp in info_grp.findall(_tag("OfficerDirTrstKeyEmplGrp")):
            officer = OfficerCompensation()
            person_nm = officer_grp.find(_tag("PersonNm"))
            if person_nm is not None and person_nm.text:
                officer.name = person_nm.text.strip()
            officer.title = _text(officer_grp, "TitleTxt")
            officer.average_hours_per_week = _float(officer_grp, "AverageHrsPerWkDevotedToPosRt")
            officer.reportable_comp_from_org = _int(officer_grp, "CompensationAmt")
            officer.is_officer = True
            result.officers.append(officer)

    result.parse_quality = 0.5  # 990-PF has different structure


# ---------------------------------------------------------------------------
# Convenience: Full Pipeline (search + fetch + parse)
# ---------------------------------------------------------------------------


def fetch_and_parse_990(
    ein: str,
    tax_year: Optional[int] = None,
    return_type: Optional[str] = None,
) -> list[Parsed990]:
    """
    Complete pipeline: search for an EIN, fetch XML for each filing, parse all.

    Args:
        ein: EIN with or without dash.
        tax_year: Optional — only fetch filings for this tax year.
        return_type: Optional — only fetch this return type (e.g., "990").

    Returns:
        List of Parsed990 objects, one per filing, sorted by tax year descending.
    """
    return_types = [return_type] if return_type else None
    search_result = search_990_by_ein(ein, return_types=return_types)

    if search_result.total_found == 0:
        logger.warning("No filings found for EIN %s", ein)
        return []

    results: list[Parsed990] = []
    for filing in search_result.filings:
        if tax_year and filing.tax_year != tax_year:
            continue

        try:
            xml_text = fetch_990_xml(filing)
            parsed = parse_990_xml(
                xml_text,
                source_object_id=filing.object_id,
                source_batch_id=filing.xml_batch_id,
            )
            results.append(parsed)
            logger.info(
                "Parsed %s %s for EIN %s (quality: %.1f)",
                parsed.return_type,
                parsed.tax_year,
                parsed.ein,
                parsed.parse_quality,
            )
        except (IRSNetworkError, IRSParseError) as e:
            logger.error("Failed to fetch/parse %s: %s", filing.object_id, e)
            continue

        time.sleep(POLITE_DELAY)

    return results


# ---------------------------------------------------------------------------
# Utility: Convert Parsed990 to dict (for JSON serialization / API responses)
# ---------------------------------------------------------------------------


def parsed_990_to_dict(parsed: Parsed990) -> dict:
    """Convert a Parsed990 to a JSON-serializable dictionary."""
    return {
        "ein": parsed.ein,
        "ein_formatted": f"{parsed.ein[:2]}-{parsed.ein[2:]}"
        if len(parsed.ein) >= 3
        else parsed.ein,
        "taxpayer_name": parsed.taxpayer_name,
        "tax_year": parsed.tax_year,
        "tax_period_begin": parsed.tax_period_begin,
        "tax_period_end": parsed.tax_period_end,
        "return_type": parsed.return_type,
        "formation_year": parsed.formation_year,
        "state": parsed.state,
        "mission": parsed.mission,
        "website": parsed.website,
        "financials": {
            "total_contributions": parsed.financials.total_contributions,
            "program_service_revenue": parsed.financials.program_service_revenue,
            "investment_income": parsed.financials.investment_income,
            "other_revenue": parsed.financials.other_revenue,
            "total_revenue": parsed.financials.total_revenue,
            "py_total_revenue": parsed.financials.py_total_revenue,
            "py_total_expenses": parsed.financials.py_total_expenses,
            "grants_paid": parsed.financials.grants_paid,
            "salaries_and_compensation": parsed.financials.salaries_and_compensation,
            "professional_fundraising": parsed.financials.professional_fundraising,
            "other_expenses": parsed.financials.other_expenses,
            "total_expenses": parsed.financials.total_expenses,
            "revenue_less_expenses": parsed.financials.revenue_less_expenses,
            "total_assets_boy": parsed.financials.total_assets_boy,
            "total_assets_eoy": parsed.financials.total_assets_eoy,
            "total_liabilities_boy": parsed.financials.total_liabilities_boy,
            "total_liabilities_eoy": parsed.financials.total_liabilities_eoy,
            "net_assets_boy": parsed.financials.net_assets_boy,
            "net_assets_eoy": parsed.financials.net_assets_eoy,
            "cash_non_interest_bearing_eoy": parsed.financials.cash_non_interest_bearing_eoy,
            "savings_and_temp_investments_eoy": parsed.financials.savings_and_temp_investments_eoy,
        },
        "governance": {
            "schedule_b_required": parsed.governance.schedule_b_required,
            "political_campaign_activity": parsed.governance.political_campaign_activity,
            "donor_advised_fund": parsed.governance.donor_advised_fund,
            "schedule_l_required": parsed.governance.schedule_l_required,
            "loan_outstanding": parsed.governance.loan_outstanding,
            "grant_to_related_person": parsed.governance.grant_to_related_person,
            "business_rln_with_org_member": parsed.governance.business_rln_with_org_member,
            "business_rln_with_family": parsed.governance.business_rln_with_family,
            "business_rln_with_35_ctrl": parsed.governance.business_rln_with_35_ctrl,
            "unrelated_business_income": parsed.governance.unrelated_business_income,
            "schedule_j_required": parsed.governance.schedule_j_required,
            "tax_exempt_bonds": parsed.governance.tax_exempt_bonds,
            "voting_members_governing_body": parsed.governance.voting_members_governing_body,
            "independent_voting_members": parsed.governance.independent_voting_members,
            "family_or_business_relationship": parsed.governance.family_or_business_relationship,
            "delegation_of_mgmt_duties": parsed.governance.delegation_of_mgmt_duties,
            "material_diversion_or_misuse": parsed.governance.material_diversion_or_misuse,
            "conflict_of_interest_policy": parsed.governance.conflict_of_interest_policy,
            "annual_disclosure_covered": parsed.governance.annual_disclosure_covered,
            "regular_monitoring_enforced": parsed.governance.regular_monitoring_enforced,
            "whistleblower_policy": parsed.governance.whistleblower_policy,
            "document_retention_policy": parsed.governance.document_retention_policy,
            "compensation_process_ceo": parsed.governance.compensation_process_ceo,
            "compensation_process_other": parsed.governance.compensation_process_other,
            "minutes_of_governing_body": parsed.governance.minutes_of_governing_body,
            "minutes_of_committees": parsed.governance.minutes_of_committees,
            "form990_provided_to_governing_body": parsed.governance.form990_provided_to_governing_body,
        },
        "officers": [
            {
                "name": o.name,
                "title": o.title,
                "average_hours_per_week": o.average_hours_per_week,
                "reportable_comp_from_org": o.reportable_comp_from_org,
                "reportable_comp_from_related": o.reportable_comp_from_related,
                "other_compensation": o.other_compensation,
                "total_compensation": o.total_compensation,
                "is_officer": o.is_officer,
                "is_former": o.is_former,
                "is_highest_compensated": o.is_highest_compensated,
                "is_key_employee": o.is_key_employee,
            }
            for o in parsed.officers
        ],
        "total_reportable_comp_from_org": parsed.total_reportable_comp_from_org,
        "individuals_over_100k": parsed.individuals_over_100k,
        "num_employees": parsed.num_employees,
        "num_volunteers": parsed.num_volunteers,
        "parse_quality": parsed.parse_quality,
        "source": "IRS_TEOS_XML",
        "source_object_id": parsed.source_object_id,
        "source_batch_id": parsed.source_batch_id,
    }


def filing_to_dict(record: IndexRecord) -> dict:
    """Convert an IndexRecord to a JSON-serializable dictionary for search results."""
    return {
        "ein": record.ein_formatted,
        "taxpayer_name": record.taxpayer_name,
        "return_type": record.return_type,
        "tax_year": record.tax_year,
        "tax_period": record.tax_period,
        "object_id": record.object_id,
        "batch_id": record.xml_batch_id,
        "index_year": record.index_year,
    }


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def clear_caches() -> None:
    """Clear all in-memory caches (index + ZIP directory)."""
    _index_cache.clear()
    _zip_directory_cache.clear()
    logger.info("Cleared IRS connector caches")
