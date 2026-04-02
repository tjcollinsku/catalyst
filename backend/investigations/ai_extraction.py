"""
AI-powered entity extraction layer for Catalyst.

Enhances the regex-based entity_extraction module with Claude API calls for
deeper, context-aware extraction from documents.

Architecture: "AI proposes, human confirms, rules detect"
    - This module (Layer 1): AI reads documents and proposes structured entities
    - data_quality.py validates the proposals before DB insertion
    - signal_rules.py (Layer 2) runs deterministic fraud detection on the clean data
    - The AI NEVER makes detection decisions — it only extracts data

Pipeline position:
    extract_from_pdf() → regex extract_entities() → AI enhance → validate → DB
                                                     ^^^^^^^^^
                                                    (this module)

Usage:
    from investigations.ai_extraction import ai_extract_entities, ai_extract_990

    # Full document extraction (persons, orgs, relationships, dates, amounts)
    result = await ai_extract_entities(text, doc_type="DEED")

    # Specialized 990 extraction (the fields OCR gets wrong)
    result = await ai_extract_990(text)

    # Merge AI results with regex results
    merged = merge_extractions(regex_result, ai_result)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("catalyst.ai_extraction")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load API key from environment (set in .env, loaded by Django settings via
# python-dotenv). We import lazily so this module can be tested without Django.
_API_KEY: str | None = None


def _get_api_key() -> str:
    """Resolve the Anthropic API key, caching after first lookup."""
    global _API_KEY
    if _API_KEY is None:
        _API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    if not _API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
    return _API_KEY


def _get_client():
    """
    Create and return an Anthropic client.

    Lazy import so the module can be imported even if the anthropic
    package isn't installed — it only fails when you actually call AI.
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError(
            "The 'anthropic' package is required for AI extraction. "
            "Install it with: pip install anthropic"
        )
    return Anthropic(api_key=_get_api_key())


# Model to use. Claude 3.5 Sonnet is the best balance of speed, cost, and
# quality for structured extraction tasks.
AI_MODEL = "claude-sonnet-4-20250514"

# Maximum tokens for extraction responses. Structured JSON rarely exceeds this.
MAX_TOKENS = 4096

# Temperature — 0 for deterministic extraction (no creativity needed).
TEMPERATURE = 0.0


# ---------------------------------------------------------------------------
# Confidence tracking — every AI proposal carries a confidence score
# ---------------------------------------------------------------------------


@dataclass
class AIProposal:
    """
    A single entity proposed by the AI, awaiting human confirmation.

    The 'confidence' field (0.0–1.0) is set by the AI itself based on how
    certain it is about the extraction. Investigators see this in the UI
    and can accept/reject each proposal.
    """

    entity_type: str  # "person", "org", "relationship", "date", "amount", etc.
    data: dict[str, Any]  # The extracted fields
    confidence: float  # 0.0–1.0, set by AI
    source_text: str  # The snippet of text the AI extracted from
    reasoning: str = ""  # Why the AI thinks this entity exists


@dataclass
class AIExtractionResult:
    """Container for all AI-extracted entities from a document."""

    proposals: list[AIProposal] = field(default_factory=list)
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None

    @property
    def persons(self) -> list[AIProposal]:
        return [p for p in self.proposals if p.entity_type == "person"]

    @property
    def orgs(self) -> list[AIProposal]:
        return [p for p in self.proposals if p.entity_type == "org"]

    @property
    def relationships(self) -> list[AIProposal]:
        return [p for p in self.proposals if p.entity_type == "relationship"]

    @property
    def financials(self) -> list[AIProposal]:
        return [p for p in self.proposals if p.entity_type == "financial"]

    @property
    def dates(self) -> list[AIProposal]:
        return [p for p in self.proposals if p.entity_type == "date"]

    @property
    def amounts(self) -> list[AIProposal]:
        return [p for p in self.proposals if p.entity_type == "amount"]


