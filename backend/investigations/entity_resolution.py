"""
Entity resolution service for Catalyst.

Stage 3 of the entity resolution pipeline. Takes normalized entity candidates
and either matches them to existing DB records (exact match) or flags them as
candidates for human review (fuzzy match).

The two-tier strategy:

    Tier 1 — Exact match (automatic, no human review needed):
        Normalize both the incoming name and all existing names/aliases in the
        case. If the normalized forms match, it's the same entity. Upsert
        safely — create if new, return existing if already present.

    Tier 2 — Fuzzy match (flagged for review, never auto-merged):
        Use sequence similarity to find names that are close but not identical.
        These go into a FuzzyMatchCandidate structure returned to the caller.
        The caller (upload pipeline) can store these for investigator review.
        They are NEVER automatically merged into existing records.

    Threshold guidance:
        >= 0.92  →  Very likely same person (typo, missing initial)
        0.75–0.91 →  Possibly same person (review recommended)
        < 0.75   →  Probably different people (not surfaced)

This module has Django model imports because it writes to the database.
It is designed to be called from within a Django request/response cycle
or a background task — not directly from tests without a DB.

Pipeline position:
    extract_entities()  →  normalize_*()  →  resolve_persons() / resolve_orgs()  →  DB
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from .entity_normalization import normalize_org_name, normalize_person_name

if TYPE_CHECKING:
    from .models import Case, Document, Organization, Person

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fuzzy match thresholds
# ---------------------------------------------------------------------------

# Minimum similarity to surface a fuzzy candidate for investigator review.
FUZZY_REVIEW_THRESHOLD = 0.75

# Above this threshold, log a note that the match is very strong
# (but still do NOT auto-merge — human confirmation is always required).
FUZZY_HIGH_CONFIDENCE_THRESHOLD = 0.92


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------


@dataclass
class PersonResolutionResult:
    """
    Returned by resolve_person() for each candidate name.

    Attributes:
        person:           The Person record that was matched or created.
        created:          True if a new Person record was inserted.
        matched_alias:    If matched via an alias, the alias that matched.
        fuzzy_candidates: List of near-matches found (but not merged).
    """

    person: "Person"
    created: bool
    matched_alias: str | None = None
    fuzzy_candidates: list["FuzzyCandidate"] = field(default_factory=list)


@dataclass
class OrgResolutionResult:
    """
    Returned by resolve_org() for each candidate org name.
    """

    org: "Organization"
    created: bool
    matched_alias: str | None = None
    fuzzy_candidates: list["FuzzyCandidate"] = field(default_factory=list)


@dataclass
class FuzzyCandidate:
    """
    A near-match that was NOT automatically merged.
    Returned to the caller for investigator review.

    Attributes:
        incoming_raw:       The raw name from the document being processed.
        incoming_normalized: The normalized form of the incoming name.
        existing_id:        UUID of the existing Person or Organization record.
        existing_raw:       The full_name (or name) on the existing record.
        existing_normalized: The normalized form of the existing name.
        similarity:         SequenceMatcher ratio (0.0 – 1.0).
        entity_type:        "person" or "org"
    """

    incoming_raw: str
    incoming_normalized: str
    existing_id: str
    existing_raw: str
    existing_normalized: str
    similarity: float
    entity_type: str


# ---------------------------------------------------------------------------
# Similarity helper
# ---------------------------------------------------------------------------


def _similarity(a: str, b: str) -> float:
    """
    Return a similarity ratio between two normalized strings using
    Python's built-in SequenceMatcher (Ratcliff/Obershelp algorithm).

    0.0 = completely different
    1.0 = identical

    We use this rather than a third-party library (like rapidfuzz) to keep
    dependencies minimal for Phase 2. If performance becomes a concern with
    large cases, rapidfuzz can be swapped in with the same interface.
    """
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Person resolution
# ---------------------------------------------------------------------------


def resolve_person(
    raw_name: str,
    case: "Case",
    document: "Document | None" = None,
    context_note: str = "",
    role: str | None = None,
    address: str | None = None,
    phone: str | None = None,
    aliases: list[str] | None = None,
    notes: str | None = None,
) -> PersonResolutionResult:
    """
    Resolve a raw person name against existing Person records in the case.

    Exact match strategy:
        1. Normalize the incoming name.
        2. For every existing Person in the case, normalize their full_name
           and each entry in their aliases list.
        3. If any normalized form matches → return that Person (no insert).
        4. If no match → create a new Person record.

    Fuzzy match strategy (runs after exact match attempt):
        5. For every existing Person that didn't exact-match, compute
           similarity between the incoming normalized name and their
           normalized full_name.
        6. If similarity >= FUZZY_REVIEW_THRESHOLD → add to fuzzy_candidates.
        7. fuzzy_candidates are returned to the caller but NEVER auto-merged.

    If document is provided, a PersonDocument link is created/updated
    to record that this person appears in this document.

    Args:
        raw_name:     Name as extracted from the document.
        case:         The Case this document belongs to.
        document:     Optional Document to link the person to.
        context_note: Optional note about where/how name appeared.

    Returns:
        PersonResolutionResult with .person, .created, and .fuzzy_candidates.
    """
    from .models import Person

    incoming_norm = normalize_person_name(raw_name)

    if not incoming_norm:
        logger.warning("resolve_person: empty normalized name for raw=%r", raw_name)
        # Still create a minimal record rather than silently dropping it
        person, created = Person.objects.get_or_create(
            case=case,
            full_name=raw_name.strip(),
        )
        return PersonResolutionResult(person=person, created=created)

    existing_persons = list(Person.objects.filter(case=case))

    # --- Tier 1: Exact match ------------------------------------------------
    for existing in existing_persons:
        # Check full_name
        if normalize_person_name(existing.full_name) == incoming_norm:
            _enrich_person(existing, role=role, address=address, phone=phone)
            _maybe_link_person_document(existing, document, context_note)
            logger.debug(
                "resolve_person: exact match on full_name — %r → id=%s",
                raw_name,
                existing.id,
            )
            return PersonResolutionResult(
                person=existing,
                created=False,
                matched_alias=None,
            )
        # Check aliases
        for alias in existing.aliases or []:
            if normalize_person_name(alias) == incoming_norm:
                _maybe_link_person_document(existing, document, context_note)
                logger.debug(
                    "resolve_person: exact match on alias %r — %r → id=%s",
                    alias,
                    raw_name,
                    existing.id,
                )
                return PersonResolutionResult(
                    person=existing,
                    created=False,
                    matched_alias=alias,
                )

    # --- No exact match — collect fuzzy candidates before creating ----------
    fuzzy_candidates: list[FuzzyCandidate] = []
    for existing in existing_persons:
        existing_norm = normalize_person_name(existing.full_name)
        sim = _similarity(incoming_norm, existing_norm)
        if sim >= FUZZY_REVIEW_THRESHOLD:
            candidate = FuzzyCandidate(
                incoming_raw=raw_name,
                incoming_normalized=incoming_norm,
                existing_id=str(existing.id),
                existing_raw=existing.full_name,
                existing_normalized=existing_norm,
                similarity=round(sim, 4),
                entity_type="person",
            )
            fuzzy_candidates.append(candidate)
            level = "HIGH-CONFIDENCE" if sim >= FUZZY_HIGH_CONFIDENCE_THRESHOLD else "review"
            logger.info(
                "resolve_person: fuzzy candidate [%s, sim=%.3f] %r ~ %r",
                level,
                sim,
                raw_name,
                existing.full_name,
            )

    # Sort fuzzy candidates by similarity descending (best match first)
    fuzzy_candidates.sort(key=lambda c: c.similarity, reverse=True)

    # --- Tier 1 miss — create new Person record -----------------------------
    create_kwargs: dict = {"case": case, "full_name": raw_name.strip()}
    if address:
        create_kwargs["address"] = address
    if phone:
        create_kwargs["phone"] = phone
    if aliases:
        create_kwargs["aliases"] = aliases
    if notes:
        create_kwargs["notes"] = notes
    if role:
        create_kwargs["role_tags"] = [_role_to_tag(role)]

    person = Person.objects.create(**create_kwargs)
    _maybe_link_person_document(person, document, context_note)
    logger.debug("resolve_person: created new Person %r id=%s", raw_name, person.id)

    return PersonResolutionResult(
        person=person,
        created=True,
        fuzzy_candidates=fuzzy_candidates,
    )


def _maybe_link_person_document(
    person: "Person",
    document: "Document | None",
    context_note: str,
) -> None:
    """
    Create a PersonDocument link if a document was provided.
    Uses get_or_create to stay idempotent — safe to call multiple times.
    """
    if document is None:
        return
    from .models import PersonDocument

    PersonDocument.objects.get_or_create(
        person=person,
        document=document,
        defaults={"context_note": context_note or ""},
    )


def _role_to_tag(role: str) -> str:
    """Map a free-text role string to a PersonRole enum tag."""
    low = role.lower()
    mapping = {
        "president": "OFFICER",
        "vice president": "OFFICER",
        "vice preside": "OFFICER",
        "treasurer": "OFFICER",
        "secretary": "OFFICER",
        "ceo": "OFFICER",
        "cfo": "OFFICER",
        "executive director": "OFFICER",
        "director": "BOARD_MEMBER",
        "trustee": "TRUSTEE",
        "chairman": "BOARD_MEMBER",
        "board member": "BOARD_MEMBER",
        "member": "BOARD_MEMBER",
        "tax preparer": "TAX_PREPARER",
        "principal officer": "OFFICER",
        "registered agent": "REGISTERED_AGENT",
        "attorney": "ATTORNEY",
    }
    for key, tag in mapping.items():
        if key in low:
            return tag
    return "OFFICER"


def _enrich_person(
    person: "Person",
    role: str | None = None,
    address: str | None = None,
    phone: str | None = None,
) -> None:
    """Fill in blank fields on an existing Person if we have new data."""
    updated = False
    if address and not person.address:
        person.address = address
        updated = True
    if phone and not person.phone:
        person.phone = phone
        updated = True
    if role:
        tag = _role_to_tag(role)
        if tag not in (person.role_tags or []):
            person.role_tags = list(person.role_tags or []) + [tag]
            updated = True
    if updated:
        person.save()
        logger.debug("_enrich_person: updated Person %s with new fields", person.id)


# ---------------------------------------------------------------------------
# Organization resolution
# ---------------------------------------------------------------------------


def resolve_org(
    raw_name: str,
    case: "Case",
    document: "Document | None" = None,
    context_note: str = "",
    ein: str | None = None,
    address: str | None = None,
    phone: str | None = None,
    org_type: str | None = None,
    registration_state: str | None = None,
    notes: str | None = None,
) -> OrgResolutionResult:
    """
    Resolve a raw organization name against existing Organization records
    in the case. Follows the same two-tier strategy as resolve_person().

    Args:
        raw_name:     Org name as extracted from the document.
        case:         The Case this document belongs to.
        document:     Optional Document to link the org to.
        context_note: Optional note about context.

    Returns:
        OrgResolutionResult with .org, .created, and .fuzzy_candidates.
    """
    from .models import Organization

    incoming_norm = normalize_org_name(raw_name)

    if not incoming_norm:
        logger.warning("resolve_org: empty normalized name for raw=%r", raw_name)
        org, created = Organization.objects.get_or_create(
            case=case,
            name=raw_name.strip(),
        )
        return OrgResolutionResult(org=org, created=created)

    existing_orgs = list(Organization.objects.filter(case=case))

    # --- Tier 1: Exact match ------------------------------------------------
    for existing in existing_orgs:
        if normalize_org_name(existing.name) == incoming_norm:
            _enrich_org(existing, ein=ein, address=address, phone=phone)
            _maybe_link_org_document(existing, document, context_note)
            logger.debug(
                "resolve_org: exact match — %r → id=%s",
                raw_name,
                existing.id,
            )
            return OrgResolutionResult(
                org=existing,
                created=False,
                matched_alias=None,
            )

    # --- No exact match — collect fuzzy candidates --------------------------
    fuzzy_candidates: list[FuzzyCandidate] = []
    for existing in existing_orgs:
        existing_norm = normalize_org_name(existing.name)
        sim = _similarity(incoming_norm, existing_norm)
        if sim >= FUZZY_REVIEW_THRESHOLD:
            candidate = FuzzyCandidate(
                incoming_raw=raw_name,
                incoming_normalized=incoming_norm,
                existing_id=str(existing.id),
                existing_raw=existing.name,
                existing_normalized=existing_norm,
                similarity=round(sim, 4),
                entity_type="org",
            )
            fuzzy_candidates.append(candidate)
            logger.info(
                "resolve_org: fuzzy candidate [sim=%.3f] %r ~ %r",
                sim,
                raw_name,
                existing.name,
            )

    fuzzy_candidates.sort(key=lambda c: c.similarity, reverse=True)

    # --- Create new Org record ----------------------------------------------
    create_kwargs: dict = {"case": case, "name": raw_name.strip()}
    if ein:
        create_kwargs["ein"] = ein
    if address:
        create_kwargs["address"] = address
    if phone:
        create_kwargs["phone"] = phone
    if org_type:
        create_kwargs["org_type"] = org_type
    if registration_state:
        create_kwargs["registration_state"] = registration_state
    if notes:
        create_kwargs["notes"] = notes

    org = Organization.objects.create(**create_kwargs)
    _maybe_link_org_document(org, document, context_note)
    logger.debug("resolve_org: created new Organization %r id=%s", raw_name, org.id)

    return OrgResolutionResult(
        org=org,
        created=True,
        fuzzy_candidates=fuzzy_candidates,
    )


def _enrich_org(
    org: "Organization",
    ein: str | None = None,
    address: str | None = None,
    phone: str | None = None,
) -> None:
    """Fill in blank fields on an existing Organization if we have new data."""
    updated = False
    if ein and not org.ein:
        org.ein = ein
        updated = True
    if address and not org.address:
        org.address = address
        updated = True
    if phone and not org.phone:
        org.phone = phone
        updated = True
    if updated:
        org.save()
        logger.debug("_enrich_org: updated Organization %s with new fields", org.id)


def _maybe_link_org_document(
    org: "Organization",
    document: "Document | None",
    context_note: str,
) -> None:
    """Create an OrgDocument link if a document was provided. Idempotent."""
    if document is None:
        return
    from .models import OrgDocument

    OrgDocument.objects.get_or_create(
        org=org,
        document=document,
        defaults={"context_note": context_note or ""},
    )


# ---------------------------------------------------------------------------
# Batch resolution entry point
#
# Called by the upload pipeline with the full output of extract_entities().
# Processes all persons and orgs, returns a summary of what was created
# and what fuzzy candidates need investigator review.
# ---------------------------------------------------------------------------


@dataclass
class ResolutionSummary:
    """
    Summary of what resolve_all_entities() did.

    Attributes:
        persons_created:     Number of new Person records inserted.
        persons_matched:     Number of existing Person records matched.
        orgs_created:        Number of new Organization records inserted.
        orgs_matched:        Number of existing Organization records matched.
        fuzzy_candidates:    All fuzzy candidates across persons and orgs,
                             sorted by similarity descending.
    """

    persons_created: int = 0
    persons_matched: int = 0
    orgs_created: int = 0
    orgs_matched: int = 0
    fuzzy_candidates: list[FuzzyCandidate] = field(default_factory=list)


def resolve_all_entities(
    extraction_result: dict,
    case: "Case",
    document: "Document | None" = None,
) -> ResolutionSummary:
    """
    Process the full output of extract_entities() and resolve all persons
    and orgs against the case's existing entity records.

    Args:
        extraction_result: The dict returned by extract_entities().
        case:              The Case the document belongs to.
        document:          The Document being processed (for link creation).

    Returns:
        ResolutionSummary with counts and any fuzzy candidates.
    """
    summary = ResolutionSummary()

    meta = extraction_result.get("meta", {})

    for person_hit in extraction_result.get("persons", []):
        result = resolve_person(
            raw_name=person_hit["raw"],
            case=case,
            document=document,
            context_note=person_hit.get("context", ""),
            role=person_hit.get("role"),
            address=person_hit.get("address"),
            phone=person_hit.get("phone"),
            aliases=person_hit.get("aliases"),
            notes=person_hit.get("notes"),
        )
        # If this is a 990 preparer, link them to the firm org
        if person_hit.get("source") == "990_preparer" and meta.get("preparer_firm"):
            _link_person_to_firm(result.person, meta["preparer_firm"], case, document)

        if result.created:
            summary.persons_created += 1
        else:
            summary.persons_matched += 1
        summary.fuzzy_candidates.extend(result.fuzzy_candidates)

    for org_hit in extraction_result.get("orgs", []):
        result = resolve_org(
            raw_name=org_hit["raw"],
            case=case,
            document=document,
            context_note=org_hit.get("context", ""),
            ein=org_hit.get("ein"),
            address=org_hit.get("address"),
            phone=org_hit.get("phone"),
        )
        if result.created:
            summary.orgs_created += 1
        else:
            summary.orgs_matched += 1
        summary.fuzzy_candidates.extend(result.fuzzy_candidates)

    # If we got the org's EIN from the 990, enrich the main org
    if meta.get("org_ein"):
        _enrich_case_org_ein(case, meta["org_ein"])

    # Sort all fuzzy candidates by similarity descending
    summary.fuzzy_candidates.sort(key=lambda c: c.similarity, reverse=True)

    logger.info(
        "resolve_all_entities: persons +%d matched=%d | orgs +%d matched=%d | fuzzy_candidates=%d",
        summary.persons_created,
        summary.persons_matched,
        summary.orgs_created,
        summary.orgs_matched,
        len(summary.fuzzy_candidates),
    )

    return summary


def _link_person_to_firm(
    person: "Person",
    firm_name: str,
    case: "Case",
    document: "Document | None",
) -> None:
    """Create a PersonOrganization link between a preparer and their firm."""
    from .models import Organization, PersonOrganization

    from .entity_normalization import normalize_org_name

    target_norm = normalize_org_name(firm_name)
    for org in Organization.objects.filter(case=case):
        if normalize_org_name(org.name) == target_norm:
            PersonOrganization.objects.get_or_create(
                person=person,
                org=org,
                defaults={"role": "Tax Preparer"},
            )
            logger.debug(
                "_link_person_to_firm: linked %s → %s",
                person.full_name,
                org.name,
            )
            return


def _enrich_case_org_ein(case: "Case", ein: str) -> None:
    """
    If the case has an org with no EIN that matches the case name,
    fill in the EIN from the 990.
    """
    from .models import Organization

    orgs = Organization.objects.filter(case=case, ein__isnull=True) | Organization.objects.filter(
        case=case, ein=""
    )
    for org in orgs:
        # Heuristic: if the org name appears in the case name or vice versa
        if org.name.lower() in case.name.lower() or case.name.lower() in org.name.lower():
            org.ein = ein
            org.save()
            logger.debug("_enrich_case_org_ein: set EIN %s on org %s", ein, org.name)
            return
