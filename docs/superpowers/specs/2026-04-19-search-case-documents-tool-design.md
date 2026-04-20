# Design: `search_case_documents` — First Agentic Tool for `ai/ask/`

**Date:** 2026-04-19
**Author:** Tyler Collins (with Claude)
**Status:** Design — awaiting review before implementation plan
**Related:** `docs/team/investigative-agent-system-prompt.md`, `backend/investigations/ai_proxy.py`

---

## Purpose

Give the `ai/ask/` investigative assistant the ability to search OCR'd document text within the current case. This is the first tool in the agentic tool-use loop. Without it, the assistant can only reason over the dumped case summary — it cannot verify whether a specific name, EIN, parcel number, or phrase actually appears in the source documents it's asked about.

This tool is the foundation for cross-referencing 990 disclosures against uploaded deeds, UCC filings, and other evidence.

---

## Scope

### In scope
- One new tool function: `search_case_documents(query)`
- Tool definition dict in the Anthropic API format
- Refactor of `ai_ask()` into an agentic tool-use loop
- System-prompt edit: nudge toward tool use, remove JSON-output instruction
- New response shape from `ai_ask()`: `{"answer": str, "tool_calls_made": [...], ...}`

### Out of scope (deferred to later tools / sessions)
- Additional tools (`get_financials`, `search_entities`, `check_990_schedules`, etc.)
- pytest coverage with mocked Anthropic client
- Tool-result caching within a conversation
- Separate tool-call rate-limit budget
- Frontend changes to surface `tool_calls_made` in the UI

---

## Architecture

### The tool function (pure DB call, no AI)

```python
def _tool_search_case_documents(case, query: str, limit: int = 10) -> dict:
    """Search OCR'd document text within a single case. Case-insensitive substring match.

    Returns up to `limit` matches. Each result includes a ~200-char snippet around the
    first occurrence in that document, plus document metadata (name, type, sha256) so the
    agent can cite sources in its final answer.
    """
```

- Query: `Document.objects.filter(case=case, extracted_text__icontains=query).exclude(extracted_text__isnull=True).exclude(extracted_text__exact="")[:limit]`
- Snippet: `text[max(0, idx-200) : idx + len(query) + 200]` where `idx = text.lower().find(query.lower())`
- Returns: `{"query": str, "match_count": int, "results": [{"document_id": str, "display_name": str, "doc_type": str, "sha256": str, "snippet": str, "match_position": int}]}`
- No matches returns `{"match_count": 0, "results": []}` — **not** an error.
- Real exceptions (DB connection, unexpected crashes) bubble up to the loop and are converted to `{"type": "tool_result", "tool_use_id": ..., "is_error": True, "content": str(exception)}` so Claude knows the tool itself broke rather than returning empty.

### The tool definition

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
```

### The agentic loop in `ai_ask()`

Replaces the current single-call body. High-level flow:

```
1. Rate-limit check (1 decrement per user question — unchanged).
2. Build case context, assemble messages list from conversation history.
3. Initial API call: client.messages.create(..., tools=[SEARCH_DOCS_TOOL]).
4. Loop while response.stop_reason == "tool_use" AND iteration < 5:
     a. For each `tool_use` block in response.content:
          - Look up tool by name; execute with provided input.
          - Build a `tool_result` content block with the result dict (json-serialized).
          - On exception: build tool_result with is_error=True.
          - Record {name, input, match_count} to tool_calls_made list.
     b. Append {role: "assistant", content: response.content} to messages.
     c. Append {role: "user", content: [all tool_result blocks]} to messages.
     d. Re-call client.messages.create(..., tools=[SEARCH_DOCS_TOOL]).
     e. iteration += 1.
5. After loop: extract final text from response.content (text blocks only).
6. Return {"answer": text, "tool_calls_made": [...], "_model": ..., "_usage": ...,
           "tool_budget_exceeded": True if iteration == 5 and stop_reason still tool_use}.
```

**Iteration cap: 5.** Conservative for a single-tool setup. Raise later as traces justify it.

**Tool dispatch:** A single `TOOLS` dict maps tool name → callable. Adding tool 2 later means one new entry in the dict and one new function — no loop changes.

### System-prompt changes

1. **Add one short paragraph** just before the RESPONSE FORMAT section:
   > *You have access to a document search tool (`search_case_documents`). Prefer citing actual document text over relying only on the case summary above. Before making a pattern claim about a specific name, EIN, or parcel, search for it.*

2. **Strip the JSON-output block** at the end:
   ```
   Respond with valid JSON:
   { "what_data_shows": ..., "pattern_assessment": ..., ... }
   ```
   and replace with:
   > *Respond in prose. Structure your answer in four labeled sections: "What the data shows", "Pattern assessment", "Exculpatory note", "Thread to pull". End with a brief "Sources cited" list referencing document names or 990 line numbers.*

The Catalyst principle, governing rules, indicator knowledge, and language rules all stay untouched.

### Response shape

**Before:**
```json
{
  "what_data_shows": "...",
  "pattern_assessment": "...",
  "exculpatory_note": "...",
  "thread_to_pull": "...",
  "sources_cited": [...],
  "_model": "...",
  "_usage": {...}
}
```

**After:**
```json
{
  "answer": "WHAT THE DATA SHOWS\n...\n\nPATTERN ASSESSMENT\n...\n\n(etc.)",
  "tool_calls_made": [
    {"name": "search_case_documents", "input": {"query": "Baumer"}, "match_count": 3}
  ],
  // On tool error, the entry is:
  //   {"name": "search_case_documents", "input": {...}, "error": "..."}
  "_model": "claude-sonnet-4-20250514",
  "_usage": {"input_tokens": ..., "output_tokens": ...},
  "tool_budget_exceeded": false
}
```

The existing JSON-parse fallback in `ai_ask()` already returns `{answer: raw, sources: [], follow_up_questions: []}` when parsing fails — views and frontend already tolerate an `answer` string, so the frontend should render correctly without changes. `tool_calls_made` is additive and ignored until the UI is updated.

---

## Data Flow

```
User question via POST /api/cases/<id>/ai/ask/
        │
        ▼
