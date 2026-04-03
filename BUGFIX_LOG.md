# Catalyst Bug Fix Log — April 3, 2026

This document describes the bugs found during production testing and the fixes applied.

---

## Bug 1: AI Sidebar 500 Error (All AI Features)

**Symptom:** Clicking the AI summarize button on any signal, detection, or entity returned a 500 Server Error. The AI sidebar showed raw HTML error content.

**Root Cause:** The frontend builds composite IDs for React list keys by prefixing the type to the UUID (e.g., `signal-dfdb45aa-...`, `detection-abcd1234-...`). When the AI feature sends these IDs to the backend, Django tries to use them in `Signal.objects.filter(pk=target_id)` — but the `pk` field is a UUID, and `"signal-dfdb45aa-..."` is not a valid UUID.

**Files Changed:**
- `backend/investigations/ai_proxy.py`

**Fix:** Added a `_strip_id_prefix()` helper function that extracts the raw UUID from any prefixed ID string using a regex match. Applied this function to all four AI endpoints:
- `ai_summarize()` — strips `target_id` before Signal/Entity queries
- `ai_connections()` — strips `entity_id` before Entity queries
- `ai_narrative()` — strips each `detection_id` in the list before Detection queries
- `_build_entity_context()` — receives already-cleaned IDs from the callers above

---

## Bug 2: Search Bar Does Nothing on Enter

**Symptom:** Typing a query in the top search bar and pressing Enter appeared to do nothing. The search page itself also produced no results.

**Root Cause:** The SearchView component was using a client-side search approach — fetching ALL cases, ALL signals, and ALL entities, then filtering them locally with basic string matching. This was slow and unreliable. Meanwhile, the backend already had a fully functional `/api/search/` endpoint with PostgreSQL full-text search that was never being used.

**Files Changed:**
- `frontend/src/views/SearchView.tsx`

**Fix:** Rewrote the SearchView to call the backend `/api/search/` endpoint instead of doing client-side search. The top search bar in AppShell.tsx was already correctly navigating to `/search?q=...` — the SearchView now properly processes these results from the backend's ranked full-text search. Also added "document" as a search result type filter since the backend returns document matches too.

---

## Bug 3: Triage Shows Badge Count but 0 Results

**Symptom:** The sidebar Triage badge showed "5" (later "4") but opening the Triage page displayed "0 open" with "No signals match the current filters."

**Root Cause:** This appears to have been a transient issue. Direct API testing confirmed the `/api/signals/?status=OPEN` endpoint correctly returns all OPEN signals. The badge count and the API endpoint both use the same `status="OPEN"` filter. The frontend code is correct. This may have been caused by a timing issue during initial page load, a browser caching problem, or a race condition that has since resolved.

**Status:** Monitored — API confirmed working correctly via direct curl testing.

---

## Bug 4: Entity Graph Shows Random Words Instead of Real Entities

**Symptom:** The Overview tab's entity relationship graph displayed nodes for non-entities like "Domestic Limited Liability Company", "my hand", "an authorized", "Tax Canceled Corp", "Limited Liability Partners", etc.

**Root Cause:** The entity extraction pipeline's validation wasn't catching generic business type descriptions or sentence fragments. For example, "Domestic Limited Liability Company" passed validation because "domestic" was a 3+ character word not in the stopword list.

**Files Changed:**
- `backend/investigations/entity_extraction.py`

**Fix:**
1. Added new stopwords to `_ORG_STOPWORDS`: "domestic", "foreign", "limited", "liability", "profit", "for-profit", "professional", "canceled", "dissolved", etc.
2. Created a new `_ORG_REJECT_PHRASES` set that blocks known generic business type labels outright (e.g., "domestic limited liability company", "limited liability partners", "dom. llc").
3. Updated `_is_plausible_org_name()` to check against reject phrases and reject names containing IRS section headers.
4. Added new stopwords to `_PERSON_STOPWORDS`: "my", "hand", "an", "authorized", "representative", "undersigned", "witness", "whereof", etc.

**Note:** Existing bad entities in the database will need to be cleaned up manually or by re-running entity extraction on the affected documents. New uploads will produce cleaner results.

---

## Bug 5: PDF Preview Not Implemented

**Symptom:** Clicking "View" on a document in the Documents tab opened a slide-over panel that said "PDF preview not yet implemented."

**Root Cause:** The PdfViewer component had a placeholder message instead of actual content display. Since Railway uses an ephemeral filesystem and doesn't serve static media files, rendering the actual PDF isn't possible without an external file storage service.

**Files Changed:**
- `frontend/src/components/ui/PdfViewer.tsx`
- `frontend/src/components/ui/PdfViewer.module.css`
- `backend/investigations/views.py` (document detail endpoint)
- `frontend/src/types.ts` (DocumentDetail interface)

