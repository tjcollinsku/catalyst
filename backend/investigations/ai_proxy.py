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
import time
from typing import Any

logger = logging.getLogger("catalyst.ai_proxy")

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
        raise ImportError("The 'anthropic' package is required. pip install anthropic")
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
    from .models import (
        Person, Organization, Property, FinancialInstrument,
        Signal, Detection, Finding, Document,
    )

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
            parts.append(f"  - {o.name} (type={o.org_type}, EIN={o.ein or 'N/A'})")
        parts.append("")

    props = Property.objects.filter(case=case)
    if props.exists():
        parts.append("PROPERTIES:")
        for pr in props[:15]:
            parts.append(f"  - {pr.address or pr.parcel_number} (assessed={pr.assessed_value})")
        parts.append("")

    instruments = FinancialInstrument.objects.filter(case=case)
    if instruments.exists():
        parts.append("FINANCIAL INSTRUMENTS:")
        for fi in instruments[:10]:
            parts.append(f"  - {fi.instrument_type} #{fi.filing_number} (amount={fi.amount})")
        parts.append("")

    # Signals
    signals = Signal.objects.filter(case=case).order_by("-severity", "-detected_at")
    if signals.exists():
        parts.append("SIGNALS (top 15):")
        for s in signals[:15]:
            parts.append(f"  - [{s.severity}] {s.rule_id}: {(s.detected_summary or '')[:120]}")
        parts.append("")

    # Detections
    detections = Detection.objects.filter(case=case).order_by("-severity")
    if detections.exists():
        parts.append("DETECTIONS:")
        for d in detections[:10]:
            parts.append(f"  - [{d.severity}] {d.signal_type} (confidence={d.confidence_score:.0%})")
        parts.append("")

    # Findings
    findings = Finding.objects.filter(case=case)
    if findings.exists():
        parts.append("FINDINGS:")
        for f in findings[:10]:
            parts.append(f"  - [{f.severity}] {f.title}: {f.narrative[:150]}...")
        parts.append("")

    # Documents
    docs = Document.objects.filter(case=case).order_by("-uploaded_at")
    if docs.exists():
        parts.append(f"DOCUMENTS ({docs.count()} total, showing recent 20):")
        for doc in docs[:20]:
            parts.append(f"  - {doc.display_name or doc.filename} (type={doc.doc_type})")
        parts.append("")

    text = "\n".join(parts)
    return text[:max_chars]


def _build_entity_context(entity_type: str, entity_id: str, case) -> str:
    """Build focused context about a specific entity."""
    from .models import (
        Person, Organization, Property, FinancialInstrument,
        PersonOrganization, PersonDocument, OrgDocument,
        Signal, EntitySignal, Detection,
    )

    parts = []

    if entity_type == "person":
        p = Person.objects.filter(pk=entity_id, case=case).first()
        if p:
            parts.append(f"PERSON: {p.full_name}")
            parts.append(f"Roles: {', '.join(p.role_tags) if p.role_tags else 'none'}")
            if p.aliases:
                parts.append(f"Aliases: {', '.join(p.aliases)}")
            if p.date_of_death:
                parts.append(f"Deceased: {p.date_of_death}")

            # Org roles
            for po in PersonOrganization.objects.filter(person=p).select_related("org"):
                parts.append(f"  Role: {po.role} at {po.org.name}")

            # Documents
            for pd in PersonDocument.objects.filter(person=p).select_related("document")[:10]:
                parts.append(f"  Document: {pd.document.display_name or pd.document.filename}")

            # Signals referencing this entity
            sig_ids = EntitySignal.objects.filter(
                entity_id=entity_id, entity_type="person"
            ).values_list("signal_id", flat=True)
            for sig in Signal.objects.filter(pk__in=sig_ids):
                parts.append(f"  Signal: [{sig.severity}] {sig.rule_id} — {(sig.detected_summary or '')[:100]}")

            # Detections
            for det in Detection.objects.filter(person_id=entity_id):
                parts.append(f"  Detection: [{det.severity}] {det.signal_type} (conf={det.confidence_score:.0%})")

    elif entity_type == "organization":
        o = Organization.objects.filter(pk=entity_id, case=case).first()
        if o:
            parts.append(f"ORGANIZATION: {o.name}")
            parts.append(f"Type: {o.org_type}, EIN: {o.ein or 'N/A'}, Status: {o.status}")

            for po in PersonOrganization.objects.filter(org=o).select_related("person"):
                parts.append(f"  Officer: {po.person.full_name} — {po.role}")

            for od in OrgDocument.objects.filter(org=o).select_related("document")[:10]:
                parts.append(f"  Document: {od.document.display_name or od.document.filename}")

    elif entity_type == "property":
        pr = Property.objects.filter(pk=entity_id, case=case).first()
        if pr:
            parts.append(f"PROPERTY: {pr.address or pr.parcel_number}")
            parts.append(f"County: {pr.county}, Assessed: {pr.assessed_value}, Purchase: {pr.purchase_price}")

    elif entity_type == "financial_instrument":
        fi = FinancialInstrument.objects.filter(pk=entity_id, case=case).first()
        if fi:
            parts.append(f"FINANCIAL INSTRUMENT: {fi.instrument_type} #{fi.filing_number}")
            parts.append(f"Amount: {fi.amount}, Filed: {fi.filing_date}")

    return "\n".join(parts)