# ---------------------------------------------------------------------------
# System prompts — instruct Claude on what to extract and how to format it
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_GENERAL = """You are an entity extraction engine for a forensic
document analysis system investigating nonprofit charity fraud. Your job is to
read document text and extract structured entities.

CRITICAL RULES:
1. You ONLY extract data. You NEVER make fraud determinations or accusations.
2. Extract what the document SAYS, not what you think it means.
3. Every extraction must include a confidence score (0.0-1.0).
4. If something is ambiguous, extract it with lower confidence and explain why.
5. Prefer precision over recall — missing an entity is better than hallucinating one.

You must respond with ONLY valid JSON matching the schema below. No markdown,
no explanation text outside the JSON.

Response schema:
{
  "persons": [
    {
      "name": "Full Name",
      "role": "grantor|grantee|officer|director|trustee|beneficiary|signer|other",
      "title": "President (if stated)",
      "context": "The exact text snippet where this person appears",
      "confidence": 0.95,
      "reasoning": "Why you extracted this person"
    }
  ],
  "organizations": [
    {
      "name": "Org Name Inc.",
      "org_type": "nonprofit|llc|llp|corporation|trust|land_trust|sole_prop|government|other",
      "ein": "XX-XXXXXXX (if found)",
      "state_of_formation": "OH (if found)",
      "context": "The exact text snippet",
      "confidence": 0.95,
      "reasoning": "Why"
    }
  ],
  "relationships": [
    {
      "person_or_org_1": "Name A",
      "person_or_org_2": "Name B",
      "relationship_type": (
        "officer_of|director_of|member_of|owner_of|spouse|parent_child|"
        "sibling|business_partner|contractor|grantor_grantee|"
        "employer_employee|other"
      ),
      "context": "The text that reveals this relationship",
      "confidence": 0.85,
      "reasoning": "Why"
    }
  ],
  "dates": [
    {
      "raw": "March 2, 2022",
      "normalized": "2022-03-02",
      "event": "What this date refers to (e.g., 'document execution', 'sale date')",
      "confidence": 0.99
    }
  ],
  "amounts": [
    {
      "raw": "$4,505,000.00",
      "normalized": 4505000.0,
      "purpose": "What this amount represents (e.g., 'sale price', 'consideration')",
      "confidence": 0.99
    }
  ],
  "addresses": [
    {
      "raw": "123 Main St, Example City, OH 45822",
      "street": "123 Main St",
      "city": "Example City",
      "state": "OH",
      "zip": "45822",
      "associated_entity": "Name of person/org at this address",
      "confidence": 0.90
    }
  ]
}"""

_SYSTEM_PROMPT_990 = """You are a specialized IRS Form 990 extraction engine for
a forensic document analysis system. You read OCR'd or structured 990 text and
extract the specific fields that matter for fraud investigation.

CRITICAL RULES:
1. You ONLY extract data. You NEVER make fraud determinations.
2. 990 forms have specific Yes/No checkboxes. Extract EXACTLY what the form says.
3. Financial numbers from OCR may be garbled. Flag low-confidence numbers.
4. Officer/director names from OCR are often mangled. Extract your best reading.
5. Pay special attention to:
   - Part IV (Checklist of Required Schedules) — the Yes/No answers
   - Part VII (Officers, Directors, Trustees) — compensation data
   - Schedule L (Transactions with Interested Persons)
   - Schedule B (Schedule of Contributors) if present
   - Part IX (Statement of Functional Expenses)

You must respond with ONLY valid JSON matching this schema:

{
  "tax_year": "2022",
  "ein": "82-4458479",
  "org_name": "Organization Name",
  "confidence_overall": 0.85,

  "officers": [
    {
      "name": "John Doe",
      "title": "President",
      "hours_per_week": 40.0,
      "reportable_compensation": 0,
      "other_compensation": 0,
      "is_former": false,
      "confidence": 0.90
    }
  ],

  "part_iv_checklist": {
    "line_25a_related_party_transaction": {"answer": "No", "confidence": 0.95},
    "line_25b_excess_benefit_transaction": {"answer": "No", "confidence": 0.95},
    "line_26_loan_to_officer": {"answer": "No", "confidence": 0.90},
    "line_27_grant_to_officer": {"answer": "No", "confidence": 0.90},
    "line_28a_officer_is_entity_officer": {"answer": "No", "confidence": 0.85},
    "line_28b_officer_family_relationship": {"answer": "No", "confidence": 0.85},
    "line_28c_entity_with_officer": {"answer": "No", "confidence": 0.85},
    "line_5_independent_contractors": {"answer": "Yes", "confidence": 0.90}
  },

  "financials": {
    "total_revenue": 0,
    "total_expenses": 0,
    "net_assets_eoy": 0,
    "program_service_expenses": 0,
    "management_expenses": 0,
    "fundraising_expenses": 0,
    "total_compensation": 0,
    "number_voting_members": 0,
    "number_independent_members": 0,
    "number_employees": 0,
    "number_volunteers": 0,
    "unrelated_business_revenue": 0,
    "confidence": 0.80
  },

  "schedule_l_present": false,
  "schedule_b_present": false,

  "contractors": [
    {
      "name": "Contractor Name",
      "services": "What they were paid for",
      "compensation": 0,
      "confidence": 0.85
    }
  ],

  "notes": "Any important observations about data quality, OCR issues, etc."
}"""