views.api_case_ai_ask  (extracts question, passes to ai_proxy)
        │
        ▼
ai_proxy.ai_ask(case, question, history)
        │
        ├─ rate-limit check (1 decrement)
        ├─ build case context (_build_case_context, unchanged)
        ├─ assemble messages list
        │
        ▼
Claude API call #1 (tools=[SEARCH_DOCS_TOOL])
        │
        ├─ stop_reason == "end_turn"  → return answer. DONE.
        │
        └─ stop_reason == "tool_use"
              │
              ├─ execute _tool_search_case_documents(case, query)
              │         (Django ORM: filter case_id + extracted_text__icontains)
              │
              ├─ build tool_result content block
              │
              ├─ append assistant + user(tool_result) to messages
              │
              ▼
        Claude API call #2..N (same tools, expanded messages)
              │
              (loop until end_turn OR 5 iterations)
              │
              ▼
        Final text extracted from response.content
              │
              ▼
        Return {answer, tool_calls_made, _model, _usage}
```

---

## Error Handling

| Failure mode | Behavior |
|---|---|
| Empty query string from model | Tool returns `{"match_count": 0, "results": []}` (empty `icontains` match). Claude reformulates. |
| Case has zero OCR'd documents | Same as above — normal empty result. |
| DB exception during search | Caught in loop, returned as `{"is_error": true, "content": str(e)}` tool_result. Claude sees the failure and either tries another approach or proceeds without that data. |
| Loop exceeds 5 iterations | Break out. Extract any text blocks from the last response; if the last response was pure `tool_use` (no text), return `answer: "(tool-use budget exceeded before final answer)"`. Flag `tool_budget_exceeded: true`. Log at WARNING. |
| Anthropic API exception | Caught at outer try/except (same pattern as existing code), returns `{"error": str(e)}`. |
| Model returns malformed tool input | The Anthropic SDK validates against `input_schema` before we see it; invalid tool_use should not reach our dispatch. If it does (extra fields, etc.), our function accepts `query` and ignores the rest. |

---

## Testing (this session)

Manual verification against the Bright Future Foundation demo case:

1. Start backend locally: `python backend/manage.py runserver`
2. Ensure demo case is seeded: `python backend/manage.py seed_demo`
3. POST to `/api/cases/<bright-future-uuid>/ai/ask/` with questions designed to trigger the tool:
   - *"Does any document mention payments to Karen's construction company?"* — should fire `search_case_documents` with a query like "Karen" or "construction".
   - *"What does the 2022 Form 990 say about related-party transactions?"* — should search for "Schedule L" or "related party".
   - *"Find any mention of parcel 12-345-678."* — should search for the parcel number.
4. Inspect the returned `tool_calls_made` array to confirm the tool fired and what it was called with.
5. Inspect `answer` for the 4-section format and verify sources are cited from actual document content rather than hallucinated.
6. Check server logs for the INFO-level tool-call log lines.

Failure modes to probe:
- Ask a question about a name that does not appear in any document — confirm the agent says so explicitly rather than inventing evidence.
- Ask about the demo case with zero docs (temporarily disable seeding) — confirm empty-result handling.

---

## Trade-offs Accepted

- **Plain prose output instead of structured JSON.** Simpler, more reliable with tool use. Cost: any future consumer that relied on the structured fields (`what_data_shows`, `pattern_assessment`, etc.) must now parse prose or update the prompt. Acceptable because the current frontend already falls back to treating the answer as a string.
- **5-iteration cap.** Conservative. May occasionally cut off a legitimately long chain of searches. If so, raise after observing real traces.
- **No tool-result caching within a conversation.** A mildly confused model could fire the same query twice. Cheap enough to not matter at this scale; revisit if logs show the pattern.
- **Rate limit decrements once per user question, not per API call in the loop.** One question could generate 5 API calls under the hood. This matches user-facing cost expectations but means a burst of 10 questions in a minute could cost ~50 API calls. Acceptable for a portfolio demo.
- **Single-tool scope.** Design anticipates tools 2+ by using a dispatch dict, but only ships tool 1. Tools 2+ are separate specs.

---

## Rollback Plan

If the agentic loop breaks `ai/ask/` in a way that can't be quickly fixed, revert `ai_proxy.py` to the previous commit. The tool function and tool definition are new — they don't affect any other endpoint. The system-prompt change is confined to `ASK_SYSTEM` and is independent.

---

## Open questions

None — all design questions were resolved during the brainstorm Q1–Q7.
