# `search_case_documents` Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first agentic tool (`search_case_documents`) to Catalyst's `ai/ask/` endpoint so Claude can query OCR'd document text inside a case instead of relying only on the dumped case summary.

**Architecture:** One new pure-DB helper function (`_tool_search_case_documents`), one new tool-definition dict (`SEARCH_DOCS_TOOL`), one new dispatch dict (`TOOLS`), and a refactor of `ai_ask()` from a single API call into an agentic tool-use loop capped at 5 iterations. System prompt is edited to nudge tool use and drop the JSON-output instruction. Response shape changes from structured-JSON to `{answer: str, tool_calls_made: [...]}`.

**Tech Stack:** Python 3.11, Django 4.2 ORM, Anthropic Python SDK (already a dependency, already used in this file).

**Spec:** [docs/superpowers/specs/2026-04-19-search-case-documents-tool-design.md](../specs/2026-04-19-search-case-documents-tool-design.md)

---

## Orientation (read once before Task 1)

All work in this plan happens in a single file: [backend/investigations/ai_proxy.py](../../../backend/investigations/ai_proxy.py).

The current `ai_ask()` lives at lines 708-759. It already uses `client.messages.create(...)` directly (not the `_call_ai` wrapper) because of multi-turn conversation history, so we have the shape we need — we just need to wrap it in a loop.

