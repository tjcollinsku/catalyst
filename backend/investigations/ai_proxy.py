"""
AI proxy layer for Catalyst — case-aware AI assistance endpoints.

Provides four capabilities:
    1. Summarize — summarize evidence for a signal or entity (Haiku, fast/cheap)
    2. Connections — suggest entity connections (Sonnet, deeper analysis)
    3. Narrative — draft finding narratives from detection evidence (Sonnet)
    4. Ask — free-form case question (Sonnet, conversational)

Architecture:
    - Each function gathers relevant case data (entities, signals, docs, financials)
    - Builds a structured prompt with the evidence context
    - Calls Claude API via the same SDK pattern as ai_extraction.py
    - Returns structured JSON response
    - Simple in-memory cache (10 min TTL) to avoid redundant calls
    - Rate limiting: 10 calls per minute per case

Cost controls:
    - Summarize uses Haiku (fast, ~10x cheaper)
    - Others use Sonnet (deeper reasoning)
    - Input context capped at ~8K tokens per call
    - Temperature 0.2 for summarize, 0.3 for creative tasks (narrative, ask)
    - All responses are JSON-only (no markdown waste)
"""

import hashlib
import json
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger("catalyst.ai_proxy")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# UUID v4 regex: 8-4-4-4-12 hex digits
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _strip_id_prefix(prefixed_id: str) -> str:
    """Extract raw UUID from a frontend-prefixed ID like 'signal-dfdb45aa-...'

    The frontend prepends type prefixes (signal-, detection-, finding-,
    entity-, etc.) to UUIDs for React list keys.  The backend needs
    the raw UUID for database queries.
    """
    if not prefixed_id:
        return prefixed_id
    # If it's already a bare UUID, return as-is
    if _UUID_RE.match(prefixed_id):
        return prefixed_id
    # Otherwise strip everything before the first UUID
    m = _UUID_RE.search(prefixed_id)
    if m:
        return m.group(0)
    return prefixed_id


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096
MAX_CONTEXT_CHARS = 24000  # ~6K tokens — leaves room for prompt + response

# ---------------------------------------------------------------------------
# Shared client (lazy init, same pattern as ai_extraction.py)
# ---------------------------------------------------------------------------

_API_KEY: str | None = None


def _get_api_key() -> str:
    global _API_KEY
    if _API_KEY is None:
        _API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    if not _API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set.")
    return _API_KEY


def _get_client():
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError(
            "The 'anthropic' package is required. pip install anthropic")
    return Anthropic(api_key=_get_api_key())


# ---------------------------------------------------------------------------
# Simple in-memory cache (TTL = 10 minutes)
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 600  # 10 minutes


def _cache_key(prefix: str, *args: str) -> str:
    raw = f"{prefix}:{'|'.join(args)}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> Any | None:
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
        del _cache[key]
    return None


def _cache_set(key: str, val: Any) -> None:
    # Evict stale entries if cache grows large
    if len(_cache) > 200:
        now = time.time()
        stale = [k for k, (ts, _) in _cache.items() if now - ts > CACHE_TTL]
        for k in stale:
            del _cache[k]
    _cache[key] = (time.time(), val)


# ---------------------------------------------------------------------------
# Rate limiting (10 calls/min per case, in-memory)
# ---------------------------------------------------------------------------

_rate_buckets: dict[str, list[float]] = {}
RATE_LIMIT = 10
RATE_WINDOW = 60  # seconds


def _check_rate_limit(case_id: str) -> bool:
    """Return True if the call is allowed, False if rate-limited."""
    now = time.time()
    bucket = _rate_buckets.setdefault(case_id, [])
    # Purge old timestamps
    bucket[:] = [t for t in bucket if now - t < RATE_WINDOW]
    if len(bucket) >= RATE_LIMIT:
        return False
    bucket.append(now)
    return True


# ---------------------------------------------------------------------------
# Context builders — gather case data into prompt-friendly text
# ---------------------------------------------------------------------------


