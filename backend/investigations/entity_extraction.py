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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Person name validation — reject false positives from form boilerplate
#
# IRS 990 forms (especially OCR'd) produce "SECTION, A Iv" or "OH, Example City"
# which the inverted-name regex reads as person names. We filter these out
# using a stopword set covering: US state abbreviations, Roman numerals,
# 990 form section labels, common form field words, and short junk tokens.
# ---------------------------------------------------------------------------

_PERSON_STOPWORDS: set[str] = {
    # US state abbreviations (two-letter)
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    "dc",
    # Roman numerals
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "xi", "xii", "xiii", "xiv", "xv", "xvi",
    # IRS 990 form labels and section markers
    "section", "part", "line", "lines", "schedule", "form",
    "type", "types", "sections", "page", "pages",
    "exhibit", "appendix", "attachment", "item",
    # Common form field words (not person names)
    "date", "sign", "signature", "name", "title", "address",
    "street", "city", "state", "zip", "phone", "fax", "email",
    "number", "amount", "total", "year", "return", "tax", "payroll", "liability",
    "code", "description", "status", "check", "box", "key",
    "here", "from", "and", "the", "for", "not", "yes", "no",
    "other", "see", "instructions", "above", "below",
    "organization", "employer", "revenue", "expenses",
    "compensation", "assets", "liabilities", "net", "gross",
    "beginning", "end", "current", "prior", "amended",
    "initial", "final", "terminated", "group",
    # Geographic words that appear in OCR'd addresses
    "county", "township", "village", "road", "rd", "ave", "avenue",
    "blvd", "drive", "dr", "lane", "ln", "court", "ct", "place", "pl",
    "suite", "ste", "floor", "building", "room", "po", "box",
    "street", "st", "main", "north", "south", "east", "west",
    "hwy", "highway", "pkwy", "parkway", "circle", "cir",
    # Professional credential abbreviations (appear after names: "BROERING, EA")
    "ea", "cpa", "jd", "esq", "md", "do", "phd", "rn", "lpn",
    "cfp", "cfa", "mba", "macc", "dba",
    # Legal designators that leak into person matches
    "llc", "inc", "corp", "ltd",
    # Common OCR junk
    "example_city", "example_township", "maria", "stein",  # Example Charity case city names
    "executive", "ceo", "director", "officer", "president",
    "secretary", "treasurer", "chairman", "vice", "board",
    "member", "trustee", "manager",
}


def _is_plausible_person_name(name: str) -> bool:
    """
    Return True only if the candidate name looks like an actual person name
    rather than form boilerplate, section headers, or address fragments.

    Rules:
      1. Must have at least 2 tokens (first + last minimum)
      2. Every token (ignoring periods) must NOT be a stopword
         — if ALL tokens are stopwords, reject
      3. At least one token must be 3+ chars (rejects "A Vi", "E Iv")
      4. Reject names where any token is a bare Roman numeral (i–xvi)
         unless accompanied by a plausible first name (3+ char non-stopword)
    """
    tokens = name.split()
    if len(tokens) < 2:
        return False

    clean_tokens = [t.rstrip(".").lower() for t in tokens]

    # If ALL tokens are stopwords → reject (e.g. "Oh Example City", "Sign Here")
    non_stop = [t for t in clean_tokens if t not in _PERSON_STOPWORDS]
    if not non_stop:
        return False

    # Need at least 2 non-stopword tokens to form a plausible first+last name.
    # A single real token paired with a stopword (e.g. "Date Karen") is junk.
    if len(non_stop) < 2:
        return False

    # At least one substantive token must be 3+ chars
    # (rejects things like "A Vi", "E Iv")
    substantive = [t for t in non_stop if len(t) >= 3]
    if not substantive:
        return False

    return True


# ---------------------------------------------------------------------------
# Organization name validation — reject 990 form boilerplate
#
# The org regex anchors on legal designators (Inc, Trust, Association, etc.)
# but IRS 990 forms use those words in section headers and field labels:
#   "Section A. Officers, Directors, Trust"
#   "Governance, Management"
#   "Organization Exempt From Inc"
# We filter these the same way we filter person junk.
# ---------------------------------------------------------------------------

