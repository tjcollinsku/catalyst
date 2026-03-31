"""
Entity normalization service for Catalyst.

Stage 2 of the entity resolution pipeline. Converts raw extracted strings
into a consistent canonical form that can be reliably compared for matching.

Why normalization matters:
    "HOMAN, JOHN A."  and  "John A. Homan"  and  "john homan"
    are all the same person, but a naive string comparison treats them as
    three distinct people. Normalization collapses them into a single
    comparable form so the matching stage can do its job accurately.

This module is stateless and has no Django imports. It operates purely on
strings and returns strings.

Pipeline position:
    extract_entities()  →  normalize_*()  →  resolve  →  DB
"""

import re
import unicodedata

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_unicode(text: str) -> str:
    """
    Normalize Unicode characters to their closest ASCII equivalent.
    Handles accented characters, smart quotes, em-dashes, etc.
    that sometimes appear in OCR output or copy-pasted text.

    Example:
        "Héctor García-López"  →  "hector garcia-lopez"
    """
    # NFKD decomposition separates base characters from diacritics,
    # then encoding to ASCII with 'ignore' drops the diacritics.
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _collapse_whitespace(text: str) -> str:
    """Replace any sequence of whitespace (including newlines, tabs) with a single space."""
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Name inversion detection and correction
#
# Legal documents often use "LAST, FIRST" order.
# We detect this and reorder to "FIRST LAST" before normalization,
# so both forms land on the same canonical string.
# ---------------------------------------------------------------------------

_INVERTED_NAME_RE = re.compile(r"^([A-Za-z\-']+),\s*([A-Za-z].*?)(?:\s+(Jr\.?|Sr\.?|II|III|IV))?$")


def _uninvert_name(raw: str) -> str:
    """
    If a name is in "LAST, FIRST" format, reorder to "FIRST LAST".
    If it's already in "FIRST LAST" format, return unchanged.

    Examples:
        "HOMAN, JOHN A."    →  "JOHN A. HOMAN"
        "WINNER, MARY JO"   →  "MARY JO WINNER"
        "John A. Homan"     →  "John A. Homan"   (unchanged)
    """
    match = _INVERTED_NAME_RE.match(raw.strip())
    if match:
        last = match.group(1)
        first = match.group(2)
        suffix = match.group(3)
        if suffix:
            return f"{first} {last} {suffix}"
        return f"{first} {last}"
    return raw


# ---------------------------------------------------------------------------
# Public API — Person name normalization
# ---------------------------------------------------------------------------