_SYSTEM_PROMPT_OBITUARY = """You are a specialized obituary/death notice extraction
engine for a forensic document analysis system. Obituaries contain critical family
relationship data that reveals insider networks.

CRITICAL RULES:
1. You ONLY extract data. You NEVER make fraud determinations.
2. Obituaries reveal family trees. Extract ALL family relationships mentioned.
3. Pay attention to: spouse, children, siblings, parents, in-laws, grandchildren.
4. Married names vs maiden names matter — extract both when stated.
5. "Preceded in death by" = deceased. "Survived by" = living (as of obit date).

You must respond with ONLY valid JSON matching this schema:

{
  "deceased": {
    "name": "Full Name",
    "birth_date": "YYYY-MM-DD or null",
    "death_date": "YYYY-MM-DD or null",
    "age_at_death": 84,
    "residence": "City, State",
    "confidence": 0.95
  },
  "family_relationships": [
    {
      "person": "Full Name",
      "relationship_to_deceased": (
        "spouse|child|sibling|parent|grandchild|in_law|niece_nephew|other"
      ),
      "status": "living|deceased",
      "spouse_name": "Their spouse's name if mentioned",
      "maiden_name": "If mentioned (née ...)",
      "context": "the text snippet",
      "confidence": 0.90
    }
  ],
  "organizations_mentioned": [
    {
      "name": "Org Name",
      "context": "How it's mentioned (employer, church, charity, etc.)",
      "confidence": 0.85
    }
  ],
  "locations_mentioned": [
    {
      "place": "Russia, OH",
      "context": "Residence, burial, etc.",
      "confidence": 0.90
    }
  ]
}"""


# ---------------------------------------------------------------------------
# Core extraction functions
# ---------------------------------------------------------------------------


def ai_extract_entities(
    text: str,
    doc_type: str = "OTHER",
    max_text_length: int = 15000,
) -> AIExtractionResult:
    """
    Use Claude to extract entities from document text.

    This is the general-purpose extractor. For 990s and obituaries, use
    the specialized functions below.

    Parameters
    ----------
    text : str
        Raw extracted text from a document.
    doc_type : str
        Document type hint (DEED, PARCEL_RECORD, UCC_FILING, etc.)
    max_text_length : int
        Truncate input text to this length to control API costs.
        Default 15k chars ≈ 4k tokens.

    Returns
    -------
    AIExtractionResult with proposals and token usage.
    """
    if not text or not text.strip():
        return AIExtractionResult(error="Empty text provided")

    # Truncate very long documents to control costs
    input_text = text[:max_text_length]
    if len(text) > max_text_length:
        input_text += f"\n\n[... truncated, {len(text) - max_text_length} chars omitted ...]"

    user_prompt = (
        f"Document type: {doc_type}\n\n"
        f"--- DOCUMENT TEXT ---\n{input_text}\n--- END DOCUMENT TEXT ---\n\n"
        "Extract all persons, organizations, relationships, dates, amounts, "
        "and addresses from this document. Respond with ONLY the JSON."
    )

    return _call_claude(
        system_prompt=_SYSTEM_PROMPT_GENERAL,
        user_prompt=user_prompt,
        parse_fn=_parse_general_response,
    )