_ORG_STOPWORDS: set[str] = {
    # IRS 990 form section / field words
    "section", "part", "line", "lines", "schedule", "form", "forms",
    "page", "exhibit", "appendix", "attachment", "item", "type",
    "return", "tax", "exempt", "exemption", "status",
    "officers", "directors", "trustees", "employees",
    "governance", "management", "policies", "compensation",
    "revenue", "expenses", "income", "assets", "liabilities",
    "net", "gross", "adjusted", "total", "beginning", "end",
    "current", "prior", "amended", "initial", "final",
    "organization", "employer", "public", "private",
    "statement", "financial", "balance", "sheet",
    "contributions", "grants", "program", "fundraising",
    "investment", "investments",
    # Roman numerals
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "xi", "xii", "xiii", "xiv", "xv", "xvi",
    # Generic words that aren't org-name-specific
    "the", "a", "an", "of", "from", "for", "and", "or", "in",
    "to", "on", "at", "by", "with", "as", "is", "are", "was",
    "see", "check", "list", "other", "all", "any", "each",
    # IRS form identifiers that get mashed into org names
    "w-2g", "1099", "w-2", "990", "990-t", "990-ez", "990-pf",
    "1040", "1120", "8868",
    # Designators themselves (already the anchor — if they're the only
    # substantive word, the match is junk like "LI Association")
    "inc", "incorporated", "llc", "corp", "corporation",
    "foundation", "association", "assoc", "trust", "company",
    "co", "partners", "partnership", "lp", "llp",
    "management", "services", "group", "enterprises", "ventures",
    "cic", "nfp", "non-profit", "nonprofit",
    "associates", "ministries",
    # Common OCR artifacts from PDF timestamps/headers
    "pm", "am", "ul", "li",
}


def _is_plausible_org_name(name: str) -> bool:
    """
    Return True only if the candidate org name looks like an actual
    organization rather than 990 form boilerplate.

    Rules:
      1. After stripping legal designators and stopwords, at least one
         substantive word (3+ chars) must remain — that's the actual org name.
      2. The full name must be at least 2 tokens.
    """
    tokens = name.replace(",", " ").replace(".", " ").split()
    if len(tokens) < 2:
        return False

    clean = [t.lower().strip() for t in tokens if t.strip()]

    # Tokens that are NOT stopwords
    non_stop = [t for t in clean if t not in _ORG_STOPWORDS]
    if not non_stop:
        return False

    # At least one non-stopword must be 3+ chars (rejects "LI Association")
    substantive = [t for t in non_stop if len(t) >= 3]
    if not substantive:
        return False

    return True


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
        (?:"""
    + _ORG_DESIGNATORS
    + r""")  # Ending in a legal designator
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
        r"\bthe\s+(\d{1,2})(?:st|nd|rd|th)\s+day\s+of\s+("
        + _MONTH_NAMES
        + r"),?\s+((?:19|20)\d{2})\b",
        re.IGNORECASE,
    ),
]

_MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
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

_PARCEL_PATTERN = re.compile(r"\b([A-Z]?\d{2,3}[-\s]\d{4,7}(?:[.\-]\d{3})?)\b")

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
            # groups: (day, month_name, year) — legal prose
            day = int(groups[0])
            month = _MONTH_MAP.get(groups[1].lower())
            year = int(groups[2])
        else:
            return None

        if month is None or not (1 <= month <= 12) or not (1 <= day <= 31):
            return None

        dt = datetime(year, month, day)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Main extraction function
#
# This is the public API of this module. It scans raw OCR/extracted text and
# returns a dictionary of candidate entities grouped by type.
#
# The caller (entity_resolution.py) will then:
#   1. Fuzzy-match candidates against existing DB entities
#   2. Create new Person/Organization/Property records as needed
#   3. Return a summary of what was created vs. matched
# ---------------------------------------------------------------------------


