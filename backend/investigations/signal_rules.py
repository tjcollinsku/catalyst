"""
Signal Detection Engine for Catalyst.

Evaluates cases and documents against the SR-001 through SR-010 rule set
defined in the Catalyst Charter v2.0, Section 3.6.

Design principles:
  - Rule evaluator functions are stateless and side-effect-free.
  - Each evaluator accepts (case, document=None) and returns list[SignalTrigger].
  - A rule returns [] when no signal is triggered — never None.
  - Individual rule failures are caught and logged; one bad rule never blocks the rest.
  - This module has no Django view imports — it only uses ORM models.
  - Deduplication and persistence are handled by persist_signals(), not evaluators.

Entry points:
  evaluate_document(case, document) -> list[SignalTrigger]
      Runs document-scoped rules: SR-001, SR-002, SR-005, SR-006.
      Call immediately after a document is uploaded and text is extracted.

  evaluate_case(case, trigger_doc=None) -> list[SignalTrigger]
      Runs case-scoped cross-document rules: SR-003, SR-004, SR-007,
      SR-008, SR-009, SR-010.
      Call after every upload — case-level patterns may emerge with each new doc.

  persist_signals(case, triggers, trigger_doc=None) -> list[Signal]
      Persists SignalTrigger results to the DB with deduplication.
      Returns list of newly created Signal instances (duplicates skipped).
"""

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

logger = logging.getLogger("investigations.signal_rules")


# ---------------------------------------------------------------------------
# Rule metadata registry
#
# Static lookup table used by the API serializer and admin views.
# Keeps rule titles and descriptions in one place — not on the DB model.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleInfo:
    rule_id: str
    severity: str       # CRITICAL | HIGH | MEDIUM | LOW
    title: str
    description: str    # One-sentence charter description


RULE_REGISTRY: dict[str, RuleInfo] = {
    "SR-001": RuleInfo(
        rule_id="SR-001",
        severity="CRITICAL",
        title="Deceased Person Named in Post-Death Document",
        description=(
            "Document signed or electronically filed by an individual whose "
            "recorded date of death precedes the filing date."
        ),
    ),
    "SR-002": RuleInfo(
        rule_id="SR-002",
        severity="CRITICAL",
        title="Entity Named Before Formation Date",
        description=(
            "Entity named as grantee or party in a document predates the "
            "entity's formation date as recorded with the Secretary of State."
        ),
    ),
    "SR-003": RuleInfo(
        rule_id="SR-003",
        severity="HIGH",
        title="Purchase Price Deviates >50% From Assessed Value",
        description=(
            "Purchase price deviates more than 50% from county-assessed value, "
            "in either direction."
        ),
    ),
    "SR-004": RuleInfo(
        rule_id="SR-004",
        severity="HIGH",
        title="UCC Amendment Burst — Three or More Within 24 Hours",
        description=(
            "Three or more UCC amendments to the same master financing statement "
            "file number occur within a 24-hour window."
        ),
    ),
    "SR-005": RuleInfo(
        rule_id="SR-005",
        severity="HIGH",
        title="Zero-Consideration Transfer Detected",
        description=(
            "Zero-consideration transfer between parties who share a common "
            "officer, attorney, or family relationship in other case documents."
        ),
    ),
    "SR-006": RuleInfo(
        rule_id="SR-006",
        severity="HIGH",
        title="IRS 990 Part IV Line 28 Yes Without Schedule L",
        description=(
            "IRS Form 990 Part IV Line 28a, 28b, or 28c answered Yes with no "
            "corresponding Schedule L present in the filing."
        ),
    ),
    "SR-007": RuleInfo(
        rule_id="SR-007",
        severity="HIGH",
        title="Building Permit Applicant May Not Be Property Owner",
        description=(
            "Building permit applicant differs from the recorded owner of the "
            "parcel on which construction is permitted."
        ),
    ),
    "SR-008": RuleInfo(
        rule_id="SR-008",
        severity="MEDIUM",
        title="Survey Recorded More Than 90 Days Before Purchase",
        description=(
            "Survey or plat recorded for a property more than 90 days before "
            "the recorded purchase date for the same parcel."
        ),
    ),
    "SR-009": RuleInfo(
        rule_id="SR-009",
        severity="MEDIUM",
        title="Single Contractor Named on All Building Permits",
        description=(
            "Single contractor named on 100% of permits for a given applicant "
            "across multiple years with no evidence of competitive bidding."
        ),
    ),
    "SR-010": RuleInfo(
        rule_id="SR-010",
        severity="MEDIUM",
        title="No IRS Form 990 Found for Tax-Exempt Organization",
        description=(
            "Tax-exempt organization has not filed a required Form 990 for one "
            "or more years in which it held tax-exempt status."
        ),
    ),
}