def ai_extract_990(
    text: str,
    max_text_length: int = 20000,
) -> AIExtractionResult:
    """
    Specialized 990 extraction — pulls the fields OCR typically mangles.

    This targets Part IV checklist answers, officer compensation, financial
    totals, and Schedule L/B presence — the exact data our signal rules
    (SR-006, SR-011, SR-012, SR-013, SR-025, SR-026, SR-029) need.

    Parameters
    ----------
    text : str
        Raw OCR'd or structured text from a 990 form.
    max_text_length : int
        Truncate limit. 990s are long; 20k chars covers most of the form.

    Returns
    -------
    AIExtractionResult with proposals for financial and officer data.
    """
    if not text or not text.strip():
        return AIExtractionResult(error="Empty text provided")

    input_text = text[:max_text_length]
    if len(text) > max_text_length:
        input_text += f"\n\n[... truncated, {len(text) - max_text_length} chars omitted ...]"

    user_prompt = (
        "--- IRS FORM 990 TEXT ---\n"
        f"{input_text}\n"
        "--- END 990 TEXT ---\n\n"
        "Extract all structured data from this 990 form. Pay special attention to "
        "Part IV Yes/No answers, officer compensation in Part VII, and financial "
        "totals. Respond with ONLY the JSON."
    )

    return _call_claude(
        system_prompt=_SYSTEM_PROMPT_990,
        user_prompt=user_prompt,
        parse_fn=_parse_990_response,
    )


def ai_extract_obituary(
    text: str,
    max_text_length: int = 5000,
) -> AIExtractionResult:
    """
    Specialized obituary extraction — maps family relationship networks.

    Obituaries are the #1 source for discovering hidden family connections
    between insiders. This is how we found the Example-FamilyMember-ExampleSeller-RelatedParty
    network in the Example Charity case.

    Parameters
    ----------
    text : str
        Raw text from an obituary or death notice.
    max_text_length : int
        Obituaries are short; 5k is generous.

    Returns
    -------
    AIExtractionResult with person and relationship proposals.
    """
    if not text or not text.strip():
        return AIExtractionResult(error="Empty text provided")

    input_text = text[:max_text_length]

    user_prompt = (
        "--- OBITUARY TEXT ---\n"
        f"{input_text}\n"
        "--- END OBITUARY TEXT ---\n\n"
        "Extract all persons, family relationships, organizations, and locations "
        "from this obituary. Respond with ONLY the JSON."
    )

    return _call_claude(
        system_prompt=_SYSTEM_PROMPT_OBITUARY,
        user_prompt=user_prompt,
        parse_fn=_parse_obituary_response,
    )


# ---------------------------------------------------------------------------
# API call wrapper
# ---------------------------------------------------------------------------


def _call_claude(
    system_prompt: str,
    user_prompt: str,
    parse_fn,
) -> AIExtractionResult:
    """
    Make a Claude API call and parse the response.

    Handles errors gracefully — if the API call fails, returns an
    AIExtractionResult with the error message rather than raising.
    This ensures the upload pipeline never crashes due to AI issues;
    the regex extractor output remains as the fallback.
    """
    try:
        client = _get_client()
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Extract the text content from the response
        raw_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text

        # Parse the JSON response into AIProposal objects
        result = parse_fn(raw_text)
        result.model_used = AI_MODEL
        result.input_tokens = response.usage.input_tokens
        result.output_tokens = response.usage.output_tokens

        logger.info(
            "ai_extraction_complete",
            extra={
                "model": AI_MODEL,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "proposals": len(result.proposals),
            },
        )
        return result

    except ImportError as e:
        logger.error("ai_extraction_import_error", extra={"error": str(e)})
        return AIExtractionResult(error=str(e))

    except Exception as e:
        logger.error("ai_extraction_error", extra={"error": str(e)})
        return AIExtractionResult(error=str(e))


# ---------------------------------------------------------------------------
# Response parsers — convert Claude's JSON into AIProposal lists
# ---------------------------------------------------------------------------