def extract_entities(text: str, doc_type: str = "OTHER") -> dict[str, list[dict[str, Any]]]:
    """
    Extract structured entity candidates from raw document text.

    Parameters
    ----------
    text : str
        The raw extracted (or OCR'd) text from a document.
    doc_type : str
        The classified document type (e.g. "DEED", "IRS_990", "PARCEL_RECORD").
        Used to tune extraction heuristics.

    Returns
    -------
    dict with keys: persons, orgs, dates, amounts, parcels, filing_refs, financials, meta
        Each value is a list of dicts with at minimum a "raw" key and optional
        "normalized", "context", and type-specific fields.
    """
    if not text or not text.strip():
        return {
            "persons": [],
            "orgs": [],
            "dates": [],
            "amounts": [],
            "parcels": [],
            "filing_refs": [],
            "financials": [],
            "meta": {"doc_type": doc_type, "text_length": 0},
        }

    persons: list[dict[str, Any]] = []
    orgs: list[dict[str, Any]] = []
    dates: list[dict[str, Any]] = []
    amounts: list[dict[str, Any]] = []
    parcels: list[dict[str, Any]] = []
    filing_refs: list[dict[str, Any]] = []

    seen_persons: set[str] = set()
    seen_orgs: set[str] = set()

    # --- Person extraction ---

    # Pass 1: Labeled patterns (high confidence — GRANTOR:, GRANTEE:, etc.)
    for m in _PERSON_LABEL_PATTERN.finditer(text):
        raw = m.group(1).strip()
        normalized = " ".join(raw.split())  # collapse whitespace
        key = normalized.lower()
        if key not in seen_persons and _is_plausible_person_name(normalized):
            seen_persons.add(key)
            persons.append({
                "raw": normalized,
                "context": _get_context(text, m),
                "source": "labeled",
            })

    # Pass 2: Inverted names (EXAMPLE, JOHN A.)
    for m in _PERSON_INVERTED_PATTERN.finditer(text):
        last_part = m.group(1).strip()
        first_part = m.group(2).strip()
        # Re-order to Western format: "John A. Example"
        raw_inverted = f"{first_part} {last_part}".title()
        key = raw_inverted.lower()
        if key not in seen_persons and _is_plausible_person_name(raw_inverted):
            seen_persons.add(key)
            persons.append({
                "raw": raw_inverted,
                "context": _get_context(text, m),
                "source": "inverted",
            })

    # --- Organization extraction ---

    for m in _ORG_PATTERN.finditer(text):
        raw = m.group(1).strip().rstrip(",")
        normalized = " ".join(raw.split())
        key = normalized.lower()
        if key not in seen_orgs and _is_plausible_org_name(normalized):
            seen_orgs.add(key)
            orgs.append({
                "raw": normalized,
                "context": _get_context(text, m),
            })

    # --- Date extraction ---

    seen_dates: set[str] = set()
    for idx, pattern in enumerate(_DATE_PATTERNS):
        for m in pattern.finditer(text):
            raw = m.group(0).strip()
            normalized = _normalize_date(m, idx)
            date_key = normalized or raw
            if date_key not in seen_dates:
                seen_dates.add(date_key)
                entry: dict[str, Any] = {
                    "raw": raw,
                    "context": _get_context(text, m),
                }
                if normalized:
                    entry["normalized"] = normalized
                dates.append(entry)

    # --- Dollar amount extraction ---

    seen_amounts: set[str] = set()
    for m in _AMOUNT_PATTERN.finditer(text):
        raw = m.group(0).strip()
        numeric_str = m.group(1).replace(",", "")
        try:
            normalized_val = float(numeric_str)
        except ValueError:
            continue
        amount_key = str(normalized_val)
        if amount_key not in seen_amounts:
            seen_amounts.add(amount_key)
            amounts.append({
                "raw": raw,
                "normalized": normalized_val,
                "context": _get_context(text, m),
            })

    # --- Parcel number extraction ---

    seen_parcels: set[str] = set()
    for m in _PARCEL_PATTERN.finditer(text):
        raw = m.group(1).strip()
        if raw not in seen_parcels:
            seen_parcels.add(raw)
            parcels.append({
                "raw": raw,
                "context": _get_context(text, m),
            })

    # --- Filing reference extraction ---

    seen_refs: set[str] = set()
    for m in _FILING_REF_PATTERN.finditer(text):
        raw = m.group(1).strip()
        if raw not in seen_refs:
            seen_refs.add(raw)
            filing_refs.append({
                "raw": raw,
                "context": _get_context(text, m),
            })

    # --- IRS 990 financial extraction (doc_type-specific) ---

    financials: list[dict[str, Any]] = []
    if doc_type in ("IRS_990", "IRS_990T"):
        financials = _extract_990_financials(text)

    return {
        "persons": persons,
        "orgs": orgs,
        "dates": dates,
        "amounts": amounts,
        "parcels": parcels,
        "filing_refs": filing_refs,
        "financials": financials,
        "meta": {
            "doc_type": doc_type,
            "text_length": len(text),
            "person_count": len(persons),
            "org_count": len(orgs),
            "date_count": len(dates),
            "amount_count": len(amounts),
            "parcel_count": len(parcels),
            "filing_ref_count": len(filing_refs),
        },
    }


