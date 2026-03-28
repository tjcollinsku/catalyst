"""
Entity extraction service for Catalyst documents.

Stage 1 of the entity resolution pipeline. Accepts raw extracted text and
returns structured dictionaries of candidate entities found in that text.

This module is intentionally stateless and has no Django imports — it operates
purely on strings and returns plain Python data structures. This makes it easy
to test in isolation and reuse outside the upload pipeline.

Pipeline position:
    extract_from_pdf()  →  extract_entities()  →  normalize  →  resolve  →  DB

Usage:
    from investigations.entity_extraction import extract_entities

    results = extract_entities(text, doc_type="DEED")
    # results = {
    #     "persons":   [{"raw": "John A. Example", "context": "GRANTOR: John A. Example"}],
    #     "orgs":      [{"raw": "Example Charity Ministries, Inc.", "context": "..."}],
    #     "dates":     [{"raw": "March 2, 2022", "normalized": "2022-03-02"}],
    #     "amounts":   [{"raw": "$4,505,000", "normalized": 4505000.0}],
    #     "parcels":   [{"raw": "12-001234.000"}],
    #     "filing_refs": [{"raw": "OH-2022-0012345"}],
    # }
"""

import re
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Person name patterns
#
# Public records documents surface names in several common formats:
#
#   "GRANTOR: John A. Example"         — labeled field, Western order
#   "EXAMPLE, JOHN A."                 — all-caps, inverted (last, first)
#   "John Example"                     — no middle initial
#   "Jane Doe"          — hyphenated surname
#   "signed by John A. Example"        — inline prose reference
#
# Strategy: look for labeled context clues (GRANTOR, GRANTEE, SIGNER, etc.)
# first — these are high-confidence. Then fall back to a general capitalized
# name pattern for prose contexts.
#
# We deliberately do NOT try to catch every possible name. False negatives
# (missing a name) are safer than false positives (treating "County Recorder"
# as a person name). The fuzzy match layer and human review catch the rest.
# ---------------------------------------------------------------------------

