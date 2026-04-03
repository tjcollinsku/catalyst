"""
Form 990 Specialized Parser for Catalyst

This module parses already-extracted IRS Form 990 PDF text and pulls out
structured form answers that Catalyst's signal rules need.

This is NOT OCR — the text is already extracted (via PyMuPDF or Tesseract).
This is pattern matching on the text to find and extract specific Part/Line
values that correspond to IRS Form 990 data fields.

The parser extracts:
- Part IV (Checklist of Required Schedules): Yes/No checkboxes for related-party
  transactions, loans, business transactions, etc.
- Part VI (Governance, Management, and Disclosure): Board composition, policies,
  conflict of interest, whistleblower, compensation process
- Part VII (Compensation): Officer/director/trustee compensation table
- Financials: Revenue, expenses, net assets, compensation totals

Signal Rules Dependencies:
- SR-006: Part IV Lines 28-29 (transactions with interested persons) + Schedule L
- SR-011: Part VI Line 1b (independent board members)
- SR-012: Part VI Line 12a (conflict of interest policy)
- SR-013: Part VII compensation table ($0 at high-revenue orgs)
- SR-021: Financial data (revenue spike year-over-year)
- SR-025: Part IV Line 28 vs Schedule L consistency

Regex Robustness:
- Handles OCR noise (missing spaces, extra whitespace, line breaks in words)
- Recognizes both "Yes" and "X" in yes/no checkbox fields (990 forms use X)
- Handles "No" and empty/blank for negative answers
- Case-insensitive matching
- Works with both searchable PDF text and OCR'd text

IRS Domain Notes:
- Part IV Line 28a-c: Did org report receivables/loans/grants to interested persons?
- Part IV Line 29: Did org report business transactions with interested persons?
  If Yes to any, Schedule L must be filed.
- Part VI Line 1a: Total voting board members
- Part VI Line 1b: Independent voting board members (no material interest in org)
- Part VI Line 12a: Written conflict of interest policy (Yes/No)
- Part VII Section A: Current officers, directors, trustees table with compensation

Usage:
    from investigations.form990_parser import parse_form_990, get_governance_red_flags

    text = extract_from_pdf("Form_990.pdf")  # Already-extracted text
    parsed = parse_form_990(text)

    print(parsed["parse_quality"])  # How confident in extraction?
    print(parsed["part_vi"]["line_12a"])  # Conflict of interest policy

    red_flags = get_governance_red_flags(parsed)
    for flag in red_flags:
        print(flag)  # "No conflict of interest policy", etc.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes for Parsed Results
# ---------------------------------------------------------------------------


@dataclass
class PartIVData:
    """Part IV — Checklist of Required Schedules: Yes/No checkbox answers."""

    # Business transactions with interested persons (Lines 25-29)
    line_25a: Optional[str] = None  # Current officers? (Yes/No)
    line_25b: Optional[str] = None  # Former officers? (Yes/No)
    line_26: Optional[str] = None  # Loans to/from officers? (Yes/No)
    line_28a: Optional[str] = None  # Receivables from officers? (Yes/No)
    line_28b: Optional[str] = None  # Loans to/from officers? (Yes/No)
    line_28c: Optional[str] = None  # Grants/assistance to officers? (Yes/No)
    line_29: Optional[str] = None  # Business transactions with interested persons? (Yes/No)

    def __bool__(self) -> bool:
        """True if any field is populated."""
        return any(getattr(self, k) is not None for k in self.__dataclass_fields__)


@dataclass
class PartVISectionA:
    """Part VI Section A — Governing Body and Management."""

    line_1a: Optional[int] = None  # Number of voting board members
    line_1b: Optional[int] = None  # Number of independent voting members
    line_2: Optional[str] = None  # Family/business relationships among officers? (Yes/No)
    line_3: Optional[str] = None  # Management delegated to external entity? (Yes/No)
    line_4: Optional[str] = None  # Significant changes to governing documents? (Yes/No)
    line_5: Optional[str] = None  # Significant diversion of assets? (Yes/No)
    line_6: Optional[str] = None  # Members or stockholders? (Yes/No)
    line_7a: Optional[str] = None  # Governance decisions subject to approval? (Yes/No)
    line_7b: Optional[str] = None  # Decisions at meeting or written consent? (Yes/No)

    def __bool__(self) -> bool:
        return any(getattr(self, k) is not None for k in self.__dataclass_fields__)


@dataclass
class PartVISectionB:
    """Part VI Section B — Policies."""

    line_10: Optional[str] = None  # Local chapters? (Yes/No)
    line_11: Optional[str] = None  # 990 provided to all board members? (Yes/No)
    line_12a: Optional[str] = (
        None  # Written conflict of interest policy? (Yes/No) — CRITICAL for SR-012
    )
    line_12b: Optional[str] = None  # Officers required to disclose? (Yes/No)
    line_12c: Optional[str] = None  # Regularly monitor/enforce policy? (Yes/No)
    line_13: Optional[str] = None  # Written whistleblower policy? (Yes/No)
    line_14: Optional[str] = None  # Written document retention policy? (Yes/No)
    line_15a: Optional[str] = None  # Process for CEO compensation? (Yes/No)
    line_15b: Optional[str] = None  # Process for other officers? (Yes/No)

    def __bool__(self) -> bool:
        return any(getattr(self, k) is not None for k in self.__dataclass_fields__)


@dataclass
class PartVIData:
    """Part VI — Governance, Management, and Disclosure."""

    section_a: PartVISectionA = field(default_factory=PartVISectionA)
    section_b: PartVISectionB = field(default_factory=PartVISectionB)

    def __bool__(self) -> bool:
        return bool(self.section_a) or bool(self.section_b)


@dataclass
class OfficerCompensation:
    """One officer/director/trustee from Part VII compensation table."""

    name: Optional[str] = None
    title: Optional[str] = None
    average_hours_per_week: Optional[float] = None
    reportable_compensation_from_org: Optional[float] = None
    reportable_compensation_from_related_orgs: Optional[float] = None
    estimated_other_compensation: Optional[float] = None

    def total_compensation(self) -> float:
        """Sum of all three compensation columns."""
        total = 0.0
        if self.reportable_compensation_from_org:
            total += self.reportable_compensation_from_org
        if self.reportable_compensation_from_related_orgs:
            total += self.reportable_compensation_from_related_orgs
        if self.estimated_other_compensation:
            total += self.estimated_other_compensation
        return total


@dataclass
class PartVIIData:
    """Part VII — Compensation of Officers, Directors, Trustees, Key Employees."""

    section_a: list[OfficerCompensation] = field(default_factory=list)  # Current officers

    def __bool__(self) -> bool:
        return len(self.section_a) > 0


@dataclass
class FinancialData:
    """Enhanced financial summary from Form 990 Parts I, VIII, IX, X."""

    total_revenue: Optional[float] = None  # Part I Line 12 or Part VIII total
    total_expenses: Optional[float] = None  # Part I Line 18 or Part IX total
    net_assets_beginning_of_year: Optional[float] = None  # Part X
    net_assets_end_of_year: Optional[float] = None  # Part X
    officer_compensation_total: Optional[float] = None  # Sum from Part VII
    tax_year: Optional[int] = None

    def __bool__(self) -> bool:
        return any(getattr(self, k) is not None for k in self.__dataclass_fields__)


@dataclass
class Form990ParseResult:
    """Complete parsed Form 990 data structure."""

    part_iv: PartIVData = field(default_factory=PartIVData)
    part_vi: PartVIData = field(default_factory=PartVIData)
    part_vii: PartVIIData = field(default_factory=PartVIIData)
    financials: FinancialData = field(default_factory=FinancialData)

    # Metadata
    parse_quality: float = 0.0  # 0.0–1.0: confidence in extraction
    extracted_fields_count: int = 0  # How many fields successfully extracted
    total_fields_attempted: int = 0  # Total fields we looked for

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "part_iv": {
                "line_25a": self.part_iv.line_25a,
                "line_25b": self.part_iv.line_25b,
                "line_26": self.part_iv.line_26,
                "line_28a": self.part_iv.line_28a,
                "line_28b": self.part_iv.line_28b,
                "line_28c": self.part_iv.line_28c,
                "line_29": self.part_iv.line_29,
            },
            "part_vi": {
                "section_a": {
                    "line_1a": self.part_vi.section_a.line_1a,
                    "line_1b": self.part_vi.section_a.line_1b,
                    "line_2": self.part_vi.section_a.line_2,
                    "line_3": self.part_vi.section_a.line_3,
                    "line_4": self.part_vi.section_a.line_4,
                    "line_5": self.part_vi.section_a.line_5,
                    "line_6": self.part_vi.section_a.line_6,
                    "line_7a": self.part_vi.section_a.line_7a,
                    "line_7b": self.part_vi.section_a.line_7b,
                },
                "section_b": {
                    "line_10": self.part_vi.section_b.line_10,
                    "line_11": self.part_vi.section_b.line_11,
                    "line_12a": self.part_vi.section_b.line_12a,
                    "line_12b": self.part_vi.section_b.line_12b,
                    "line_12c": self.part_vi.section_b.line_12c,
                    "line_13": self.part_vi.section_b.line_13,
                    "line_14": self.part_vi.section_b.line_14,
                    "line_15a": self.part_vi.section_b.line_15a,
                    "line_15b": self.part_vi.section_b.line_15b,
                },
            },
            "part_vii": {
                "officers": [
                    {
                        "name": officer.name,
                        "title": officer.title,
                        "average_hours_per_week": officer.average_hours_per_week,
                        "reportable_compensation_from_org": (
                            officer.reportable_compensation_from_org
                        ),
                        "reportable_compensation_from_related_orgs": (
                            officer.reportable_compensation_from_related_orgs
                        ),
                        "estimated_other_compensation": officer.estimated_other_compensation,
                    }
                    for officer in self.part_vii.section_a
                ],
            },
            "financials": {
                "total_revenue": self.financials.total_revenue,
                "total_expenses": self.financials.total_expenses,
                "net_assets_beginning_of_year": self.financials.net_assets_beginning_of_year,
                "net_assets_end_of_year": self.financials.net_assets_end_of_year,
                "officer_compensation_total": self.financials.officer_compensation_total,
                "tax_year": self.financials.tax_year,
            },
            "parse_quality": self.parse_quality,
            "extracted_fields_count": self.extracted_fields_count,
            "total_fields_attempted": self.total_fields_attempted,
        }


# ---------------------------------------------------------------------------
# Regex Pattern Definitions
# Robust to OCR noise, missing spaces, case variance
# ---------------------------------------------------------------------------


def _normalize_yes_no(text: str) -> Optional[str]:
    """
    Convert various yes/no representations to canonical form.

    Handles:
    - "Yes" / "No" (text)
    - "X" / "☒" (checkbox mark on yes)
    - Empty / whitespace (checkbox mark on no)

    Returns: "Yes", "No", or None if ambiguous.
    """
    if not text:
        return None

    text = text.strip().upper()

    # Affirmative responses
    if text in ("YES", "Y", "X", "☒", "TRUE", "✓", "✔"):
        return "Yes"

    # Negative responses
    if text in ("NO", "N", "", " ", "FALSE"):
        return "No"

    # Try to extract from longer text (e.g., "Yes, see schedule" → "Yes")
    if "YES" in text:
        return "Yes"
    if "NO" in text and "YES" not in text:
        return "No"

    return None


def _extract_numeric(text: str) -> Optional[float]:
    """
    Extract a numeric value from text.

    Handles: "5", "5.0", "$5,000.00", etc.
    Returns float or None.
    """
    if not text:
        return None

    # Remove common formatting
    cleaned = text.replace("$", "").replace(",", "").strip()

    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_integer(text: str) -> Optional[int]:
    """
    Extract an integer from text.
    Returns int or None.
    """
    num = _extract_numeric(text)
    if num is not None:
        return int(num)
    return None


# Part IV Yes/No patterns
# Flexible to handle line breaks, extra spaces, OCR noise
_PART_IV_PATTERNS = [
    (
        "line_25a",
        re.compile(
            r"(?:Line\s+)?25\s*a.*?(?:current|former)?\s*officer[s]?.*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_25b",
        re.compile(
            r"(?:Line\s+)?25\s*b.*?(?:former)?\s*officer[s]?.*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_26",
        re.compile(
            r"(?:Line\s+)?26.*?(?:loan|advance).*?officer[s]?.*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_28a",
        re.compile(
            r"(?:Line\s+)?28\s*a.*?(?:receivable|business\s+transaction).*?officer[s]?.*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_28b",
        re.compile(
            r"(?:Line\s+)?28\s*b.*?(?:loan|advance).*?officer[s]?.*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_28c",
        re.compile(
            r"(?:Line\s+)?28\s*c.*?(?:grant|assistance).*?officer[s]?.*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_29",
        re.compile(
            r"(?:Line\s+)?29.*?(?:business\s+)?transaction.*?(?:interested|officer).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
]


# Part VI Section A patterns
_PART_VI_A_PATTERNS = [
    ("line_1a", re.compile(r"1\s*a[^\d]*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)),
    ("line_1b", re.compile(r"1\s*b[^\d]*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)),
    (
        "line_2",
        re.compile(
            r"(?:Line\s+)?2.*?(?:family|business)?\s*(?:relationship).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_3",
        re.compile(
            r"(?:Line\s+)?3.*?(?:delegate|delegated).*?(?:management).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_4",
        re.compile(
            r"(?:Line\s+)?4.*?(?:significant)?\s*(?:change).*?(?:governing\s+)?(?:document).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_5",
        re.compile(
            r"(?:Line\s+)?5.*?(?:significant)?\s*(?:diversion).*?(?:asset).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_6",
        re.compile(
            r"(?:Line\s+)?6.*?(?:member|stockholder).*?(?:(Yes|No|X|☒))", re.IGNORECASE | re.DOTALL
        ),
    ),
    (
        "line_7a",
        re.compile(
            r"(?:Line\s+)?7\s*a.*?(?:governance|decision).*?(?:approval).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_7b",
        re.compile(
            r"(?:Line\s+)?7\s*b.*?(?:meeting|written).*?(?:consent).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
]


# Part VI Section B patterns
_PART_VI_B_PATTERNS = [
    (
        "line_10",
        re.compile(
            r"(?:Line\s+)?10.*?(?:local)?\s*(?:chapter).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_11",
        re.compile(
            r"(?:Line\s+)?11.*?(?:copy|provided).*?(?:990).*?(?:governing|board).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_12a",
        re.compile(
            r"(?:Line\s+)?12\s*a.*?(?:written)?\s*(?:conflict).*?(?:interest).*?(?:policy).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_12b",
        re.compile(
            r"(?:Line\s+)?12\s*b.*?(?:officer|director).*?(?:required).*?(?:disclose).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_12c",
        re.compile(
            r"(?:Line\s+)?12\s*c.*?(?:regularly|monitor).*?(?:enforce).*?(?:compliance).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_13",
        re.compile(
            r"(?:Line\s+)?13.*?(?:written)?\s*(?:whistleblower).*?(?:policy).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_14",
        re.compile(
            r"(?:Line\s+)?14.*?(?:written)?\s*(?:document).*?(?:retention|destruction).*?(?:policy).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_15a",
        re.compile(
            r"(?:Line\s+)?15\s*a.*?(?:process).*?(?:CEO|chief\s+executive).*?(?:compensation).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "line_15b",
        re.compile(
            r"(?:Line\s+)?15\s*b.*?(?:process).*?(?:other|other\s+officer).*?(?:compensation).*?(?:(Yes|No|X|☒))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
]


# ---------------------------------------------------------------------------
# Main Parser Function
# ---------------------------------------------------------------------------


def parse_form_990(text: str) -> dict[str, Any]:
    """
    Parse structured data from Form 990 extracted text.

    Extracts Part IV, Part VI, Part VII, and financial data from already-
    extracted 990 PDF text. This is not OCR — the text layer is already
    available; we're pattern-matching to find form field answers.

    Args:
        text: Already-extracted text from a 990 PDF (searchable or OCR'd)

    Returns:
        dict with keys: 'part_iv', 'part_vi', 'part_vii', 'financials',
        'parse_quality', 'extracted_fields_count', 'total_fields_attempted'

        All values are safe for JSON serialization. Use to_dict() method
        on the Form990ParseResult for complete serialization.

    Example:
        text = extract_from_pdf("Form_990.pdf")
        parsed = parse_form_990(text)

        if parsed["parse_quality"] > 0.6:
            print(f"Form 990 extracted with {parsed['extracted_fields_count']} fields")

        if parsed["part_vi"]["section_b"]["line_12a"] == "No":
            print("No conflict of interest policy found")
    """
    result = Form990ParseResult()

    # Parse Part IV (Yes/No checkboxes)
    _parse_part_iv(text, result)

    # Parse Part VI Section A (Board composition)
    _parse_part_vi_section_a(text, result)

    # Parse Part VI Section B (Policies)
    _parse_part_vi_section_b(text, result)

    # Parse Part VII (Compensation table)
    _parse_part_vii(text, result)

    # Parse Financial data
    _parse_financials(text, result)

    # Calculate parse quality
    _calculate_parse_quality(result)

    logger.info(
        f"Form 990 parse complete: {result.extracted_fields_count} "
        f"of {result.total_fields_attempted} fields extracted "
        f"(quality={result.parse_quality:.2f})"
    )

    return result.to_dict()


def _parse_part_iv(text: str, result: Form990ParseResult) -> None:
    """
    Extract Part IV — Checklist of Required Schedules.

    Looks for Yes/No answers to questions about related-party transactions,
    loans to/from officers, grants, and business transactions.

    IRS Context: If any of these lines = Yes, corresponding schedules must
    be filed (e.g., Schedule L for line 28/29).
    """
    for field_name, pattern in _PART_IV_PATTERNS:
        m = pattern.search(text)
        if m:
            raw_answer = m.group(1).strip() if m.lastindex >= 1 else None
            normalized = _normalize_yes_no(raw_answer) if raw_answer else None
            if normalized:
                setattr(result.part_iv, field_name, normalized)
                result.extracted_fields_count += 1
                logger.debug(f"Part IV {field_name}: {normalized}")
        result.total_fields_attempted += 1


def _parse_part_vi_section_a(text: str, result: Form990ParseResult) -> None:
    """
    Extract Part VI Section A — Governing Body and Management.

    Key fields:
    - Line 1a: Total voting board members (numeric)
    - Line 1b: Independent voting members (numeric) — SR-011 uses this
    - Lines 2-7: Yes/No governance questions

    IRS Context: Line 1b = 0 is a governance red flag. Independent members
    are those with no material financial interest in org transactions.
    """
    for field_name, pattern in _PART_VI_A_PATTERNS:
        m = pattern.search(text)
        if m:
            raw_value = m.group(1).strip() if m.lastindex >= 1 else None
            if raw_value:
                if "line_1" in field_name:
                    # Lines 1a and 1b are numeric
                    value = _extract_integer(raw_value)
                    if value is not None:
                        setattr(result.part_vi.section_a, field_name, value)
                        result.extracted_fields_count += 1
                        logger.debug(f"Part VI Section A {field_name}: {value}")
                else:
                    # All other lines are Yes/No
                    normalized = _normalize_yes_no(raw_value)
                    if normalized:
                        setattr(result.part_vi.section_a, field_name, normalized)
                        result.extracted_fields_count += 1
                        logger.debug(f"Part VI Section A {field_name}: {normalized}")
        result.total_fields_attempted += 1


def _parse_part_vi_section_b(text: str, result: Form990ParseResult) -> None:
    """
    Extract Part VI Section B — Policies.

    CRITICAL for Catalyst: Line 12a (Conflict of Interest Policy) is used by SR-012.

    Extracts:
    - Line 12a: Written conflict of interest policy? (Yes/No)
    - Line 13: Written whistleblower policy? (Yes/No)
    - Line 14: Written document retention policy? (Yes/No)
    - Lines 15a-15b: Compensation committee process? (Yes/No)

    IRS Context: Organizations without documented conflict of interest
    policies create IRC 4958 excess benefit transaction risk.
    """
    for field_name, pattern in _PART_VI_B_PATTERNS:
        m = pattern.search(text)
        if m:
            raw_answer = m.group(1).strip() if m.lastindex >= 1 else None
            if raw_answer:
                normalized = _normalize_yes_no(raw_answer)
                if normalized:
                    setattr(result.part_vi.section_b, field_name, normalized)
                    result.extracted_fields_count += 1
                    if field_name == "line_12a":
                        logger.debug(f"[CRITICAL] Part VI Section B {field_name}: {normalized}")
                    else:
                        logger.debug(f"Part VI Section B {field_name}: {normalized}")
        result.total_fields_attempted += 1


def _parse_part_vii(text: str, result: Form990ParseResult) -> None:
    """
    Extract Part VII — Compensation of Officers, Directors, Trustees.

    Part VII Section A is a table with columns:
    1. Name and Title
    2. Average Hours Per Week
    3. Reportable Compensation from Organization
    4. Reportable Compensation from Related Organizations
    5. Estimated Amount of Other Compensation

    SR-013 uses this data: looks for officers with $0 compensation at
    organizations with gross receipts > $500K.

    IRS Context: All current officers/directors/trustees must be listed
    regardless of compensation. The five highest-paid employees (>$XK)
    and five highest-paid independent contractors also appear.

    Compensation amounts are:
    - From org: W-2 box 1 or 5, or Form 1099-NEC box 1 / 1099-MISC box 6
    - From related: Similar for related entities
    - Other: Fringe benefits, use of property, anything not on W-2/1099
    """
    # Look for Part VII section
    part_vii_match = re.search(
        r"(?:Part\s+VII|Officers.*?Compensation).*?(?=Part\s+VIII|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if not part_vii_match:
        logger.debug("Part VII section not found in text")
        result.total_fields_attempted += 1
        return

    part_vii_text = part_vii_match.group(0)

    # Extract officer table rows
    # Pattern: Name Title HoursPerWeek Comp1 Comp2 Comp3
    # Allows for multiple spaces, commas, dollar signs, newlines in names
    officer_pattern = re.compile(
        r"^(.+?)\s{2,}(.+?)\s{2,}([\d.]+)\s{2,}(\$?[\d,]+|\$?[\d,]+\.\d+)\s{2,}"
        r"(\$?[\d,]+|\$?[\d,]+\.\d+)\s{2,}(\$?[\d,]+|\$?[\d,]+\.\d+)",
        re.MULTILINE | re.IGNORECASE,
    )

    # Find all officer rows, accounting for multi-line names
    lines = part_vii_text.split("\n")
    i = 0
    officers_found = 0

    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines and headers
        if not line or "name" in line.lower() or "title" in line.lower():
            i += 1
            continue

        # Try to match officer row
        m = officer_pattern.match(line)
        if m and officers_found < 20:  # Limit to 20 officers to avoid spam
            try:
                officer = OfficerCompensation(
                    name=m.group(1).strip(),
                    title=m.group(2).strip(),
                    average_hours_per_week=_extract_numeric(m.group(3)),
                    reportable_compensation_from_org=_extract_numeric(m.group(4)),
                    reportable_compensation_from_related_orgs=_extract_numeric(m.group(5)),
                    estimated_other_compensation=_extract_numeric(m.group(6)),
                )
                result.part_vii.section_a.append(officer)
                officers_found += 1
                logger.debug(f"Officer found: {officer.name} ({officer.title})")
            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse officer row: {e}")

        i += 1

    if officers_found > 0:
        result.extracted_fields_count += 1

    result.total_fields_attempted += 1


def _parse_financials(text: str, result: Form990ParseResult) -> None:
    """
    Extract financial data from Form 990 Parts I, VIII, IX, X.

    Looks for:
    - Total Revenue (Part I Line 12 or Part VIII)
    - Total Expenses (Part I Line 18 or Part IX)
    - Net Assets Beginning of Year (Part X)
    - Net Assets End of Year (Part X)
    - Tax Year (from header)

    Also sums officer compensation from Part VII for comparison.

    Used by: SR-021 (revenue spike detection)
    """
    fin = result.financials

    # Extract Total Revenue
    revenue_patterns = [
        r"Total\s+Revenue.*?(\$?[\d,]+(?:\.\d{2})?)",  # Part I Line 12
        r"Part\s+VIII.*?Total\s+Revenue.*?(\$?[\d,]+(?:\.\d{2})?)",
    ]
    for pattern_str in revenue_patterns:
        pattern = re.compile(pattern_str, re.IGNORECASE | re.DOTALL)
        m = pattern.search(text)
        if m:
            fin.total_revenue = _extract_numeric(m.group(1))
            if fin.total_revenue:
                result.extracted_fields_count += 1
                logger.debug(f"Total Revenue: ${fin.total_revenue:,.2f}")
                break
    result.total_fields_attempted += 1

    # Extract Total Expenses
    expense_patterns = [
        r"Total\s+Expense.*?(\$?[\d,]+(?:\.\d{2})?)",  # Part I Line 18
        r"Part\s+IX.*?Total\s+Functional\s+Expense.*?(\$?[\d,]+(?:\.\d{2})?)",
    ]
    for pattern_str in expense_patterns:
        pattern = re.compile(pattern_str, re.IGNORECASE | re.DOTALL)
        m = pattern.search(text)
        if m:
            fin.total_expenses = _extract_numeric(m.group(1))
            if fin.total_expenses:
                result.extracted_fields_count += 1
                logger.debug(f"Total Expenses: ${fin.total_expenses:,.2f}")
                break
    result.total_fields_attempted += 1

    # Extract Net Assets Beginning/End (Part X Balance Sheet)
    net_assets_begin_pattern = re.compile(
        r"Net\s+Asset.*?Beginning.*?(\$?[\d,]+(?:\.\d{2})?)", re.IGNORECASE | re.DOTALL
    )
    m = net_assets_begin_pattern.search(text)
    if m:
        fin.net_assets_beginning_of_year = _extract_numeric(m.group(1))
        if fin.net_assets_beginning_of_year:
            result.extracted_fields_count += 1
            logger.debug(f"Net Assets (beginning): ${fin.net_assets_beginning_of_year:,.2f}")
    result.total_fields_attempted += 1

    net_assets_end_pattern = re.compile(
        r"Net\s+Asset.*?End.*?(\$?[\d,]+(?:\.\d{2})?)", re.IGNORECASE | re.DOTALL
    )
    m = net_assets_end_pattern.search(text)
    if m:
        fin.net_assets_end_of_year = _extract_numeric(m.group(1))
        if fin.net_assets_end_of_year:
            result.extracted_fields_count += 1
            logger.debug(f"Net Assets (end): ${fin.net_assets_end_of_year:,.2f}")
    result.total_fields_attempted += 1

    # Extract Tax Year
    year_pattern = re.compile(
        r"(?:For\s+Tax\s+Year\s+Ending|Tax\s+Year|Year\s+Ended?)\s+(\d{1,2})/(\d{1,2})/(\d{4})",
        re.IGNORECASE,
    )
    m = year_pattern.search(text)
    if m:
        fin.tax_year = int(m.group(3))
        result.extracted_fields_count += 1
        logger.debug(f"Tax Year: {fin.tax_year}")
    result.total_fields_attempted += 1

    # Calculate officer compensation total from Part VII
    if result.part_vii.section_a:
        total_comp = sum(officer.total_compensation() for officer in result.part_vii.section_a)
        fin.officer_compensation_total = total_comp if total_comp > 0 else None
        if fin.officer_compensation_total:
            result.extracted_fields_count += 1
            logger.debug(f"Officer Compensation Total: ${fin.officer_compensation_total:,.2f}")
    result.total_fields_attempted += 1


def _calculate_parse_quality(result: Form990ParseResult) -> None:
    """
    Calculate parse_quality score (0.0–1.0) based on extraction success.

    Quality is: (extracted_fields_count / total_fields_attempted)

    A quality < 0.3 suggests OCR failure, missing form sections, or
    unrecognized form format. Investigation needed.
    """
    if result.total_fields_attempted == 0:
        result.parse_quality = 0.0
    else:
        result.parse_quality = min(
            1.0, result.extracted_fields_count / result.total_fields_attempted
        )


# ---------------------------------------------------------------------------
# Governance and Compensation Analysis Functions
# ---------------------------------------------------------------------------


def get_governance_red_flags(parsed: dict[str, Any]) -> list[str]:
    """
    Analyze parsed Form 990 data and return a list of plain-English red flags.

    Red flags include:
    - No independent board members (Line 1b = 0)
    - No conflict of interest policy (Line 12a = No)
    - No whistleblower policy (Line 13 = No)
    - No document retention policy (Line 14 = No)
    - Transactions with interested persons but no apparent conflict policy

    Args:
        parsed: Result dict from parse_form_990()

    Returns:
        list[str]: Plain-language red flags, empty if none found

    Example:
        red_flags = get_governance_red_flags(parsed)
        for flag in red_flags:
            print(f"⚠️  {flag}")
    """
    flags = []

    # Extract nested data for easier access
    part_vi_a = parsed.get("part_vi", {}).get("section_a", {})
    part_vi_b = parsed.get("part_vi", {}).get("section_b", {})
    part_iv = parsed.get("part_iv", {})

    # SR-011: Zero independent board members
    line_1a = part_vi_a.get("line_1a")
    line_1b = part_vi_a.get("line_1b")

    if line_1a is not None and line_1b is not None:
        if line_1a >= 3 and line_1b == 0:
            flags.append(
                "No independent board members disclosed (Part VI Line 1b = 0) — "
                "governance failure requiring oversight"
            )
        elif line_1a >= 1 and line_1b == 0:
            flags.append(
                "Zero independent board members (Part VI Line 1b = 0) — "
                "all board members are insiders"
            )

    # SR-012: No conflict of interest policy at revenue-generating org
    line_12a = part_vi_b.get("line_12a")
    if line_12a == "No":
        flags.append(
            "No written conflict of interest policy (Part VI Line 12a = No) — "
            "creates excess benefit transaction risk under IRC 4958"
        )

    # Additional governance red flags
    line_12b = part_vi_b.get("line_12b")
    if line_12b == "No":
        flags.append(
            "Officers not required to disclose potential conflicts (Part VI Line 12b = No)"
        )

    line_12c = part_vi_b.get("line_12c")
    if line_12c == "No":
        flags.append(
            "No regular monitoring/enforcement of conflict of interest policy "
            "(Part VI Line 12c = No)"
        )

    line_13 = part_vi_b.get("line_13")
    if line_13 == "No":
        flags.append(
            "No written whistleblower policy (Part VI Line 13 = No) — "
            "reduces ability to detect internal misconduct"
        )

    line_14 = part_vi_b.get("line_14")
    if line_14 == "No":
        flags.append(
            "No written document retention policy (Part VI Line 14 = No) — "
            "creates evidence preservation risk"
        )

    # SR-006: Part IV says transactions with interested persons, but no policy?
    line_28_yes = any(part_iv.get(f"line_28{x}") == "Yes" for x in ("a", "b", "c"))
    line_29_yes = part_iv.get("line_29") == "Yes"

    if (line_28_yes or line_29_yes) and line_12a == "No":
        flags.append(
            "Organization reports transactions with interested persons "
            "(Part IV Line 28/29 = Yes) but has no conflict of interest policy "
            "(Part VI Line 12a = No) — high self-dealing risk"
        )

    return flags


def get_compensation_anomalies(parsed: dict[str, Any]) -> list[str]:
    """
    Analyze officer compensation and flag anomalies.

    Anomalies flagged:
    - $0 compensation for officers at high-revenue org (SR-013)
    - No officers listed
    - Extreme concentration (one officer >> others)

    Args:
        parsed: Result dict from parse_form_990()

    Returns:
        list[str]: Plain-language compensation anomalies

    Example:
        anomalies = get_compensation_anomalies(parsed)
        for anomaly in anomalies:
            print(f"⚠️  {anomaly}")
    """
    flags = []

    officers = parsed.get("part_vii", {}).get("officers", [])
    financials = parsed.get("financials", {})
    total_revenue = financials.get("total_revenue")

    if not officers:
        flags.append("No officers listed in Part VII compensation table")
        return flags

    # SR-013: $0 compensation at high-revenue org
    if total_revenue and total_revenue > 500000:
        zero_comp_officers = [
            o
            for o in officers
            if not o.get("reportable_compensation_from_org")
            and not o.get("reportable_compensation_from_related_orgs")
            and not o.get("estimated_other_compensation")
        ]

        for officer in zero_comp_officers:
            flags.append(
                f"Officer '{officer.get('name', 'Unknown')}' "
                f"({officer.get('title', 'Unknown')}) reports $0 compensation "
                f"at organization with ${total_revenue:,.0f} in revenue — "
                f"possible unreported or hidden compensation"
            )

    # Concentration analysis
    if len(officers) >= 3:
        total_comp = sum(
            (o.get("reportable_compensation_from_org") or 0)
            + (o.get("reportable_compensation_from_related_orgs") or 0)
            + (o.get("estimated_other_compensation") or 0)
            for o in officers
        )

        if total_comp > 0:
            for officer in officers:
                officer_total = (
                    (officer.get("reportable_compensation_from_org") or 0)
                    + (officer.get("reportable_compensation_from_related_orgs") or 0)
                    + (officer.get("estimated_other_compensation") or 0)
                )
                if officer_total > 0:
                    share = officer_total / total_comp
                    if share > 0.75:
                        flags.append(
                            f"Officer '{officer.get('name', 'Unknown')}' "
                            f"receives {share:.0%} of total compensation — "
                            f"extreme concentration"
                        )

    return flags