# ---------------------------------------------------------------------------
# IRS 990 financial line-item extraction
#
# The 990 form has specific line numbers with financial figures:
#   Line 8:  Total contributions and grants
#   Line 9:  Program service revenue
#   Line 12: Total revenue
#   Line 18: Total expenses
#   Line 19: Revenue less expenses
#   Line 20: Total assets (BOY)
#   Line 22: Total liabilities (BOY)
#
# We look for these labeled lines and extract the dollar figures.
# ---------------------------------------------------------------------------

_990_LINE_PATTERNS = [
    ("total_revenue", re.compile(
        r"total\s+revenue[^\n$]*?\$?\s*([\d,]{4,}(?:\.\d{2})?)", re.IGNORECASE
    )),
    ("total_expenses", re.compile(
        r"total\s+(?:functional\s+)?expenses[^\n$]*?\$?\s*([\d,]{4,}(?:\.\d{2})?)", re.IGNORECASE
    )),
    ("net_income", re.compile(
        r"revenue\s+less\s+expenses[^\n$]*?\$?\s*([\d,]{4,}(?:\.\d{2})?)", re.IGNORECASE
    )),
    ("total_assets_eoy", re.compile(
        r"total\s+assets[^\n$]*?\$?\s*([\d,]{4,}(?:\.\d{2})?)", re.IGNORECASE
    )),
    ("total_liabilities_eoy", re.compile(
        r"total\s+liabilities[^\n$]*?\$?\s*([\d,]{4,}(?:\.\d{2})?)", re.IGNORECASE
    )),
    ("net_assets_eoy", re.compile(
        r"net\s+assets?\s+or\s+fund\s+balances?[^\n$]*?\$?\s*([\d,]{4,}(?:\.\d{2})?)", re.IGNORECASE
    )),
    ("contributions_and_grants", re.compile(
        r"contributions\s+and\s+grants[^\n$]*?\$?\s*([\d,]{4,}(?:\.\d{2})?)", re.IGNORECASE
    )),
    ("program_service_revenue", re.compile(
        r"program\s+service\s+revenue[^\n$]*?\$?\s*([\d,]{4,}(?:\.\d{2})?)", re.IGNORECASE
    )),
]

# Tax year pattern — 990 forms have "Tax year beginning ... ending ..."
_TAX_YEAR_PATTERN = re.compile(
    r"tax\s+(?:year|period)\s+(?:beginning|ending)\s+.*?((?:19|20)\d{2})",
    re.IGNORECASE,
)


def _extract_990_financials(text: str) -> list[dict[str, Any]]:
    """
    Extract IRS 990 financial line items from OCR'd form text.

    Returns a list of dicts with keys: field, raw, value.
    """
    results: list[dict[str, Any]] = []
    for field_name, pattern in _990_LINE_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1).strip()
            try:
                value = float(raw.replace(",", ""))
            except ValueError:
                continue
            results.append({
                "field": field_name,
                "raw": raw,
                "value": value,
            })

    # Try to extract tax year
    year_match = _TAX_YEAR_PATTERN.search(text)
    if year_match:
        results.append({
            "field": "tax_year",
            "raw": year_match.group(1),
            "value": int(year_match.group(1)),
        })

    return results


# ---------------------------------------------------------------------------
# County Auditor Parcel Card Parser
#
# Darke County (and many Ohio counties using darkecountyrealestate.org or
# Beacon portals) produce parcel card PDFs with a consistent structure:
#
#   Page 1: Header, Location (parcel, owner, address, municipality,
#           township, school district, mailing address), Valuation summary
#   Page 2: Historic valuation table, Legal section, property details
#   Page 3: Sales history table, Land details, Improvements
#   Page 4: Tax information
#   Page 5: Tax distributions, Special assessments
#
# The OCR text has a label-on-one-line, value-on-next-line structure:
#   "Owner\nEXAMPLE CHARITY INC\n"
#   "Address\n47 PATTERSON\n"
#
# Sales history is a multi-row table where each sale spans multiple lines
# because PDF text extraction wraps long buyer/seller names.
#
# This parser extracts structured data that feeds into:
#   - Property model (parcel_number, address, county, assessed_value, purchase_price)
#   - PropertyTransaction model (date, buyer, seller, price, deed type, book/page)
#   - Entity extraction (owner names → Person/Organization entities)
#   - Signal rules SR-003 (valuation anomaly) and SR-005 (zero consideration)
# ---------------------------------------------------------------------------

