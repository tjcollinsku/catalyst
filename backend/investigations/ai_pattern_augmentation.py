"""AI Pattern Augmentation — single-pass case-level pattern detector.

Reads a Case with its entities, findings, financial snapshots, and document
excerpts; asks Claude to highlight patterns the rule engine cannot see;
writes each returned pattern as a Finding with source=AI.

See docs/superpowers/specs/2026-04-21-async-frontend-and-ai-patterns-design.md
"""
from __future__ import annotations

import json
import logging
from typing import Any

from django.db import transaction

from investigations import ai_proxy
from investigations.models import (
    Case,
    Document,
    FinancialSnapshot,
    Finding,
    FindingDocument,
    FindingEntity,
    FindingSource,
    Organization,
    Person,
    Property,
    Relationship,
)

logger = logging.getLogger(__name__)

MAX_EXCERPT_CHARS = 2000
MAX_DOCUMENTS = 60

ALLOWED_AI_WEIGHTS = {"SPECULATIVE", "DIRECTIONAL"}
REQUIRED_PATTERN_FIELDS = (
    "title",
    "description",
    "rationale",
    "evidence_weight",
    "doc_refs",
    "suggested_action",
)

SYSTEM_PROMPT = """\
You are a pattern-detection assistant for a public-records fraud
investigator. You are NOT an accuser. You highlight patterns across the
documents and entities you are shown and point toward what the
investigator should pull next. You never assert fraud; never use the words
"fraud", "crime", "illegal", or "guilty". Describe patterns, not verdicts.

Every pattern you return must:
  - cite at least one document by its Doc-N reference,
  - carry an `evidence_weight` of either `SPECULATIVE` or `DIRECTIONAL`
    (never `DOCUMENTED` or `TRACED` \u2014 those require human confirmation),
  - include a plain-language `rationale`,
  - include a concrete `suggested_action` (what to pull or check next).

Prioritize patterns the brittle rule engine cannot see: entity
disambiguation (same person with different name spellings), timeline
anomalies across documents, missing documents a pattern implies should
exist, narrative inconsistencies between filings.

Respond with strict JSON only, matching this schema:
{
  "patterns": [
    {
      "title": "...",
      "description": "...",
      "rationale": "...",
      "evidence_weight": "SPECULATIVE" | "DIRECTIONAL",
      "entity_refs": ["uuid", ...],
      "doc_refs": ["Doc-1", ...],
      "suggested_action": "..."
    }
  ]
}
If you find no patterns, return {"patterns": []}. No prose outside JSON.
"""


def build_context(case: Case) -> dict[str, Any]:
    ctx, _ = build_context_with_refs(case)
    return ctx


def build_context_with_refs(case: Case) -> tuple[dict[str, Any], dict[str, str]]:
    persons = list(Person.objects.filter(case=case))
    orgs = list(Organization.objects.filter(case=case))
    properties = list(Property.objects.filter(case=case))
    snapshots = list(FinancialSnapshot.objects.filter(case=case))
    relationships = list(Relationship.objects.filter(case=case))
    existing_findings = list(Finding.objects.filter(case=case))

    docs = list(Document.objects.filter(case=case).order_by("uploaded_at")[:MAX_DOCUMENTS])
    doc_ref_map: dict[str, str] = {}
    doc_entries: list[dict[str, Any]] = []
    for i, d in enumerate(docs, start=1):
        ref = f"Doc-{i}"
        doc_ref_map[ref] = str(d.id)
        excerpt = (d.extracted_text or "")[:MAX_EXCERPT_CHARS]
        doc_entries.append({
            "ref": ref,
            "doc_type": d.doc_type or "",
            "filename": d.filename,
            "text_excerpt": excerpt,
        })

    ctx: dict[str, Any] = {
        "case": {
            "id": str(case.id),
            "name": case.name,
            "status": case.status,
        },
        "entities": {
            "persons": [
                {
                    "id": str(p.id),
                    "name": p.full_name,
                    "aliases": list(p.aliases or []),
                    "role_tags": list(p.role_tags or []),
                }
                for p in persons
            ],
            "organizations": [
                {
                    "id": str(o.id),
                    "name": o.name,
                    "ein": o.ein or "",
                    "org_type": o.org_type or "",
                }
                for o in orgs
            ],
            "properties": [
                {
                    "id": str(pr.id),
                    "parcel_number": pr.parcel_number or "",
                    "address": pr.address or "",
                    "assessed_value": float(pr.assessed_value or 0),
                    "purchase_price": float(pr.purchase_price or 0),
                }
                for pr in properties
            ],
        },
        "financial_snapshots": [
            {
                "org_id": str(s.organization_id) if s.organization_id else "",
                "tax_year": s.tax_year,
                "revenue": int(s.total_revenue or 0),
                "expenses": int(s.total_expenses or 0),
                "net_assets": int(s.net_assets_eoy or 0),
            }
            for s in snapshots
        ],
        "relationships": [
            {
                "person_a_id": str(r.person_a_id),
                "person_b_id": str(r.person_b_id),
                "relationship_type": r.relationship_type,
            }
            for r in relationships
        ],
        "existing_findings": [
            {
                "rule_id": f.rule_id or "",
                "title": f.title,
                "status": f.status,
                "evidence_weight": f.evidence_weight,
                "source": f.source,
            }
            for f in existing_findings
        ],
        "documents": doc_entries,
    }
    return ctx, doc_ref_map