The `Document` model has `case` (FK), `extracted_text` (TextField, nullable), `display_name`, `filename`, `doc_type`, `sha256_hash`. Confirmed at [backend/investigations/models.py:157](../../../backend/investigations/models.py#L157).

**Testing note:** No pytest coverage this session — per spec decision, verification is manual against the Bright Future Foundation demo case. Each task ends with a commit.

**Commit discipline:** Tyler commits from his local machine per CLAUDE.md (sandbox git has hook issues). Plan will write commits as instructions for Tyler to run locally, not as `git commit` calls from the sandbox.

---

## Task 1: Add the tool function

**Files:**
- Modify: `backend/investigations/ai_proxy.py` — add `_tool_search_case_documents` after the existing helper functions (~line 225, before `_build_finding_context`)

- [ ] **Step 1: Add the tool function**

Insert the following into `ai_proxy.py`. Place it in a new section just above the `Core AI call wrapper` comment block (currently around line 330), after the existing context builders. Add a section header comment so it's easy to find.

```python
# ---------------------------------------------------------------------------
# Agentic tools — pure DB callables invoked by Claude inside ai_ask()
# ---------------------------------------------------------------------------


def _tool_search_case_documents(case, query: str, limit: int = 10) -> dict:
    """Search OCR'd document text within a single case.

    Case-insensitive substring match against Document.extracted_text. Returns
    up to `limit` matching documents, each with a ~200-char snippet around
    the first occurrence. Documents with empty or missing extracted_text are
    excluded.

    This function is called by Claude via the agentic tool-use loop in
    ai_ask(). Real exceptions bubble up to the loop, which converts them to
    is_error tool_result blocks.
    """
    from .models import Document

    if not query or not query.strip():
        return {"query": query, "match_count": 0, "results": []}

    qs = (
        Document.objects.filter(case=case, extracted_text__icontains=query)
        .exclude(extracted_text__isnull=True)
        .exclude(extracted_text__exact="")[:limit]
    )

    results = []
    q_lower = query.lower()
    for doc in qs:
        text = doc.extracted_text or ""
        idx = text.lower().find(q_lower)
        if idx < 0:
            # Shouldn't happen given the icontains filter, but be defensive
            continue
        start = max(0, idx - 200)
        end = min(len(text), idx + len(query) + 200)
        snippet = text[start:end]
        results.append(
            {
                "document_id": str(doc.pk),
                "display_name": doc.display_name or doc.filename,
                "doc_type": doc.doc_type,
                "sha256": doc.sha256_hash,
                "snippet": snippet,
                "match_position": idx,
            }
        )

    return {"query": query, "match_count": len(results), "results": results}
```

- [ ] **Step 2: Sanity-check the function compiles**

Run: `python -c "from backend.investigations import ai_proxy; print(ai_proxy._tool_search_case_documents)"`

Expected: prints `<function _tool_search_case_documents at 0x...>` with no errors.

If Django complains about settings, run instead from inside a Django shell:
```
cd backend && python manage.py shell -c "from investigations import ai_proxy; print(ai_proxy._tool_search_case_documents)"
```

- [ ] **Step 3: Commit**

Stage and commit on the local machine:

```bash
git add backend/investigations/ai_proxy.py
git commit -m "feat: add _tool_search_case_documents helper for agentic ai/ask/"
```

---

## Task 2: Add tool definition and dispatch dict

**Files:**
- Modify: `backend/investigations/ai_proxy.py` — add `SEARCH_DOCS_TOOL` and `TOOLS` immediately after the new `_tool_search_case_documents` function

- [ ] **Step 1: Add the tool definition and dispatch dict**

Append directly below the `_tool_search_case_documents` function from Task 1:

```python


SEARCH_DOCS_TOOL = {
    "name": "search_case_documents",
    "description": (
        "Search OCR'd document text within the current case. Use this to verify "
        "whether a fact appears in source documents, cross-reference 990 disclosures "
        "against deeds or UCC filings, or find supporting evidence before making a "
        "pattern claim. Returns up to 10 matching documents, each with a ~200-char "
        "snippet around the first match. Case-insensitive substring search. "
        "Search for distinctive names, EINs, parcel numbers, or phrases — not common "
        "words."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Text to search for (case-insensitive substring match)",
            },
        },
        "required": ["query"],
    },
}


# Name → callable. Each callable receives (case, **tool_input) and returns a
# JSON-serializable dict. Adding a new tool means one new entry here plus one
# new function above — no loop changes.
TOOLS = {
    "search_case_documents": _tool_search_case_documents,
}
```

- [ ] **Step 2: Sanity-check the definitions load**

Run from inside the Django shell:
```
cd backend && python manage.py shell -c "from investigations.ai_proxy import SEARCH_DOCS_TOOL, TOOLS; print(SEARCH_DOCS_TOOL['name'], list(TOOLS.keys()))"
```

Expected: `search_case_documents ['search_case_documents']`

- [ ] **Step 3: Commit**

```bash
git add backend/investigations/ai_proxy.py
git commit -m "feat: add SEARCH_DOCS_TOOL definition and TOOLS dispatch dict"
```

---

## Task 3: Update `ASK_SYSTEM` prompt

**Files:**
- Modify: `backend/investigations/ai_proxy.py:598-705` — edit the `ASK_SYSTEM` constant

- [ ] **Step 1: Add the tool-awareness paragraph**

Find this line in `ASK_SYSTEM` (currently around line 675):

```
RESPONSE FORMAT — structure every response as:
```

Insert a new paragraph immediately ABOVE that line (before `RESPONSE FORMAT`). The prompt should now contain:

```
TOOLS AVAILABLE:
You have access to a document search tool (search_case_documents). Prefer citing
actual document text over relying only on the case summary above. Before making
a pattern claim about a specific name, EIN, or parcel number, search for it.

RESPONSE FORMAT — structure every response as:
```

- [ ] **Step 2: Replace the JSON-output block with a prose-output instruction**

Find the tail of `ASK_SYSTEM` — the block that currently reads:

```
Respond with valid JSON:
{
  "what_data_shows": "factual observations with citations",
  "pattern_assessment": "indicator matches with severity levels",
  "exculpatory_note": "plausible innocent explanation or null",
  "thread_to_pull": "one specific next investigative action",
  "sources_cited": [{"name": "...", "field": "990 Part IX Line 11 / doc page / filing date"}]
}
"""
```

Replace it with:

```
Respond in prose (NOT JSON). Use the four labeled sections above as headers in
your response. End with a brief "Sources cited" section listing document names
or 990 line numbers you referenced.
"""
```

Leave everything above (`LANGUAGE RULES`, etc.) untouched.

- [ ] **Step 3: Sanity-check the prompt string is still valid Python**

Run from inside the Django shell:
```
cd backend && python manage.py shell -c "from investigations.ai_proxy import ASK_SYSTEM; print(len(ASK_SYSTEM), 'TOOLS AVAILABLE' in ASK_SYSTEM, 'JSON' not in ASK_SYSTEM.split('RESPONSE FORMAT')[1])"
```

Expected: a length number, then `True True`.

- [ ] **Step 4: Commit**

```bash
git add backend/investigations/ai_proxy.py
git commit -m "feat: update ASK_SYSTEM for tool use and prose output"
```

---

## Task 4: Refactor `ai_ask()` into an agentic loop

**Files:**
- Modify: `backend/investigations/ai_proxy.py:708-759` — replace the body of `ai_ask`

- [ ] **Step 1: Replace the `ai_ask` function**

Open [backend/investigations/ai_proxy.py](../../../backend/investigations/ai_proxy.py) and find `def ai_ask(case, question: str, conversation_history: list[dict] | None = None) -> dict:` at line 708. Replace the entire function (everything from the `def ai_ask` line through the final `return {"error": str(e)}` line) with:

```python
def ai_ask(
    case,
    question: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """Answer a free-form question about the case using the agentic tool loop.

    The model may call tools (currently just search_case_documents) up to
    MAX_TOOL_ITERATIONS times to gather evidence before producing the final
    answer. Rate limit decrements once per user question, regardless of how
    many Claude API calls happen inside the loop.

    Returns:
        {
          "answer": str,                    # prose response from Claude
          "tool_calls_made": list[dict],    # [{name, input, match_count|error}]
          "tool_budget_exceeded": bool,
          "_model": str,
          "_usage": {"input_tokens": int, "output_tokens": int},
        }
        or {"error": "..."} on rate-limit / API failure.
    """
    MAX_TOOL_ITERATIONS = 5

    if not _check_rate_limit(str(case.pk)):
        return {"error": "Rate limit exceeded. Try again in a minute."}

    case_ctx = _build_case_context(case)

    # Build messages list for multi-turn conversation
    messages: list[dict] = []
    if conversation_history:
        for msg in conversation_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    user_content = f"CASE DATA:\n{case_ctx}\n\nQUESTION: {question}"
    messages.append({"role": "user", "content": user_content})

    tool_calls_made: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0
    tool_budget_exceeded = False

    try:
        client = _get_client()
        tools_param = [SEARCH_DOCS_TOOL]

        response = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=MAX_TOKENS,
            temperature=0.3,
            system=ASK_SYSTEM,
            messages=messages,
            tools=tools_param,
        )
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        iteration = 0
        while response.stop_reason == "tool_use":
            if iteration >= MAX_TOOL_ITERATIONS:
                tool_budget_exceeded = True
                logger.warning(
                    "ai_ask tool budget exceeded (case=%s, iterations=%d)",
                    case.pk,
                    iteration,
                )
                break

            tool_result_blocks: list[dict] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                tool_name = block.name
                tool_input = dict(block.input)
                tool_use_id = block.id
                logger.info(
                    "ai_ask tool call: case=%s tool=%s input=%s",
                    case.pk,
                    tool_name,
                    tool_input,
                )
                record: dict = {"name": tool_name, "input": tool_input}
                try:
                    fn = TOOLS.get(tool_name)
                    if fn is None:
                        raise ValueError(f"Unknown tool: {tool_name}")
                    result = fn(case, **tool_input)
                    record["match_count"] = result.get("match_count", 0)
                    tool_result_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps(result, default=str),
                        }
                    )
                except Exception as exc:
                    logger.exception(
                        "ai_ask tool error: case=%s tool=%s", case.pk, tool_name
                    )
                    record["error"] = str(exc)
                    tool_result_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "is_error": True,
                            "content": str(exc),
                        }
                    )
                tool_calls_made.append(record)

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_result_blocks})

            response = client.messages.create(
                model=MODEL_SONNET,
                max_tokens=MAX_TOKENS,
                temperature=0.3,
                system=ASK_SYSTEM,
                messages=messages,
                tools=tools_param,
            )
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens
            iteration += 1

        # Extract final prose answer from text blocks in the last response
        text_parts = [
            getattr(block, "text", "")
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        answer = "\n".join(p for p in text_parts if p).strip()
        if not answer and tool_budget_exceeded:
            answer = "(tool-use budget exceeded before final answer)"

        return {
            "answer": answer,
            "tool_calls_made": tool_calls_made,
            "tool_budget_exceeded": tool_budget_exceeded,
            "_model": MODEL_SONNET,
            "_usage": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            },
        }

    except Exception as e:
        logger.error("AI ask failed: %s", e)
        return {"error": str(e)}
```

Key points for the engineer:
- The old `json.loads(cleaned)` parsing logic is gone. The answer is plain prose.
- Token usage is summed across every API call in the loop.
- The existing `conversation_history` handling (last 6 messages) is preserved.
- `response.content` from a `tool_use` stop is passed back as-is in the assistant turn — the SDK accepts the block objects directly.
- `tool_result` content is passed as a JSON string, not the raw dict. Claude parses it on its side.

- [ ] **Step 2: Sanity-check the function imports and signature**

Run from inside the Django shell:
```
cd backend && python manage.py shell -c "from investigations.ai_proxy import ai_ask; import inspect; print(inspect.signature(ai_ask))"
```

Expected: `(case, question: str, conversation_history: list[dict] | None = None) -> dict`

- [ ] **Step 3: Run ruff to catch style issues**

Run: `ruff check backend/investigations/ai_proxy.py`

Expected: no errors. If E501 (line too long) appears, break the long string literal with parenthesized concatenation — `views.py`/`ai_proxy.py` are under the 100-char cap per CLAUDE.md code-style rules.

- [ ] **Step 4: Commit**

```bash
git add backend/investigations/ai_proxy.py
git commit -m "feat: convert ai_ask into agentic tool-use loop"
```

---

## Task 5: Manual verification against Bright Future Foundation

**Files:** none — this is a runtime verification step.

- [ ] **Step 1: Start the backend locally**

```bash
cd backend
python manage.py runserver
```

Expected: server boots on `http://localhost:8000` with no ImportError or syntax error.

- [ ] **Step 2: Ensure the demo case is seeded**

In a second terminal:
```bash
cd backend
python manage.py seed_demo
```

Expected: either "already seeded" or a summary of entities created. Note the Case UUID printed at the end — call it `$CASE_ID` below.

Find it later with:
```bash
python manage.py shell -c "from investigations.models import Case; print([(c.name, c.pk) for c in Case.objects.all()])"
```

- [ ] **Step 3: Get a CSRF token**

```bash
curl -c /tmp/cat_cookies.txt http://localhost:8000/api/csrf/
```

Expected: `{"csrfToken": "..."}`. The cookie is stored in `/tmp/cat_cookies.txt` for the next call.

- [ ] **Step 4: Ask a question that should trigger the tool**

Pick a question about the demo case. Bright Future Foundation includes a fictional person "Karen" and a construction-related entity — the exact names are in [backend/investigations/management/commands/seed_demo.py](../../../backend/investigations/management/commands/seed_demo.py). Check that file first for the actual names seeded, then substitute.

```bash
CASE_ID="<the uuid from step 2>"
CSRF=$(grep csrftoken /tmp/cat_cookies.txt | awk '{print $7}')

curl -X POST "http://localhost:8000/api/cases/$CASE_ID/ai/ask/" \
  -b /tmp/cat_cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF" \
  -d '{"question": "Does any document mention payments to a construction company?"}' \
  | python -m json.tool
```

Expected response shape:
```json
{
  "answer": "WHAT THE DATA SHOWS\n...",
  "tool_calls_made": [
    {"name": "search_case_documents", "input": {"query": "..."}, "match_count": 1}
  ],
  "tool_budget_exceeded": false,
  "_model": "claude-sonnet-4-20250514",
  "_usage": {"input_tokens": ..., "output_tokens": ...}
}
```

Verify:
1. `tool_calls_made` is non-empty (the agent actually used the tool).
2. `answer` contains the four section headers (WHAT THE DATA SHOWS, PATTERN ASSESSMENT, EXCULPATORY NOTE, THREAD TO PULL).
3. The `answer` cites document names that exist in the seeded case, not invented ones.
4. Server log shows an `INFO` line: `ai_ask tool call: case=... tool=search_case_documents input={'query': '...'}`.

- [ ] **Step 5: Probe a no-match case**

```bash
curl -X POST "http://localhost:8000/api/cases/$CASE_ID/ai/ask/" \
  -b /tmp/cat_cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF" \
  -d '{"question": "Does any document mention Xyzzyxabcdef Corporation?"}' \
  | python -m json.tool
```

Verify:
1. `tool_calls_made` includes a call with `match_count: 0`.
2. `answer` explicitly states that the name does not appear in the documents — NOT a fabricated quote.

- [ ] **Step 6: Probe a question that shouldn't need the tool**

```bash
curl -X POST "http://localhost:8000/api/cases/$CASE_ID/ai/ask/" \
  -b /tmp/cat_cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF" \
  -d '{"question": "How many documents are in this case?"}' \
  | python -m json.tool
```

Verify: The agent may or may not call the tool — either is acceptable. The point is the loop still terminates cleanly with `stop_reason == "end_turn"` on the first response (i.e. `tool_calls_made` can be empty without error).

- [ ] **Step 7: No commit**

Manual verification only. If a regression is discovered, fix it in a follow-up task or ask the author.

---

## Task 6: Final commit and push

**Files:** none — repository housekeeping.

- [ ] **Step 1: Check status is clean**

```bash
git status
git log --oneline -5
```

Expected: the 4 commits from Tasks 1-4 are in your log. Working tree clean.

- [ ] **Step 2: Push to main (or PR branch) when Tyler decides**

Per CLAUDE.md, Tyler pushes from his local machine. Do not push from the sandbox.

```bash
git push origin main  # or the feature branch
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Tool function — Task 1
- [x] Tool definition dict — Task 2
- [x] Dispatch dict (TOOLS) — Task 2
- [x] System prompt edits (add TOOLS AVAILABLE, drop JSON block) — Task 3
- [x] Agentic loop refactor (5-iteration cap, token summing, error handling) — Task 4
- [x] Response shape change (`answer`, `tool_calls_made`, `tool_budget_exceeded`) — Task 4
- [x] Manual verification per spec — Task 5
- [x] Rate-limit decrement once per question — Task 4 (line: `_check_rate_limit` once, before loop)
- [x] `is_error` tool_result on exception — Task 4
- [x] Logging at INFO on tool call, WARNING on budget exceeded, exception on tool error — Task 4

**Placeholder scan:** No TBDs, no "similar to", no vague error-handling directives. Every code block is complete.

**Type consistency:** `TOOLS` dict, `SEARCH_DOCS_TOOL` constant, `MAX_TOOL_ITERATIONS` local, `tool_calls_made` list — names consistent across Tasks 2 and 4.

**Out-of-scope confirmation:** No pytest tests (per spec), no frontend changes (per spec), no new tools beyond `search_case_documents` (per spec).
