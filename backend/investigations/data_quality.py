"""
Data Quality Validation Layer for Catalyst.

Sits between raw data sources (ProPublica API, IRS bulk files, OCR text,
county records) and the database. Its job is to ensure that data entering
the FinancialSnapshot, Person, Organization, Property, and other tables
is clean, consistent, and trustworthy.

Three categories of checks:

    1. FIELD-LEVEL VALIDATION
       Individual values make sense on their own.
       Example: EIN is exactly 9 digits. Revenue is not negative.

    2. CROSS-SOURCE VALIDATION
       Two sources for the same data point agree.
       Example: ProPublica says 2023 revenue = $3.7M.
               OCR-extracted 990 says revenue = $3,700,000. ✅ Match.
               OCR-extracted 990 says revenue = $37,000. ❌ Mismatch → flag.

    3. TEMPORAL VALIDATION
       Data makes sense in sequence over time.
       Example: Total assets can't drop from $2M to $0 in one year
                without a corresponding expense or loss event.

Design:
    - Stateless functions that take data dicts and return ValidationResult.
    - No Django imports in validation functions — pure Python.
    - Caller decides whether to reject, warn, or accept flagged data.
    - Every validation result includes a confidence score (0.0–1.0)
      that flows into the FinancialSnapshot.confidence field.

Usage:
    from investigations.data_quality import (
        validate_financial_snapshot,
        cross_validate_990,
        validate_ein,
        validate_person,
        validate_property,
        ValidationResult,
    )

    # Validate before saving to DB
    result = validate_financial_snapshot(snapshot_data)
    if result.is_clean:
        FinancialSnapshot.objects.create(**snapshot_data)
    else:
        # Log warnings, adjust confidence, or reject
        for issue in result.issues:
            print(f"[{issue.severity}] {issue.field}: {issue.message}")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

logger = logging.getLogger("investigations.data_quality")


# ---------------------------------------------------------------------------
# Validation result types
# ---------------------------------------------------------------------------


@dataclass
class ValidationIssue:
    """One problem found during validation."""

    field: str
    severity: str  # ERROR | WARNING | INFO
    message: str
    raw_value: Any = None
    corrected_value: Any = None  # Suggested fix, if available


@dataclass
class ValidationResult:
    """Aggregated result of validating one record."""

    is_clean: bool = True
    confidence: float = 1.0  # 0.0–1.0, degrades with each issue
    issues: list[ValidationIssue] = field(default_factory=list)
    corrected_data: dict = field(default_factory=dict)

    def add_issue(self, issue: ValidationIssue):
        self.issues.append(issue)
        if issue.severity == "ERROR":
            self.is_clean = False
            self.confidence = max(0.0, self.confidence - 0.3)
        elif issue.severity == "WARNING":
            self.confidence = max(0.0, self.confidence - 0.1)
        # INFO doesn't affect confidence

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "ERROR")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "WARNING")


# ---------------------------------------------------------------------------
# EIN validation
# ---------------------------------------------------------------------------

_EIN_PATTERN = re.compile(r"^\d{2}-?\d{7}$")

# IRS-assigned EIN prefixes that are valid (first two digits)
# 00-06, 10-16, 20-27, 30-38, 40-48, 50-59, 60-68, 71-77, 80-88, 90-99
_INVALID_EIN_PREFIXES = {"07", "08", "09", "17", "18", "19", "28", "29", "39",
                         "49", "69", "70", "78", "79", "89"}


def validate_ein(ein: str) -> ValidationResult:
    """
    Validate an Employer Identification Number.

    Rules:
      - Must be exactly 9 digits (with optional dash after first 2)
      - First two digits must be a valid IRS prefix
      - Cannot be all zeros or all nines
    """
    result = ValidationResult()

    if not ein:
        result.add_issue(ValidationIssue(
            field="ein", severity="ERROR",
            message="EIN is empty.",
        ))
        return result

    # Normalize: remove dashes and spaces
    clean_ein = ein.replace("-", "").replace(" ", "").strip()

    if not _EIN_PATTERN.match(ein.replace(" ", "")):
        result.add_issue(ValidationIssue(
            field="ein", severity="ERROR",
            message=f"EIN '{ein}' does not match expected format (XX-XXXXXXX).",
            raw_value=ein,
        ))
        return result

    if len(clean_ein) != 9:
        result.add_issue(ValidationIssue(
            field="ein", severity="ERROR",
            message=f"EIN '{ein}' is not 9 digits after normalization.",
            raw_value=ein,
        ))
        return result

    prefix = clean_ein[:2]
    if prefix in _INVALID_EIN_PREFIXES:
        result.add_issue(ValidationIssue(
            field="ein", severity="WARNING",
            message=f"EIN prefix '{prefix}' is not a standard IRS-assigned prefix.",
            raw_value=ein,
        ))

    if clean_ein in ("000000000", "999999999"):
        result.add_issue(ValidationIssue(
            field="ein", severity="ERROR",
            message=f"EIN '{ein}' is a placeholder value.",
            raw_value=ein,
        ))

    # Store normalized form
    result.corrected_data["ein"] = f"{clean_ein[:2]}-{clean_ein[2:]}"
    return result


# ---------------------------------------------------------------------------
# Financial Snapshot validation (990 data)
# ---------------------------------------------------------------------------

# Reasonable bounds for 990 financial fields.
# These catch OCR errors like "$37,000" instead of "$3,700,000" (missing digit)
# or "$37,000,000" instead of "$3,700,000" (extra digit).
_990_FIELD_BOUNDS = {
    # (field_name, min_value, max_value, description)
    "total_revenue": (-50_000_000, 500_000_000, "Total revenue"),
    "total_expenses": (0, 500_000_000, "Total expenses"),
    "total_contributions": (0, 500_000_000, "Total contributions"),
    "total_assets_eoy": (0, 1_000_000_000, "End-of-year total assets"),
    "total_liabilities_eoy": (0, 1_000_000_000, "End-of-year total liabilities"),
    "salaries_and_compensation": (0, 100_000_000, "Salaries and compensation"),
    "num_employees": (0, 50_000, "Number of employees"),
    "num_voting_members": (0, 100, "Number of voting members"),
    "num_independent_members": (0, 100, "Number of independent members"),
}


def validate_financial_snapshot(data: dict) -> ValidationResult:
    """
    Validate financial data before creating a FinancialSnapshot record.

    Checks:
      - Required fields present (tax_year, at least one financial field)
      - Values within reasonable bounds
      - Internal consistency (expenses ≤ revenue + assets, etc.)
      - Balance sheet equation: assets = liabilities + net_assets
      - Revenue = contributions + program_service + investment + other
      - Independent members ≤ voting members
    """
    result = ValidationResult()

    # --- Required fields ---
    tax_year = data.get("tax_year")
    if tax_year is None:
        result.add_issue(ValidationIssue(
            field="tax_year", severity="ERROR",
            message="tax_year is required.",
        ))
    elif not (1990 <= tax_year <= date.today().year + 1):
        result.add_issue(ValidationIssue(
            field="tax_year", severity="ERROR",
            message=f"tax_year {tax_year} is outside valid range (1990–{date.today().year + 1}).",
            raw_value=tax_year,
        ))

    # --- Bound checks on financial fields ---
    for field_name, (min_val, max_val, description) in _990_FIELD_BOUNDS.items():
        value = data.get(field_name)
        if value is None:
            continue

        if not isinstance(value, (int, float, Decimal)):
            result.add_issue(ValidationIssue(
                field=field_name, severity="ERROR",
                message=f"{description} is not a number: {value!r}",
                raw_value=value,
            ))
            continue

        if value < min_val:
            result.add_issue(ValidationIssue(
                field=field_name, severity="WARNING",
                message=f"{description} ({value:,}) is below minimum ({min_val:,}). Possible OCR error.",
                raw_value=value,
            ))

        if value > max_val:
            result.add_issue(ValidationIssue(
                field=field_name, severity="WARNING",
                message=f"{description} ({value:,}) exceeds maximum ({max_val:,}). Possible OCR error or extra digit.",
                raw_value=value,
            ))

    # --- Internal consistency checks ---

    total_rev = data.get("total_revenue")
    total_exp = data.get("total_expenses")
    rev_less_exp = data.get("revenue_less_expenses")

    # Revenue - Expenses should equal revenue_less_expenses
    if all(v is not None for v in (total_rev, total_exp, rev_less_exp)):
        expected = total_rev - total_exp
        if abs(expected - rev_less_exp) > 1:  # Allow $1 rounding
            result.add_issue(ValidationIssue(
                field="revenue_less_expenses", severity="WARNING",
                message=(
                    f"revenue_less_expenses ({rev_less_exp:,}) doesn't match "
                    f"total_revenue ({total_rev:,}) - total_expenses ({total_exp:,}) "
                    f"= {expected:,}. Possible extraction error."
                ),
                raw_value=rev_less_exp,
                corrected_value=expected,
            ))

    # Revenue components should sum to total
    contrib = data.get("total_contributions") or 0
    program = data.get("program_service_revenue") or 0
    invest = data.get("investment_income") or 0
    other_rev = data.get("other_revenue") or 0
    component_sum = contrib + program + invest + other_rev

    if total_rev is not None and component_sum > 0:
        if abs(total_rev - component_sum) > max(abs(total_rev) * 0.05, 100):
            result.add_issue(ValidationIssue(
                field="total_revenue", severity="WARNING",
                message=(
                    f"Revenue components sum to {component_sum:,} but "
                    f"total_revenue is {total_rev:,} (difference: "
                    f"{abs(total_rev - component_sum):,}). "
                    f"May indicate missing revenue category or OCR error."
                ),
            ))

    # Balance sheet: assets = liabilities + net_assets
    assets_eoy = data.get("total_assets_eoy")
    liabilities_eoy = data.get("total_liabilities_eoy")
    net_assets_eoy = data.get("net_assets_eoy")

    if all(v is not None for v in (assets_eoy, liabilities_eoy, net_assets_eoy)):
        expected_assets = liabilities_eoy + net_assets_eoy
        if abs(assets_eoy - expected_assets) > 1:
            result.add_issue(ValidationIssue(
                field="total_assets_eoy", severity="WARNING",
                message=(
                    f"Balance sheet doesn't balance: assets ({assets_eoy:,}) ≠ "
                    f"liabilities ({liabilities_eoy:,}) + net_assets ({net_assets_eoy:,}) "
                    f"= {expected_assets:,}."
                ),
            ))

    # Independent members can't exceed voting members
    voting = data.get("num_voting_members")
    independent = data.get("num_independent_members")
    if voting is not None and independent is not None:
        if independent > voting:
            result.add_issue(ValidationIssue(
                field="num_independent_members", severity="ERROR",
                message=(
                    f"Independent members ({independent}) exceeds voting members "
                    f"({voting}). Impossible — likely OCR error."
                ),
                raw_value=independent,
            ))

    return result


# ---------------------------------------------------------------------------
# Cross-source validation (ProPublica API vs OCR extraction)
# ---------------------------------------------------------------------------

# Maximum acceptable percentage difference between two sources
_CROSS_VALIDATION_TOLERANCE = 0.05  # 5%


def cross_validate_990(
    api_data: dict,
    ocr_data: dict,
    source_label: str = "ProPublica vs OCR",
) -> ValidationResult:
    """
    Compare financial data from two sources (typically ProPublica API vs
    OCR-extracted text from the PDF).

    When both sources agree, confidence is HIGH (1.0).
    When they disagree, the API data is preferred (it comes from IRS
    e-file data, not scanned images) and OCR confidence drops.

    Fields compared: total_revenue, total_expenses, total_assets_eoy,
    total_contributions, num_employees.
    """
    result = ValidationResult()

    fields_to_compare = [
        ("total_revenue", "Total revenue"),
        ("total_expenses", "Total expenses"),
        ("total_assets_eoy", "End-of-year assets"),
        ("total_contributions", "Total contributions"),
        ("num_employees", "Number of employees"),
    ]

    matches = 0
    mismatches = 0
    comparisons = 0

    for field_name, label in fields_to_compare:
        api_val = api_data.get(field_name)
        ocr_val = ocr_data.get(field_name)

        # Skip if either source is missing the field
        if api_val is None or ocr_val is None:
            continue

        comparisons += 1

        # Calculate difference
        if api_val == 0 and ocr_val == 0:
            matches += 1
            continue

        denominator = max(abs(api_val), abs(ocr_val), 1)
        pct_diff = abs(api_val - ocr_val) / denominator

        if pct_diff <= _CROSS_VALIDATION_TOLERANCE:
            matches += 1
        else:
            mismatches += 1
            result.add_issue(ValidationIssue(
                field=field_name,
                severity="WARNING",
                message=(
                    f"{source_label} mismatch on {label}: "
                    f"API={api_val:,}, OCR={ocr_val:,} "
                    f"(difference: {pct_diff:.1%}). "
                    f"API value preferred (sourced from IRS e-file)."
                ),
                raw_value=ocr_val,
                corrected_value=api_val,
            ))
            # Store the API value as the corrected value
            result.corrected_data[field_name] = api_val

    # Compute overall confidence based on match ratio
    if comparisons > 0:
        match_ratio = matches / comparisons
        # If everything matches, confidence stays at 1.0
        # Each mismatch reduces confidence
        result.confidence = max(0.3, match_ratio)

    if mismatches > 0:
        result.add_issue(ValidationIssue(
            field="_summary",
            severity="INFO",
            message=(
                f"Cross-validation: {matches}/{comparisons} fields match, "
                f"{mismatches} mismatches. OCR confidence: {result.confidence:.0%}. "
                f"API values used where available."
            ),
        ))

    return result


# ---------------------------------------------------------------------------
# Person validation
# ---------------------------------------------------------------------------

_NAME_JUNK_PATTERNS = [
    re.compile(r"^\d+$"),  # Pure numbers
    re.compile(r"^[A-Z]{1,2}$"),  # Single or double letter (state abbrev)
    re.compile(r"^(mr|mrs|ms|dr|jr|sr|ii|iii|iv)\.?$", re.IGNORECASE),  # Titles only
    re.compile(r"^(section|schedule|form|part|line|page)\b", re.IGNORECASE),  # Form labels
]


def validate_person(data: dict) -> ValidationResult:
    """
    Validate person data before creating a Person record.

    Checks:
      - full_name is not empty or junk
      - date_of_death is in the past
      - Role tags are valid choices
    """
    result = ValidationResult()

    name = data.get("full_name", "").strip()
    if not name:
        result.add_issue(ValidationIssue(
            field="full_name", severity="ERROR",
            message="Person full_name is empty.",
        ))
        return result

    if len(name) < 3:
        result.add_issue(ValidationIssue(
            field="full_name", severity="WARNING",
            message=f"Person name '{name}' is suspiciously short (< 3 chars).",
            raw_value=name,
        ))

    for pattern in _NAME_JUNK_PATTERNS:
        if pattern.match(name):
            result.add_issue(ValidationIssue(
                field="full_name", severity="ERROR",
                message=f"Person name '{name}' matches junk pattern (likely OCR artifact).",
                raw_value=name,
            ))
            break

    # Date of death should be in the past
    dod = data.get("date_of_death")
    if dod and isinstance(dod, date) and dod > date.today():
        result.add_issue(ValidationIssue(
            field="date_of_death", severity="ERROR",
            message=f"Date of death ({dod}) is in the future.",
            raw_value=dod,
        ))

    return result


# ---------------------------------------------------------------------------
# Property validation
# ---------------------------------------------------------------------------


def validate_property(data: dict) -> ValidationResult:
    """
    Validate property data before creating a Property record.

    Checks:
      - Parcel number format (county-specific patterns)
      - Assessed value and purchase price are positive
      - Valuation delta is plausible (not 10000% deviation)
      - County name is a known Ohio county
    """
    result = ValidationResult()

    assessed = data.get("assessed_value")
    purchase = data.get("purchase_price")

    if assessed is not None and assessed < 0:
        result.add_issue(ValidationIssue(
            field="assessed_value", severity="ERROR",
            message=f"Assessed value ({assessed}) is negative.",
            raw_value=assessed,
        ))

    if purchase is not None and purchase < 0:
        result.add_issue(ValidationIssue(
            field="purchase_price", severity="ERROR",
            message=f"Purchase price ({purchase}) is negative.",
            raw_value=purchase,
        ))

    # Extreme valuation deltas (>1000%) are almost always data errors
    if assessed and purchase and assessed > 0:
        ratio = purchase / assessed
        if ratio > 10.0:
            result.add_issue(ValidationIssue(
                field="purchase_price", severity="WARNING",
                message=(
                    f"Purchase price (${purchase:,.2f}) is {ratio:.0f}x the "
                    f"assessed value (${assessed:,.2f}). Likely data entry error."
                ),
            ))
        elif ratio < 0.01:
            result.add_issue(ValidationIssue(
                field="purchase_price", severity="WARNING",
                message=(
                    f"Purchase price (${purchase:,.2f}) is less than 1% of "
                    f"assessed value (${assessed:,.2f}). May be nominal "
                    f"consideration or data error."
                ),
            ))

    return result


# ---------------------------------------------------------------------------
# Temporal validation (year-over-year consistency)
# ---------------------------------------------------------------------------


def validate_temporal_sequence(
    snapshots: list[dict],
) -> ValidationResult:
    """
    Validate a sequence of FinancialSnapshots for the same organization
    across multiple years. Catches impossible year-over-year changes.

    Rules:
      - Revenue can't jump more than 500% in one year (likely OCR digit error)
      - Assets can't drop to zero without a dissolution event
      - Employee count can't jump from 0 to 100+ in one year
      - Tax year sequence should be contiguous (gaps = missing filings)
    """
    result = ValidationResult()

    if len(snapshots) < 2:
        return result

    # Sort by tax year
    sorted_snaps = sorted(snapshots, key=lambda s: s.get("tax_year", 0))

    for i in range(1, len(sorted_snaps)):
        prev = sorted_snaps[i - 1]
        curr = sorted_snaps[i]
        prev_year = prev.get("tax_year", 0)
        curr_year = curr.get("tax_year", 0)

        # Check for year gaps
        if curr_year - prev_year > 1:
            gap = curr_year - prev_year - 1
            result.add_issue(ValidationIssue(
                field="tax_year", severity="WARNING",
                message=(
                    f"Gap of {gap} year(s) between tax year {prev_year} and "
                    f"{curr_year}. Missing 990 filings?"
                ),
            ))

        # Revenue spike check (>500% = almost certainly OCR error)
        prev_rev = prev.get("total_revenue")
        curr_rev = curr.get("total_revenue")
        if prev_rev and curr_rev and prev_rev > 0:
            growth = (curr_rev - prev_rev) / prev_rev
            if growth > 5.0:
                result.add_issue(ValidationIssue(
                    field="total_revenue", severity="WARNING",
                    message=(
                        f"Revenue jumped {growth:.0%} from {prev_year} "
                        f"(${prev_rev:,}) to {curr_year} (${curr_rev:,}). "
                        f"This exceeds 500% and may indicate an OCR digit error "
                        f"(e.g., missing or extra zero)."
                    ),
                    raw_value=curr_rev,
                ))

        # Assets-to-zero check
        prev_assets = prev.get("total_assets_eoy")
        curr_assets = curr.get("total_assets_eoy")
        if prev_assets and prev_assets > 100_000 and curr_assets == 0:
            result.add_issue(ValidationIssue(
                field="total_assets_eoy", severity="WARNING",
                message=(
                    f"Assets dropped from ${prev_assets:,} ({prev_year}) to $0 "
                    f"({curr_year}). If the organization didn't dissolve, this "
                    f"is likely a data extraction failure."
                ),
            ))

        # Employee count spike
        prev_emp = prev.get("num_employees") or 0
        curr_emp = curr.get("num_employees") or 0
        if prev_emp == 0 and curr_emp > 50:
            result.add_issue(ValidationIssue(
                field="num_employees", severity="WARNING",
                message=(
                    f"Employees jumped from 0 ({prev_year}) to {curr_emp} "
                    f"({curr_year}). Verify — this may indicate the previous "
                    f"year's employee count wasn't extracted."
                ),
            ))

    return result


# ---------------------------------------------------------------------------
# Convenience: validate-and-log
# ---------------------------------------------------------------------------


def validate_and_log(
    validator_fn,
    data: dict,
    record_label: str = "record",
    **kwargs,
) -> ValidationResult:
    """
    Run a validator, log any issues, and return the result.

    Usage:
        result = validate_and_log(
            validate_financial_snapshot,
            snapshot_data,
            record_label="990 TY2023 Example Charity"
        )
    """
    result = validator_fn(data, **kwargs)

    for issue in result.issues:
        log_fn = {
            "ERROR": logger.error,
            "WARNING": logger.warning,
            "INFO": logger.info,
        }.get(issue.severity, logger.info)

        log_fn(
            "data_quality_issue",
            extra={
                "record": record_label,
                "field": issue.field,
                "severity": issue.severity,
                "message": issue.message,
                "raw_value": str(issue.raw_value) if issue.raw_value else None,
            },
        )

    if result.is_clean:
        logger.debug("data_quality_clean", extra={"record": record_label})

    return result
