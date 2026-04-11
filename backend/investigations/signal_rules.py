"""
Signal Detection Engine for Catalyst.

Evaluates cases and documents against the active signal rule set
(SR-003, SR-004, SR-005, SR-006, SR-010, SR-012, SR-013, SR-015, SR-017,
SR-021, SR-024, SR-025, SR-026, SR-029).

Design principles:
  - Rule evaluator functions are stateless and side-effect-free.
  - Each evaluator accepts (case, document=None) and returns list[SignalTrigger].
  - A rule returns [] when no signal is triggered — never None.
  - Individual rule failures are caught and logged; one bad rule never blocks the rest.
  - This module has no Django view imports — it only uses ORM models.
  - Deduplication and persistence are handled by persist_signals(), not evaluators.

Entry points:
  evaluate_document(case, document) -> list[SignalTrigger]
      Runs document-scoped rules: SR-005, SR-006, SR-012, SR-013.
      Call immediately after a document is uploaded and text is extracted.

  evaluate_case(case, trigger_doc=None) -> list[SignalTrigger]
      Runs case-scoped cross-document rules: SR-003, SR-004, SR-010, SR-015,
      SR-017, SR-021, SR-024, SR-025, SR-026, SR-029.
      Call after every upload — case-level patterns may emerge with each new doc.

  persist_signals(case, triggers, trigger_doc=None) -> list[Signal]
      Persists SignalTrigger results to the DB with deduplication.
      Returns list of newly created Signal instances (duplicates skipped).
"""