def _safe_json_parse(raw_text: str) -> dict | None:
    """
    Parse JSON from Claude's response, tolerant of markdown code fences.

    Claude sometimes wraps JSON in ```json ... ``` even when told not to.
    We strip that wrapper before parsing.
    """
    text = raw_text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[first_newline + 1 :]
    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("ai_json_parse_failed", extra={"error": str(e), "raw": text[:200]})
        return None


def _parse_general_response(raw_text: str) -> AIExtractionResult:
    """Parse the general entity extraction JSON into AIProposal objects."""
    data = _safe_json_parse(raw_text)
    if data is None:
        return AIExtractionResult(error="Failed to parse AI response as JSON")

    proposals: list[AIProposal] = []

    # --- Persons ---
    for p in data.get("persons", []):
        proposals.append(
            AIProposal(
                entity_type="person",
                data={
                    "name": p.get("name", ""),
                    "role": p.get("role", "other"),
                    "title": p.get("title", ""),
                },
                confidence=float(p.get("confidence", 0.5)),
                source_text=p.get("context", ""),
                reasoning=p.get("reasoning", ""),
            )
        )

    # --- Organizations ---
    for o in data.get("organizations", []):
        proposals.append(
            AIProposal(
                entity_type="org",
                data={
                    "name": o.get("name", ""),
                    "org_type": o.get("org_type", "other"),
                    "ein": o.get("ein", ""),
                    "state_of_formation": o.get("state_of_formation", ""),
                },
                confidence=float(o.get("confidence", 0.5)),
                source_text=o.get("context", ""),
                reasoning=o.get("reasoning", ""),
            )
        )

    # --- Relationships ---
    for r in data.get("relationships", []):
        proposals.append(
            AIProposal(
                entity_type="relationship",
                data={
                    "entity_1": r.get("person_or_org_1", ""),
                    "entity_2": r.get("person_or_org_2", ""),
                    "relationship_type": r.get("relationship_type", "other"),
                },
                confidence=float(r.get("confidence", 0.5)),
                source_text=r.get("context", ""),
                reasoning=r.get("reasoning", ""),
            )
        )

    # --- Dates ---
    for d in data.get("dates", []):
        proposals.append(
            AIProposal(
                entity_type="date",
                data={
                    "raw": d.get("raw", ""),
                    "normalized": d.get("normalized", ""),
                    "event": d.get("event", ""),
                },
                confidence=float(d.get("confidence", 0.5)),
                source_text=d.get("raw", ""),
            )
        )

    # --- Amounts ---
    for a in data.get("amounts", []):
        proposals.append(
            AIProposal(
                entity_type="amount",
                data={
                    "raw": a.get("raw", ""),
                    "normalized": a.get("normalized", 0.0),
                    "purpose": a.get("purpose", ""),
                },
                confidence=float(a.get("confidence", 0.5)),
                source_text=a.get("raw", ""),
            )
        )

    # --- Addresses ---
    for addr in data.get("addresses", []):
        proposals.append(
            AIProposal(
                entity_type="address",
                data={
                    "raw": addr.get("raw", ""),
                    "street": addr.get("street", ""),
                    "city": addr.get("city", ""),
                    "state": addr.get("state", ""),
                    "zip": addr.get("zip", ""),
                    "associated_entity": addr.get("associated_entity", ""),
                },
                confidence=float(addr.get("confidence", 0.5)),
                source_text=addr.get("raw", ""),
            )
        )

    return AIExtractionResult(proposals=proposals)