def _build_signal_context(signal) -> str:
    """Build focused context about a specific signal."""
    parts = [
        f"SIGNAL: {signal.rule_id}",
        f"Severity: {signal.severity}",
        f"Status: {signal.status}",
        f"Summary: {signal.detected_summary or 'No summary'}",
        f"Detected: {signal.detected_at}",
    ]
    if signal.trigger_doc:
        parts.append(f"Trigger document: {signal.trigger_doc.display_name or signal.trigger_doc.filename}")
        if signal.trigger_doc.extracted_text:
            parts.append(f"Document excerpt: {signal.trigger_doc.extracted_text[:2000]}")
    if signal.investigator_note:
        parts.append(f"Investigator note: {signal.investigator_note}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Core AI call wrapper
# ---------------------------------------------------------------------------

def _call_ai(system_prompt: str, user_message: str, model: str = MODEL_SONNET,
             temperature: float = 0.2, max_tokens: int = MAX_TOKENS) -> dict:
    """Make a Claude API call and return parsed JSON response."""
    client = _get_client()
    try:
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
            lines = [l for l in lines if not l.strip().startswith("```")]
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
- Respond ONLY with valid JSON: {"summary": "...", "key_facts": ["...", "..."], "risk_level": "high|medium|low"}
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

    if target_type == "signal":
        from .models import Signal
        signal = Signal.objects.filter(pk=target_id, case=case).select_related("trigger_doc").first()
        if not signal:
            return {"error": "Signal not found."}
        context = _build_signal_context(signal)
    else:
        context = _build_entity_context(target_type, target_id, case)

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
Analyze the case data and suggest potential connections between entities that the investigator may not have noticed.

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
        user_msg += "\n\nFocus your analysis on connections involving the FOCUS ENTITY above."
    else:
        user_msg += "\n\nAnalyze all entities and suggest connections the investigator may have missed."

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


def ai_narrative(case, detection_ids: list[str], tone: str = "formal") -> dict:
    """Draft a finding narrative from detection evidence. Uses Sonnet."""
    sorted_ids = sorted(detection_ids)
    ck = _cache_key("narrative", str(case.pk), ",".join(sorted_ids), tone)
    cached = _cache_get(ck)
    if cached:
        cached["_cached"] = True
        return cached

    if not _check_rate_limit(str(case.pk)):
        return {"error": "Rate limit exceeded. Try again in a minute."}

    from .models import Detection

    detections = Detection.objects.filter(pk__in=detection_ids, case=case)
    if not detections.exists():
        return {"error": "No detections found."}

    # Build detection context
    parts = [f"Case: {case.name}\n"]
    for det in detections:
        parts.append(f"DETECTION: {det.signal_type} [{det.severity}]")
        parts.append(f"  Confidence: {det.confidence_score:.0%}")
        parts.append(f"  Evidence: {json.dumps(det.evidence_snapshot, default=str)[:600]}")
        if det.investigator_note:
            parts.append(f"  Investigator note: {det.investigator_note}")
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

ASK_SYSTEM = """You are an AI investigative analyst for the Catalyst forensic investigation platform.
You have deep knowledge of nonprofit fraud, charity governance, property transaction analysis,
IRS Form 990 analysis, and Ohio Revised Code.

The investigator will ask you questions about the case data provided below.

Rules:
- Base your answers ONLY on the case data provided. Do not hallucinate facts.
- If you're unsure, say so. Never fabricate evidence.
- When referencing documents or entities, cite them by name.
- Be concise but thorough.
- If the question involves a legal interpretation, note that you're not a lawyer.

Respond ONLY with valid JSON:
{
  "answer": "your answer text",
  "sources": [{"type": "document|entity|signal|detection", "name": "...", "relevance": "why this source supports the answer"}],
  "follow_up_questions": ["suggested follow-up questions the investigator might want to ask"]
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
        for msg in conversation_history[-6:]:  # Keep last 6 messages for context
            messages.append({"role": msg["role"], "content": msg["content"]})

    # Current question with case context
    user_content = f"CASE DATA:\n{case_ctx}\n\nQUESTION: {question}"
    messages.append({"role": "user", "content": user_content})

    # Use the client directly for multi-turn
    client = _get_client()
    try:
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
            lines = [l for l in lines if not l.strip().startswith("```")]
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