# Labels that typically precede a person name in public records documents.
_PERSON_LABEL_PATTERN = re.compile(
    r"""
    (?:                                 # Non-capturing group for label options
        GRANTOR|GRANTEE|DEBTOR|
        SECURED\s+PARTY|SIGNER|
        OFFICER|INCORPORATOR|
        REGISTERED\s+AGENT|NOTARY|
        TRUSTEE|ATTORNEY|WITNESS|
        DECEASED|SIGNED\s+BY|
        PREPARED\s+BY|ACKNOWLEDGED\s+BY
    )
    \s*[:\-]?\s*                        # Optional colon, dash, or whitespace
    (                                   # Capture group: the name itself
        [A-Z][a-z]+                     # First name (capitalized)
        (?:\s+[A-Z]\.?)?                # Optional middle name or initial
        \s+
        [A-Z][a-zA-Z\-']+              # Last name (may contain hyphen or apostrophe)
        (?:\s+(?:Jr\.|Sr\.|II|III|IV))? # Optional suffix
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Inverted format: "EXAMPLE, JOHN A." — common in legal and government documents.
# Matches: ALL-CAPS-LAST, First Middle? (optional suffix)
_PERSON_INVERTED_PATTERN = re.compile(
    r"""
    \b
    ([A-Z]{2,}                          # Last name in ALL CAPS (2+ chars)
    (?:\s+[A-Z]{2,})?)                  # Optional second all-caps word (e.g. hyphenated)
    ,\s*                                # Comma separator
    ([A-Z][A-Za-z]+                     # First name (title-case or ALL CAPS)
    (?:\s+[A-Z]\.?)?)                   # Optional middle name or initial
    (?:\s+(?:Jr\.|Sr\.|II|III|IV))?     # Optional suffix
    \b
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Organization name patterns
#
# Org names in public records almost always include a legal designator:
# Inc., LLC, L.L.C., Corp., Foundation, Ministries, etc.
# We anchor on those designators rather than trying to pattern-match
# arbitrary capitalized phrases.
# ---------------------------------------------------------------------------

_ORG_DESIGNATORS = (
    r"Inc\.?|Incorporated|LLC|L\.L\.C\.|L\.P\.|LLP|L\.L\.P\."
    r"|Corp\.?|Corporation|Foundation|Ministries|Association|Assoc\."
    r"|Authority|Trust|Co\.(?!\s+[a-z])|Company|Partners|Partnership"
    r"|Management|Mgmt\.?|Services|Group|Enterprises|Ventures"
    r"|CIC|NFP|Non-Profit|Nonprofit"
)

_ORG_PATTERN = re.compile(
    r"""
    (                                   # Capture: the full org name
        (?:[A-Z][a-zA-Z0-9&,'.\-]+\s+)+ # One or more capitalized words
        (?:""" + _ORG_DESIGNATORS + r""")  # Ending in a legal designator
        (?:\s*,?\s*(?:Inc\.?|LLC|Corp\.?))? # Optional secondary designator
    )
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Date patterns
#
# Public records use a wide variety of date formats:
#   "March 2, 2022"        — long-form month name
#   "03/02/2022"           — MM/DD/YYYY
#   "2022-03-02"           — ISO 8601 (already normalized)
#   "the 2nd day of March" — legal prose style
# ---------------------------------------------------------------------------

_MONTH_NAMES = (
    r"January|February|March|April|May|June|July|August|"
    r"September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)

_DATE_PATTERNS = [
    # "March 2, 2022" or "March 02, 2022"
    re.compile(
        r"\b(" + _MONTH_NAMES + r")\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b",
        re.IGNORECASE,
    ),
    # "03/02/2022" or "3/2/2022"
    re.compile(r"\b(\d{1,2})/(\d{1,2})/((?:19|20)\d{2})\b"),
    # "2022-03-02" — ISO 8601
    re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b"),
    # "the 2nd day of March, 2022" — legal prose
    re.compile(
        r"\bthe\s+(\d{1,2})(?:st|nd|rd|th)\s+day\s+of\s+(" +
        _MONTH_NAMES + r"),?\s+((?:19|20)\d{2})\b",
        re.IGNORECASE,
    ),
]

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}

# ---------------------------------------------------------------------------
# Dollar amount patterns
#
# Formats seen in public records:
#   "$4,505,000"       — standard US currency
#   "$4,505,000.00"    — with cents
#   "$300,000"         — no cents
#   "4505000.00"       — no dollar sign (sometimes in tables)
#   "FOUR HUNDRED..."  — written out (NOT captured — too error-prone)
# ---------------------------------------------------------------------------

_AMOUNT_PATTERN = re.compile(
    r"""
    \$\s*                               # Dollar sign (required — avoids zip codes, years)
    (                                   # Capture: the numeric portion
        \d{1,3}                         # 1-3 leading digits
        (?:,\d{3})*                     # Thousands groups (optional)
        (?:\.\d{2})?                    # Cents (optional)
    )
    \b
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Parcel number patterns
#
# Ohio county auditor parcel numbers vary by county but follow recognizable
# formats:
#   "12-001234.000"    — Hardin County style
#   "34-0012345"       — two-part numeric
#   "A01-0001-00-000"  — alphanumeric
# ---------------------------------------------------------------------------

_PARCEL_PATTERN = re.compile(
    r"\b([A-Z]?\d{2,3}[-\s]\d{4,7}(?:[.\-]\d{3})?)\b"
)

# ---------------------------------------------------------------------------
# Filing reference number patterns
#
# UCC filing numbers, SOS filing numbers, instrument numbers:
#   "OH 00123456789"     — Ohio UCC
#   "FH 2022-001234"     — county instrument
#   "2022-0012345"       — generic year-prefixed reference
# ---------------------------------------------------------------------------

_FILING_REF_PATTERN = re.compile(
    r"""
    \b
    (
        (?:OH|IN|KY|PA|WV|MI)\s*\d{11}  # Ohio-style UCC: state + 11 digits
        |
        [A-Z]{1,3}\s*\d{4}[-\s]\d{4,8}  # State prefix + year + sequence
        |
        (?:19|20)\d{2}[-\s]\d{5,9}       # Year-prefixed generic reference
    )
    \b
    """,
    re.VERBOSE,
)


# ---------------------------------------------------------------------------
# Context window helper
#
# When we find a match, we want to capture a short slice of surrounding text.
# This serves two purposes:
#   1. Helps the investigator understand how the entity appeared in the document
#   2. May reveal role context ("GRANTOR: John Example" tells us his role)
# ---------------------------------------------------------------------------

def _get_context(text: str, match: re.Match, window: int = 80) -> str:
    """Return up to `window` characters on each side of a regex match."""
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    snippet = text[start:end].replace("\n", " ").strip()
    return snippet


# ---------------------------------------------------------------------------
# Date normalization helper (internal to this module)
# ---------------------------------------------------------------------------

def _normalize_date(match: re.Match, pattern_index: int) -> str | None:
    """
    Attempt to normalize a date regex match to ISO 8601 (YYYY-MM-DD).
    Returns None if the date cannot be parsed.

    pattern_index corresponds to the position in _DATE_PATTERNS:
        0 = "March 2, 2022"
        1 = "03/02/2022"
        2 = "2022-03-02"  (already ISO)
        3 = "the 2nd day of March, 2022"
    """
    try:
        groups = match.groups()
        if pattern_index == 0:
            # groups: (month_name, day, year)
            month = _MONTH_MAP.get(groups[0].lower())
            day = int(groups[1])
            year = int(groups[2])
        elif pattern_index == 1:
            # groups: (month_num, day, year)
            month = int(groups[0])
            day = int(groups[1])
            year = int(groups[2])
        elif pattern_index == 2:
            # groups: (year, month, day) — already ISO
            year = int(groups[0])
            month = int(groups[1])
            day = int(groups[2])
        elif pattern_index == 3:
            # groups: (day, month_name, year)
            day = int(groups[0])
            month = _MONTH_MAP.get(groups[1].lower())
            year = int(groups[2])
        else:
            return None

        if month is None:
            return None

        return datetime(year, month, day).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Amount normalization helper
# ---------------------------------------------------------------------------

def _normalize_amount(raw_numeric: str) -> float | None:
    """
    Convert a raw numeric string like "4,505,000.00" to a Python float.
    Returns None if conversion fails.
    """
    try:
        return float(raw_numeric.replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_entities(text: str, doc_type: str = "OTHER") -> dict[str, list[dict[str, Any]]]:
    """
    Extract candidate entities from raw document text.

    Args:
        text:     Raw extracted text from a document (from extract_from_pdf).
        doc_type: Document type string (e.g., "DEED", "UCC", "IRS_990").
                  Reserved for future use — may enable doc-type-specific
                  pattern weighting in a later milestone.

    Returns:
        A dict with six keys, each a list of match dicts:

        persons:
            raw      — name as it appeared in the document
            context  — surrounding text snippet (up to 80 chars each side)

        orgs:
            raw      — org name as it appeared
            context  — surrounding text snippet

        dates:
            raw        — date string as it appeared
            normalized — ISO 8601 string ("YYYY-MM-DD"), or None if unparseable
            context    — surrounding text snippet

        amounts:
            raw        — full match including $ sign
            normalized — float value, or None if unparseable
            context    — surrounding text snippet

        parcels:
            raw      — parcel number as it appeared
            context  — surrounding text snippet

        filing_refs:
            raw      — filing reference number as it appeared
            context  — surrounding text snippet
    """
    if not text or not text.strip():
        return {
            "persons": [],
            "orgs": [],
            "dates": [],
            "amounts": [],
            "parcels": [],
            "filing_refs": [],
        }

    results: dict[str, list[dict[str, Any]]] = {
        "persons": [],
        "orgs": [],
        "dates": [],
        "amounts": [],
        "parcels": [],
        "filing_refs": [],
    }

    # --- Persons (labeled context) ------------------------------------------
    seen_persons: set[str] = set()
    for match in _PERSON_LABEL_PATTERN.finditer(text):
        raw = match.group(1).strip()
        if raw and raw not in seen_persons:
            seen_persons.add(raw)
            results["persons"].append({
                "raw": raw,
                "context": _get_context(text, match),
            })

    # --- Persons (inverted format) -------------------------------------------
    for match in _PERSON_INVERTED_PATTERN.finditer(text):
        # Re-assemble into "First Last" order for consistency
        last = match.group(1).strip().title()
        first_middle = match.group(2).strip().title()
        raw = f"{first_middle} {last}"
        if raw not in seen_persons:
            seen_persons.add(raw)
            results["persons"].append({
                "raw": raw,
                "context": _get_context(text, match),
            })

    # --- Organizations -------------------------------------------------------
    seen_orgs: set[str] = set()
    for match in _ORG_PATTERN.finditer(text):
        raw = match.group(1).strip().rstrip(",")
        if raw and raw not in seen_orgs and len(raw) > 4:
            seen_orgs.add(raw)
            results["orgs"].append({
                "raw": raw,
                "context": _get_context(text, match),
            })

    # --- Dates ---------------------------------------------------------------
    seen_dates: set[str] = set()
    for pattern_index, pattern in enumerate(_DATE_PATTERNS):
        for match in pattern.finditer(text):
            raw = match.group(0).strip()
            normalized = _normalize_date(match, pattern_index)
            key = normalized or raw  # deduplicate by normalized form when possible
            if key not in seen_dates:
                seen_dates.add(key)
                results["dates"].append({
                    "raw": raw,
                    "normalized": normalized,
                    "context": _get_context(text, match),
                })

    # --- Amounts -------------------------------------------------------------
    seen_amounts: set[float] = set()
    for match in _AMOUNT_PATTERN.finditer(text):
        raw = match.group(0).strip()
        normalized = _normalize_amount(match.group(1))
        # Deduplicate by value — same dollar amount appearing twice is one entry
        if normalized is not None and normalized not in seen_amounts:
            seen_amounts.add(normalized)
            results["amounts"].append({
                "raw": raw,
                "normalized": normalized,
                "context": _get_context(text, match),
            })
        elif normalized is None and raw not in {a["raw"] for a in results["amounts"]}:
            results["amounts"].append({
                "raw": raw,
                "normalized": None,
                "context": _get_context(text, match),
            })

    # --- Parcel numbers ------------------------------------------------------
    seen_parcels: set[str] = set()
    for match in _PARCEL_PATTERN.finditer(text):
        raw = match.group(1).strip()
        if raw not in seen_parcels:
            seen_parcels.add(raw)
            results["parcels"].append({
                "raw": raw,
                "context": _get_context(text, match),
            })

    # --- Filing reference numbers --------------------------------------------
    seen_refs: set[str] = set()
    for match in _FILING_REF_PATTERN.finditer(text):
        raw = match.group(1).strip()
        if raw not in seen_refs:
            seen_refs.add(raw)
            results["filing_refs"].append({
                "raw": raw,
                "context": _get_context(text, match),
            })

    return results