def _parse_990_response(raw_text: str) -> AIExtractionResult:
    """Parse the 990-specific JSON into AIProposal objects."""
    data = _safe_json_parse(raw_text)
    if data is None:
        return AIExtractionResult(error="Failed to parse AI 990 response as JSON")

    proposals: list[AIProposal] = []

    # --- Officers ---
    for officer in data.get("officers", []):
        proposals.append(
            AIProposal(
                entity_type="person",
                data={
                    "name": officer.get("name", ""),
                    "title": officer.get("title", ""),
                    "role": "officer",
                    "hours_per_week": officer.get("hours_per_week", 0),
                    "reportable_compensation": officer.get("reportable_compensation", 0),
                    "other_compensation": officer.get("other_compensation", 0),
                    "is_former": officer.get("is_former", False),
                },
                confidence=float(officer.get("confidence", 0.5)),
                source_text=f"990 Part VII: {officer.get('name', '')}",
            )
        )

    # --- Part IV Checklist (the Yes/No answers signal rules need) ---
    checklist = data.get("part_iv_checklist", {})
    if checklist:
        proposals.append(
            AIProposal(
                entity_type="financial",
                data={
                    "data_type": "990_part_iv_checklist",
                    "tax_year": data.get("tax_year", ""),
                    "ein": data.get("ein", ""),
                    "checklist": {
                        key: {
                            "answer": val.get("answer", ""),
                            "confidence": float(val.get("confidence", 0.5)),
                        }
                        for key, val in checklist.items()
                        if isinstance(val, dict)
                    },
                },
                confidence=float(data.get("confidence_overall", 0.7)),
                source_text="990 Part IV",
            )
        )

    # --- Financial totals ---
    financials = data.get("financials", {})
    if financials:
        proposals.append(
            AIProposal(
                entity_type="financial",
                data={
                    "data_type": "990_financials",
                    "tax_year": data.get("tax_year", ""),
                    "ein": data.get("ein", ""),
                    "total_revenue": financials.get("total_revenue", 0),
                    "total_expenses": financials.get("total_expenses", 0),
                    "net_assets_eoy": financials.get("net_assets_eoy", 0),
                    "program_service_expenses": financials.get("program_service_expenses", 0),
                    "management_expenses": financials.get("management_expenses", 0),
                    "fundraising_expenses": financials.get("fundraising_expenses", 0),
                    "total_compensation": financials.get("total_compensation", 0),
                    "number_voting_members": financials.get("number_voting_members", 0),
                    "number_independent_members": financials.get("number_independent_members", 0),
                    "number_employees": financials.get("number_employees", 0),
                    "number_volunteers": financials.get("number_volunteers", 0),
                    "unrelated_business_revenue": financials.get("unrelated_business_revenue", 0),
                },
                confidence=float(financials.get("confidence", 0.7)),
                source_text="990 financial summary",
            )
        )

    # --- Contractors ---
    for contractor in data.get("contractors", []):
        proposals.append(
            AIProposal(
                entity_type="person",
                data={
                    "name": contractor.get("name", ""),
                    "role": "contractor",
                    "services": contractor.get("services", ""),
                    "compensation": contractor.get("compensation", 0),
                },
                confidence=float(contractor.get("confidence", 0.5)),
                source_text=f"990 Part VII contractors: {contractor.get('name', '')}",
            )
        )

    # --- Schedule presence flags ---
    proposals.append(
        AIProposal(
            entity_type="financial",
            data={
                "data_type": "990_schedule_flags",
                "tax_year": data.get("tax_year", ""),
                "ein": data.get("ein", ""),
                "schedule_l_present": data.get("schedule_l_present", False),
                "schedule_b_present": data.get("schedule_b_present", False),
            },
            confidence=float(data.get("confidence_overall", 0.7)),
            source_text="990 schedule presence check",
        )
    )

    return AIExtractionResult(proposals=proposals)