@dataclass
class ParcelSale:
    """A single sale transaction from a parcel card's Sales table."""
    date: str | None = None           # "9/15/2022"
    buyer: str | None = None          # "EXAMPLE CHARITY INC"
    seller: str | None = None         # "INSIDER KYLE J"
    conveyance_number: str | None = None
    deed_type: str | None = None      # "WARRANTY DEED"
    book: str | None = None           # "558"
    page: str | None = None           # "861"
    valid: str | None = None          # "YES" / "NO"
    parcels_in_sale: int | None = None
    amount: float | None = None       # 300000.00


@dataclass
class ValuationYear:
    """A single row from the valuation history table."""
    year: int
    land_appraised: float | None = None
    improvements_appraised: float | None = None
    total_appraised: float | None = None
    land_assessed: float | None = None
    improvements_assessed: float | None = None
    total_assessed: float | None = None


@dataclass
class AuditorParcelCard:
    """
    Structured data extracted from a county auditor parcel card PDF.

    This is the output of parse_auditor_parcel_card(). All fields are
    optional because OCR may fail to capture any given section.
    """
    # Location
    parcel_number: str | None = None
    owner: str | None = None
    address: str | None = None
    municipality: str | None = None
    township: str | None = None
    school_district: str | None = None
    county: str | None = None

    # Mailing address
    mailing_name: str | None = None
    mailing_address: str | None = None
    mailing_city_state_zip: str | None = None

    # Valuation summary (most recent year)
    current_appraised: float | None = None
    current_assessed: float | None = None
    most_recent_sale_date: str | None = None
    most_recent_sale_price: float | None = None
    acres: float | None = None

    # Legal
    legal_description: str | None = None
    land_use_code: str | None = None
    owner_occupied: str | None = None
    homestead_reduction: str | None = None
    foreclosure: str | None = None

    # Tax
    annual_tax: float | None = None
    tax_rate: float | None = None

    # History
    valuation_history: list = field(default_factory=list)   # list[ValuationYear]
    sales_history: list = field(default_factory=list)        # list[ParcelSale]


def _parse_dollar(text: str | None) -> float | None:
    """Parse a dollar string like '$300,000.00' into a float."""
    if not text:
        return None
    cleaned = text.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_field_after_label(text: str, label: str) -> str | None:
    """
    Extract the value on the line immediately after a label line.

    Given OCR text like:
        "Owner\nEXAMPLE CHARITY INC\n"

    _extract_field_after_label(text, "Owner") returns "EXAMPLE CHARITY INC"
    """
    pattern = re.compile(
        r"^" + re.escape(label) + r"\s*$\n(.+?)$",
        re.MULTILINE,
    )
    m = pattern.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_valuation_history(text: str) -> list:
    """
    Extract valuation history rows from the parcel card text.

    The table appears between "Appraised (100%)" header and
    "Historic Appraised" footer. Each row has a year followed by
    6 dollar values (land appraised, improvements appraised, total appraised,
    land assessed, improvements assessed, total assessed).
    """
    results = []

    # Constrain to the valuation table section only
    val_start = re.search(r"Appraised\s+\(100%\)\s*\n\s*Assessed\s+\(35%\)", text)
    val_end = re.search(r"Historic\s+Appraised", text)
    if not val_start:
        return results

    start_pos = val_start.end()
    end_pos = val_end.start() if val_end else start_pos + 3000
    val_section = text[start_pos:end_pos]

    lines = val_section.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Look for a year line (standalone 4-digit year)
        if re.match(r"^(19|20)\d{2}$", line):
            year = int(line)
            # Collect the next 6 dollar values
            vals = []
            j = i + 1
            while j < len(lines) and len(vals) < 6:
                val_line = lines[j].strip()
                if re.match(r"^-?\$[\d,]+\.\d{2}$", val_line):
                    vals.append(_parse_dollar(val_line))
                    j += 1
                elif re.match(r"^(19|20)\d{2}$", val_line):
                    break  # hit the next year
                else:
                    j += 1  # skip non-value lines

            if len(vals) == 6:
                results.append(ValuationYear(
                    year=year,
                    land_appraised=vals[0],
                    improvements_appraised=vals[1],
                    total_appraised=vals[2],
                    land_assessed=vals[3],
                    improvements_assessed=vals[4],
                    total_assessed=vals[5],
                ))
            i = j
        else:
            i += 1

    return results