# ---------------------------------------------------------------------------
# SignalTrigger dataclass
#
# Returned by evaluators. Never written to the DB by the evaluator itself.
# The caller (views.py or persist_signals) handles persistence.
# ---------------------------------------------------------------------------

@dataclass
class SignalTrigger:
    rule_id: str
    severity: str
    title: str
    detected_summary: str
    trigger_entity_id: Optional[UUID] = None
    trigger_doc: object = None          # Document model instance or None


# ---------------------------------------------------------------------------
# Text patterns used by document-level rules
# ---------------------------------------------------------------------------

_ZERO_CONSIDERATION_PATTERNS = [
    re.compile(r"\$\s*0\.00\b"),
    re.compile(r"\bno\s+(?:monetary\s+)?consideration\b", re.IGNORECASE),
    re.compile(
        r"\bzero\s+(?:and\s+no[/\-]100\s+)?(?:dollars?|consideration)\b", re.IGNORECASE),
    re.compile(r"\bnominal\s+consideration\b", re.IGNORECASE),
    re.compile(r"\blove\s+and\s+affection\b", re.IGNORECASE),
    re.compile(
        r"\bten\s+dollars?\s+and\s+other\s+valuable\s+consideration\b", re.IGNORECASE),
]

_990_PART4_YES_PATTERNS = [
    re.compile(r"\b28[abc]\b.{0,60}\byes\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"line\s+28[abc].{0,30}\bx\s+yes\b", re.IGNORECASE | re.DOTALL),
]

_SCHEDULE_L_PRESENT_PATTERN = re.compile(
    r"\bschedule\s+l\b",
    re.IGNORECASE,
)

_PERMIT_APPLICANT_PATTERN = re.compile(
    r"(?:applicant|permit\s+holder|owner\s+of\s+record)[:\s]+([A-Z][A-Za-z\s,\.\-]+?)(?:\n|$)",
    re.IGNORECASE,
)

_CONTRACTOR_PATTERN = re.compile(
    r"(?:general\s+)?contractor[:\s]+([A-Z][A-Za-z\s,\.\-]+?)(?:\n|,|$)",
    re.IGNORECASE,
)

_DEED_DOC_TYPES = {"DEED", "RECORDER_INSTRUMENT"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_rule(rule_id: str, fn, results: list, *args, **kwargs):
    """
    Call a rule evaluator inside a try/except so a single bad rule
    never aborts the rest of the evaluation pass.
    """
    try:
        results.extend(fn(*args, **kwargs))
    except Exception:
        logger.exception("signal_rule_evaluation_failed",
                         extra={"rule_id": rule_id})


def _extract_dates_from_text(text: str) -> list[date]:
    """
    Pull normalized date strings out of already-extracted document text
    by calling the entity extraction module.  Returns a list of date objects.
    """
    if not text:
        return []
    # Import here to avoid circular imports at module load time.
    from .entity_extraction import extract_entities
    results = extract_entities(text)
    dates = []
    for entry in results.get("dates", []):
        normalized = entry.get("normalized")
        if normalized:
            try:
                dates.append(date.fromisoformat(normalized))
            except ValueError:
                pass
    return dates


# ---------------------------------------------------------------------------
# SR-001 — Deceased Signer
#
# Checks whether any Person in the case who has a recorded date_of_death
# is named in the document AND the document contains a date that falls after
# that person's date of death.
# ---------------------------------------------------------------------------

def evaluate_sr001_deceased_signer(case, document) -> list[SignalTrigger]:
    if not document or not document.extracted_text:
        return []

    text = document.extracted_text
    text_lower = text.lower()
    triggers = []

    deceased_persons = case.persons.filter(date_of_death__isnull=False)
    if not deceased_persons.exists():
        return []

    doc_dates = _extract_dates_from_text(text)
    if not doc_dates:
        return []

    for person in deceased_persons:
        # Quick name-presence check before doing date comparison.
        name_parts = person.full_name.lower().split()
        last_name = name_parts[-1] if name_parts else ""
        if not last_name or last_name not in text_lower:
            continue

        for doc_date in doc_dates:
            if doc_date > person.date_of_death:
                gap_days = (doc_date - person.date_of_death).days
                triggers.append(SignalTrigger(
                    rule_id="SR-001",
                    severity="CRITICAL",
                    title=RULE_REGISTRY["SR-001"].title,
                    detected_summary=(
                        f"{person.full_name} (date of death: {person.date_of_death}) "
                        f"is referenced in a document dated {doc_date} — "
                        f"{gap_days} days after death."
                    ),
                    trigger_entity_id=person.pk,
                    trigger_doc=document,
                ))
                break   # one signal per deceased person per document

    return triggers


# ---------------------------------------------------------------------------
# SR-002 — Entity Predates Formation Date
#
# Checks whether any Organization in the case has a formation_date set AND
# the organization's name appears in the document AND the document contains a
# date that precedes that formation date.
# ---------------------------------------------------------------------------

def evaluate_sr002_entity_predates_formation(case, document) -> list[SignalTrigger]:
    if not document or not document.extracted_text:
        return []

    text = document.extracted_text
    text_lower = text.lower()
    triggers = []

    orgs_with_formation = case.organizations.filter(
        formation_date__isnull=False)
    if not orgs_with_formation.exists():
        return []

    doc_dates = _extract_dates_from_text(text)
    if not doc_dates:
        return []

    for org in orgs_with_formation:
        if org.name.lower() not in text_lower:
            continue

        for doc_date in doc_dates:
            if doc_date < org.formation_date:
                gap_days = (org.formation_date - doc_date).days
                triggers.append(SignalTrigger(
                    rule_id="SR-002",
                    severity="CRITICAL",
                    title=RULE_REGISTRY["SR-002"].title,
                    detected_summary=(
                        f"'{org.name}' (formation date: {org.formation_date}) "
                        f"is named in a document dated {doc_date} — "
                        f"{gap_days} days before the entity existed."
                    ),
                    trigger_entity_id=org.pk,
                    trigger_doc=document,
                ))
                break   # one signal per org per document

    return triggers


# ---------------------------------------------------------------------------
# SR-003 — Valuation Anomaly
#
# Case-scoped.  Checks all Property records in the case where both
# purchase_price and assessed_value are set.  Flags any deviation > 50%.
# ---------------------------------------------------------------------------

def evaluate_sr003_valuation_anomaly(case, trigger_doc=None) -> list[SignalTrigger]:
    triggers = []

    for prop in case.properties.filter(
        purchase_price__isnull=False,
        assessed_value__isnull=False,
    ):
        if prop.assessed_value == 0:
            continue

        deviation = abs(prop.purchase_price -
                        prop.assessed_value) / prop.assessed_value
        if deviation <= Decimal("0.50"):
            continue

        direction = "above" if prop.purchase_price > prop.assessed_value else "below"
        label = prop.parcel_number or prop.address or str(prop.pk)
        triggers.append(SignalTrigger(
            rule_id="SR-003",
            severity="HIGH",
            title=RULE_REGISTRY["SR-003"].title,
            detected_summary=(
                f"Property '{label}': purchase price ${prop.purchase_price:,.2f} is "
                f"{float(deviation) * 100:.0f}% {direction} assessed value "
                f"${prop.assessed_value:,.2f}."
            ),
            trigger_entity_id=prop.pk,
            trigger_doc=trigger_doc,
        ))

    return triggers


# ---------------------------------------------------------------------------
# SR-004 — UCC Amendment Burst
#
# Case-scoped.  Finds clusters of 3+ FinancialInstrument records with the
# same filing-number prefix where all filing dates fall within a 24-hour
# window.
# ---------------------------------------------------------------------------

def evaluate_sr004_ucc_burst(case, trigger_doc=None) -> list[SignalTrigger]:
    ucc_instruments = list(
        case.financial_instruments.filter(
            instrument_type="UCC_FILING",
            filing_date__isnull=False,
        ).order_by("filing_date")
    )

    if len(ucc_instruments) < 3:
        return []

    # Group by first 16 characters of filing_number as a proxy for the master
    # filing number.  Empty / missing filing numbers go into their own bucket.
    groups: dict[str, list] = defaultdict(list)
    for instr in ucc_instruments:
        prefix = (instr.filing_number or "")[
            :16].strip() or f"_unknown_{instr.pk}"
        groups[prefix].append(instr)

    triggers = []
    seen_windows: set = set()

    for prefix, instruments in groups.items():
        if len(instruments) < 3:
            continue

        dates = sorted(i.filing_date for i in instruments)
        for i, anchor in enumerate(dates):
            window_dates = [d for d in dates if abs((d - anchor).days) <= 1]
            if len(window_dates) < 3:
                continue

            window_key = (prefix, min(window_dates), max(window_dates))
            if window_key in seen_windows:
                continue
            seen_windows.add(window_key)

            triggers.append(SignalTrigger(
                rule_id="SR-004",
                severity="HIGH",
                title=RULE_REGISTRY["SR-004"].title,
                detected_summary=(
                    f"{len(window_dates)} UCC amendments to filing number prefix "
                    f"'{prefix}' between {min(window_dates)} and {max(window_dates)} "
                    f"({abs((max(window_dates) - min(window_dates)).days * 24)} hours or less)."
                ),
                trigger_entity_id=instruments[0].pk,
                trigger_doc=trigger_doc,
            ))
            break   # one signal per group prefix

    return triggers


# ---------------------------------------------------------------------------
# SR-005 — Zero-Consideration Transfer
#
# Document-scoped.  Matches zero-consideration language in deed/instrument
# documents.  Always worth human review for related-party transfers.
# ---------------------------------------------------------------------------

def evaluate_sr005_zero_consideration(case, document) -> list[SignalTrigger]:
    if not document or not document.extracted_text:
        return []
    if document.doc_type not in _DEED_DOC_TYPES:
        return []

    text = document.extracted_text
    for pattern in _ZERO_CONSIDERATION_PATTERNS:
        if pattern.search(text):
            return [SignalTrigger(
                rule_id="SR-005",
                severity="HIGH",
                title=RULE_REGISTRY["SR-005"].title,
                detected_summary=(
                    "Deed or instrument contains zero-consideration or nominal "
                    "consideration language. Review for related-party transfer."
                ),
                trigger_doc=document,
            )]

    return []


# ---------------------------------------------------------------------------
# SR-006 — IRS 990 Schedule L Missing
#
# Document-scoped.  Checks IRS_990 documents for evidence that Part IV
# Line 28a/b/c was answered "Yes" without Schedule L being present.
# ---------------------------------------------------------------------------

def evaluate_sr006_990_schedule_l(case, document) -> list[SignalTrigger]:
    if not document or not document.extracted_text:
        return []
    if document.doc_type != "IRS_990":
        return []

    text = document.extracted_text

    triggered = any(p.search(text) for p in _990_PART4_YES_PATTERNS)
    if not triggered:
        return []

    # If Schedule L text is present in the same document, no signal.
    if _SCHEDULE_L_PRESENT_PATTERN.search(text):
        return []

    return [SignalTrigger(
        rule_id="SR-006",
        severity="HIGH",
        title=RULE_REGISTRY["SR-006"].title,
        detected_summary=(
            "Form 990 indicates transactions with interested persons "
            "(Part IV Line 28a/b/c = Yes) but Schedule L is absent from this filing."
        ),
        trigger_doc=document,
    )]


# ---------------------------------------------------------------------------
# SR-007 — Building Permit Applicant vs. Property Owner
#
# Case-scoped.  Compares the applicant name extracted from BUILDING_PERMIT
# documents against known persons and organizations in the case.  Flags
# permits where the stated applicant does not match any case entity.
# ---------------------------------------------------------------------------

def evaluate_sr007_permit_owner_mismatch(case, trigger_doc=None) -> list[SignalTrigger]:
    permit_docs = list(
        case.documents.filter(doc_type="BUILDING_PERMIT",
                              extracted_text__isnull=False)
    )
    if not permit_docs:
        return []

    # Build a set of known entity names for the case.
    case_names: set[str] = set()
    for org in case.organizations.all():
        case_names.add(org.name.lower().strip())
    for person in case.persons.all():
        case_names.add(person.full_name.lower().strip())

    if not case_names:
        return []

    triggers = []
    for permit_doc in permit_docs:
        text = permit_doc.extracted_text or ""
        match = _PERMIT_APPLICANT_PATTERN.search(text)
        if not match:
            continue

        applicant = match.group(1).strip()
        applicant_lower = applicant.lower()

        name_matched = any(
            applicant_lower in entity_name or entity_name in applicant_lower
            for entity_name in case_names
        )

        if not name_matched:
            triggers.append(SignalTrigger(
                rule_id="SR-007",
                severity="HIGH",
                title=RULE_REGISTRY["SR-007"].title,
                detected_summary=(
                    f"Building permit applicant '{applicant}' does not match any "
                    f"known person or organization in this case."
                ),
                trigger_doc=permit_doc,
            ))

    return triggers


# ---------------------------------------------------------------------------
# SR-008 — Survey Recorded Before Purchase
#
# Case-scoped.  Looks for documents whose filename or subtype indicates a
# survey or plat.  If the earliest date extracted from that document precedes
# any financial instrument filing date in the case by more than 90 days,
# the rule fires.
# ---------------------------------------------------------------------------

def evaluate_sr008_survey_before_purchase(case, trigger_doc=None) -> list[SignalTrigger]:
    _SURVEY_TERMS = ("survey", "plat", "boundary")

    survey_docs = [
        doc for doc in case.documents.filter(extracted_text__isnull=False)
        if any(
            term in (doc.filename or "").lower() or
            term in (doc.doc_subtype or "").lower()
            for term in _SURVEY_TERMS
        )
    ]

    if not survey_docs:
        return []

    purchase_instruments = list(
        case.financial_instruments.filter(filing_date__isnull=False)
    )
    if not purchase_instruments:
        return []

    triggers = []
    for survey_doc in survey_docs:
        survey_dates = _extract_dates_from_text(survey_doc.extracted_text)
        if not survey_dates:
            continue

        earliest_survey = min(survey_dates)

        for instrument in purchase_instruments:
            gap = (instrument.filing_date - earliest_survey).days
            if gap > 90:
                triggers.append(SignalTrigger(
                    rule_id="SR-008",
                    severity="MEDIUM",
                    title=RULE_REGISTRY["SR-008"].title,
                    detected_summary=(
                        f"Survey dated {earliest_survey} precedes financial instrument "
                        f"'{instrument.filing_number or instrument.pk}' dated "
                        f"{instrument.filing_date} by {gap} days."
                    ),
                    trigger_doc=survey_doc,
                ))
                break   # one signal per survey doc

    return triggers


# ---------------------------------------------------------------------------
# SR-009 — Single Contractor on All Permits
#
# Case-scoped.  Extracts contractor names from all BUILDING_PERMIT documents
# in the case.  If two or more permits share the same contractor (100% of
# attributable permits), the rule fires.
# ---------------------------------------------------------------------------

def evaluate_sr009_single_contractor(case, trigger_doc=None) -> list[SignalTrigger]:
    permit_docs = list(
        case.documents.filter(doc_type="BUILDING_PERMIT",
                              extracted_text__isnull=False)
    )
    if len(permit_docs) < 2:
        return []

    contractors = []
    for doc in permit_docs:
        m = _CONTRACTOR_PATTERN.search(doc.extracted_text or "")
        if m:
            contractors.append(m.group(1).strip())

    if len(contractors) < 2:
        return []

    counts = Counter(c.lower() for c in contractors)
    most_common_name, most_common_count = counts.most_common(1)[0]

    if most_common_count < len(contractors):
        return []

    return [SignalTrigger(
        rule_id="SR-009",
        severity="MEDIUM",
        title=RULE_REGISTRY["SR-009"].title,
        detected_summary=(
            f"'{contractors[0]}' appears as contractor on all {len(contractors)} "
            f"building permit documents with no evidence of competitive bidding."
        ),
        trigger_doc=trigger_doc,
    )]


# ---------------------------------------------------------------------------
# SR-010 — Missing IRS Form 990
#
# Case-scoped.  If the case contains any Organization with org_type=CHARITY,
# and no IRS_990 documents have been added to the case, this rule fires.
# ---------------------------------------------------------------------------

def evaluate_sr010_missing_990(case, trigger_doc=None) -> list[SignalTrigger]:
    charity_orgs = list(case.organizations.filter(org_type="CHARITY"))
    if not charity_orgs:
        return []

    has_990 = case.documents.filter(doc_type="IRS_990").exists()
    if has_990:
        return []

    triggers = []
    for org in charity_orgs:
        triggers.append(SignalTrigger(
            rule_id="SR-010",
            severity="MEDIUM",
            title=RULE_REGISTRY["SR-010"].title,
            detected_summary=(
                f"'{org.name}' is classified as a charity but no IRS Form 990 "
                f"documents have been added to this case."
            ),
            trigger_entity_id=org.pk,
            trigger_doc=trigger_doc,
        ))

    return triggers


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def evaluate_document(case, document) -> list[SignalTrigger]:
    """
    Run all document-scoped signal rules against a single document.

    Rules evaluated: SR-001, SR-002, SR-005, SR-006.
    Safe to call immediately after text extraction on every upload.
    """
    triggers: list[SignalTrigger] = []
    _run_rule("SR-001", evaluate_sr001_deceased_signer,
              triggers, case, document)
    _run_rule("SR-002", evaluate_sr002_entity_predates_formation,
              triggers, case, document)
    _run_rule("SR-005", evaluate_sr005_zero_consideration,
              triggers, case, document)
    _run_rule("SR-006", evaluate_sr006_990_schedule_l,
              triggers, case, document)
    return triggers


def evaluate_case(case, trigger_doc=None) -> list[SignalTrigger]:
    """
    Run all case-scoped signal rules.

    Rules evaluated: SR-003, SR-004, SR-007, SR-008, SR-009, SR-010.
    Operates on all entities and documents in the case — call after every
    upload so cross-document patterns are detected as the case grows.

    trigger_doc: the document that triggered this evaluation pass.
    Used to associate newly created Signal records with the causal document
    when no more specific entity is the natural trigger.
    """
    triggers: list[SignalTrigger] = []
    _run_rule("SR-003", evaluate_sr003_valuation_anomaly,
              triggers, case, trigger_doc)
    _run_rule("SR-004", evaluate_sr004_ucc_burst, triggers, case, trigger_doc)
    _run_rule("SR-007", evaluate_sr007_permit_owner_mismatch,
              triggers, case, trigger_doc)
    _run_rule("SR-008", evaluate_sr008_survey_before_purchase,
              triggers, case, trigger_doc)
    _run_rule("SR-009", evaluate_sr009_single_contractor,
              triggers, case, trigger_doc)
    _run_rule("SR-010", evaluate_sr010_missing_990,
              triggers, case, trigger_doc)
    return triggers


def persist_signals(case, triggers: list[SignalTrigger]) -> list:
    """
    Persist SignalTrigger results to the database with deduplication.

    A signal is skipped (deduplicated) if a Signal record already exists for
    the same (case, rule_id, trigger_entity_id, trigger_doc) combination that
    is not in DISMISSED status.

    Returns: list of newly created Signal model instances.
    """
    # Import inside function to keep this module importable in stateless contexts.
    from .models import Signal, SignalStatus

    created = []
    for trigger in triggers:
        trigger_doc_id = trigger.trigger_doc.pk if trigger.trigger_doc else None

        already_exists = Signal.objects.filter(
            case=case,
            rule_id=trigger.rule_id,
            trigger_entity_id=trigger.trigger_entity_id,
            trigger_doc_id=trigger_doc_id,
        ).exclude(status=SignalStatus.DISMISSED).exists()

        if already_exists:
            continue

        signal = Signal.objects.create(
            case=case,
            rule_id=trigger.rule_id,
            severity=trigger.severity,
            trigger_entity_id=trigger.trigger_entity_id,
            trigger_doc_id=trigger_doc_id,
            detected_summary=trigger.detected_summary,
            status=SignalStatus.OPEN,
        )
        created.append(signal)
        logger.info(
            "signal_detected",
            extra={
                "signal_id": str(signal.pk),
                "rule_id": signal.rule_id,
                "severity": signal.severity,
                "case_id": str(case.pk),
            },
        )

    return created