def _build_case_context(case, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Build a text summary of the case for use as AI context."""
    from .models import Document, FinancialInstrument, Finding, Organization, Person, Property

    parts = []
    parts.append(f"CASE: {case.name} (ID: {case.pk})")
    parts.append(f"Status: {case.status}")
    if case.notes:
        parts.append(f"Notes: {case.notes[:500]}")
    parts.append("")

    # Entities
    persons = Person.objects.filter(case=case)
    if persons.exists():
        parts.append("PERSONS:")
        for p in persons[:20]:
            roles = ", ".join(p.role_tags) if p.role_tags else "no roles"
            parts.append(f"  - {p.full_name} ({roles})")
        parts.append("")

    orgs = Organization.objects.filter(case=case)
    if orgs.exists():
        parts.append("ORGANIZATIONS:")
        for o in orgs[:10]:
            parts.append(
                f"  - {o.name} (type={o.org_type}, EIN={o.ein or 'N/A'})")
        parts.append("")

    props = Property.objects.filter(case=case)
    if props.exists():
        parts.append("PROPERTIES:")
        for pr in props[:15]:
            parts.append(
                f"  - {pr.address or pr.parcel_number} (assessed={pr.assessed_value})")
        parts.append("")

    instruments = FinancialInstrument.objects.filter(case=case)
    if instruments.exists():
        parts.append("FINANCIAL INSTRUMENTS:")
        for fi in instruments[:10]:
            parts.append(
                f"  - {fi.instrument_type} #{fi.filing_number} (amount={fi.amount})")
        parts.append("")

    # Findings
    findings = Finding.objects.filter(case=case)
    if findings.exists():
        parts.append("FINDINGS:")
        for f in findings[:10]:
            details = (f.narrative or f.description or "")[:150]
            parts.append(f"  - [{f.severity}] {f.title}: {details}")
        parts.append("")

    # Documents
    docs = Document.objects.filter(case=case).order_by("-uploaded_at")
    if docs.exists():
        parts.append(f"DOCUMENTS ({docs.count()} total, showing recent 20):")
        for doc in docs[:20]:
            parts.append(
                f"  - {doc.display_name or doc.filename} (type={doc.doc_type})")
        parts.append("")

    text = "\n".join(parts)
    return text[:max_chars]


def _build_entity_context(entity_type: str, entity_id: str, case) -> str:
    """Build focused context about a specific entity."""
    from .models import (
        FinancialInstrument,
        Finding,
        FindingEntity,
        Organization,
        OrgDocument,
        Person,
        PersonDocument,
        PersonOrganization,
        Property,
    )

    parts = []

    if entity_type == "person":
        p = Person.objects.filter(pk=entity_id, case=case).first()
        if p:
            parts.append(f"PERSON: {p.full_name}")
            parts.append(
                f"Roles: {', '.join(p.role_tags) if p.role_tags else 'none'}")
            if p.aliases:
                parts.append(f"Aliases: {', '.join(p.aliases)}")
            if p.date_of_death:
                parts.append(f"Deceased: {p.date_of_death}")

            # Org roles
            for po in PersonOrganization.objects.filter(person=p).select_related("org"):
                parts.append(f"  Role: {po.role} at {po.org.name}")

            # Documents
            for pd in PersonDocument.objects.filter(person=p).select_related("document")[:10]:
                parts.append(
                    f"  Document: {pd.document.display_name or pd.document.filename}")

            # Findings referencing this entity
            finding_ids = FindingEntity.objects.filter(
                entity_id=entity_id,
                entity_type="person",
            ).values_list("finding_id", flat=True)
            for finding in Finding.objects.filter(pk__in=finding_ids).order_by("-created_at")[:10]:
                summary = (finding.narrative or finding.description or "")[
                    :100]
                parts.append(
                    f"  Finding: [{finding.severity}] {finding.title} — {summary}")

    elif entity_type == "organization":
        o = Organization.objects.filter(pk=entity_id, case=case).first()
        if o:
            parts.append(f"ORGANIZATION: {o.name}")
            parts.append(
                f"Type: {o.org_type}, EIN: {o.ein or 'N/A'}, Status: {o.status}")

            for po in PersonOrganization.objects.filter(org=o).select_related("person"):
                parts.append(f"  Officer: {po.person.full_name} — {po.role}")

            for od in OrgDocument.objects.filter(org=o).select_related("document")[:10]:
                parts.append(
                    f"  Document: {od.document.display_name or od.document.filename}")

    elif entity_type == "property":
        pr = Property.objects.filter(pk=entity_id, case=case).first()
        if pr:
            parts.append(f"PROPERTY: {pr.address or pr.parcel_number}")
            county_info = (
                f"County: {pr.county}, Assessed: {pr.assessed_value}, Purchase: {pr.purchase_price}"
            )
            parts.append(county_info)

    elif entity_type == "financial_instrument":
        fi = FinancialInstrument.objects.filter(
            pk=entity_id, case=case).first()
        if fi:
            header = f"FINANCIAL INSTRUMENT: {fi.instrument_type} #{fi.filing_number}"
            parts.append(header)
            parts.append(f"Amount: {fi.amount}, Filed: {fi.filing_date}")

    return "\n".join(parts)


def _build_finding_context(finding) -> str:
    """Build focused context about a specific finding."""
    parts = [
        f"FINDING: {finding.rule_id or 'MANUAL'}",
        f"Severity: {finding.severity}",
        f"Status: {finding.status}",
        f"Title: {finding.title}",
        f"Evidence Weight: {finding.evidence_weight}",
        f"Source: {finding.source}",
    ]
    if finding.description:
        parts.append(f"Description: {finding.description}")
    if finding.narrative:
        parts.append(f"Narrative: {finding.narrative}")
    if finding.trigger_doc:
        doc_name = finding.trigger_doc.display_name or finding.trigger_doc.filename
        parts.append(f"Trigger document: {doc_name}")
        if finding.trigger_doc.extracted_text:
            parts.append(
                f"Document excerpt: {finding.trigger_doc.extracted_text[:2000]}")
    if finding.investigator_note:
        parts.append(f"Investigator note: {finding.investigator_note}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Core AI call wrapper
# ---------------------------------------------------------------------------


def _call_ai(
    system_prompt: str,
    user_message: str,
    model: str = MODEL_SONNET,
    temperature: float = 0.2,
    max_tokens: int = MAX_TOKENS,
) -> dict:
    """Make a Claude API call and return parsed JSON response."""
    try:
        client = _get_client()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text

        # Try to parse JSON (may be wrapped in code fences)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Strip markdown fences
            lines = cleaned.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        result = json.loads(cleaned)
        result["_model"] = model
        result["_usage"] = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return result

    except json.JSONDecodeError:
        logger.warning("AI returned non-JSON response: %s", raw[:200])
        return {"error": "AI returned non-JSON response", "raw": raw[:500]}
    except Exception as e:
        logger.error("AI call failed: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# 1. SUMMARIZE — fast summary of a signal or entity (Haiku)
# ---------------------------------------------------------------------------

SUMMARIZE_SYSTEM = """You are an AI assistant for a forensic investigation platform.
Summarize the provided evidence concisely for an investigator.

Rules:
- Be factual and specific. Cite names, dates, amounts.
- Keep summary to 2-3 sentences.
- If the evidence suggests fraud patterns, note them briefly.
- Respond ONLY with valid JSON: {"summary": "...", "key_facts": [...],
  "risk_level": "high|medium|low"}
"""


def ai_summarize(case, target_type: str, target_id: str) -> dict:
    """Summarize evidence for a signal or entity. Uses Haiku for speed."""
    ck = _cache_key("summarize", str(case.pk), target_type, target_id)
    cached = _cache_get(ck)
    if cached:
        cached["_cached"] = True
        return cached

    if not _check_rate_limit(str(case.pk)):
        return {"error": "Rate limit exceeded. Try again in a minute."}

    # Strip frontend type prefixes (e.g. "signal-uuid" → "uuid")
    clean_id = _strip_id_prefix(target_id)

    if target_type in {"signal", "finding"}:
        from .models import Finding

        finding = (
            Finding.objects.filter(pk=clean_id, case=case).select_related(
                "trigger_doc").first()
        )
        if not finding:
            return {"error": "Finding not found."}
        context = _build_finding_context(finding)
    else:
        context = _build_entity_context(target_type, clean_id, case)

    if not context.strip():
        return {"error": "No data found for this target."}

    case_brief = f"Case: {case.name}\n\n"
    result = _call_ai(
        SUMMARIZE_SYSTEM,
        case_brief + context,
        model=MODEL_HAIKU,
        temperature=0.2,
    )

    if "error" not in result:
        _cache_set(ck, result)
    return result


# ---------------------------------------------------------------------------
# 2. CONNECTIONS — suggest entity connections (Sonnet)
# ---------------------------------------------------------------------------

CONNECTIONS_SYSTEM = """You are an AI assistant for a forensic fraud investigation platform.
Analyze the case data and suggest potential connections between entities that may not be obvious.

Focus on:
- Shared addresses between persons and organizations
- Officers who appear across multiple organizations
- Properties transacted between related parties
- Financial instruments linking otherwise separate entities
- Social connections that suggest patronage networks
- Temporal patterns (events happening in suspicious sequence)

Respond ONLY with valid JSON:
{
  "suggestions": [
    {
      "from_entity": "name",
      "to_entity": "name",
      "relationship": "description of the connection",
      "reasoning": "why this connection matters for the investigation",
      "confidence": 0.0-1.0
    }
  ],
  "patterns_detected": ["brief description of any fraud patterns noticed"]
}
"""


def ai_connections(case, entity_id: str | None = None) -> dict:
    """Suggest entity connections. Uses Sonnet for deeper analysis."""
    # Strip frontend type prefix from entity_id
    if entity_id:
        entity_id = _strip_id_prefix(entity_id)
    ck = _cache_key("connections", str(case.pk), entity_id or "all")
    cached = _cache_get(ck)
    if cached:
        cached["_cached"] = True
        return cached

    if not _check_rate_limit(str(case.pk)):
        return {"error": "Rate limit exceeded. Try again in a minute."}

    context = _build_case_context(case)
    if entity_id:
        # Add focused entity context
        # Try each type until we find it
        for etype in ["person", "organization", "property", "financial_instrument"]:
            entity_ctx = _build_entity_context(etype, entity_id, case)
            if entity_ctx:
                context += f"\n\nFOCUS ENTITY:\n{entity_ctx}"
                break

    user_msg = context
    if entity_id:
        user_msg += "\n\nFocus analysis on connections involving the FOCUS ENTITY above."
    else:
        focus_msg = "\n\nAnalyze all entities and suggest potential connections not yet explored."
        user_msg += focus_msg

    result = _call_ai(
        CONNECTIONS_SYSTEM,
        user_msg,
        model=MODEL_SONNET,
        temperature=0.2,
    )

    if "error" not in result:
        _cache_set(ck, result)
    return result


# ---------------------------------------------------------------------------
# 3. NARRATIVE — draft finding narrative (Sonnet)
# ---------------------------------------------------------------------------

NARRATIVE_SYSTEM = """You are an AI assistant for a forensic investigation platform.
Draft a professional finding narrative for a government referral memo.

The narrative should:
- Be written in formal investigative language suitable for submission to regulators
- Present facts chronologically
- Cite specific documents, dates, amounts, and persons
- Identify the applicable legal violations (Ohio Revised Code, IRC sections)
- Distinguish between confirmed facts and inferences
- Be 2-4 paragraphs long

Respond ONLY with valid JSON:
{
  "narrative": "the full narrative text",
  "key_points": ["bulleted key facts"],
  "legal_refs": ["ORC §1702.30", "IRC §4941"],
  "severity_assessment": "critical|high|medium|low",
  "confidence": 0.0-1.0
}
"""


def ai_narrative(case, finding_ids: list[str], tone: str = "formal") -> dict:
    """Draft a finding narrative from finding evidence. Uses Sonnet."""
    # Strip frontend type prefixes from finding IDs
    finding_ids = [_strip_id_prefix(fid) for fid in finding_ids]
    sorted_ids = sorted(finding_ids)
    ck = _cache_key("narrative", str(case.pk), ",".join(sorted_ids), tone)
    cached = _cache_get(ck)
    if cached:
        cached["_cached"] = True
        return cached

    if not _check_rate_limit(str(case.pk)):
        return {"error": "Rate limit exceeded. Try again in a minute."}

    from .models import Finding

    findings = Finding.objects.filter(pk__in=finding_ids, case=case)
    if not findings.exists():
        return {"error": "No findings found."}

    # Build finding context
    parts = [f"Case: {case.name}\n"]
    for finding in findings:
        parts.append(f"FINDING: {finding.title} [{finding.severity}]")
        parts.append(f"  Status: {finding.status}")
        parts.append(f"  Evidence Weight: {finding.evidence_weight}")
        parts.append(
            f"  Evidence: {json.dumps(finding.evidence_snapshot or {}, default=str)[:600]}"
        )
        if finding.narrative:
            parts.append(f"  Narrative: {finding.narrative[:600]}")
        if finding.investigator_note:
            parts.append(f"  Investigator note: {finding.investigator_note}")
        parts.append("")

    # Add broader case context for cross-referencing
    case_ctx = _build_case_context(case, max_chars=8000)
    parts.append("CASE CONTEXT:\n" + case_ctx)

    user_msg = "\n".join(parts)
    if tone == "technical":
        user_msg += "\n\nUse technical, data-driven language."
    else:
        user_msg += "\n\nUse formal investigative language suitable for a government referral."

    result = _call_ai(
        NARRATIVE_SYSTEM,
        user_msg,
        model=MODEL_SONNET,
        temperature=0.3,
    )

    if "error" not in result:
        _cache_set(ck, result)
    return result


# ---------------------------------------------------------------------------
# 4. ASK — free-form case question (Sonnet, conversational)
# ---------------------------------------------------------------------------

ASK_SYSTEM = """You are Catalyst's investigative research assistant — a paralegal working under the
Catalyst Investigation Methodology (CAT-SOP-001).

THE CATALYST PRINCIPLE:
The human investigator is always the decision-maker. You organize, structure, and present.
You never accuse, conclude, or act autonomously. The most dangerous output is one that
removes human judgment from the chain.

YOUR ROLE:
You help a citizen investigator analyze public records for anomalous patterns in nonprofit
organizations, property transactions, financial instruments, and corporate filings. You surface
patterns. The investigator evaluates them. You do not draw legal conclusions.

GOVERNING RULES:
1. Every signal requires investigator confirmation. You produce signals, never findings.
2. Consider both inculpatory AND exculpatory explanations. Always note a plausible innocent
   alternative if one exists.
3. Every factual claim must trace to a specific source in the case data provided. If you
   cannot cite a source, you cannot make the claim.
4. Minimum scope: answer only what the evidence supports. Do not speculate beyond the data.

INVESTIGATION PHASE AWARENESS:
Tailor your analysis to the current case phase:
- PREDICATION/PLANNING: What anomalies are visible? What sources should be searched?
- COLLECTION: What records are missing? What sources haven't been searched?
- ANALYSIS: Surface cross-document patterns. Which entities appear on multiple sides?
- FINDINGS: Can each observation stand alone with citations? What legal references apply?
- REFERRED: Are all findings cited? Are source documents accounted for?

INDICATOR KNOWLEDGE — apply these thresholds when analyzing case data:

Identity & Authorization:
- Deceased Signer: Document filed after person's recorded date of death = CRITICAL (binary)
- Pre-Formation Entity: Entity named in document before SOS formation date = CRITICAL (binary)

Temporal Anomaly:
- Amendment Cluster: 3+ UCC amendments to same filing within 24 hours = HIGH;
  5+ within 1 hour = CRITICAL
- Pre-Acquisition Survey: Survey 90+ days before purchase of same parcel = MEDIUM;
  180+ days = HIGH

Valuation Anomaly:
- Purchase-Assessment Divergence: >50% deviation from assessed value = HIGH;
  >200% = CRITICAL. Overpayment may indicate value inflation; underpayment may indicate
  asset stripping.
- Zero-Consideration Related Transfer: $0-$10 deed consideration between parties sharing
  any officer, attorney, or family relationship = HIGH. Multiple such transfers = CRITICAL.

Governance & Disclosure:
- Missing Schedule L: 990 Part IV Line 28a/28b/28c answered Yes but no Schedule L = HIGH;
  2+ consecutive years = CRITICAL
- Missing 990: Tax-exempt org with no filing for 1 year = MEDIUM; 2+ years = HIGH

Concentration & Control:
- Sole-Source Contractor: One contractor on 100% of permits across 2+ years = MEDIUM;
  3+ years AND >$500K total = HIGH; combined with related-party relationship = CRITICAL
- Permit-Ownership Mismatch: Permit applicant differs from parcel owner = HIGH; especially
  significant when applicant is nonprofit and owner is officer-controlled LLC

Financial Ratio Flags (from 990 data):
- Program expense ratio < 50% of total expenses (normal ≥65%) = flag
- Admin expense ratio > 35% (normal ≤25%) = flag
- Revenue swing > 100% year-over-year = flag
- $0 officer compensation at organization with >$500K revenue = flag
- Single revenue source > 80% of total revenue = flag
- Asset cost basis on 990 exceeds documented purchase prices = flag (off-book acquisitions)

Cross-Document Patterns (highest investigative value — only visible across multiple documents):
- Circular Entity Network: Charitable funds cycling through contracts back to officer-
  controlled assets. 3+ entities with shared officers in asset-movement cycle = HIGH.
- Dormant Entity in Active Network: $0 revenue/assets/expenses for 2+ years but appearing
  in transactions with active case entities = MEDIUM; dormant statutory entity = CRITICAL.
- Attorney Dual Representation: Same attorney on both sides of transaction without conflict
  waiver = MEDIUM; 3+ such transactions = HIGH.
- Charity Conduit: Nonprofit pays contractor who works on officer's private LLC property,
  990 discloses neither = HIGH. Charitable funds improving private real estate.

RESPONSE FORMAT — structure every response as:

1. WHAT THE DATA SHOWS
   State only what is directly observable in the case data. Cite specifically: document name,
   990 part and line number, filing date, entity name.

2. PATTERN ASSESSMENT
   Apply indicator knowledge. Use: "This pattern is consistent with [indicator]."
   Never say "this proves" or "this is fraud."

3. EXCULPATORY NOTE
   State a plausible innocent explanation if one exists. This is not optional.

4. THREAD TO PULL
   End with one specific investigative action. Name the record, the source, the comparison.

LANGUAGE RULES:
- USE: "consistent with," "pattern suggests," "warrants investigation," "the data shows"
- NEVER USE: "committed fraud," "is guilty," "this proves," "clearly violated"
- Always cite document name and specific field when referencing evidence
- When data is insufficient to assess a pattern, say so explicitly

Respond with valid JSON:
{
  "what_data_shows": "factual observations with citations",
  "pattern_assessment": "indicator matches with severity levels",
  "exculpatory_note": "plausible innocent explanation or null",
  "thread_to_pull": "one specific next investigative action",
  "sources_cited": [{"name": "...", "field": "990 Part IX Line 11 / doc page / filing date"}]
}
"""


def ai_ask(case, question: str, conversation_history: list[dict] | None = None) -> dict:
    """Answer a free-form question about the case. Uses Sonnet."""
    # Don't cache conversational queries — each is unique
    if not _check_rate_limit(str(case.pk)):
        return {"error": "Rate limit exceeded. Try again in a minute."}

    case_ctx = _build_case_context(case)

    # Build messages list for multi-turn conversation
    messages = []

    if conversation_history:
        # Keep last 6 messages for context
        for msg in conversation_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    # Current question with case context
    user_content = f"CASE DATA:\n{case_ctx}\n\nQUESTION: {question}"
    messages.append({"role": "user", "content": user_content})

    try:
        # Use the client directly for multi-turn
        client = _get_client()
        response = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=MAX_TOKENS,
            temperature=0.3,
            system=ASK_SYSTEM,
            messages=messages,
        )
        raw = response.content[0].text

        # Parse JSON
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        result = json.loads(cleaned)
        result["_model"] = MODEL_SONNET
        result["_usage"] = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return result

    except json.JSONDecodeError:
        return {"answer": raw, "sources": [], "follow_up_questions": []}
    except Exception as e:
        logger.error("AI ask failed: %s", e)
        return {"error": str(e)}
