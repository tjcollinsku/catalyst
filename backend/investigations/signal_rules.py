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
from dataclasses import dataclass
from datetime import date
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
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    title: str
    description: str  # One-sentence charter description


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
            "Purchase price deviates more than 50% from county-assessed value, in either direction."
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
    "SR-011": RuleInfo(
        rule_id="SR-011",
        severity="HIGH",
        title="No Independent Board Members Disclosed on Form 990",
        description=(
            "Form 990 Part VI discloses zero independent voting members of the "
            "governing body, indicating a fully insider-controlled board."
        ),
    ),
    "SR-012": RuleInfo(
        rule_id="SR-012",
        severity="HIGH",
        title="No Conflict of Interest Policy at Material-Revenue Organization",
        description=(
            "Form 990 Part VI Line 12a answered No — the organization has no "
            "written conflict of interest policy despite material revenue."
        ),
    ),
    "SR-013": RuleInfo(
        rule_id="SR-013",
        severity="HIGH",
        title="Principal Officer Reports Zero Compensation at High-Revenue Organization",
        description=(
            "Form 990 Part VII lists the principal officer with $0 reportable "
            "compensation at an organization with gross receipts exceeding $500,000, "
            "which may indicate unreported compensation or related-party payments."
        ),
    ),
    # -----------------------------------------------------------------
    # NEW RULES: Entity-level, relationship, and financial patterns
    # These use the new Address, Relationship, TransactionChain, and
    # SocialMediaConnection models added in the schema enhancement.
    # -----------------------------------------------------------------
    "SR-014": RuleInfo(
        rule_id="SR-014",
        severity="HIGH",
        title="Address Nexus — Multiple Entities Share an Address",
        description=(
            "Two or more distinct entities (persons, organizations, LLPs) are "
            "linked to the same normalized address, suggesting a shared "
            "operational hub or undisclosed control relationship."
        ),
    ),
    "SR-015": RuleInfo(
        rule_id="SR-015",
        severity="CRITICAL",
        title="Insider Swap — Related Party on Both Sides of Transaction",
        description=(
            "A property transaction where the buyer and seller (or their officers) "
            "share a family or business relationship, indicating a non-arm's-length "
            "transfer that may constitute private benefit or self-dealing."
        ),
    ),
    "SR-016": RuleInfo(
        rule_id="SR-016",
        severity="HIGH",
        title="Family Network Density — Governance Dominated by Related Persons",
        description=(
            "More than 50% of persons linked to case organizations share family "
            "relationships, indicating a patronage network rather than independent "
            "governance."
        ),
    ),
    "SR-017": RuleInfo(
        rule_id="SR-017",
        severity="HIGH",
        title="UCC Blanket Lien on Charity-Connected Entity",
        description=(
            "A UCC filing with blanket lien language ('all assets', 'all equipment') "
            "names a debtor who is also an officer, agent, or family member of a "
            "case organization, creating commingling risk."
        ),
    ),
    "SR-018": RuleInfo(
        rule_id="SR-018",
        severity="HIGH",
        title="Rapid Property Flip — Resale Within 30 Days",
        description=(
            "Property acquired and resold (or transferred) within 30 days, "
            "suggesting the transaction was pre-arranged rather than arm's-length."
        ),
    ),
    "SR-019": RuleInfo(
        rule_id="SR-019",
        severity="MEDIUM",
        title="Entity Proliferation — Multiple Formations Within 90 Days",
        description=(
            "Three or more organizations formed within a 90-day window where "
            "any share an officer, address, or family relationship."
        ),
    ),
    "SR-020": RuleInfo(
        rule_id="SR-020",
        severity="MEDIUM",
        title="Multi-County Property Cluster",
        description=(
            "Case properties span three or more counties, indicating geographic "
            "dispersion that may be designed to avoid single-county scrutiny."
        ),
    ),
    "SR-021": RuleInfo(
        rule_id="SR-021",
        severity="HIGH",
        title="Revenue Spike — Year-over-Year Increase Exceeds 100%",
        description=(
            "Total revenue on Form 990 more than doubles from one tax year to "
            "the next, warranting review of the contribution sources."
        ),
    ),
    "SR-022": RuleInfo(
        rule_id="SR-022",
        severity="MEDIUM",
        title="Social Connection Cluster — Case Persons Share Social Network",
        description=(
            "Five or more persons involved in case transactions are connected "
            "on social media to a case officer, suggesting a patronage network."
        ),
    ),
    "SR-023": RuleInfo(
        rule_id="SR-023",
        severity="HIGH",
        title="Entity Formation Precedes Related Acquisition",
        description=(
            "A new entity is formed within 30 days of a property acquisition "
            "by a related entity or family member, suggesting the formation "
            "was designed to facilitate or obscure the transaction."
        ),
    ),
    "SR-024": RuleInfo(
        rule_id="SR-024",
        severity="HIGH",
        title="Charity Acquires from Family Then Transfers to Insider",
        description=(
            "Charity purchases property from a family-connected seller, then "
            "transfers or grants the same property to another related party. "
            "Classic conduit pattern for private benefit distribution."
        ),
    ),
    # -----------------------------------------------------------------
    # 990 CONTRADICTION RULES
    # These compare what the 990 SAYS vs what the DATABASE PROVES.
    # This is where rule-based detection meets evidence-based rebuttal.
    # -----------------------------------------------------------------
    "SR-025": RuleInfo(
        rule_id="SR-025",
        severity="CRITICAL",
        title="990 Denies Related-Party Transactions — Evidence Contradicts",
        description=(
            "Form 990 Part IV Line 28 answered 'No' to transactions with "
            "interested persons, but the case database contains confirmed "
            "Relationship records linking organization officers to transaction "
            "counterparties. This is a false disclosure to the IRS."
        ),
    ),
    "SR-026": RuleInfo(
        rule_id="SR-026",
        severity="HIGH",
        title="990 Denies Independent Contractors — Evidence Contradicts",
        description=(
            "Form 990 Part IV Line 25 (compensation of independent contractors) "
            "or Schedule J answered 'No', but building permits or case documents "
            "show contractors performing significant work for the organization."
        ),
    ),
    "SR-027": RuleInfo(
        rule_id="SR-027",
        severity="HIGH",
        title="990-T Filed But 990 Denies Unrelated Business Income",
        description=(
            "An IRS Form 990-T (Exempt Organization Business Income Tax Return) "
            "exists in the case, but the corresponding 990 Part IV Line 3 does "
            "not acknowledge unrelated business activity."
        ),
    ),
    "SR-028": RuleInfo(
        rule_id="SR-028",
        severity="HIGH",
        title="Major Donor Concentration Without Schedule B Detail",
        description=(
            "Contributions exceed 50% of total revenue but no Schedule B "
            "(major donors) detail is present, or the organization claims "
            "public charity status while relying heavily on a few large gifts."
        ),
    ),
    "SR-029": RuleInfo(
        rule_id="SR-029",
        severity="HIGH",
        title="Low Program Expense Ratio — Charity Spending on Non-Mission Assets",
        description=(
            "Less than 50% of total expenses go to program services, with "
            "the remainder spent on real estate acquisition, construction, "
            "or other non-mission activities."
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
    trigger_doc: object = None  # Document model instance or None


# ---------------------------------------------------------------------------
# Text patterns used by document-level rules
# ---------------------------------------------------------------------------

_ZERO_CONSIDERATION_PATTERNS = [
    re.compile(r"\$\s*0\.00\b"),
    re.compile(r"\bno\s+(?:monetary\s+)?consideration\b", re.IGNORECASE),
    re.compile(r"\bzero\s+(?:and\s+no[/\-]100\s+)?(?:dollars?|consideration)\b", re.IGNORECASE),
    re.compile(r"\bnominal\s+consideration\b", re.IGNORECASE),
    re.compile(r"\blove\s+and\s+affection\b", re.IGNORECASE),
    re.compile(r"\bten\s+dollars?\s+and\s+other\s+valuable\s+consideration\b", re.IGNORECASE),
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

# SR-011 — No independent board members
# Matches "0" or "zero" on the line for independent voting members (Part VI line 1b)
_INDEPENDENT_MEMBERS_ZERO_PATTERNS = [
    re.compile(
        r"(?:independent\s+voting\s+members?|line\s+1b)[^\n]{0,80}\b(0|zero)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b4\s*\n?\s*(?:Number\s+of\s+independent[^\n]{0,60})?\s*4\s+0\b",
        re.IGNORECASE,
    ),
]

# SR-012 — No conflict of interest policy
_NO_COI_POLICY_PATTERNS = [
    re.compile(
        r"conflict\s+of\s+interest\s+policy[^\n]{0,80}No\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"12a[^\n]{0,60}No\b",
        re.IGNORECASE,
    ),
]

# SR-013 — Gross receipts and zero officer compensation
# Captures gross receipts dollar amount from 990 header
_GROSS_RECEIPTS_PATTERN = re.compile(
    r"Gross\s+receipts?\s*\$\s*([\d,]+)",
    re.IGNORECASE,
)
# Matches lines where a named officer shows $0 / 0 compensation in Part VII table
_ZERO_OFFICER_COMP_PATTERN = re.compile(
    r"(?:president|principal\s+officer|executive\s+director|ceo|cfo|treasurer|secretary)"
    r"[^\n]{0,200}?\b0\s+0\s+0\b",
    re.IGNORECASE | re.DOTALL,
)


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
        logger.exception("signal_rule_evaluation_failed", extra={"rule_id": rule_id})


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
                triggers.append(
                    SignalTrigger(
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
                    )
                )
                break  # one signal per deceased person per document

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

    orgs_with_formation = case.organizations.filter(formation_date__isnull=False)
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
                triggers.append(
                    SignalTrigger(
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
                    )
                )
                break  # one signal per org per document

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

        deviation = abs(prop.purchase_price - prop.assessed_value) / prop.assessed_value
        if deviation <= Decimal("0.50"):
            continue

        direction = "above" if prop.purchase_price > prop.assessed_value else "below"
        label = prop.parcel_number or prop.address or str(prop.pk)
        triggers.append(
            SignalTrigger(
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
            )
        )

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
        prefix = (instr.filing_number or "")[:16].strip() or f"_unknown_{instr.pk}"
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

            triggers.append(
                SignalTrigger(
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
                )
            )
            break  # one signal per group prefix

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
            return [
                SignalTrigger(
                    rule_id="SR-005",
                    severity="HIGH",
                    title=RULE_REGISTRY["SR-005"].title,
                    detected_summary=(
                        "Deed or instrument contains zero-consideration or nominal "
                        "consideration language. Review for related-party transfer."
                    ),
                    trigger_doc=document,
                )
            ]

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

    return [
        SignalTrigger(
            rule_id="SR-006",
            severity="HIGH",
            title=RULE_REGISTRY["SR-006"].title,
            detected_summary=(
                "Form 990 indicates transactions with interested persons "
                "(Part IV Line 28a/b/c = Yes) but Schedule L is absent from this filing."
            ),
            trigger_doc=document,
        )
    ]


# ---------------------------------------------------------------------------
# SR-007 — Building Permit Applicant vs. Property Owner
#
# Case-scoped.  Compares the applicant name extracted from BUILDING_PERMIT
# documents against known persons and organizations in the case.  Flags
# permits where the stated applicant does not match any case entity.
# ---------------------------------------------------------------------------


def evaluate_sr007_permit_owner_mismatch(case, trigger_doc=None) -> list[SignalTrigger]:
    permit_docs = list(
        case.documents.filter(doc_type="BUILDING_PERMIT", extracted_text__isnull=False)
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
            triggers.append(
                SignalTrigger(
                    rule_id="SR-007",
                    severity="HIGH",
                    title=RULE_REGISTRY["SR-007"].title,
                    detected_summary=(
                        f"Building permit applicant '{applicant}' does not match any "
                        f"known person or organization in this case."
                    ),
                    trigger_doc=permit_doc,
                )
            )

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
        doc
        for doc in case.documents.filter(extracted_text__isnull=False)
        if any(
            term in (doc.filename or "").lower() or term in (doc.doc_subtype or "").lower()
            for term in _SURVEY_TERMS
        )
    ]

    if not survey_docs:
        return []

    purchase_instruments = list(case.financial_instruments.filter(filing_date__isnull=False))
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
                triggers.append(
                    SignalTrigger(
                        rule_id="SR-008",
                        severity="MEDIUM",
                        title=RULE_REGISTRY["SR-008"].title,
                        detected_summary=(
                            f"Survey dated {earliest_survey} precedes financial instrument "
                            f"'{instrument.filing_number or instrument.pk}' dated "
                            f"{instrument.filing_date} by {gap} days."
                        ),
                        trigger_doc=survey_doc,
                    )
                )
                break  # one signal per survey doc

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
        case.documents.filter(doc_type="BUILDING_PERMIT", extracted_text__isnull=False)
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

    return [
        SignalTrigger(
            rule_id="SR-009",
            severity="MEDIUM",
            title=RULE_REGISTRY["SR-009"].title,
            detected_summary=(
                f"'{most_common_name}' appears as contractor on all {len(contractors)} "
                f"building permit documents with no evidence of competitive bidding."
            ),
            trigger_doc=trigger_doc,
        )
    ]


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
        triggers.append(
            SignalTrigger(
                rule_id="SR-010",
                severity="MEDIUM",
                title=RULE_REGISTRY["SR-010"].title,
                detected_summary=(
                    f"'{org.name}' is classified as a charity but no IRS Form 990 "
                    f"documents have been added to this case."
                ),
                trigger_entity_id=org.pk,
                trigger_doc=trigger_doc,
            )
        )

    return triggers


# ---------------------------------------------------------------------------
# SR-011 — No Independent Board Members
#
# Document-scoped.  Checks IRS_990 documents for evidence that the number of
# independent voting members of the governing body (Part VI, line 1b) is zero.
# ---------------------------------------------------------------------------


def evaluate_sr011_no_independent_board(case, document) -> list[SignalTrigger]:
    if not document or not document.extracted_text:
        return []
    if document.doc_type != "IRS_990":
        return []

    text = document.extracted_text

    # Primary pattern: look for "4  0" line structure (line 1b = 0 independent members)
    # The 990 renders as: "4 Number of independent voting members ... 4  0"
    # Also catches explicit "independent voting members ... 0" text
    matched = any(p.search(text) for p in _INDEPENDENT_MEMBERS_ZERO_PATTERNS)

    # Fallback: find "independent voting members" and check if a bare "0" immediately
    # follows within 120 chars (handles OCR spacing variations)
    if not matched:
        idx = text.lower().find("independent voting members")
        if idx >= 0:
            snippet = text[idx : idx + 120]
            if re.search(r"\b0\b", snippet):
                matched = True

    if not matched:
        return []

    return [
        SignalTrigger(
            rule_id="SR-011",
            severity="HIGH",
            title=RULE_REGISTRY["SR-011"].title,
            detected_summary=(
                "Form 990 Part VI discloses zero independent voting members of the "
                "governing body. The organization appears to be fully insider-controlled "
                "with no independent oversight — a primary self-dealing risk factor."
            ),
            trigger_doc=document,
        )
    ]


# ---------------------------------------------------------------------------
# SR-012 — No Conflict of Interest Policy
#
# Document-scoped.  Checks IRS_990 documents for Part VI Line 12a answered
# "No" — the organization has no written conflict of interest policy.
# ---------------------------------------------------------------------------


def evaluate_sr012_no_coi_policy(case, document) -> list[SignalTrigger]:
    if not document or not document.extracted_text:
        return []
    if document.doc_type != "IRS_990":
        return []

    text = document.extracted_text

    matched = any(p.search(text) for p in _NO_COI_POLICY_PATTERNS)

    # Fallback: find the COI policy question and look for "No" within 120 chars
    if not matched:
        idx = text.lower().find("conflict of interest policy")
        if idx >= 0:
            snippet = text[idx : idx + 120]
            if re.search(r"\bNo\b", snippet, re.IGNORECASE):
                matched = True

    if not matched:
        return []

    return [
        SignalTrigger(
            rule_id="SR-012",
            severity="HIGH",
            title=RULE_REGISTRY["SR-012"].title,
            detected_summary=(
                "Form 990 Part VI Line 12a indicates no written conflict of interest "
                "policy exists. Without a COI policy, self-dealing transactions between "
                "officers and the organization are structurally undetectable."
            ),
            trigger_doc=document,
        )
    ]


# ---------------------------------------------------------------------------
# SR-013 — Zero Officer Compensation at High-Revenue Organization
#
# Document-scoped.  Checks IRS_990 documents where gross receipts exceed
# $500,000 and the principal officer or named officers report $0 compensation.
# This pattern may indicate unreported compensation, related-party payments,
# or commingling of personal and organizational finances.
# ---------------------------------------------------------------------------

_SR013_REVENUE_THRESHOLD = 500_000


def evaluate_sr013_zero_officer_pay(case, document) -> list[SignalTrigger]:
    if not document or not document.extracted_text:
        return []
    if document.doc_type != "IRS_990":
        return []

    text = document.extracted_text

    # Extract gross receipts
    receipts_match = _GROSS_RECEIPTS_PATTERN.search(text)
    if not receipts_match:
        return []

    try:
        gross_receipts = int(receipts_match.group(1).replace(",", ""))
    except ValueError:
        return []

    if gross_receipts < _SR013_REVENUE_THRESHOLD:
        return []

    # Check for zero officer compensation
    matched = bool(_ZERO_OFFICER_COMP_PATTERN.search(text))

    # Fallback: look for the Part VII officer table — if named officers all show 0
    if not matched:
        idx = text.find("Section A. Officers")
        if idx >= 0:
            section = text[idx : idx + 2000]
            # Count named persons and zero-comp entries
            zero_entries = len(re.findall(r"\b0\s+0\s+0\b", section))
            named_entries = len(re.findall(r"\(\d+\)\s+[A-Z][A-Z\s]+\n", section))
            if zero_entries > 0 and named_entries > 0 and zero_entries >= named_entries:
                matched = True

    if not matched:
        return []

    return [
        SignalTrigger(
            rule_id="SR-013",
            severity="HIGH",
            title=RULE_REGISTRY["SR-013"].title,
            detected_summary=(
                f"Form 990 reports gross receipts of ${gross_receipts:,} but lists "
                f"named officers with $0 reportable compensation. At this revenue level, "
                f"zero officer pay warrants review for unreported compensation, "
                f"related-party payments, or commingling of funds."
            ),
            trigger_doc=document,
        )
    ]


# ===========================================================================
# NEW RULE EVALUATORS — Entity, Relationship, Financial, Timing
#
# These rules use the enhanced models (Address, Relationship, TransactionChain,
# SocialMediaConnection) to detect patterns that span multiple entities and
# documents. They are all case-scoped (not document-scoped) because the
# patterns only emerge when you look across the whole case.
#
# REAL-WORLD EXAMPLE for each rule (from the Example Charity case):
#   SR-014: 123 Main St → charity + Jay Example + Example Partners
#   SR-015: Charity buys from ExampleSeller → flips to Insider (Jay's uncle sold it)
#   SR-016: Jay, Karen, FamilyMember2, Ron E, FamilyMember — all family
#   SR-017: Example Lender blanket lien on Example Partners at charity address
#   SR-018: ExampleSeller land → Example Charity → Insider in 5 days
#   SR-019: Example Charity Inc + Example Charity Real Estate LLC both formed 2019
#   SR-020: Darke + Mercer + Shelby + Hardin counties
#   SR-021: 2019 revenue spike ($X.XM contributions in year 2)
#   SR-022: 14 Facebook friends match obituary surnames
#   SR-023: Example Ag Mgmt LLP formed 10 days before property buy
#   SR-024: Charity buys from ExampleSeller (family) → gives to Insider (insider)
# ===========================================================================


# ---------------------------------------------------------------------------
# SR-014 — Address Nexus
#
# Case-scoped. Queries the Address model for any address linked to 2+
# distinct entities (persons OR organizations). This is the rule that would
# have caught 123 Main St being shared by the charity, Jay Example, and
# Example Partners.
#
# HOW IT WORKS:
#   Address table has PersonAddress and OrgAddress junction tables.
#   We count how many distinct entities link to each address.
#   If count >= 2, we fire the signal.
# ---------------------------------------------------------------------------


def evaluate_sr014_address_nexus(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import Address

    triggers = []

    # Get all addresses for this case with their linked entities
    addresses = Address.objects.filter(case=case).prefetch_related(
        "person_addresses__person", "org_addresses__org"
    )

    for addr in addresses:
        # Collect all distinct entity names linked to this address
        linked_entities = []

        for pa in addr.person_addresses.all():
            linked_entities.append(
                ("Person", pa.person.full_name, pa.person.pk)
            )

        for oa in addr.org_addresses.all():
            linked_entities.append(
                ("Organization", oa.org.name, oa.org.pk)
            )

        if len(linked_entities) < 2:
            continue

        # Build human-readable summary
        entity_names = [f"{etype}: {name}" for etype, name, _ in linked_entities]
        summary_list = ", ".join(entity_names[:5])
        if len(entity_names) > 5:
            summary_list += f" (+{len(entity_names) - 5} more)"

        triggers.append(
            SignalTrigger(
                rule_id="SR-014",
                severity="HIGH",
                title=RULE_REGISTRY["SR-014"].title,
                detected_summary=(
                    f"Address '{addr.raw_text or addr.street}' is shared by "
                    f"{len(linked_entities)} entities: {summary_list}. "
                    f"Shared addresses may indicate undisclosed control relationships."
                ),
                trigger_entity_id=addr.pk,
                trigger_doc=trigger_doc,
            )
        )

    return triggers


# ---------------------------------------------------------------------------
# SR-015 — Insider Swap Detection
#
# Case-scoped. This is the BIG one. Looks at PropertyTransactions where:
#   1. The buyer or seller is a case organization (charity/LLC), AND
#   2. The other party (or their officers) has a Relationship to someone
#      connected to the organization.
#
# In the Example Charity case, this catches:
#   - Charity buys from ExampleOwner → ExampleOwner's son gets property from charity
#   - Charity buys from ExampleSeller (Jay's uncle) → flips to Insider (insider)
#   - Charity gives lot to FamilyMember (Jay's uncle's family)
#   - Charity gives lot to Mescher (Example Lender officer's family)
# ---------------------------------------------------------------------------


def evaluate_sr015_insider_swap(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import (
        Organization,
        PersonOrganization,
        PropertyTransaction,
        Relationship,
    )

    triggers = []

    # Step 1: Get all persons who hold roles in case organizations
    org_person_links = PersonOrganization.objects.filter(
        org__case=case
    ).select_related("person", "org")

    # Build a set of person IDs who are "insiders" (officers/agents of orgs)
    insider_person_ids = set()
    insider_org_ids = set()
    person_to_orgs: dict[UUID, list[str]] = defaultdict(list)

    for link in org_person_links:
        insider_person_ids.add(link.person.pk)
        insider_org_ids.add(link.org.pk)
        person_to_orgs[link.person.pk].append(link.org.name)

    if not insider_person_ids:
        return []

    # Step 2: Get all family/business relationships involving insiders
    related_to_insiders = set()
    relationship_map: dict[UUID, list[tuple]] = defaultdict(list)

    relationships = Relationship.objects.filter(
        case=case
    ).select_related("person_a", "person_b")

    for rel in relationships:
        if rel.person_a.pk in insider_person_ids:
            related_to_insiders.add(rel.person_b.pk)
            relationship_map[rel.person_b.pk].append(
                (rel.person_a.full_name, rel.relationship_type)
            )
        if rel.person_b.pk in insider_person_ids:
            related_to_insiders.add(rel.person_a.pk)
            relationship_map[rel.person_a.pk].append(
                (rel.person_b.full_name, rel.relationship_type)
            )

    # The "extended insider network" = direct insiders + their family/associates
    extended_network = insider_person_ids | related_to_insiders

    if not extended_network:
        return []

    # Step 3: Check every property transaction for insider involvement
    transactions = PropertyTransaction.objects.filter(
        property__case=case,
    ).select_related("property")

    for txn in transactions:
        buyer_is_insider = txn.buyer_id in extended_network or txn.buyer_id in insider_org_ids
        seller_is_insider = txn.seller_id in extended_network or txn.seller_id in insider_org_ids

        if not (buyer_is_insider or seller_is_insider):
            continue

        # Build the explanation
        parties = []
        if txn.buyer_id in insider_person_ids:
            orgs = person_to_orgs.get(txn.buyer_id, [])
            parties.append(f"Buyer '{txn.buyer_name}' is officer of {', '.join(orgs)}")
        elif txn.buyer_id in related_to_insiders:
            rels = relationship_map.get(txn.buyer_id, [])
            rel_desc = "; ".join(f"{name} ({rtype})" for name, rtype in rels[:3])
            parties.append(f"Buyer '{txn.buyer_name}' is related to insider(s): {rel_desc}")

        if txn.seller_id in insider_person_ids:
            orgs = person_to_orgs.get(txn.seller_id, [])
            parties.append(f"Seller '{txn.seller_name}' is officer of {', '.join(orgs)}")
        elif txn.seller_id in related_to_insiders:
            rels = relationship_map.get(txn.seller_id, [])
            rel_desc = "; ".join(f"{name} ({rtype})" for name, rtype in rels[:3])
            parties.append(f"Seller '{txn.seller_name}' is related to insider(s): {rel_desc}")

        if not parties:
            continue

        prop_label = txn.property.address or txn.property.parcel_number or str(txn.property.pk)
        price_str = f" for ${txn.price:,.2f}" if txn.price else ""

        triggers.append(
            SignalTrigger(
                rule_id="SR-015",
                severity="CRITICAL",
                title=RULE_REGISTRY["SR-015"].title,
                detected_summary=(
                    f"Property '{prop_label}' transaction on {txn.transaction_date}"
                    f"{price_str}: {'; '.join(parties)}. "
                    f"This transaction involves parties in the insider network."
                ),
                trigger_entity_id=txn.property.pk,
                trigger_doc=trigger_doc,
            )
        )

    return triggers


# ---------------------------------------------------------------------------
# SR-016 — Family Network Density
#
# Case-scoped. Counts Relationship records of type FAMILY/SPOUSE/PARENT_CHILD/
# SIBLING among persons who hold roles in case organizations. If more than
# 50% of org-linked persons are related to each other, the governance is
# family-dominated → not independent.
# ---------------------------------------------------------------------------


def evaluate_sr016_family_network_density(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import PersonOrganization, Relationship

    # Get all persons linked to organizations in this case
    org_person_links = PersonOrganization.objects.filter(
        org__case=case
    ).select_related("person")

    org_person_ids = set()
    for link in org_person_links:
        org_person_ids.add(link.person.pk)

    if len(org_person_ids) < 2:
        return []

    # Count how many of these persons share family relationships
    family_types = {"FAMILY", "SPOUSE", "PARENT_CHILD", "SIBLING"}

    family_rels = Relationship.objects.filter(
        case=case,
        relationship_type__in=family_types,
        person_a__pk__in=org_person_ids,
        person_b__pk__in=org_person_ids,
    )

    # Collect persons who are in at least one family relationship
    persons_in_family = set()
    for rel in family_rels:
        persons_in_family.add(rel.person_a_id)
        persons_in_family.add(rel.person_b_id)

    if not persons_in_family:
        return []

    density = len(persons_in_family) / len(org_person_ids)

    if density < 0.50:
        return []

    return [
        SignalTrigger(
            rule_id="SR-016",
            severity="HIGH",
            title=RULE_REGISTRY["SR-016"].title,
            detected_summary=(
                f"{len(persons_in_family)} of {len(org_person_ids)} persons linked "
                f"to case organizations ({density:.0%}) share family relationships. "
                f"This level of family density in governance indicates insider "
                f"control rather than independent oversight."
            ),
            trigger_doc=trigger_doc,
        )
    ]


# ---------------------------------------------------------------------------
# SR-017 — UCC Blanket Lien on Charity-Connected Entity
#
# Case-scoped. Finds FinancialInstruments where is_blanket_lien=True and
# the debtor is connected to a charity organization through PersonOrganization
# or Relationship.
# ---------------------------------------------------------------------------


def evaluate_sr017_blanket_lien_charity(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import PersonOrganization

    triggers = []

    blanket_liens = list(
        case.financial_instruments.filter(is_blanket_lien=True)
    )

    if not blanket_liens:
        return []

    # Get all persons who are officers/agents of CHARITY organizations
    charity_person_ids = set(
        PersonOrganization.objects.filter(
            org__case=case, org__org_type="CHARITY"
        ).values_list("person_id", flat=True)
    )

    for lien in blanket_liens:
        # Check if the debtor is a charity-connected person
        if lien.debtor_id and lien.debtor_id in charity_person_ids:
            triggers.append(
                SignalTrigger(
                    rule_id="SR-017",
                    severity="HIGH",
                    title=RULE_REGISTRY["SR-017"].title,
                    detected_summary=(
                        f"UCC filing '{lien.filing_number}' ({lien.filing_date}) is a "
                        f"blanket lien covering '{lien.collateral_description[:100]}...' "
                        f"The debtor is also linked to a charity in this case. "
                        f"Blanket liens create commingling risk between personal/farm "
                        f"assets and charitable assets."
                    ),
                    trigger_entity_id=lien.pk,
                    trigger_doc=trigger_doc,
                )
            )

    return triggers


# ---------------------------------------------------------------------------
# SR-018 — Rapid Property Flip (≤30 days)
#
# Case-scoped. Looks for properties with 2+ transactions where the time
# between consecutive transactions is 30 days or less.
# Catches: ExampleSeller → Example Charity → Insider in 5 days.
# ---------------------------------------------------------------------------


def evaluate_sr018_rapid_flip(case, trigger_doc=None) -> list[SignalTrigger]:
    triggers = []

    for prop in case.properties.all():
        txns = list(
            prop.transactions.filter(
                transaction_date__isnull=False
            ).order_by("transaction_date")
        )

        if len(txns) < 2:
            continue

        for i in range(len(txns) - 1):
            t1, t2 = txns[i], txns[i + 1]
            gap_days = (t2.transaction_date - t1.transaction_date).days

            if gap_days > 30:
                continue

            prop_label = prop.address or prop.parcel_number or str(prop.pk)

            triggers.append(
                SignalTrigger(
                    rule_id="SR-018",
                    severity="HIGH",
                    title=RULE_REGISTRY["SR-018"].title,
                    detected_summary=(
                        f"Property '{prop_label}' changed hands twice in {gap_days} days: "
                        f"({t1.transaction_date}) {t1.seller_name or '?'} → {t1.buyer_name or '?'}, "
                        f"then ({t2.transaction_date}) {t2.seller_name or '?'} → {t2.buyer_name or '?'}. "
                        f"Rapid flips suggest pre-arranged transactions."
                    ),
                    trigger_entity_id=prop.pk,
                    trigger_doc=trigger_doc,
                )
            )

    return triggers


# ---------------------------------------------------------------------------
# SR-019 — Entity Proliferation (3+ formations in 90 days)
#
# Case-scoped. Checks whether 3+ organizations in the case were formed
# within any 90-day window. The Example Charity case had the charity, Example Charity Real
# Estate LLC, and connected entities all formed close together.
# ---------------------------------------------------------------------------


def evaluate_sr019_entity_proliferation(case, trigger_doc=None) -> list[SignalTrigger]:
    orgs = list(
        case.organizations.filter(
            formation_date__isnull=False
        ).order_by("formation_date")
    )

    if len(orgs) < 3:
        return []

    triggers = []
    seen_windows: set[tuple] = set()

    for i, anchor_org in enumerate(orgs):
        window_orgs = [
            o for o in orgs
            if 0 <= (o.formation_date - anchor_org.formation_date).days <= 90
        ]

        if len(window_orgs) < 3:
            continue

        window_key = tuple(sorted(o.pk for o in window_orgs))
        if window_key in seen_windows:
            continue
        seen_windows.add(window_key)

        names = ", ".join(o.name for o in window_orgs[:5])
        span = (window_orgs[-1].formation_date - window_orgs[0].formation_date).days

        triggers.append(
            SignalTrigger(
                rule_id="SR-019",
                severity="MEDIUM",
                title=RULE_REGISTRY["SR-019"].title,
                detected_summary=(
                    f"{len(window_orgs)} entities formed within {span} days: {names}. "
                    f"Rapid entity creation may indicate structuring to distribute "
                    f"control or obscure asset flows."
                ),
                trigger_doc=trigger_doc,
            )
        )

    return triggers


# ---------------------------------------------------------------------------
# SR-020 — Multi-County Property Cluster
#
# Case-scoped. Counts distinct counties across all properties in the case.
# If 3+ counties, the geographic spread may be intentional to avoid
# single-county oversight.
# ---------------------------------------------------------------------------


def evaluate_sr020_multi_county(case, trigger_doc=None) -> list[SignalTrigger]:
    counties = set(
        case.properties.exclude(
            county__isnull=True
        ).exclude(
            county=""
        ).values_list("county", flat=True)
    )

    if len(counties) < 3:
        return []

    county_list = ", ".join(sorted(counties))

    return [
        SignalTrigger(
            rule_id="SR-020",
            severity="MEDIUM",
            title=RULE_REGISTRY["SR-020"].title,
            detected_summary=(
                f"Case properties span {len(counties)} counties: {county_list}. "
                f"Geographic dispersion across multiple county jurisdictions may "
                f"be designed to avoid consolidated scrutiny by any single auditor."
            ),
            trigger_doc=trigger_doc,
        )
    ]


# ---------------------------------------------------------------------------
# SR-021 — Revenue Spike (YoY > 100%)
#
# Case-scoped. Compares consecutive FinancialSnapshot records for the same
# organization. If total_revenue more than doubles year-over-year, flag it.
# In the Example Charity case: $X.XM in contributions appeared in Year 2.
# ---------------------------------------------------------------------------


def evaluate_sr021_revenue_spike(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import FinancialSnapshot

    triggers = []

    # Get all snapshots grouped by organization
    snapshots = list(
        FinancialSnapshot.objects.filter(
            case=case,
            total_revenue__isnull=False,
        ).order_by("organization_id", "tax_year")
    )

    if len(snapshots) < 2:
        return []

    # Group by org
    org_snapshots: dict[Optional[UUID], list] = defaultdict(list)
    for snap in snapshots:
        org_snapshots[snap.organization_id].append(snap)

    for org_id, snaps in org_snapshots.items():
        for i in range(len(snaps) - 1):
            prev, curr = snaps[i], snaps[i + 1]

            if prev.total_revenue <= 0:
                continue

            growth = (curr.total_revenue - prev.total_revenue) / prev.total_revenue

            if growth < 1.0:  # Less than 100% increase
                continue

            org_name = curr.ein or str(org_id or "Unknown")
            triggers.append(
                SignalTrigger(
                    rule_id="SR-021",
                    severity="HIGH",
                    title=RULE_REGISTRY["SR-021"].title,
                    detected_summary=(
                        f"Organization '{org_name}': revenue jumped from "
                        f"${prev.total_revenue:,} ({prev.tax_year}) to "
                        f"${curr.total_revenue:,} ({curr.tax_year}) — "
                        f"a {growth:.0%} increase. Review contribution sources."
                    ),
                    trigger_entity_id=org_id,
                    trigger_doc=trigger_doc,
                )
            )

    return triggers


# ---------------------------------------------------------------------------
# SR-022 — Social Connection Cluster
#
# Case-scoped. Counts SocialMediaConnection records where a case person
# (officer/agent) has 5+ connections to other persons who appear in case
# documents or transactions. Suggests a patronage network.
# ---------------------------------------------------------------------------


def evaluate_sr022_social_cluster(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import SocialMediaConnection

    triggers = []

    connections = SocialMediaConnection.objects.filter(
        case=case,
        connected_person__isnull=False,  # Only count linked connections
    ).select_related("person", "connected_person")

    # Group by the primary person (the one whose profile was examined)
    person_connections: dict[UUID, list] = defaultdict(list)
    for conn in connections:
        person_connections[conn.person.pk].append(conn)

    _SOCIAL_CLUSTER_THRESHOLD = 5

    for person_id, conns in person_connections.items():
        if len(conns) < _SOCIAL_CLUSTER_THRESHOLD:
            continue

        person_name = conns[0].person.full_name
        connected_names = [c.connected_person.full_name for c in conns[:8]]
        names_str = ", ".join(connected_names)
        if len(conns) > 8:
            names_str += f" (+{len(conns) - 8} more)"

        triggers.append(
            SignalTrigger(
                rule_id="SR-022",
                severity="MEDIUM",
                title=RULE_REGISTRY["SR-022"].title,
                detected_summary=(
                    f"{person_name} has {len(conns)} social media connections to "
                    f"other case persons: {names_str}. "
                    f"High social network overlap suggests a patronage network "
                    f"rather than independent governance."
                ),
                trigger_entity_id=person_id,
                trigger_doc=trigger_doc,
            )
        )

    return triggers


# ---------------------------------------------------------------------------
# SR-023 — Entity Formation Precedes Related Acquisition
#
# Case-scoped. Checks whether any organization was formed within 30 days
# BEFORE a PropertyTransaction involving a related organization or person.
# Catches: Example Ag Mgmt LLP formed 10 days before property buy.
# ---------------------------------------------------------------------------


def evaluate_sr023_formation_before_acquisition(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import PersonOrganization, PropertyTransaction, Relationship

    triggers = []

    orgs_with_dates = list(
        case.organizations.filter(formation_date__isnull=False)
    )

    if not orgs_with_dates:
        return []

    # Build a map of person → organizations they're linked to
    person_org_map: dict[UUID, set[UUID]] = defaultdict(set)
    for link in PersonOrganization.objects.filter(org__case=case):
        person_org_map[link.person_id].add(link.org_id)

    # Build a map of person → related persons (through any relationship)
    person_relatives: dict[UUID, set[UUID]] = defaultdict(set)
    for rel in Relationship.objects.filter(case=case):
        person_relatives[rel.person_a_id].add(rel.person_b_id)
        person_relatives[rel.person_b_id].add(rel.person_a_id)

    # Get all property transactions with dates
    txns = list(
        PropertyTransaction.objects.filter(
            property__case=case,
            transaction_date__isnull=False,
        ).select_related("property")
    )

    for org in orgs_with_dates:
        # Find persons linked to this org
        org_persons = set(
            PersonOrganization.objects.filter(
                org=org
            ).values_list("person_id", flat=True)
        )

        # Find all persons related to those org persons
        extended_persons = set(org_persons)
        for pid in org_persons:
            extended_persons |= person_relatives.get(pid, set())

        # Find all OTHER orgs those extended persons are linked to
        related_org_ids = set()
        for pid in extended_persons:
            related_org_ids |= person_org_map.get(pid, set())
        related_org_ids.discard(org.pk)  # Don't match self

        for txn in txns:
            # Check if this transaction involves a related org or person
            txn_involves_related = (
                txn.buyer_id in related_org_ids
                or txn.seller_id in related_org_ids
                or txn.buyer_id in extended_persons
                or txn.seller_id in extended_persons
            )

            if not txn_involves_related:
                continue

            # Check timing: org formed within 30 days BEFORE the transaction
            days_before = (txn.transaction_date - org.formation_date).days
            if not (0 <= days_before <= 30):
                continue

            prop_label = txn.property.address or txn.property.parcel_number or "unknown"

            triggers.append(
                SignalTrigger(
                    rule_id="SR-023",
                    severity="HIGH",
                    title=RULE_REGISTRY["SR-023"].title,
                    detected_summary=(
                        f"'{org.name}' formed on {org.formation_date}, "
                        f"{days_before} days before property transaction at "
                        f"'{prop_label}' on {txn.transaction_date}. "
                        f"The new entity's officers/family are connected to "
                        f"the transaction parties."
                    ),
                    trigger_entity_id=org.pk,
                    trigger_doc=trigger_doc,
                )
            )

    return triggers


# ---------------------------------------------------------------------------
# SR-024 — Charity Conduit Pattern (Buy from Family → Give to Insider)
#
# Case-scoped. Finds TransactionChains of type INSIDER_SWAP where:
#   Step 1: Charity buys property from a family-connected seller
#   Step 2: Charity transfers/grants the same property to another insider
#
# This is the full conduit pattern: charity is used as a pass-through to
# move value from one family member to another while claiming charitable
# purpose.
# ---------------------------------------------------------------------------


def evaluate_sr024_charity_conduit(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import TransactionChain

    triggers = []

    chains = TransactionChain.objects.filter(
        case=case,
        chain_type="INSIDER_SWAP",
    ).prefetch_related("links__transaction__property")

    for chain in chains:
        links = list(chain.links.order_by("sequence_number"))
        if len(links) < 2:
            continue

        first_txn = links[0].transaction
        last_txn = links[-1].transaction

        prop_label = (
            first_txn.property.address
            or first_txn.property.parcel_number
            or "unknown property"
        )

        time_span = chain.time_span_days or "unknown"

        triggers.append(
            SignalTrigger(
                rule_id="SR-024",
                severity="HIGH",
                title=RULE_REGISTRY["SR-024"].title,
                detected_summary=(
                    f"Conduit pattern on '{prop_label}': "
                    f"Step 1 ({first_txn.transaction_date}): {first_txn.seller_name or '?'} "
                    f"→ {first_txn.buyer_name or '?'}. "
                    f"Step {len(links)} ({last_txn.transaction_date}): "
                    f"{last_txn.seller_name or '?'} → {last_txn.buyer_name or '?'}. "
                    f"Total chain span: {time_span} days. "
                    f"Chain label: '{chain.label}'."
                ),
                trigger_entity_id=first_txn.property.pk,
                trigger_doc=trigger_doc,
            )
        )

    return triggers


# ===========================================================================
# 990 CONTRADICTION RULES (SR-025 through SR-029)
#
# These are the most powerful rules in the engine. They don't just look at
# the 990 in isolation — they compare what the 990 SAYS against what the
# DATABASE HAS PROVEN through other documents.
#
# Example: Example Charity marked "No" on Line 28 (transactions with interested
# persons). But our database has Relationship records proving Karen Example
# (president) is married to Jay Example, whose uncle Nick Example sold land
# to the charity, which was flipped to an insider 5 days later.
# The 990 says "No." The database says "Yes." → SR-025 fires: CRITICAL.
# ===========================================================================


# Text patterns for 990 Part IV "No" answers
_LINE_28_NO_PATTERNS = [
    re.compile(r"28[abc][^\n]{0,60}\bno\b", re.IGNORECASE),
    re.compile(r"(?:interested\s+person|related\s+part)[^\n]{0,80}\bno\b", re.IGNORECASE),
]

_LINE_25_NO_PATTERN = re.compile(
    r"(?:25[ab]|independent\s+contractor)[^\n]{0,80}\bno\b",
    re.IGNORECASE,
)

_LINE_3_NO_PATTERN = re.compile(
    r"(?:line\s+3|unrelated\s+business)[^\n]{0,80}\bno\b",
    re.IGNORECASE,
)

_SCHEDULE_B_PATTERN = re.compile(r"\bschedule\s+b\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# SR-025 — 990 Denies Related-Party Transactions, Evidence Contradicts
#
# This is the rule that catches the LIE. The charity says "No, we don't
# do business with insiders." But we have proof they do.
#
# Step 1: Check if any 990 document has Line 28 = "No"
# Step 2: Check if the database has confirmed insider transactions
#         (Relationships linking officers to transaction counterparties)
# Step 3: If both are true → CRITICAL: false disclosure to IRS
# ---------------------------------------------------------------------------


def evaluate_sr025_990_denies_related_party(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import PersonOrganization, PropertyTransaction, Relationship

    # Step 1: Find 990 documents where Line 28 says "No"
    denial_docs = []
    for doc in case.documents.filter(doc_type="IRS_990", extracted_text__isnull=False):
        text = doc.extracted_text
        if any(p.search(text) for p in _LINE_28_NO_PATTERNS):
            denial_docs.append(doc)

    if not denial_docs:
        return []

    # Step 2: Check if database has evidence of related-party transactions
    # Get all persons who are officers/agents of CHARITY orgs
    charity_person_ids = set(
        PersonOrganization.objects.filter(
            org__case=case, org__org_type="CHARITY"
        ).values_list("person_id", flat=True)
    )

    if not charity_person_ids:
        return []

    # Get all persons related to charity officers
    related_person_ids = set()
    for rel in Relationship.objects.filter(case=case):
        if rel.person_a_id in charity_person_ids:
            related_person_ids.add(rel.person_b_id)
        if rel.person_b_id in charity_person_ids:
            related_person_ids.add(rel.person_a_id)

    extended_network = charity_person_ids | related_person_ids

    if not extended_network:
        return []

    # Check if any property transaction involves someone in the network
    related_txns = []
    for prop in case.properties.all():
        for txn in prop.transactions.all():
            if txn.buyer_id in extended_network or txn.seller_id in extended_network:
                related_txns.append(txn)

    if not related_txns:
        return []

    # Step 3: FIRE — 990 says "No" but evidence says "Yes"
    triggers = []
    txn_examples = related_txns[:3]  # Show up to 3 examples
    example_strs = []
    for txn in txn_examples:
        prop_label = txn.property.address or txn.property.parcel_number or "?"
        example_strs.append(
            f"{txn.seller_name or '?'} → {txn.buyer_name or '?'} "
            f"({prop_label}, {txn.transaction_date})"
        )

    for doc in denial_docs:
        triggers.append(
            SignalTrigger(
                rule_id="SR-025",
                severity="CRITICAL",
                title=RULE_REGISTRY["SR-025"].title,
                detected_summary=(
                    f"Form 990 ({doc.display_name or doc.filename}) answers 'No' "
                    f"to Part IV Line 28 (transactions with interested persons), "
                    f"but the case database contains {len(related_txns)} property "
                    f"transaction(s) involving persons related to organization "
                    f"officers. Examples: {'; '.join(example_strs)}. "
                    f"This is a material misrepresentation on a federal tax filing."
                ),
                trigger_doc=doc,
            )
        )

    return triggers


# ---------------------------------------------------------------------------
# SR-026 — 990 Denies Independent Contractors, Evidence Contradicts
#
# Charity says "No" to using contractors, but building permits show
# Doe Construction built everything.
# ---------------------------------------------------------------------------


def evaluate_sr026_990_denies_contractors(case, trigger_doc=None) -> list[SignalTrigger]:
    # Step 1: Find 990 documents where contractor question says "No"
    denial_docs = []
    for doc in case.documents.filter(doc_type="IRS_990", extracted_text__isnull=False):
        if _LINE_25_NO_PATTERN.search(doc.extracted_text):
            denial_docs.append(doc)

    if not denial_docs:
        return []

    # Step 2: Check if building permits exist (evidence of contractors)
    permit_docs = list(
        case.documents.filter(doc_type="BUILDING_PERMIT")
    )

    # Also check for contractor names extracted from permits
    contractor_names = set()
    for permit in permit_docs:
        if permit.extracted_text:
            m = _CONTRACTOR_PATTERN.search(permit.extracted_text)
            if m:
                contractor_names.add(m.group(1).strip())

    if not permit_docs:
        return []

    triggers = []
    contractor_str = ", ".join(contractor_names) if contractor_names else "unnamed contractors"

    for doc in denial_docs:
        triggers.append(
            SignalTrigger(
                rule_id="SR-026",
                severity="HIGH",
                title=RULE_REGISTRY["SR-026"].title,
                detected_summary=(
                    f"Form 990 ({doc.display_name or doc.filename}) indicates "
                    f"no independent contractor compensation, but {len(permit_docs)} "
                    f"building permit(s) in the case name contractors: "
                    f"{contractor_str}. Construction contractors performing "
                    f"significant work must be reported on Form 990."
                ),
                trigger_doc=doc,
            )
        )

    return triggers


# ---------------------------------------------------------------------------
# SR-027 — 990-T Filed But 990 Denies Unrelated Business
# ---------------------------------------------------------------------------


def evaluate_sr027_990t_contradicts_990(case, trigger_doc=None) -> list[SignalTrigger]:
    # Check if a 990-T document exists
    has_990t = case.documents.filter(doc_type="IRS_990T").exists()
    if not has_990t:
        return []

    # Check if any 990 denies unrelated business income
    triggers = []
    for doc in case.documents.filter(doc_type="IRS_990", extracted_text__isnull=False):
        if _LINE_3_NO_PATTERN.search(doc.extracted_text):
            triggers.append(
                SignalTrigger(
                    rule_id="SR-027",
                    severity="HIGH",
                    title=RULE_REGISTRY["SR-027"].title,
                    detected_summary=(
                        f"Form 990 ({doc.display_name or doc.filename}) answers 'No' "
                        f"to unrelated business activity (Part IV Line 3), but a "
                        f"Form 990-T is filed for this organization — which is only "
                        f"required when unrelated business income exists. The 990 and "
                        f"990-T are contradictory."
                    ),
                    trigger_doc=doc,
                )
            )

    return triggers


# ---------------------------------------------------------------------------
# SR-028 — Major Donor Concentration Without Schedule B
# ---------------------------------------------------------------------------


def evaluate_sr028_donor_concentration(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import FinancialSnapshot

    triggers = []

    snapshots = FinancialSnapshot.objects.filter(
        case=case,
        total_revenue__isnull=False,
        total_contributions__isnull=False,
    )

    for snap in snapshots:
        if snap.total_revenue <= 0:
            continue

        contrib_pct = snap.total_contributions / snap.total_revenue

        if contrib_pct < 0.50:
            continue  # Contributions aren't dominant — skip

        # Check if the corresponding 990 document has Schedule B
        if snap.document and snap.document.extracted_text:
            if _SCHEDULE_B_PATTERN.search(snap.document.extracted_text):
                continue  # Schedule B is present — OK

        triggers.append(
            SignalTrigger(
                rule_id="SR-028",
                severity="HIGH",
                title=RULE_REGISTRY["SR-028"].title,
                detected_summary=(
                    f"Tax year {snap.tax_year}: contributions (${snap.total_contributions:,}) "
                    f"represent {contrib_pct:.0%} of total revenue "
                    f"(${snap.total_revenue:,}), but no Schedule B (major donor "
                    f"disclosure) is present. When contributions dominate revenue, "
                    f"the identity of major donors is material to assessing "
                    f"independence and potential quid-pro-quo arrangements."
                ),
                trigger_entity_id=snap.organization_id,
                trigger_doc=snap.document,
            )
        )

    return triggers


# ---------------------------------------------------------------------------
# SR-029 — Low Program Expense Ratio
#
# If less than 50% of spending goes to program services, the charity
# is spending more on real estate, admin, or other non-mission activities
# than on its stated charitable purpose.
# ---------------------------------------------------------------------------

_PROGRAM_EXPENSE_MIN_RATIO = Decimal("0.50")


def evaluate_sr029_low_program_ratio(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import FinancialSnapshot

    triggers = []

    snapshots = FinancialSnapshot.objects.filter(
        case=case,
        total_expenses__isnull=False,
    )

    for snap in snapshots:
        if snap.total_expenses <= 0:
            continue

        # Program expenses = total_expenses - (salaries + fundraising + other)
        # Or if we have grants_paid, that's a direct program expense
        # For now, use: program = total_expenses - salaries - professional_fundraising - other_expenses
        # If any component is missing, we can't compute — skip
        salaries = snap.salaries_and_compensation or 0
        fundraising = snap.professional_fundraising or 0
        other = snap.other_expenses or 0

        non_program = salaries + fundraising + other
        if non_program == 0:
            continue  # Can't compute ratio without components

        program_expenses = snap.total_expenses - non_program
        if program_expenses < 0:
            program_expenses = 0  # Rounding artifact

        ratio = Decimal(str(program_expenses)) / Decimal(str(snap.total_expenses))

        if ratio >= _PROGRAM_EXPENSE_MIN_RATIO:
            continue

        triggers.append(
            SignalTrigger(
                rule_id="SR-029",
                severity="HIGH",
                title=RULE_REGISTRY["SR-029"].title,
                detected_summary=(
                    f"Tax year {snap.tax_year}: only {float(ratio):.0%} of total "
                    f"expenses (${snap.total_expenses:,}) went to program services. "
                    f"Salaries: ${salaries:,}, Fundraising: ${fundraising:,}, "
                    f"Other: ${other:,}. A charity spending less than 50% on its "
                    f"mission warrants review of whether assets are being "
                    f"diverted to private benefit."
                ),
                trigger_entity_id=snap.organization_id,
                trigger_doc=snap.document,
            )
        )

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
    _run_rule("SR-001", evaluate_sr001_deceased_signer, triggers, case, document)
    _run_rule("SR-002", evaluate_sr002_entity_predates_formation, triggers, case, document)
    _run_rule("SR-005", evaluate_sr005_zero_consideration, triggers, case, document)
    _run_rule("SR-006", evaluate_sr006_990_schedule_l, triggers, case, document)
    _run_rule("SR-011", evaluate_sr011_no_independent_board, triggers, case, document)
    _run_rule("SR-012", evaluate_sr012_no_coi_policy, triggers, case, document)
    _run_rule("SR-013", evaluate_sr013_zero_officer_pay, triggers, case, document)
    return triggers


def evaluate_case(case, trigger_doc=None) -> list[SignalTrigger]:
    """
    Run all case-scoped signal rules.

    Original rules: SR-003, SR-004, SR-007, SR-008, SR-009, SR-010.
    New rules:      SR-014 through SR-024.

    Operates on all entities and documents in the case — call after every
    upload so cross-document patterns are detected as the case grows.

    trigger_doc: the document that triggered this evaluation pass.
    Used to associate newly created Signal records with the causal document
    when no more specific entity is the natural trigger.
    """
    triggers: list[SignalTrigger] = []

    # --- Original case-scoped rules ---
    _run_rule("SR-003", evaluate_sr003_valuation_anomaly, triggers, case, trigger_doc)
    _run_rule("SR-004", evaluate_sr004_ucc_burst, triggers, case, trigger_doc)
    _run_rule("SR-007", evaluate_sr007_permit_owner_mismatch, triggers, case, trigger_doc)
    _run_rule("SR-008", evaluate_sr008_survey_before_purchase, triggers, case, trigger_doc)
    _run_rule("SR-009", evaluate_sr009_single_contractor, triggers, case, trigger_doc)
    _run_rule("SR-010", evaluate_sr010_missing_990, triggers, case, trigger_doc)

    # --- New entity/relationship/financial rules ---
    _run_rule("SR-014", evaluate_sr014_address_nexus, triggers, case, trigger_doc)
    _run_rule("SR-015", evaluate_sr015_insider_swap, triggers, case, trigger_doc)
    _run_rule("SR-016", evaluate_sr016_family_network_density, triggers, case, trigger_doc)
    _run_rule("SR-017", evaluate_sr017_blanket_lien_charity, triggers, case, trigger_doc)
    _run_rule("SR-018", evaluate_sr018_rapid_flip, triggers, case, trigger_doc)
    _run_rule("SR-019", evaluate_sr019_entity_proliferation, triggers, case, trigger_doc)
    _run_rule("SR-020", evaluate_sr020_multi_county, triggers, case, trigger_doc)
    _run_rule("SR-021", evaluate_sr021_revenue_spike, triggers, case, trigger_doc)
    _run_rule("SR-022", evaluate_sr022_social_cluster, triggers, case, trigger_doc)
    _run_rule("SR-023", evaluate_sr023_formation_before_acquisition, triggers, case, trigger_doc)
    _run_rule("SR-024", evaluate_sr024_charity_conduit, triggers, case, trigger_doc)

    # --- 990 contradiction rules ---
    _run_rule("SR-025", evaluate_sr025_990_denies_related_party, triggers, case, trigger_doc)
    _run_rule("SR-026", evaluate_sr026_990_denies_contractors, triggers, case, trigger_doc)
    _run_rule("SR-027", evaluate_sr027_990t_contradicts_990, triggers, case, trigger_doc)
    _run_rule("SR-028", evaluate_sr028_donor_concentration, triggers, case, trigger_doc)
    _run_rule("SR-029", evaluate_sr029_low_program_ratio, triggers, case, trigger_doc)

    return triggers


# Maps SR rule IDs to Detection.signal_type values.
_RULE_TO_SIGNAL_TYPE: dict[str, str] = {
    "SR-001": "DECEASED_SIGNER",
    "SR-002": "DATE_IMPOSSIBILITY",
    "SR-003": "VALUATION_DELTA",
    "SR-004": "UCC_LOOP",
    "SR-005": "SELF_DEALING",
    "SR-006": "SELF_DEALING",
    "SR-007": "PROCUREMENT_BYPASS",
    "SR-008": "TIMELINE_COMPRESSION",
    "SR-009": "PROCUREMENT_BYPASS",
    "SR-010": "REVENUE_ANOMALY",
    "SR-011": "SELF_DEALING",
    "SR-012": "SELF_DEALING",
    "SR-013": "PHANTOM_OFFICER",
    # --- New rules ---
    "SR-014": "ADDRESS_NEXUS",
    "SR-015": "INSIDER_SWAP",
    "SR-016": "FAMILY_NETWORK",
    "SR-017": "UCC_BLANKET_LIEN",
    "SR-018": "INSIDER_SWAP",
    "SR-019": "ENTITY_PROLIFERATION",
    "SR-020": "MULTI_COUNTY_CLUSTER",
    "SR-021": "REVENUE_ANOMALY",
    "SR-022": "SOCIAL_CLUSTER",
    "SR-023": "RELATED_PARTY_TX",
    "SR-024": "INSIDER_SWAP",
    # --- 990 contradiction rules ---
    "SR-025": "RELATED_PARTY_TX",
    "SR-026": "PROCUREMENT_BYPASS",
    "SR-027": "REVENUE_ANOMALY",
    "SR-028": "REVENUE_ANOMALY",
    "SR-029": "EXPENSE_RATIO",
}


def persist_signals(case, triggers: list[SignalTrigger]) -> list:
    """
    Persist SignalTrigger results to the **Signal** table with deduplication.

    Per the charter's three-tier workflow:
        Signal (automated) → Detection (confirmed anomaly) → Finding (narrative)

    Signals are the raw automated detections. An investigator reviews them and
    can escalate a Signal to a Detection (confirmation) and eventually to a
    Finding (investigator narrative).

    A trigger is skipped if a Signal already exists for the same
    (case, rule_id, trigger_doc) combination that is not DISMISSED.

    Returns: list of newly created Signal instances.
    """
    from .models import Signal, SignalStatus

    created = []
    seen_this_batch: set[tuple] = set()

    for trigger in triggers:
        trigger_doc = trigger.trigger_doc
        trigger_doc_id = trigger_doc.pk if trigger_doc else None

        # Dedup within this batch
        batch_key = (trigger.rule_id, trigger_doc_id)
        if batch_key in seen_this_batch:
            continue
        seen_this_batch.add(batch_key)

        # Dedup against DB: skip if a non-dismissed Signal exists for this
        # (case, rule_id, trigger_doc) combination.
        existing_qs = Signal.objects.filter(
            case=case,
            rule_id=trigger.rule_id,
            trigger_doc=trigger_doc,
        ).exclude(status=SignalStatus.DISMISSED)

        if existing_qs.exists():
            continue

        signal = Signal.objects.create(
            case=case,
            rule_id=trigger.rule_id,
            severity=trigger.severity,
            trigger_doc=trigger_doc,
            trigger_entity_id=trigger.trigger_entity_id,
            detected_summary=trigger.detected_summary,
            status=SignalStatus.OPEN,
        )
        created.append(signal)
        logger.info(
            "signal_created",
            extra={
                "signal_id": str(signal.pk),
                "rule_id": trigger.rule_id,
                "severity": trigger.severity,
                "case_id": str(case.pk),
            },
        )

    return created


def escalate_signal_to_detection(signal, investigator_note: str = "") -> object:
    """
    Escalate a confirmed Signal to a Detection record.

    This bridges the charter's three-tier workflow:
        Signal (automated) → Detection (confirmed) → Finding (narrative)

    Called when an investigator confirms a signal. Creates a Detection linked
    back to the Signal, preserving the full audit trail.

    Returns: the newly created Detection instance.
    """
    from .models import Detection, DetectionMethod, DetectionStatus, SignalStatus

    signal_type = _RULE_TO_SIGNAL_TYPE.get(signal.rule_id, "MISSING_REQUIRED_FIELDS")

    detection = Detection.objects.create(
        case=signal.case,
        signal_type=signal_type,
        severity=signal.severity,
        status=DetectionStatus.CONFIRMED,
        detection_method=DetectionMethod.SYSTEM_AUTO,
        primary_document=signal.trigger_doc,
        evidence_snapshot={
            "rule_id": signal.rule_id,
            "summary": signal.detected_summary,
            "escalated_from_signal": str(signal.pk),
        },
        confidence_score=1.0,
        investigator_note=investigator_note,
    )

    # Mark the signal as confirmed
    signal.status = SignalStatus.CONFIRMED
    signal.save(update_fields=["status"])

    logger.info(
        "signal_escalated_to_detection",
        extra={
            "signal_id": str(signal.pk),
            "detection_id": str(detection.pk),
            "rule_id": signal.rule_id,
            "case_id": str(signal.case_id),
        },
    )

    return detection


# ===========================================================================
# COVERAGE AUDIT — "What can't the system see yet?"
#
# This is NOT a signal rule. It's a diagnostic that tells the investigator
# which rules are BLIND because the case is missing data. Think of it as
# a checklist: "You uploaded 20 documents but zero relationship records —
# so SR-015 (insider swap) literally cannot fire even if the case is full
# of insider swaps."
#
# Call this after each evaluation pass and show the results on the dashboard
# as a "Data Gaps" panel alongside the signal flags.
# ===========================================================================


@dataclass
class CoverageGap:
    """One item in the coverage audit report."""

    rule_id: str
    rule_title: str
    gap_type: str  # MISSING_DATA | LOW_CONFIDENCE | RULE_BLIND
    message: str
    recommendation: str


def coverage_audit(case) -> list[CoverageGap]:
    """
    Analyze case data completeness and report which signal rules are
    effectively blind due to missing data.

    Returns a list of CoverageGap objects — one per identified gap.
    Show these on the dashboard as actionable recommendations.
    """
    from .models import (
        Address,
        FinancialSnapshot,
        PersonOrganization,
        Relationship,
        SocialMediaConnection,
        TransactionChain,
    )

    gaps = []

    # ── Count key data types ─────────────────────────────────────────
    doc_count = case.documents.count()
    person_count = case.persons.count()
    org_count = case.organizations.count()
    property_count = case.properties.count()
    fin_instrument_count = case.financial_instruments.count()
    relationship_count = Relationship.objects.filter(case=case).count()
    address_count = Address.objects.filter(case=case).count()
    social_count = SocialMediaConnection.objects.filter(case=case).count()
    chain_count = TransactionChain.objects.filter(case=case).count()
    snapshot_count = FinancialSnapshot.objects.filter(case=case).count()
    person_org_count = PersonOrganization.objects.filter(org__case=case).count()

    deceased_count = case.persons.filter(date_of_death__isnull=False).count()
    orgs_with_formation = case.organizations.filter(
        formation_date__isnull=False
    ).count()

    txn_count = 0
    for prop in case.properties.all():
        txn_count += prop.transactions.count()

    # ── Check each rule's data requirements ──────────────────────────

    # SR-001: Needs persons with date_of_death AND documents with text
    if deceased_count == 0:
        gaps.append(CoverageGap(
            rule_id="SR-001",
            rule_title=RULE_REGISTRY["SR-001"].title,
            gap_type="RULE_BLIND",
            message=(
                "No persons have a date_of_death recorded. SR-001 (deceased "
                "signer) cannot detect forgery without knowing who is deceased."
            ),
            recommendation=(
                "Add date_of_death to Person records for any deceased individuals "
                "mentioned in case documents (obituaries, death certificates)."
            ),
        ))

    # SR-002: Needs orgs with formation_date
    if orgs_with_formation == 0 and org_count > 0:
        gaps.append(CoverageGap(
            rule_id="SR-002",
            rule_title=RULE_REGISTRY["SR-002"].title,
            gap_type="RULE_BLIND",
            message=(
                f"{org_count} organizations exist but none have a formation_date. "
                f"SR-002 (entity predates formation) cannot run."
            ),
            recommendation=(
                "Add formation_date from Secretary of State filings to each "
                "Organization record."
            ),
        ))

    # SR-003: Needs properties with BOTH purchase_price and assessed_value
    props_with_both = case.properties.filter(
        purchase_price__isnull=False, assessed_value__isnull=False
    ).count()
    if property_count > 0 and props_with_both == 0:
        gaps.append(CoverageGap(
            rule_id="SR-003",
            rule_title=RULE_REGISTRY["SR-003"].title,
            gap_type="MISSING_DATA",
            message=(
                f"{property_count} properties exist but none have both "
                f"purchase_price and assessed_value. SR-003 (valuation anomaly) "
                f"cannot compare prices."
            ),
            recommendation=(
                "Add assessed_value from county auditor records and "
                "purchase_price from deeds to each Property record."
            ),
        ))

    # SR-014: Needs Address records with links
    if address_count == 0 and (person_count > 0 or org_count > 0):
        gaps.append(CoverageGap(
            rule_id="SR-014",
            rule_title=RULE_REGISTRY["SR-014"].title,
            gap_type="RULE_BLIND",
            message=(
                "No normalized Address records exist. SR-014 (address nexus) "
                "cannot detect shared addresses without the Address table."
            ),
            recommendation=(
                "Create Address records for addresses found on documents, then "
                "link them to Persons and Organizations via PersonAddress and "
                "OrgAddress. Focus on addresses that appear on multiple filings."
            ),
        ))

    # SR-015: Needs Relationships AND PersonOrganization links AND transactions
    if relationship_count == 0:
        gaps.append(CoverageGap(
            rule_id="SR-015",
            rule_title=RULE_REGISTRY["SR-015"].title,
            gap_type="RULE_BLIND",
            message=(
                "No Relationship records exist. SR-015 (insider swap) cannot "
                "detect related-party transactions without knowing who is related "
                "to whom. This is the most important gap to fill."
            ),
            recommendation=(
                "Add Relationship records for family connections (obituaries), "
                "business partnerships (SOS filings), and social connections "
                "(Facebook). Even partial relationship data enables detection."
            ),
        ))
    elif person_org_count == 0:
        gaps.append(CoverageGap(
            rule_id="SR-015",
            rule_title=RULE_REGISTRY["SR-015"].title,
            gap_type="MISSING_DATA",
            message=(
                f"{relationship_count} relationships recorded but no "
                f"PersonOrganization links. SR-015 needs to know who the "
                f"'insiders' are (officers/agents of organizations)."
            ),
            recommendation=(
                "Add PersonOrganization records linking persons to their roles "
                "in case organizations (officer, agent, incorporator, etc.)."
            ),
        ))

    # SR-016: Needs both Relationships and PersonOrganization
    if relationship_count == 0 or person_org_count == 0:
        gaps.append(CoverageGap(
            rule_id="SR-016",
            rule_title=RULE_REGISTRY["SR-016"].title,
            gap_type="RULE_BLIND",
            message=(
                "SR-016 (family network density) requires both Relationship "
                "records and PersonOrganization links to measure how much of "
                "governance is family-controlled."
            ),
            recommendation=(
                "Add family Relationships (from obituaries) and "
                "PersonOrganization links (from 990s and SOS filings)."
            ),
        ))

    # SR-017: Needs blanket lien data on FinancialInstruments
    blanket_count = case.financial_instruments.filter(is_blanket_lien=True).count()
    if fin_instrument_count > 0 and blanket_count == 0:
        gaps.append(CoverageGap(
            rule_id="SR-017",
            rule_title=RULE_REGISTRY["SR-017"].title,
            gap_type="LOW_CONFIDENCE",
            message=(
                f"{fin_instrument_count} financial instruments exist but none "
                f"are flagged as blanket liens. Either there are no blanket liens, "
                f"or the is_blanket_lien field hasn't been populated."
            ),
            recommendation=(
                "Review UCC filings for 'all assets', 'all equipment', or similar "
                "blanket language and set is_blanket_lien=True on those records."
            ),
        ))

    # SR-018/SR-024: Needs property transactions
    if property_count > 0 and txn_count == 0:
        gaps.append(CoverageGap(
            rule_id="SR-018",
            rule_title=RULE_REGISTRY["SR-018"].title,
            gap_type="RULE_BLIND",
            message=(
                f"{property_count} properties exist but no PropertyTransaction "
                f"records. SR-018 (rapid flip) and SR-024 (conduit pattern) "
                f"need transaction history to detect patterns."
            ),
            recommendation=(
                "Add PropertyTransaction records from deeds — at minimum: "
                "transaction_date, buyer_id, seller_id, buyer_name, seller_name, "
                "and price."
            ),
        ))

    # SR-021: Needs FinancialSnapshot data
    if snapshot_count == 0 and org_count > 0:
        charity_count = case.organizations.filter(org_type="CHARITY").count()
        if charity_count > 0:
            gaps.append(CoverageGap(
                rule_id="SR-021",
                rule_title=RULE_REGISTRY["SR-021"].title,
                gap_type="RULE_BLIND",
                message=(
                    "No FinancialSnapshot records exist for any charity. "
                    "SR-021 (revenue spike) needs multi-year 990 data to detect "
                    "anomalous growth patterns."
                ),
                recommendation=(
                    "Add FinancialSnapshot records from each year's Form 990. "
                    "At minimum: tax_year, total_revenue, total_contributions, "
                    "total_expenses."
                ),
            ))

    # SR-022: Needs social media data
    if social_count == 0 and person_count >= 3:
        gaps.append(CoverageGap(
            rule_id="SR-022",
            rule_title=RULE_REGISTRY["SR-022"].title,
            gap_type="LOW_CONFIDENCE",
            message=(
                "No SocialMediaConnection records exist. SR-022 (social cluster) "
                "is optional but powerful — it detects patronage networks that "
                "don't appear on any official filing."
            ),
            recommendation=(
                "If available, add Facebook/LinkedIn connections between case "
                "persons. Focus on the primary officer's friend list and look for "
                "overlap with transaction parties."
            ),
        ))

    # SR-023: Needs orgs with formation dates AND transactions
    if orgs_with_formation == 0 or txn_count == 0:
        gaps.append(CoverageGap(
            rule_id="SR-023",
            rule_title=RULE_REGISTRY["SR-023"].title,
            gap_type="RULE_BLIND",
            message=(
                "SR-023 (entity formation before acquisition) needs both "
                "organization formation_dates and PropertyTransaction records "
                "to detect suspicious timing."
            ),
            recommendation=(
                "Add formation_date to Organizations (from SOS) and "
                "PropertyTransaction records (from deeds)."
            ),
        ))

    # ── General completeness check ───────────────────────────────────
    if doc_count > 0 and person_count == 0 and org_count == 0:
        gaps.append(CoverageGap(
            rule_id="ALL",
            rule_title="Entity Extraction Incomplete",
            gap_type="MISSING_DATA",
            message=(
                f"{doc_count} documents uploaded but no Person or Organization "
                f"records created. Most signal rules need entity data to work."
            ),
            recommendation=(
                "Run entity extraction on uploaded documents, or manually create "
                "Person and Organization records for entities named in the documents."
            ),
        ))

    # ── Manual vs automatic detection ratio ──────────────────────────
    from .models import Detection

    auto_count = Detection.objects.filter(
        case=case, detection_method="SYSTEM_AUTO"
    ).count()
    manual_count = Detection.objects.filter(
        case=case, detection_method="INVESTIGATOR_MANUAL"
    ).count()

    if manual_count > auto_count and manual_count >= 3:
        gaps.append(CoverageGap(
            rule_id="META",
            rule_title="Manual Detections Outnumber Automatic",
            gap_type="LOW_CONFIDENCE",
            message=(
                f"Investigators have manually flagged {manual_count} issues vs "
                f"{auto_count} automatic detections. This suggests the signal "
                f"rules are missing patterns that humans are catching."
            ),
            recommendation=(
                "Review manually-flagged detections for common patterns. "
                "These represent candidates for new automatic signal rules. "
                "Consider adding new SR rules based on the manual findings."
            ),
        ))

    return gaps
