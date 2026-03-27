"""
Document type classification service for Catalyst.

Uses keyword scoring against extracted text to suggest a DocumentType.
The classifier is intentionally rule-based (no ML dependency) so it is
transparent, auditable, and easy to extend with new document types.

Usage:
    from investigations.classification import classify_document

    doc_type = classify_document(extracted_text)
    # Returns a DocumentType value: "DEED", "UCC", "IRS_990", "AUDITOR", "OTHER"
"""

import re

# ---------------------------------------------------------------------------
# Keyword rules
# Each entry is (pattern, weight). Patterns are compiled once at import time.
# Higher total weight wins. Ties fall through to OTHER.
# ---------------------------------------------------------------------------

_RULES: dict[str, list[tuple[re.Pattern, int]]] = {
    "DEED": [
        (re.compile(r"\bwarranty deed\b", re.I), 10),
        (re.compile(r"\bquitclaim deed\b", re.I), 10),
        (re.compile(r"\bgrant(?:or|ee)\b", re.I), 4),
        (re.compile(r"\brecorded\b.{0,60}\bcounty recorder\b", re.I), 6),
        (re.compile(r"\bparcel\b", re.I), 3),
        (re.compile(r"\blegal description\b", re.I), 5),
        (re.compile(r"\bin witness whereof\b", re.I), 4),
        (re.compile(r"\bconvey(?:s|ed|ance)?\b", re.I), 3),
        (re.compile(r"\b(?:lot|block|subdivision)\b", re.I), 2),
    ],
    "PARCEL_RECORD": [
        (re.compile(r"\bparcel(?:\s+number|\s+id)?\b", re.I), 8),
        (re.compile(r"\bcounty auditor\b", re.I), 7),
        (re.compile(r"\bassessed value\b", re.I), 6),
        (re.compile(r"\bmarket value\b", re.I), 5),
        (re.compile(r"\bproperty card\b", re.I), 7),
        (re.compile(r"\bowner name\b", re.I), 4),
    ],
    "RECORDER_INSTRUMENT": [
        (re.compile(r"\binstrument\s*(?:no\.?|number)\b", re.I), 10),
        (re.compile(r"\brecorded\s+on\b", re.I), 6),
        (re.compile(r"\bbook\s+\d+\b", re.I), 3),
        (re.compile(r"\bpage\s+\d+\b", re.I), 3),
        (re.compile(r"\bcounty recorder\b", re.I), 6),
    ],
    "MORTGAGE": [
        (re.compile(r"\bmortgage\b", re.I), 10),
        (re.compile(r"\bmortgagor\b", re.I), 8),
        (re.compile(r"\bmortgagee\b", re.I), 8),
        (re.compile(r"\bnote\b.{0,50}\bprincipal\b", re.I), 5),
        (re.compile(r"\binterest rate\b", re.I), 5),
    ],
    "LIEN": [
        (re.compile(r"\blien\b", re.I), 10),
        (re.compile(r"\btax lien\b", re.I), 9),
        (re.compile(r"\bmechanic(?:'s)? lien\b", re.I), 9),
        (re.compile(r"\bclaim of lien\b", re.I), 8),
        (re.compile(r"\brelease of lien\b", re.I), 7),
    ],
    "UCC": [
        (re.compile(r"\bucc[-\s]?1\b", re.I), 10),
        (re.compile(r"\bucc[-\s]?3\b", re.I), 10),
        (re.compile(r"\bfinancing statement\b", re.I), 10),
        (re.compile(r"\bsecured party\b", re.I), 7),
        (re.compile(r"\bdebtor\b", re.I), 4),
        (re.compile(r"\bcollateral\b", re.I), 5),
        (re.compile(r"\buniform commercial code\b", re.I), 8),
        (re.compile(r"\bsecurity interest\b", re.I), 6),
        (re.compile(r"\bfilings?\b.{0,40}\bsecretary of state\b", re.I), 5),
    ],
    "IRS_990": [
        (re.compile(r"\bform\s+990\b", re.I), 10),
        (re.compile(r"\breturn of organization\b", re.I), 10),
        (re.compile(r"\bexempt from income tax\b", re.I), 8),
        (re.compile(r"\bschedule\s+[a-o]\b", re.I), 3),
        (re.compile(r"\bprogram service revenue\b", re.I), 6),
        (re.compile(r"\bcontributions and grants\b", re.I), 5),
        (re.compile(r"\bemployer identification number\b", re.I), 4),
        (re.compile(r"\bein\b", re.I), 2),
        (re.compile(r"\birs\b", re.I), 2),
        (re.compile(r"\b501\(c\)\b", re.I), 6),
    ],
    "IRS_990T": [
        (re.compile(r"\bform\s+990-t\b", re.I), 10),
        (re.compile(r"\bexempt organization business income tax return\b", re.I), 10),
        (re.compile(r"\bunrelated business taxable income\b", re.I), 8),
        (re.compile(r"\bubti\b", re.I), 6),
    ],
    "SOS_FILING": [
        (re.compile(r"\bsecretary of state\b", re.I), 8),
        (re.compile(r"\barticles of incorporation\b", re.I), 8),
        (re.compile(r"\barticles of organization\b", re.I), 8),
        (re.compile(r"\bentity number\b", re.I), 5),
        (re.compile(r"\bcharter\b", re.I), 5),
    ],
    "COURT_FILING": [
        (re.compile(r"\bin the\s+court\s+of\b", re.I), 8),
        (re.compile(r"\bcase\s+no\.?\b", re.I), 8),
        (re.compile(r"\bplaintiff\b", re.I), 4),
        (re.compile(r"\bdefendant\b", re.I), 4),
        (re.compile(r"\bmotion\b", re.I), 4),
        (re.compile(r"\bcomplaint\b", re.I), 4),
        (re.compile(r"\bjudgment\b", re.I), 5),
    ],
    "DEATH_RECORD": [
        (re.compile(r"\bdeath certificate\b", re.I), 10),
        (re.compile(r"\bdate of death\b", re.I), 8),
        (re.compile(r"\bdecedent\b", re.I), 8),
        (re.compile(r"\bobituary\b", re.I), 8),
        (re.compile(r"\bfuneral\b", re.I), 4),
    ],
    "SUSPECTED_FORGERY": [
        (re.compile(r"\bforger(?:y|ed)?\b", re.I), 8),
        (re.compile(r"\bfraud(?:ulent)?\s+signature\b", re.I), 8),
        (re.compile(r"\bsignature mismatch\b", re.I), 6),
        (re.compile(r"\bnotary\b.{0,60}\binvalid\b", re.I), 7),
        (re.compile(r"\baltered\s+document\b", re.I), 6),
    ],
    "WEB_ARCHIVE": [
        (re.compile(r"\bwayback machine\b", re.I), 10),
        (re.compile(r"\bweb archive\b", re.I), 8),
        (re.compile(r"\bhttp[s]?://\S+\b", re.I), 3),
        (re.compile(r"\bscreenshot\b", re.I), 4),
    ],
    "REFERRAL_MEMO": [
        (re.compile(r"\breferral memorandum\b", re.I), 10),
        (re.compile(r"\bcomplaint memo\b", re.I), 8),
        (re.compile(r"\bsummary of findings\b", re.I), 6),
    ],
    "AUDITOR": [
        (re.compile(r"\bauditor(?:'s)? report\b", re.I), 10),
        (re.compile(r"\bindependent auditor\b", re.I), 10),
        (re.compile(r"\bfinancial statements\b", re.I), 5),
        (re.compile(r"\bbalance sheet\b", re.I), 5),
        (re.compile(r"\binternal controls?\b", re.I), 4),
        (re.compile(r"\bin our opinion\b", re.I), 5),
        (re.compile(r"\bmaterial misstatement\b", re.I), 6),
        (re.compile(r"\bgenerally accepted accounting\b", re.I), 7),
        (re.compile(r"\bgaap\b", re.I), 4),
        (re.compile(r"\bcounty auditor\b", re.I), 8),
        (re.compile(r"\breal property\b.{0,60}\bvalue\b", re.I), 3),
    ],
}

# Minimum score required to claim a specific type; below this → OTHER.
_MIN_SCORE = 8


def classify_document(text: str) -> str:
    """
    Score extracted text against keyword rules for each DocumentType.

    Args:
        text: Extracted text from a document (may be empty).

    Returns:
        A DocumentType string value from the configured rules, or "OTHER".
        Always returns OTHER for empty/short text.
    """
    if not text or len(text) < 50:
        return "OTHER"

    scores: dict[str, int] = {}
    for doc_type, rules in _RULES.items():
        total = 0
        for pattern, weight in rules:
            if pattern.search(text):
                total += weight
        scores[doc_type] = total

    best_type = max(scores, key=lambda t: scores[t])
    if scores[best_type] >= _MIN_SCORE:
        return best_type

    return "OTHER"