import logging
import re
from collections import defaultdict
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
    "SR-010": RuleInfo(
        rule_id="SR-010",
        severity="MEDIUM",
        title="No IRS Form 990 Found for Tax-Exempt Organization",
        description=(
            "Tax-exempt organization has not filed a required Form 990 for one "
            "or more years in which it held tax-exempt status."
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
    "SR-021": RuleInfo(
        rule_id="SR-021",
        severity="HIGH",
        title="Revenue Spike — Year-over-Year Increase Exceeds 100%",
        description=(
            "Total revenue on Form 990 more than doubles from one tax year to "
            "the next, warranting review of the contribution sources."
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

_CONTRACTOR_PATTERN = re.compile(
    r"(?:general\s+)?contractor[:\s]+([A-Z][A-Za-z\s,\.\-]+?)(?:\n|,|$)",
    re.IGNORECASE,
)

_DEED_DOC_TYPES = {"DEED", "RECORDER_INSTRUMENT"}

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
# CASE-SCOPED RULE EVALUATORS — Entity, Relationship, Financial
#
# These rules use the enhanced models (Relationship, TransactionChain,
# FinancialSnapshot) to detect patterns that span multiple entities and
# documents. They are all case-scoped (not document-scoped) because the
# patterns only emerge when you look across the whole case.
#
# GROUNDED EXAMPLES (from the founding investigation):
#   SR-015: Charity buys from family → flips to insider
#   SR-017: Blanket lien on entity at charity address
#   SR-021: Revenue spike ($X.XM contributions in year 2)
#   SR-024: Charity buys from family → gives to insider (conduit)
# ===========================================================================


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
        PersonOrganization,
        PropertyTransaction,
        Relationship,
    )

    triggers = []

    # Step 1: Get all persons who hold roles in case organizations
    org_person_links = PersonOrganization.objects.filter(org__case=case).select_related(
        "person", "org"
    )

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

    relationships = Relationship.objects.filter(case=case).select_related("person_a", "person_b")

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
# SR-017 — UCC Blanket Lien on Charity-Connected Entity
#
# Case-scoped. Finds FinancialInstruments where is_blanket_lien=True and
# the debtor is connected to a charity organization through PersonOrganization
# or Relationship.
# ---------------------------------------------------------------------------


def evaluate_sr017_blanket_lien_charity(case, trigger_doc=None) -> list[SignalTrigger]:
    from .models import PersonOrganization

    triggers = []

    blanket_liens = list(case.financial_instruments.filter(is_blanket_lien=True))

    if not blanket_liens:
        return []

    # Get all persons who are officers/agents of CHARITY organizations
    charity_person_ids = set(
        PersonOrganization.objects.filter(org__case=case, org__org_type="CHARITY").values_list(
            "person_id", flat=True
        )
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
            first_txn.property.address or first_txn.property.parcel_number or "unknown property"
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
    from .models import PersonOrganization, Relationship

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
        PersonOrganization.objects.filter(org__case=case, org__org_type="CHARITY").values_list(
            "person_id", flat=True
        )
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
    permit_docs = list(case.documents.filter(doc_type="BUILDING_PERMIT"))

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
        # For now, use: program = total_expenses - salaries -
        # professional_fundraising - other_expenses
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

    Rules evaluated: SR-005, SR-006, SR-012, SR-013.
    Safe to call immediately after text extraction on every upload.
    """
    triggers: list[SignalTrigger] = []
    _run_rule("SR-005", evaluate_sr005_zero_consideration, triggers, case, document)
    _run_rule("SR-006", evaluate_sr006_990_schedule_l, triggers, case, document)
    _run_rule("SR-012", evaluate_sr012_no_coi_policy, triggers, case, document)
    _run_rule("SR-013", evaluate_sr013_zero_officer_pay, triggers, case, document)
    return triggers


def evaluate_case(case, trigger_doc=None) -> list[SignalTrigger]:
    """
    Run all case-scoped signal rules.

    Rules: SR-003, SR-004, SR-010, SR-015, SR-017, SR-021, SR-024, SR-025,
    SR-026, SR-029, and XML-SIGNALS.

    Operates on all entities and documents in the case — call after every
    upload so cross-document patterns are detected as the case grows.

    trigger_doc: the document that triggered this evaluation pass.
    Used to associate newly created Signal records with the causal document
    when no more specific entity is the natural trigger.
    """
    triggers: list[SignalTrigger] = []

    _run_rule("SR-003", evaluate_sr003_valuation_anomaly, triggers, case, trigger_doc)
    _run_rule("SR-004", evaluate_sr004_ucc_burst, triggers, case, trigger_doc)
    _run_rule("SR-010", evaluate_sr010_missing_990, triggers, case, trigger_doc)
    _run_rule("SR-015", evaluate_sr015_insider_swap, triggers, case, trigger_doc)
    _run_rule("SR-017", evaluate_sr017_blanket_lien_charity, triggers, case, trigger_doc)
    _run_rule("SR-021", evaluate_sr021_revenue_spike, triggers, case, trigger_doc)
    _run_rule("SR-024", evaluate_sr024_charity_conduit, triggers, case, trigger_doc)
    _run_rule("SR-025", evaluate_sr025_990_denies_related_party, triggers, case, trigger_doc)
    _run_rule("SR-026", evaluate_sr026_990_denies_contractors, triggers, case, trigger_doc)
    _run_rule("SR-029", evaluate_sr029_low_program_ratio, triggers, case, trigger_doc)

    # --- IRS XML structured data rules ---
    _run_rule("XML-SIGNALS", evaluate_xml_financial_snapshots, triggers, case, trigger_doc)

    return triggers


# ---------------------------------------------------------------------------
# IRS XML Financial Snapshot Signal Evaluator
#
# This evaluator runs against FinancialSnapshot records that were created
# from parsed IRS 990 XML data (source="IRS_TEOS_XML"). Unlike the document-
# scoped rules (SR-006, SR-012, SR-013) that rely on regex against
# OCR'd PDF text, these use the structured parsed data in raw_extraction.
#
# This is MORE RELIABLE than OCR-based detection because:
#   - No OCR errors or spacing issues
#   - Boolean fields are actual booleans, not "Yes"/"No" text matching
#   - Dollar amounts are actual integers, not regex-extracted strings
#   - Officer compensation is a structured list, not pattern-matched text
# ---------------------------------------------------------------------------


def evaluate_xml_financial_snapshots(case, trigger_doc=None) -> list[SignalTrigger]:
    """
    Evaluate all IRS_TEOS_XML FinancialSnapshots in a case for fraud signals.

    This runs governance, compensation, and financial checks using the
    structured data from parsed 990 XML — the same checks as SR-006,
    SR-012, SR-013, SR-029 but using reliable structured data instead of
    OCR text regex.
    """
    from .models import FinancialSnapshot

    triggers: list[SignalTrigger] = []

    snapshots = FinancialSnapshot.objects.filter(
        case=case,
        source="IRS_TEOS_XML",
        raw_extraction__isnull=False,
    )

    for snap in snapshots:
        raw = snap.raw_extraction
        if not raw or not isinstance(raw, dict):
            continue

        gov = raw.get("governance", {})
        fin = raw.get("financials", {})
        officers = raw.get("officers", [])
        tax_year = raw.get("tax_year", snap.tax_year)
        org_name = raw.get("taxpayer_name", snap.ein)

        # --- SR-006: Schedule L missing when related-party flags are Yes ---
        rp_flags = [
            gov.get("loan_outstanding"),
            gov.get("grant_to_related_person"),
            gov.get("business_rln_with_org_member"),
            gov.get("business_rln_with_family"),
            gov.get("business_rln_with_35_ctrl"),
        ]
        has_related_party = any(f is True for f in rp_flags)
        schedule_l_required = gov.get("schedule_l_required")

        if has_related_party and schedule_l_required is not True:
            which_flags = []
            if gov.get("loan_outstanding"):
                which_flags.append("loans to/from officers")
            if gov.get("grant_to_related_person"):
                which_flags.append("grants to related persons")
            if gov.get("business_rln_with_org_member"):
                which_flags.append("business with board members")
            if gov.get("business_rln_with_family"):
                which_flags.append("business with officer families")
            if gov.get("business_rln_with_35_ctrl"):
                which_flags.append("business with 35% controllers")

            triggers.append(
                SignalTrigger(
                    rule_id="SR-006",
                    severity="HIGH",
                    title=RULE_REGISTRY["SR-006"].title,
                    detected_summary=(
                        f"990 XML ({org_name}, {tax_year}): Part IV indicates "
                        f"{', '.join(which_flags)} but Schedule L may be absent. "
                        f"Related-party transactions require Schedule L disclosure."
                    ),
                    trigger_doc=trigger_doc,
                )
            )

        # --- SR-012: No conflict of interest policy ---
        coi = gov.get("conflict_of_interest_policy")
        if coi is False:
            # Extra severity if also missing whistleblower + doc retention
            missing_policies = []
            if gov.get("whistleblower_policy") is False:
                missing_policies.append("whistleblower")
            if gov.get("document_retention_policy") is False:
                missing_policies.append("document retention")

            extra = ""
            if missing_policies:
                extra = f" Also missing: {', '.join(missing_policies)} policies."

            triggers.append(
                SignalTrigger(
                    rule_id="SR-012",
                    severity="HIGH",
                    title=RULE_REGISTRY["SR-012"].title,
                    detected_summary=(
                        f"990 XML ({org_name}, {tax_year}): No written conflict "
                        f"of interest policy (Part VI Line 12a = No).{extra} "
                        f"Self-dealing transactions are structurally undetectable."
                    ),
                    trigger_doc=trigger_doc,
                )
            )

        # --- SR-013: Zero officer pay at high revenue ---
        total_rev = fin.get("total_revenue") or 0
        if total_rev >= 500_000 and officers:
            # Check if ALL officers report $0
            all_zero = all((o.get("total_compensation", 0) or 0) == 0 for o in officers)
            if all_zero:
                officer_names = [o.get("name", "?") for o in officers[:3]]
                triggers.append(
                    SignalTrigger(
                        rule_id="SR-013",
                        severity="HIGH",
                        title=RULE_REGISTRY["SR-013"].title,
                        detected_summary=(
                            f"990 XML ({org_name}, {tax_year}): Revenue is "
                            f"${total_rev:,} but all {len(officers)} officers "
                            f"report $0 compensation. Officers include: "
                            f"{', '.join(officer_names)}. Review for unreported "
                            f"compensation or related-party payments."
                        ),
                        trigger_doc=trigger_doc,
                    )
                )

        # --- SR-029: Low program expense ratio ---
        total_exp = fin.get("total_expenses") or 0
        salaries = fin.get("salaries_and_compensation") or 0
        fundraising = fin.get("professional_fundraising") or 0
        if total_exp > 0:
            overhead = salaries + fundraising
            program_pct = 1.0 - (overhead / total_exp) if total_exp > 0 else 0
            if program_pct < 0.5 and total_exp > 100_000:
                triggers.append(
                    SignalTrigger(
                        rule_id="SR-029",
                        severity="MEDIUM",
                        title=RULE_REGISTRY["SR-029"].title,
                        detected_summary=(
                            f"990 XML ({org_name}, {tax_year}): Only "
                            f"{program_pct:.0%} of expenses went to programs. "
                            f"Salaries: ${salaries:,}, Fundraising: "
                            f"${fundraising:,}, Total: ${total_exp:,}."
                        ),
                        trigger_doc=trigger_doc,
                    )
                )

        # --- Material diversion flag (governance red flag) ---
        if gov.get("material_diversion_or_misuse") is True:
            triggers.append(
                SignalTrigger(
                    rule_id="SR-025",
                    severity="CRITICAL",
                    title="Material Diversion or Misuse Disclosed",
                    detected_summary=(
                        f"990 XML ({org_name}, {tax_year}): Organization "
                        f"disclosed material diversion or misuse of assets "
                        f"in Part VI. This is a self-reported governance "
                        f"failure requiring immediate investigation."
                    ),
                    trigger_doc=trigger_doc,
                )
            )

    return triggers


# Maps SR rule IDs to anomaly type labels (for categorization).
_RULE_TO_SIGNAL_TYPE: dict[str, str] = {
    "SR-003": "VALUATION_DELTA",
    "SR-004": "UCC_LOOP",
    "SR-005": "SELF_DEALING",
    "SR-006": "SELF_DEALING",
    "SR-010": "REVENUE_ANOMALY",
    "SR-012": "SELF_DEALING",
    "SR-013": "PHANTOM_OFFICER",
    "SR-015": "INSIDER_SWAP",
    "SR-017": "UCC_BLANKET_LIEN",
    "SR-021": "REVENUE_ANOMALY",
    "SR-024": "INSIDER_SWAP",
    "SR-025": "RELATED_PARTY_TX",
    "SR-026": "PROCUREMENT_BYPASS",
    "SR-029": "EXPENSE_RATIO",
}


def persist_signals(case, triggers: list[SignalTrigger]) -> list:
    """
    Persist SignalTrigger results as Finding records with dedup.

    Each trigger becomes a Finding with status=NEW, evidence_weight=
    SPECULATIVE, source=AUTO. The investigator triages from there.

    A trigger is skipped if a non-dismissed Finding already exists
    for the same (case, rule_id, trigger_doc) combination.

    Returns: list of newly created Finding instances.
    """
    from .models import (
        EvidenceWeight,
        Finding,
        FindingDocument,
        FindingSource,
        FindingStatus,
    )

    created = []
    seen_this_batch: set[tuple] = set()

    for trigger in triggers:
        trigger_doc = trigger.trigger_doc
        trigger_doc_id = (
            trigger_doc.pk if trigger_doc else None
        )

        # Dedup within this batch
        batch_key = (trigger.rule_id, trigger_doc_id)
        if batch_key in seen_this_batch:
            continue
        seen_this_batch.add(batch_key)

        # Dedup against DB
        existing_qs = Finding.objects.filter(
            case=case,
            rule_id=trigger.rule_id,
            trigger_doc=trigger_doc,
        ).exclude(status=FindingStatus.DISMISSED)

        if existing_qs.exists():
            continue

        finding = Finding.objects.create(
            case=case,
            rule_id=trigger.rule_id,
            title=trigger.title,
            description=trigger.detected_summary,
            severity=trigger.severity,
            status=FindingStatus.NEW,
            evidence_weight=EvidenceWeight.SPECULATIVE,
            source=FindingSource.AUTO,
            trigger_doc=trigger_doc,
            trigger_entity_id=trigger.trigger_entity_id,
        )
        # Create FindingDocument M2M link so the UI can show
        # which document triggered this finding.
        if trigger_doc:
            FindingDocument.objects.get_or_create(
                finding=finding,
                document=trigger_doc,
                defaults={"context_note": "Trigger document"},
            )

        created.append(finding)
        logger.info(
            "finding_created",
            extra={
                "finding_id": str(finding.pk),
                "rule_id": trigger.rule_id,
                "severity": trigger.severity,
                "case_id": str(case.pk),
            },
        )

    return created


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
        FinancialSnapshot,
        PersonOrganization,
        Relationship,
    )

    gaps = []

    # ── Count key data types ─────────────────────────────────────────
    doc_count = case.documents.count()
    person_count = case.persons.count()
    org_count = case.organizations.count()
    property_count = case.properties.count()
    fin_instrument_count = case.financial_instruments.count()
    relationship_count = Relationship.objects.filter(case=case).count()
    snapshot_count = FinancialSnapshot.objects.filter(case=case).count()
    person_org_count = PersonOrganization.objects.filter(org__case=case).count()

    txn_count = 0
    for prop in case.properties.all():
        txn_count += prop.transactions.count()

    # ── Check each rule's data requirements ──────────────────────────

    # SR-003: Needs properties with BOTH purchase_price and assessed_value
    props_with_both = case.properties.filter(
        purchase_price__isnull=False, assessed_value__isnull=False
    ).count()
    if property_count > 0 and props_with_both == 0:
        gaps.append(
            CoverageGap(
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
            )
        )

    # SR-015: Needs Relationships AND PersonOrganization links AND transactions
    if relationship_count == 0:
        gaps.append(
            CoverageGap(
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
            )
        )
    elif person_org_count == 0:
        gaps.append(
            CoverageGap(
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
            )
        )

    # SR-017: Needs blanket lien data on FinancialInstruments
    blanket_count = case.financial_instruments.filter(is_blanket_lien=True).count()
    if fin_instrument_count > 0 and blanket_count == 0:
        gaps.append(
            CoverageGap(
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
            )
        )

    # SR-024: Needs property transactions
    if property_count > 0 and txn_count == 0:
        gaps.append(
            CoverageGap(
                rule_id="SR-024",
                rule_title=RULE_REGISTRY["SR-024"].title,
                gap_type="RULE_BLIND",
                message=(
                    f"{property_count} properties exist but no PropertyTransaction "
                    f"records. SR-024 (conduit pattern) needs transaction history to "
                    f"detect patterns."
                ),
                recommendation=(
                    "Add PropertyTransaction records from deeds — at minimum: "
                    "transaction_date, buyer_id, seller_id, buyer_name, seller_name, "
                    "and price."
                ),
            )
        )

    # SR-021: Needs FinancialSnapshot data
    if snapshot_count == 0 and org_count > 0:
        charity_count = case.organizations.filter(org_type="CHARITY").count()
        if charity_count > 0:
            gaps.append(
                CoverageGap(
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
                )
            )

    # ── General completeness check ───────────────────────────────────
    if doc_count > 0 and person_count == 0 and org_count == 0:
        gaps.append(
            CoverageGap(
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
            )
        )

    # ── Manual vs automatic finding ratio ───────────────────────────
    from .models import Finding, FindingSource

    auto_count = Finding.objects.filter(
        case=case, source=FindingSource.AUTO
    ).count()
    manual_count = Finding.objects.filter(
        case=case, source=FindingSource.MANUAL
    ).count()

    if manual_count > auto_count and manual_count >= 3:
        gaps.append(
            CoverageGap(
                rule_id="META",
                rule_title="Manual Findings Outnumber Automatic",
                gap_type="LOW_CONFIDENCE",
                message=(
                    f"Investigators have manually created "
                    f"{manual_count} findings vs {auto_count} "
                    f"auto-detected. Signal rules may be missing "
                    f"patterns that humans are catching."
                ),
                recommendation=(
                    "Review manual findings for common patterns. "
                    "These are candidates for new signal rules."
                ),
            )
        )

    return gaps