def parse_response(raw: str) -> list[dict[str, Any]]:
    """Parse Claude's response to a list of pattern dicts. Never raises."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("AI pattern response was not valid JSON")
        return []
    if not isinstance(data, dict):
        return []
    patterns = data.get("patterns")
    if not isinstance(patterns, list):
        return []
    return [p for p in patterns if isinstance(p, dict)]


def validate_patterns(
    patterns: list[dict[str, Any]],
    doc_ref_map: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:
    """Keep only patterns with real doc_refs and required fields.

    Coerces any evidence_weight that isn't SPECULATIVE or DIRECTIONAL down
    to DIRECTIONAL. Returns (kept, dropped_count).
    """
    kept: list[dict[str, Any]] = []
    dropped = 0
    for p in patterns:
        if not all(field in p for field in REQUIRED_PATTERN_FIELDS):
            dropped += 1
            continue
        doc_refs = p.get("doc_refs") or []
        if not isinstance(doc_refs, list) or not doc_refs:
            dropped += 1
            continue
        if any(ref not in doc_ref_map for ref in doc_refs):
            dropped += 1
            logger.info("Dropping AI pattern with unknown doc_ref: %s", doc_refs)
            continue
        weight = p.get("evidence_weight", "")
        if weight not in ALLOWED_AI_WEIGHTS:
            logger.info("Coercing AI evidence_weight %s -> DIRECTIONAL", weight)
            p["evidence_weight"] = "DIRECTIONAL"
        kept.append(p)
    return kept, dropped


def call_claude(context: dict[str, Any]) -> str:
    """Single Claude call with the pattern-detection system prompt.

    Thin wrapper so tests can mock this function.
    """
    user_message = (
        "Here is the case. Return patterns as strict JSON per the schema in "
        "the system prompt.\n\n" + json.dumps(context)
    )
    return ai_proxy._call_ai(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        max_tokens=4096,
    )


def analyze_case(case_id: Any) -> dict[str, Any]:
    """Run the AI pattern pass for one case. Returns a summary dict."""
    case = Case.objects.get(pk=case_id)
    context, doc_ref_map = build_context_with_refs(case)
    raw = call_claude(context)
    patterns = parse_response(raw)
    kept, dropped = validate_patterns(patterns, doc_ref_map)

    created = 0
    with transaction.atomic():
        for p in kept:
            finding = Finding.objects.create(
                case=case,
                rule_id="",
                title=p["title"][:500],
                description=p["description"],
                narrative=p.get("rationale", ""),
                severity="INFORMATIONAL",
                status="NEW",
                evidence_weight=p["evidence_weight"],
                source=FindingSource.AI,
                evidence_snapshot={
                    "rationale": p["rationale"],
                    "suggested_action": p["suggested_action"],
                    "doc_refs": p["doc_refs"],
                    "entity_refs": p.get("entity_refs", []),
                },
            )
            for ref in p["doc_refs"]:
                doc_id = doc_ref_map.get(ref)
                if doc_id:
                    FindingDocument.objects.create(
                        finding=finding,
                        document_id=doc_id,
                    )
            for entity_id in p.get("entity_refs", []):
                try:
                    FindingEntity.objects.create(
                        finding=finding,
                        entity_id=entity_id,
                        entity_type="UNKNOWN",
                    )
                except Exception:
                    logger.info("Skipping invalid entity_ref %s", entity_id)
            created += 1

    return {
        "findings_created": created,
        "patterns_dropped": dropped,
        "case_id": str(case.id),
    }