def _extract_sales_history(text: str) -> list:
    """
    Extract sales history from the parcel card text.

    Sales table OCR structure per sale:
        Line 0:  date (M/D/YYYY)
        Lines 1-N: buyer name (ALL CAPS, 1-3 lines)
        Lines N+1-M: seller name (ALL CAPS, 1-3 lines, or "Unknown")
        Line M+1: conveyance number (digits only, 1-6 digits, or "0")
        Line M+2: deed type prefix ("WD-", "QC-", or "Unknown")
        Line M+3: deed type name ("WARRANTY", or empty)
        Line M+4: deed type continued ("DEED", or empty)
        Line M+5: book number
        Line M+6: page number
        Line M+7: book/page combined ("558/861")
        Line M+8: valid ("YES" / "NO" / "UNKNOWN")
        Line M+9: parcels in sale count
        Line M+10: amount ("$300,000.00")

    Strategy: collect all lines between dates into chunks, then parse
    each chunk by walking from the END backwards (amount, parcels, valid,
    book/page, deed type, conveyance) leaving the name lines at the front.
    """
    results = []

    # Find the Sales section
    sales_match = re.search(r"\bSales\s*\n\s*Date\s*\n\s*Buyer\s*\n\s*Seller\b", text)
    if not sales_match:
        return results

    sales_text = text[sales_match.end():]

    # Cut off at "Land\n" section header to avoid bleeding
    land_cutoff = re.search(r"\nLand\s*\nLand\s+Type\b", sales_text)
    if land_cutoff:
        sales_text = sales_text[:land_cutoff.start()]

    lines = [ln.strip() for ln in sales_text.split("\n") if ln.strip()]

    date_pattern = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
    amount_pattern = re.compile(r"^-?\$[\d,]+\.\d{2}$")

    # Split into chunks: each chunk starts with a date, ends with amount
    sale_chunks: list[list[str]] = []
    current_chunk: list[str] = []

    for line in lines:
        if date_pattern.match(line):
            if current_chunk:
                sale_chunks.append(current_chunk)
            current_chunk = [line]
        elif current_chunk:
            current_chunk.append(line)
            if amount_pattern.match(line):
                sale_chunks.append(current_chunk)
                current_chunk = []

    if current_chunk:
        sale_chunks.append(current_chunk)

    for chunk in sale_chunks:
        if len(chunk) < 3:
            continue
        sale = ParcelSale()
        sale.date = chunk[0]

        # Parse from the END backwards to identify structured fields
        # The last line is the amount
        if amount_pattern.match(chunk[-1]):
            sale.amount = _parse_dollar(chunk[-1])
        else:
            continue  # malformed — skip

        # Walk backwards from amount to find structured fields
        # Expected order (from end): amount, parcels_count, valid, book/page,
        # page, book, deed_name(s), deed_prefix, conveyance
        tail = chunk[1:-1]  # everything between date and amount

        # Find conveyance number: first standalone number after names
        # Strategy: the conveyance number is the first line that is purely
        # digits (or "0") after the name block ends.
        conv_idx = None
        for idx, line in enumerate(tail):
            if re.match(r"^\d{1,6}$", line) and not re.match(r"^(19|20)\d{2}$", line):
                conv_idx = idx
                break
            # "Unknown" as a standalone line also signals end of names for old records
            if line == "Unknown" and idx > 0:
                conv_idx = idx
                break

        if conv_idx is not None:
            # Name lines are everything before conveyance
            name_lines = tail[:conv_idx]

            # Conveyance number
            if tail[conv_idx] != "Unknown":
                sale.conveyance_number = tail[conv_idx]

            # Remaining lines after conveyance: deed type, book, page, book/page, valid, parcels
            after_conv = tail[conv_idx + 1:]

            # Look for book/page pattern
            for line in after_conv:
                bp = re.match(r"^(\d{1,4})/(\d{1,4})$", line)
                if bp:
                    sale.book = bp.group(1)
                    sale.page = bp.group(2)
                    break
                # Also check "NNN NNN" with slash on separate line
                bp2 = re.match(r"^(\d{1,4})\s+(\d{1,4})$", line)
                if bp2 and "/" in " ".join(after_conv):
                    sale.book = bp2.group(1)
                    sale.page = bp2.group(2)
                    break

            # Deed type
            after_text = " ".join(after_conv)
            deed_match = re.search(
                r"(WD|QC|LC|FI|SH)"
                r"[-\s]*(WARRANTY\s+DEED|QUIT\s+CLAIM|LAND\s+CONTRACT|"
                r"FIDUCIARY|SHERIFF)",
                after_text, re.IGNORECASE,
            )
            if deed_match:
                sale.deed_type = deed_match.group(0).strip()

            # Valid flag
            if "\nYES\n" in "\n" + "\n".join(after_conv) + "\n" or "YES" in after_conv:
                sale.valid = "YES"
            elif "\nNO\n" in "\n" + "\n".join(after_conv) + "\n" or "NO" in after_conv:
                sale.valid = "NO"
            else:
                sale.valid = "UNKNOWN"
        else:
            # Couldn't find conveyance — all middle lines are names
            name_lines = tail

        # Split name_lines into buyer and seller
        # Names are ALL CAPS. The buyer comes first, seller second.
        # Each name is typically 1-3 lines. We need to find the boundary.
        #
        # Heuristic: look for a "word break" where a new surname starts.
        # Surnames start with an uppercase word that doesn't continue the
        # previous name. We detect this by checking if a line starts a new
        # "last name" pattern (single uppercase word).
        #
        # Simpler approach: the table always has buyer then seller.
        # We know from the data that names wrap at about 15 chars per line.
        # Group consecutive lines that form a coherent name.

        if name_lines:
            # Build name candidates by grouping lines
            # A new name starts when we see a line that begins with a different
            # capitalized word pattern after already having some content
            names = _split_buyer_seller(name_lines)
            if len(names) >= 2:
                sale.buyer = names[0]
                sale.seller = names[1]
            elif len(names) == 1:
                sale.buyer = names[0]

        results.append(sale)

    return results