def normalize_person_name(raw: str) -> str:
    """
    Normalize a person name to a consistent lowercase canonical form.

    Transformations applied (in order):
        1. Unicode normalization (handles OCR artifacts, accented characters)
        2. Uninvert if in "LAST, FIRST" format
        3. Strip honorifics (Mr., Mrs., Dr., etc.) — these vary too much
        4. Strip trailing suffixes that appear inconsistently (Jr, Sr, II)
           NOTE: suffixes are stripped for matching purposes only. The
           original raw value is preserved on the Person record.
        5. Remove punctuation except hyphens and apostrophes in names
        6. Collapse whitespace
        7. Lowercase

    Returns:
        A normalized string suitable for exact-match comparison.

    Examples:
        "HOMAN, JOHN A."        →  "john a homan"
        "John A. Homan"         →  "john a homan"
        "Dr. Mary Jo Winner"    →  "mary jo winner"
        "O'Brien, Patrick"      →  "patrick o'brien"
        "Jean-Paul Baumer Jr."  →  "jean-paul baumer"
    """
    if not raw or not raw.strip():
        return ""

    text = _strip_unicode(raw)
    text = _uninvert_name(text)

    # Strip honorifics
    text = re.sub(
        r"\b(Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Prof\.?|Rev\.?|Hon\.?)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Strip common suffixes (for matching only)
    text = re.sub(
        r"\s*,?\s*\b(Jr\.?|Sr\.?|II|III|IV)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove periods from initials ("A." → "A") and trailing periods
    text = re.sub(r"(?<=[A-Za-z])\.", "", text)

    # Remove any remaining punctuation EXCEPT hyphens and apostrophes
    # (hyphen preserved for: Jean-Paul; apostrophe for: O'Brien)
    text = re.sub(r"[^\w\s\-']", "", text)

    text = _collapse_whitespace(text)
    return text.lower()


# ---------------------------------------------------------------------------
# Public API — Organization name normalization
# ---------------------------------------------------------------------------

# Legal designators to strip when comparing org names.
# "Do Good Ministries, Inc." and "Do Good Ministries" should match.
_ORG_STRIP_DESIGNATORS = re.compile(
    r",?\s*\b("
    r"Inc\.?|Incorporated|LLC|L\.L\.C\.|L\.P\.|LLP|L\.L\.P\."
    r"|Corp\.?|Corporation|Co\.?"
    r")\s*$",
    re.IGNORECASE,
)

# Common words that add noise without uniqueness
_ORG_FILLER_WORDS = re.compile(
    r"\b(the|a|an|of|and|&)\b",
    re.IGNORECASE,
)


def normalize_org_name(raw: str) -> str:
    """
    Normalize an organization name to a consistent lowercase canonical form.

    Transformations applied (in order):
        1. Unicode normalization
        2. Strip trailing legal designators (Inc., LLC, Corp., etc.)
           NOTE: stripped for matching only. Original preserved on the record.
        3. Strip filler words (the, a, an, of, and, &)
        4. Remove punctuation
        5. Collapse whitespace
        6. Lowercase

    Returns:
        A normalized string suitable for exact-match comparison.

    Examples:
        "Do Good Ministries, Inc."    →  "do good ministries"
        "Do Good Ministries"          →  "do good ministries"   ← same!
        "Homan AG Management, LLC"    →  "homan ag management"
        "The Baumer Foundation"       →  "baumer foundation"
    """
    if not raw or not raw.strip():
        return ""

    text = _strip_unicode(raw)

    # Strip trailing legal designators
    text = _ORG_STRIP_DESIGNATORS.sub("", text)

    # Strip filler words
    text = _ORG_FILLER_WORDS.sub(" ", text)

    # Remove punctuation
    text = re.sub(r"[^\w\s]", " ", text)

    text = _collapse_whitespace(text)
    return text.lower()


# ---------------------------------------------------------------------------
# Public API — Date normalization
#
# Dates are already normalized to ISO 8601 by entity_extraction.py.
# This function is provided for cases where dates come in from other
# sources (e.g., manual entry, connector data) and need to be standardized.
# ---------------------------------------------------------------------------


def normalize_date_string(raw: str) -> str | None:
    """
    Attempt to normalize a date string to ISO 8601 (YYYY-MM-DD).

    Handles:
        "03/02/2022"   →  "2022-03-02"
        "3-2-2022"     →  "2022-03-02"
        "2022-03-02"   →  "2022-03-02"  (already ISO, returned as-is)

    Returns None if the string cannot be parsed as a date.
    """
    from datetime import datetime

    formats = [
        "%Y-%m-%d",  # ISO already
        "%m/%d/%Y",  # US slash
        "%m-%d-%Y",  # US dash
        "%d/%m/%Y",  # European slash (less common in US records)
    ]
    raw = raw.strip()
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Public API — Amount normalization
#
# Amounts from extraction.py are already floats. This function handles
# string inputs that may arrive from connector data or manual entry.
# ---------------------------------------------------------------------------


def normalize_amount_string(raw: str) -> float | None:
    """
    Convert a currency string to a float.

    Examples:
        "$4,505,000.00"   →  4505000.0
        "4505000"         →  4505000.0
        "$300,000"        →  300000.0

    Returns None if conversion fails.
    """
    cleaned = re.sub(r"[$,\s]", "", raw.strip())
    try:
        return float(cleaned)
    except ValueError:
        return None