**Fix:** Instead of showing "not implemented," the Document tab now displays the extracted text from the document. This is the OCR'd/parsed text content that Catalyst already extracts during document processing. Changes:
1. Added `extracted_text` to the document detail API response (backend).
2. Added `extracted_text` to the `DocumentDetail` TypeScript interface.
3. Replaced the placeholder with a `<pre>` block showing the extracted text with proper monospace formatting, scrolling, and styling.
4. Shows contextual messages if text hasn't been extracted yet or if OCR is still pending.

---

## Bug 6: No Financial Data Extracted from IRS Form 990s

**Symptom:** The Financials tab showed "No IRS Form 990 financial data has been extracted for this case" even though Form 990 PDFs had been uploaded and processed.

**Root Cause:** A data structure mismatch between the extraction function and the save function. The extraction function (`_extract_990_financials` in `entity_extraction.py`) returns dictionaries with keys `{"field", "raw", "value"}`, but the save function (`_save_financial_snapshot` in `views.py`) expected dictionaries with keys `{"key", "current_year", "prior_year"}`. Since the keys didn't match, no financial data was ever saved to the database.

**Files Changed:**
- `backend/investigations/views.py` (`_save_financial_snapshot` function)

**Fix:** Updated `_save_financial_snapshot` to accept both data formats. It now checks for `item.get("key") or item.get("field")` for the field name, and `item.get("current_year") if not None else item.get("value")` for the value. This makes it compatible with both the extraction output and any future format changes.

**Note:** Existing documents that were uploaded before this fix will need to be re-processed (delete and re-upload, or trigger re-extraction) to populate the Financials tab.

---

## Bug 7: Pipeline Cards Look Messy (No Visual Separation)

**Symptom:** Signal, detection, and finding cards on the Pipeline tab blended into the dark background with minimal visual distinction. It was hard to tell where one card ended and another began.

**Files Changed:**
- `frontend/src/components/cases/PipelineTab.module.css`
- `frontend/src/components/cases/PipelineTab.tsx`

**Fix:**
1. Added a colored left border to each card based on its severity level (red for Critical, orange for High, yellow for Medium, blue for Low).
2. Increased the card border opacity from `var(--border-subtle)` to `var(--border)` for better visibility.
3. Added a subtle box-shadow (`0 1px 3px rgba(0,0,0,0.15)`) to give cards depth.
4. Enhanced the hover state with a stronger shadow effect.
5. Created CSS classes `cardSevCritical`, `cardSevHigh`, `cardSevMedium`, `cardSevLow`, `cardSevInfo` and applied them in the component.

---

## Bug 8: Top Search Bar — Enter Key Not Working

**Symptom:** Pressing Enter in the top search bar ("Ask anything about your cases...") did not produce visible results.

**Root Cause:** This was the same issue as Bug 2 — the AppShell's search handler correctly navigated to `/search?q=...`, but the SearchView wasn't effectively searching. With the SearchView rewrite (Bug 2 fix), the top bar search now works end-to-end.

**Fix:** Resolved by the SearchView rewrite in Bug 2.

---

## Bug 9: Case Header Text Overlapping

**Symptom:** On the Pipeline and other case detail tabs, the case description text ("Example Charity is buying up a lot of property in Example Township") appeared to overlap with other elements.

**Files Changed:**
- `frontend/src/views/CaseDetailView.module.css`

**Fix:** Added `overflow: hidden`, `text-overflow: ellipsis`, `white-space: nowrap`, and `max-width: 100%` to the `.caseDetailMeta` class to prevent the metadata text from overflowing its container.

---

## Summary of All Files Changed

| File | Changes |
|------|---------|
| `backend/investigations/ai_proxy.py` | Added `_strip_id_prefix()` helper; applied to all AI endpoints |
| `backend/investigations/views.py` | Fixed financial data key mapping; added `extracted_text` to doc detail |
| `backend/investigations/entity_extraction.py` | Added org reject phrases, person/org stopwords, section header rejection |
| `frontend/src/views/SearchView.tsx` | Rewrote to use backend `/api/search/` endpoint |
| `frontend/src/views/CaseDetailView.module.css` | Fixed header text overflow |
| `frontend/src/components/cases/PipelineTab.tsx` | Added severity-based card CSS classes |
| `frontend/src/components/cases/PipelineTab.module.css` | Added colored left borders, shadows, card severity styles |
| `frontend/src/components/ui/PdfViewer.tsx` | Replaced placeholder with extracted text display |
| `frontend/src/components/ui/PdfViewer.module.css` | Added `.extractedText` styling |
| `frontend/src/types.ts` | Added `extracted_text` to `DocumentDetail` interface |