def _split_buyer_seller(name_lines: list[str]) -> list[str]:
    """
    Split a sequence of ALL-CAPS name lines into [buyer, seller].

    The OCR produces lines like:
        ["EXAMPLE CHARITY IN", "HIS NAME INC", "INSIDER KYLE", "J"]
        → buyer="EXAMPLE CHARITY INC", seller="INSIDER KYLE J"

    Strategy: Build the full text and look for known entity patterns
    (LLC, INC, CORP, etc.) as natural boundaries. If no designator found,
    use heuristic: a single-letter line (like "J") is a middle initial
    or suffix that belongs to the previous name, and a new surname
    (CAPS word not continuing a designator) starts a new name.
    """
    if not name_lines:
        return []

    # Check for "Unknown" entries (old records)
    clean = [ln for ln in name_lines if ln.strip() and ln.strip() != "Unknown"]
    if not clean:
        return []

    full = " ".join(clean)

    # Strategy 1: Look for legal designators as split points
    # If the text contains "INC" or "LLC" etc., everything up to and including
    # that designator is the buyer, the rest is the seller.
    designator_pattern = re.compile(
        r"\b(INC\.?|LLC|L\.?L\.?C\.?|CORP\.?|CORPORATION|TRUST|FOUNDATION|MINISTRIES"
        r"|ASSOCIATION|ASSOC\.?|COMPANY|CO\.?|LTD\.?|LP|LLP)\b",
        re.IGNORECASE,
    )

    # Find ALL designator positions
    designator_matches = list(designator_pattern.finditer(full))

    if designator_matches:
        # Use the FIRST designator as the end of buyer name
        first_des = designator_matches[0]
        buyer = full[:first_des.end()].strip()
        seller_part = full[first_des.end():].strip()

        if seller_part:
            return [buyer, seller_part]
        return [buyer]

    # Strategy 2: No designator — split by line grouping
    # Person names are typically "LAST FIRST MIDDLE?" (1-2 lines each)
    # A new last name starts a new person.
    # Simple heuristic: if we have 4+ lines, split in half.
    # If 2-3 lines, first line(s) = buyer, rest = seller.
    if len(clean) == 1:
        return [clean[0]]
    elif len(clean) == 2:
        return [clean[0], clean[1]]
    elif len(clean) == 3:
        # Common: "INSIDER KYLE" / "J" / "GRIESHOP" → buyer=INSIDER KYLE J, seller=GRIESHOP
        # Or: "INSIDER KYLE" / "GRIESHOP" / "DOUGLAS E"
        # Check if line 2 is a single letter (middle initial) → it belongs to line 1
        if len(clean[1]) <= 2:
            return [f"{clean[0]} {clean[1]}", clean[2]]
        else:
            return [clean[0], f"{clean[1]} {clean[2]}"]
    else:
        # 4+ lines — group lines into names
        # Single-letter/initial lines (like "J") attach to the preceding name.
        # A new "surname" line (2+ chars, ALL CAPS, after a complete name)
        # starts a new name group.
        groups = []
        current = [clean[0]]
        for line in clean[1:]:
            # Single letter/initial = continuation of current name
            if len(line) <= 2:
                current.append(line)
            # A new ALL-CAPS word that looks like a surname starts a new group
            # if the current group already has content (at least one line that
            # isn't just an initial)
            elif any(len(c) > 2 for c in current):
                groups.append(" ".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            groups.append(" ".join(current))

        if len(groups) >= 2:
            return [groups[0], " ".join(groups[1:])]
        return groups


def parse_auditor_parcel_card(text: str, county: str = "DARKE") -> AuditorParcelCard:
    """
    Parse OCR text from a county auditor parcel card PDF into structured data.

    Parameters
    ----------
    text : str
        Full OCR text from all pages of the parcel card PDF.
    county : str
        County name (default "DARKE" for Darke County, Ohio).

    Returns
    -------
    AuditorParcelCard
        Structured parcel data ready for Property/PropertyTransaction model creation.
    """
    card = AuditorParcelCard(county=county)

    # --- Location section (label\nvalue pattern) ---
    card.parcel_number = _extract_field_after_label(text, "Parcel")
    card.owner = _extract_field_after_label(text, "Owner")
    card.address = _extract_field_after_label(text, "Address")
    card.municipality = _extract_field_after_label(text, "Municipality")
    card.township = _extract_field_after_label(text, "Township")
    card.school_district = _extract_field_after_label(text, "School District")

    # Mailing address
    card.mailing_name = _extract_field_after_label(text, "Mailing Name")
    card.mailing_address = _extract_field_after_label(text, "Mailing Address")
    card.mailing_city_state_zip = _extract_field_after_label(text, "City, State, Zip")

    # --- Valuation summary (from the condensed header on page 1) ---
    # Pattern: "SOLD:  9/15/2022 $300,000.00"
    sold_match = re.search(
        r"SOLD:\s+(\d{1,2}/\d{1,2}/\d{4})\s+(-?\$[\d,]+\.\d{2})",
        text,
    )
    if sold_match:
        card.most_recent_sale_date = sold_match.group(1)
        card.most_recent_sale_price = _parse_dollar(sold_match.group(2))

    # Pattern: "Appraised\n$37,490.00"
    appraised_match = re.search(r"Appraised\s*\n\s*(-?\$[\d,]+\.\d{2})", text)
    if appraised_match:
        card.current_appraised = _parse_dollar(appraised_match.group(1))

    # Pattern: "ACRES: 0.4000"
    acres_match = re.search(r"ACRES:\s*([\d.]+)", text)
    if acres_match:
        try:
            card.acres = float(acres_match.group(1))
        except ValueError:
            pass

    # --- Legal section ---
    card.legal_description = _extract_field_after_label(text, "Legal Description")
    card.land_use_code = _extract_field_after_label(text, "Land Use")
    card.owner_occupied = _extract_field_after_label(text, "Owner Occupied")
    card.homestead_reduction = _extract_field_after_label(text, "Homestead Reduction")
    card.foreclosure = _extract_field_after_label(text, "Foreclosure")

    # --- Tax ---
    tax_match = re.search(r"Annual\s+Tax\s*\n\s*(-?\$[\d,]+\.\d{2})", text)
    if tax_match:
        card.annual_tax = _parse_dollar(tax_match.group(1))

    rate_match = re.search(r"TAX\s+RATE:\s*([\d.]+)", text)
    if rate_match:
        try:
            card.tax_rate = float(rate_match.group(1))
        except ValueError:
            pass

    # --- Valuation history table ---
    card.valuation_history = _extract_valuation_history(text)

    # If we got valuation history, use the most recent year for current values
    if card.valuation_history:
        latest = card.valuation_history[0]  # sorted newest first in OCR
        if card.current_appraised is None:
            card.current_appraised = latest.total_appraised
        card.current_assessed = latest.total_assessed

    # --- Sales history table ---
    card.sales_history = _extract_sales_history(text)

    return card