# Catalyst — Design Decisions Log

**Last Updated:** 2026-04-01
**Status:** Living document — add new decisions as they're made

This file records the "why" behind key architectural and design choices. When a future session asks "why did we do it this way?", the answer should be here.

---

## Architecture Decisions

### AD-001: Monolith, Not Microservices

**Decision:** Build as a Django monolith. Do not pursue microservices architecture.

**Context:** Charter v2 mentioned microservices as a future target. After building the system, it's clear that microservices would add operational complexity (service discovery, inter-service auth, distributed tracing, separate deployments) without adding value at this stage. The monolith is organized into logical modules (connectors, pipeline, signal engine, API layer) that could be extracted later if needed.

**Trade-off:** Simpler deployment and development. Gives up independent scaling of individual services, which is not needed for a single-user investigation tool.

### AD-002: No Django REST Framework

**Decision:** Use Django's native JSON handling instead of DRF.

**Context:** DRF adds a large dependency for functionality we don't fully need. The API is straightforward enough that custom serializer functions and view decorators handle it cleanly. This also gives full control over response shapes and validation logic.

**Trade-off:** More boilerplate for serialization. Gains full control and smaller dependency footprint.

### AD-003: Human-in-the-Loop Connector Design

**Decision:** External data connectors surface candidates for investigator review. They never auto-merge data into the database.

**Context:** Forensic investigations require defensible data provenance. Auto-importing external data would make it impossible to distinguish investigator-verified facts from machine-imported data. Every connector returns structured results that the investigator must consciously act on.

**Trade-off:** More manual work for the investigator. Gains defensible audit trail and prevents bad external data from contaminating investigations.

### AD-004: Staleness Warnings on All External Data

**Decision:** Every connector result includes a StalenessWarning (LOW/MEDIUM/HIGH) based on data age.

**Context:** Government bulk data files (IRS, Ohio SOS) are updated on schedules (monthly, quarterly). An investigator needs to know if the data they're looking at is 3 days old or 3 months old. This is critical for investigations that may be cited in legal proceedings.

### AD-005: SHA-256 on Original Bytes Before Processing

**Decision:** Hash the uploaded file immediately before any extraction, classification, or modification.

**Context:** Chain of custody. If a document is ever challenged in a legal proceeding, we need to prove that the file in the system is identical to what was originally submitted. The hash is computed on the raw bytes before the pipeline touches the file.

### AD-006: Fuzzy Entity Matching Never Auto-Merges

**Decision:** When entity resolution finds a fuzzy match (similarity 0.75-0.92), it flags the candidate but never merges automatically. Only exact matches (>0.92) are upserted.

**Context:** In forensic work, "John A. Example" and "John Example" might be the same person, or they might be father and son. An automated system cannot make that judgment call safely. Fuzzy candidates are surfaced with similarity scores for the investigator to review.

### AD-007: Extraction is Best-Effort, Never Blocking

**Decision:** A failure in entity extraction, financial extraction, or signal detection never blocks a document upload.

**Context:** The upload pipeline must be reliable. If the OCR works but entity extraction crashes, the document is still preserved with its text and hash. The `ExtractionStatus` field (COMPLETED/PARTIAL/FAILED/SKIPPED) tracks what succeeded and what didn't, so the investigator knows if they need to manually review.

### AD-008: Append-Only Audit Log

**Decision:** The AuditLog model has no update or delete operations. Django admin disables all write permissions. The database has an immutability trigger on `government_referrals.filing_date`.

**Context:** Forensic audit trails must be tamper-evident. If an auditor or opposing counsel reviews the system, they need confidence that records weren't modified after the fact.

---

## Frontend Design Decisions

### FD-001: Shell + Views Architecture

**Decision:** Persistent sidebar + header shell with swappable view panels driven by React Router.

**Rationale:** The original single-page design caused cognitive overload — case creation, signal triage, and referral tracking all competed for attention. Reference software analysis (Palantir Gotham, Splunk SOAR, Unit21, Linear) confirmed that purpose-built views for different workflows outperform god-component dashboards.

### FD-002: Always-Expanded Sidebar

**Decision:** Sidebar is always expanded (240px), never collapses to icon-only.

**Rationale:** Investigators may not be power users. A collapsible sidebar saves 200px of screen space but adds a click to navigate. For a desktop investigation tool (not mobile), the always-visible navigation is worth the space.

### FD-003: Cross-Case Triage Default

**Decision:** The signal triage queue shows signals from all cases by default, with an optional case filter.