def _parse_obituary_response(raw_text: str) -> AIExtractionResult:
    """Parse the obituary-specific JSON into AIProposal objects."""
    data = _safe_json_parse(raw_text)
    if data is None:
        return AIExtractionResult(error="Failed to parse AI obituary response as JSON")

    proposals: list[AIProposal] = []

    # --- Deceased person ---
    deceased = data.get("deceased", {})
    if deceased:
        proposals.append(
            AIProposal(
                entity_type="person",
                data={
                    "name": deceased.get("name", ""),
                    "role": "deceased",
                    "birth_date": deceased.get("birth_date"),
                    "death_date": deceased.get("death_date"),
                    "age_at_death": deceased.get("age_at_death"),
                    "residence": deceased.get("residence", ""),
                },
                confidence=float(deceased.get("confidence", 0.8)),
                source_text="Obituary subject",
            )
        )

    # --- Family relationships (the gold mine) ---
    for rel in data.get("family_relationships", []):
        # Create the person
        proposals.append(
            AIProposal(
                entity_type="person",
                data={
                    "name": rel.get("person", ""),
                    "role": "family_member",
                    "status": rel.get("status", "unknown"),
                    "spouse_name": rel.get("spouse_name", ""),
                    "maiden_name": rel.get("maiden_name", ""),
                },
                confidence=float(rel.get("confidence", 0.7)),
                source_text=rel.get("context", ""),
            )
        )

        # Create the relationship to the deceased
        if deceased.get("name"):
            proposals.append(
                AIProposal(
                    entity_type="relationship",
                    data={
                        "entity_1": deceased.get("name", ""),
                        "entity_2": rel.get("person", ""),
                        "relationship_type": rel.get("relationship_to_deceased", "other"),
                    },
                    confidence=float(rel.get("confidence", 0.7)),
                    source_text=rel.get("context", ""),
                )
            )

        # If the person's spouse is mentioned, create that relationship too
        if rel.get("spouse_name"):
            proposals.append(
                AIProposal(
                    entity_type="relationship",
                    data={
                        "entity_1": rel.get("person", ""),
                        "entity_2": rel.get("spouse_name", ""),
                        "relationship_type": "spouse",
                    },
                    confidence=float(rel.get("confidence", 0.7)) * 0.9,
                    source_text=rel.get("context", ""),
                )
            )

    # --- Organizations mentioned ---
    for org in data.get("organizations_mentioned", []):
        proposals.append(
            AIProposal(
                entity_type="org",
                data={
                    "name": org.get("name", ""),
                    "org_type": "other",
                    "context_type": org.get("context", ""),
                },
                confidence=float(org.get("confidence", 0.6)),
                source_text=org.get("context", ""),
            )
        )

    return AIExtractionResult(proposals=proposals)


# ---------------------------------------------------------------------------
# Merge AI results with regex results
# ---------------------------------------------------------------------------


def merge_extractions(
    regex_result: dict[str, list[dict[str, Any]]],
    ai_result: AIExtractionResult,
) -> dict[str, list[dict[str, Any]]]:
    """
    Merge regex-based and AI-based extraction results.

    Strategy:
    - Regex results are kept as-is (they're fast, free, and deterministic)
    - AI results are added with an "ai_proposed" flag so the UI can distinguish
    - Deduplication: if the AI found something the regex already found,
      we enrich the regex result with AI metadata instead of duplicating

    Parameters
    ----------
    regex_result : dict
        Output from entity_extraction.extract_entities()
    ai_result : AIExtractionResult
        Output from ai_extract_entities() or specialized function

    Returns
    -------
    Merged dict in the same format as regex_result, with AI additions tagged.
    """
    if ai_result.error:
        # AI failed — return regex results unchanged but log it
        logger.warning("ai_merge_skipped", extra={"error": ai_result.error})
        return regex_result

    merged = {k: list(v) for k, v in regex_result.items()}  # deep copy lists

    # Build a set of normalized names we already have from regex
    existing_persons = {p.get("raw", "").lower().strip() for p in merged.get("persons", [])}
    existing_orgs = {o.get("raw", "").lower().strip() for o in merged.get("orgs", [])}

    for proposal in ai_result.proposals:
        if proposal.entity_type == "person":
            name = proposal.data.get("name", "").lower().strip()
            if name and name not in existing_persons:
                merged.setdefault("persons", []).append(
                    {
                        "raw": proposal.data.get("name", ""),
                        "context": proposal.source_text,
                        "source": "ai",
                        "ai_confidence": proposal.confidence,
                        "ai_reasoning": proposal.reasoning,
                        "ai_role": proposal.data.get("role", ""),
                        "ai_title": proposal.data.get("title", ""),
                    }
                )
                existing_persons.add(name)

        elif proposal.entity_type == "org":
            name = proposal.data.get("name", "").lower().strip()
            if name and name not in existing_orgs:
                merged.setdefault("orgs", []).append(
                    {
                        "raw": proposal.data.get("name", ""),
                        "context": proposal.source_text,
                        "source": "ai",
                        "ai_confidence": proposal.confidence,
                        "ai_reasoning": proposal.reasoning,
                        "ai_org_type": proposal.data.get("org_type", ""),
                        "ai_ein": proposal.data.get("ein", ""),
                    }
                )
                existing_orgs.add(name)

        elif proposal.entity_type == "relationship":
            # Relationships are always new — no regex equivalent
            merged.setdefault("relationships", []).append(
                {
                    "entity_1": proposal.data.get("entity_1", ""),
                    "entity_2": proposal.data.get("entity_2", ""),
                    "relationship_type": proposal.data.get("relationship_type", ""),
                    "source": "ai",
                    "ai_confidence": proposal.confidence,
                    "ai_reasoning": proposal.reasoning,
                    "context": proposal.source_text,
                }
            )

        elif proposal.entity_type == "address":
            merged.setdefault("addresses", []).append(
                {
                    "raw": proposal.data.get("raw", ""),
                    "street": proposal.data.get("street", ""),
                    "city": proposal.data.get("city", ""),
                    "state": proposal.data.get("state", ""),
                    "zip": proposal.data.get("zip", ""),
                    "associated_entity": proposal.data.get("associated_entity", ""),
                    "source": "ai",
                    "ai_confidence": proposal.confidence,
                }
            )

        elif proposal.entity_type == "financial":
            merged.setdefault("financials", []).append(
                {
                    **proposal.data,
                    "source": "ai",
                    "ai_confidence": proposal.confidence,
                }
            )

    # Tag the merged result with AI metadata
    merged.setdefault("meta", {})
    merged["meta"]["ai_model"] = ai_result.model_used
    merged["meta"]["ai_input_tokens"] = ai_result.input_tokens
    merged["meta"]["ai_output_tokens"] = ai_result.output_tokens
    merged["meta"]["ai_proposals"] = len(ai_result.proposals)

    return merged