**Rationale:** Investigators often work multiple cases simultaneously. The highest-severity signal might not be in the case they're currently focused on. Cross-case default ensures critical signals don't get missed.

### FD-004: Dark Theme Primary, Light Toggle

**Decision:** Dark theme is the default. Light theme available via toggle in Settings.

**Rationale:** Investigation work often involves long hours of screen time. Dark themes reduce eye strain. Some agencies may require light themes for accessibility, so both options exist.

### FD-005: Keyboard-First Triage

**Decision:** `j/k` to navigate signal queue, `1/2/3` to set status (OPEN/REVIEWED/DISMISSED).

**Rationale:** Inspired by Splunk SOAR's analyst queue. Signal triage is the highest-frequency investigator workflow. Keyboard shortcuts let analysts burn through a queue without touching the mouse. Shortcuts are disabled when focus is in an input field.

### FD-006: No Third-Party State Management

**Decision:** Use React Context + useReducer for state management. No Redux, Zustand, or MobX.

**Rationale:** The app's state complexity doesn't justify a third-party library. Context + useReducer handles the current scope cleanly. Zustand is identified as the upgrade path if re-render performance becomes an issue.

### FD-007: No Component Library Migration

**Decision:** Keep custom CSS + hand-built components. No Tailwind, MUI, or Chakra migration.

**Rationale:** The current styling works. A component library migration would be a multi-session detour that doesn't add investigative capability. The CSS variables system already provides theming support.

---

## Data Design Decisions

### DD-001: UUID Primary Keys Everywhere

**Decision:** All models use UUID primary keys instead of auto-incrementing integers.

**Rationale:** UUIDs prevent enumeration attacks (can't guess the next case ID), enable future distributed systems without ID conflicts, and are more appropriate for a security-sensitive forensic tool.

**Exception:** `GovernmentReferral` uses AutoField because referral IDs need to be human-readable sequential numbers for agency correspondence.

### DD-002: RESTRICT on Case Foreign Keys

**Decision:** All entity models use `on_delete=RESTRICT` for their Case foreign key.

**Rationale:** Deleting a case should never silently cascade and destroy investigation evidence. RESTRICT forces explicit cleanup — you must remove all entities, documents, and signals before a case can be deleted. This is a safety net against accidental data loss.

### DD-003: Separate ExtractionStatus from OcrStatus

**Decision:** `OcrStatus` tracks PDF text extraction. `ExtractionStatus` tracks the post-OCR analysis pipeline (entity extraction, financial extraction, signal detection).

**Rationale:** These are different concerns. A document can have successful OCR (text extracted) but failed entity extraction (regex didn't match anything). Separating them lets investigators quickly filter for documents where the analysis pipeline needs manual review.

### DD-004: GeneratedField for Valuation Delta

**Decision:** `Property.valuation_delta` is a Django GeneratedField computed as `purchase_price - assessed_value`.

**Rationale:** This delta is a key signal input (SR-003: valuation anomaly). Computing it in the database ensures it's always consistent and queryable without application-layer calculation.

---

## Scope Decisions

### SD-001: Ohio-First Geographic Scope

**Decision:** All government data connectors target Ohio specifically. Multi-state support is deferred.

**Rationale:** The developer has domain expertise in Ohio public records. Building one state deeply is more valuable for portfolio and real-world use than building shallow support for multiple states. The connector architecture (stateless modules, consistent interfaces) makes adding states straightforward later.

### SD-002: No Authentication in V1

**Decision:** Auth (login, user management, role-based access) is deferred to post-V1.

**Rationale:** Adding auth before the core investigation workflow is complete would slow progress without adding capability. The frontend is designed for multi-user from the start (user context provider, role labels), so auth can be added later without restructuring. CSRF is implemented as defense-in-depth.

### SD-003: AI Features via API Integration

**Decision:** AI capabilities (enhanced entity extraction, memo generation, semantic search) will be implemented via Claude/OpenAI API calls, not custom ML models.

**Rationale:** Training custom models requires datasets and infrastructure that aren't available. API integration delivers higher quality results faster and demonstrates practical AI integration skills — which is what employers want to see.

---

## Reference Software Influences

These systems informed Catalyst's design:

| Software | What We Took |
|----------|-------------|
| Palantir Gotham | Multiple analytical views on the same data; the case as anchor |
| Splunk SOAR | Analyst queue pattern with keyboard-driven triage |
| Unit21 | Role-specific dashboards; cross-case views for supervisors |
| Linear | Sidebar navigation, deep-linkable URLs, Cmd+K command palette |
| Notion | Multiple views on same data (table/board), saved filter views |