# ---------------------------------------------------------------------------
# Pipeline integration — drop-in enhancement for the upload pipeline
# ---------------------------------------------------------------------------


def enhanced_extract(
    text: str,
    doc_type: str = "OTHER",
    use_ai: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """
    Run the full extraction pipeline: regex first, then AI enhancement.

    This is the main entry point for the upload pipeline. It:
    1. Runs the fast regex extractor (always)
    2. If use_ai=True, runs the appropriate AI extractor
    3. Merges the results
    4. Returns the merged dict

    The doc_type determines which AI extractor to use:
    - "IRS_990" → ai_extract_990()
    - "OBITUARY" → ai_extract_obituary()
    - Everything else → ai_extract_entities()
    """
    from .entity_extraction import extract_entities

    # Step 1: Fast regex extraction (always runs)
    regex_result = extract_entities(text, doc_type=doc_type)

    if not use_ai:
        return regex_result

    # Step 2: AI extraction (based on document type)
    if doc_type == "IRS_990":
        ai_result = ai_extract_990(text)
    elif doc_type == "OBITUARY":
        ai_result = ai_extract_obituary(text)
    else:
        ai_result = ai_extract_entities(text, doc_type=doc_type)

    # Step 3: Merge
    return merge_extractions(regex_result, ai_result)


# ---------------------------------------------------------------------------
# Batch processing — for re-processing existing documents
# ---------------------------------------------------------------------------


def reprocess_document(document_id: str) -> AIExtractionResult | None:
    """
    Re-run AI extraction on an existing document in the database.

    Useful when you've improved prompts or switched models and want to
    re-extract from documents already uploaded.

    Returns the AIExtractionResult, or None if the document has no text.
    """
    from .models import Document

    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.warning("reprocess_doc_not_found", extra={"doc_id": document_id})
        return None

    text = doc.extracted_text
    if not text:
        logger.warning("reprocess_doc_no_text", extra={"doc_id": document_id})
        return None

    doc_type = doc.document_type if hasattr(doc, "document_type") else "OTHER"

    if doc_type == "IRS_990":
        return ai_extract_990(text)
    elif doc_type == "OBITUARY":
        return ai_extract_obituary(text)
    else:
        return ai_extract_entities(text, doc_type=doc_type)
