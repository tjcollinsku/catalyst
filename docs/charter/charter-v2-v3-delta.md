# Catalyst Charter Delta — v2 vs Current Reality

**Date:** 2026-04-01
**Purpose:** Structured comparison of what charter v2 specified versus what actually exists in the codebase as of today. This document bridges v2 to v3 and makes every gap, addition, and divergence visible.

---

## How to Read This Document

Each section uses three columns:

- **Charter v2 Said** — what was specified or planned
- **What Actually Exists** — what the codebase contains right now
- **Status** — one of: ON TRACK, AHEAD, BEHIND, DIVERGED, NOT STARTED, ADDED (not in charter)

---

## 1. Document Intake (FR-101 through FR-105)

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| FR-101: Drag-and-drop PDF upload | POST endpoint for file upload; frontend has upload UI but DocumentsTab.tsx is truncated and won't compile | BEHIND |
| FR-102: Immutable document store | Files stored in Django media storage; originals preserved but not in a write-once store (MinIO/S3 planned) | PARTIAL |
| FR-103: SHA-256 hash at intake | Implemented — hash computed on original bytes before any processing | ON TRACK |
| FR-104: Document metadata recording | Implemented — filename, timestamp, size, hash, doc_type, source_url, case assignment | ON TRACK |
| FR-105: Bulk upload | Bulk upload endpoint exists (`/api/cases/<id>/documents/bulk/`) and frontend has bulk upload code, but DocumentsTab is truncated | BEHIND |

---

## 2. Document Processing (FR-201 through FR-205)

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| FR-201: Text extraction from digital PDFs | Implemented — PyMuPDF direct extraction | ON TRACK |
| FR-202: OCR for scanned PDFs | Implemented — Tesseract + Pillow fallback for files under 30MB | ON TRACK |
| FR-203: Document classification | Implemented — rule-based keyword scoring, auto-assigns doc_type | ON TRACK |
| FR-204: Structured field parsing by doc_type | Partially implemented — entity extraction extracts dates, amounts, names, parcels, filing refs. Not all doc_type templates are built. | PARTIAL |
| FR-205: Entity extraction (dates, amounts, names, orgs, parcels, filing refs) | Implemented — regex-based extraction in entity_extraction.py | ON TRACK |

---

## 3. Entity Resolution (FR-301 through FR-305)

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| FR-301: Relational entity database (Persons, Orgs, Properties, Financial Instruments, Government Actions) | Implemented — all entity models exist. "Government Actions" became GovernmentReferral. | ON TRACK |
| FR-302: Entity-to-document links with page citations | PersonDocument and OrgDocument models exist with page_reference fields | ON TRACK |
| FR-303: Cross-document entity match detection | Implemented — exact match auto-upsert + fuzzy candidate surfacing (0.75 threshold) | ON TRACK |
| FR-304: Confirm/reject/merge entity matches | Backend supports resolution results. No frontend UI for fuzzy match review. | BEHIND |
| FR-305: Deceased status tracking + post-mortem filing detection | Person.date_of_death field exists. SR-001 signal rule detects post-mortem filings. | ON TRACK |

---

## 4. Investigation Workspace (FR-401 through FR-402)

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| FR-401: Case containers grouping docs, entities, findings, signals | Implemented — Case model is the anchor for all data | ON TRACK |
| FR-402: Timeline view with filtering | No timeline view exists. AuditLog captures events but no timeline UI or endpoint. | NOT STARTED |

---

## 5. Relationship Graph (FR-501 through FR-507)

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| FR-501: Interactive relationship graph | NOT STARTED — no graph visualization exists | NOT STARTED |
| FR-502: Node types (Person, Org types, Property, Financial Instrument, Government Action) | Entity models exist but no graph representation | NOT STARTED |
| FR-503: Edge types (OFFICER_OF, ATTORNEY_FOR, GRANTOR_IN, etc.) | PersonOrganization model has role field. PropertyTransaction has buyer/seller. No formal edge type system. | PARTIAL |
| FR-504: Graph filtering by node type, edge type, date range, signal status | NOT STARTED | NOT STARTED |
| FR-505: Visual signal indicators on graph nodes | NOT STARTED | NOT STARTED |
| FR-506: Graph export to PNG and JSON | NOT STARTED | NOT STARTED |
| FR-507: Edge annotation with source citations | NOT STARTED | NOT STARTED |

**Summary:** The relationship graph — described in the charter as "the analytical core of Catalyst" — has not been started. This is the largest gap between charter and reality.

---

## 6. Signal Detection (FR-601 through FR-605)

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| FR-601: Evaluate docs/entities against signal rules on intake | Implemented — signal_rules.py runs evaluate_document() and evaluate_case() on upload | ON TRACK |
| FR-602: Signal records with rule ID, severity, entity, doc, citations, status | Signal model exists with all specified fields | ON TRACK |
| FR-603: Confirm/dismiss/escalate signals to Findings | Backend endpoints exist. Triage view works on frontend. Signal → Finding workflow exists. | ON TRACK |
| FR-604: Dismissed signals retained in audit log | AuditLog captures signal status changes | ON TRACK |
| FR-605: Extensible rule set without redeployment | Rules are in signal_rules.py — extensible by adding functions, but requires code changes, not config. | PARTIAL |

**Charter specified 10 rules (SR-001 through SR-010). Codebase implements 16 signal types.** The 6 additional types (REVENUE_ANOMALY, PHANTOM_OFFICER, NAME_RECONCILIATION, TIMELINE_COMPRESSION, CHARTER_CONFLICT, ADDRESS_NEXUS) were added beyond charter scope.

---

## 7. Findings Management (FR-701 through FR-705)

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| FR-701: Create findings linking entities, docs, signals, narrative, legal refs, severity, confidence, status | Finding model exists with all fields. Detection model also exists (not in charter). FindingEntity and FindingDocument link tables exist. | AHEAD |
| FR-702: Severity ratings (CRITICAL through INFORMATIONAL) | Implemented in FindingSeverity enum | ON TRACK |
| FR-703: Confidence levels (CONFIRMED, PROBABLE, POSSIBLE) | Implemented in FindingConfidence enum | ON TRACK |
| FR-704: Finding statuses (DRAFT through REFERRED) | Implemented in FindingStatus enum | ON TRACK |
| FR-705: Link multiple Findings into a Pattern | NOT STARTED — no Pattern model or concept exists | NOT STARTED |

---

## 8. Referral Memo Generation (FR-801 through FR-805)

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| FR-801: Generate PDF referral memos from case findings | Basic memo generation endpoint exists (`/api/cases/<id>/referral-memo/`). Produces structured output but not formatted PDF. | PARTIAL |
| FR-802: Memo content (executive summary, findings, entity profiles, timeline, graph, signal summary, hash verification) | Partial — generates findings and some metadata. No timeline, no graph export, no hash verification in memo. | BEHIND |
| FR-803: ORC and federal statute cross-references | NOT STARTED — no statute database or cross-reference system | NOT STARTED |
| FR-804: Agency-specific memo templates (Ohio AG, IRS, FBI, FCA IG) | NOT STARTED — single generic format only | NOT STARTED |
| FR-805: SHA-256 verification of cited documents in memo | Hash is stored but not verified/included in memo output | NOT STARTED |

---

## 9. Non-Functional Requirements

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| NFR-01: Encryption at rest, TLS 1.3 in transit | Not configured. Local dev only. | NOT STARTED |
| NFR-02: Secrets in env vars, not source code | Implemented — .env pattern with load_dotenv() | ON TRACK |
| NFR-03: Private repository | On GitHub (needs verification of visibility) | ON TRACK |
| NFR-04: User authentication required | NOT STARTED — no auth system | NOT STARTED |
| NFR-05: Private by Design — no external data transmission without user authorization | Connectors only fetch public data. No outbound data sharing. | ON TRACK |
| NFR-06: Mobile/tablet/desktop responsive | Desktop-only dark theme. Not responsive. | DIVERGED |
| NFR-07: Horizontal scaling via containerized microservices | Monolith architecture. Docker for DB only. Decision made to stay monolith. | DIVERGED |
| NFR-08: Concurrent cases without performance degradation | Single-user, untested at scale. Works fine for dev use. | PARTIAL |
| NFR-09: Write-once document store | Files stored but not in a write-once system. Media storage is mutable. | BEHIND |
| NFR-10: Entity modifications logged with timestamp | AuditLog model exists and captures changes | ON TRACK |
| NFR-11: Append-only audit trail | AuditLog is append-only. Admin write permissions disabled. | ON TRACK |
| NFR-12: SHA-256 verified before memo reference | NOT STARTED | NOT STARTED |

---

## 10. Architecture

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| Containerized microservices platform | Django monolith with logical module separation | DIVERGED (intentional — see AD-001) |
| Docker + Kubernetes deployment | Docker for PostgreSQL only. No Kubernetes. | BEHIND |
| MinIO/S3 file store | Django media storage | BEHIND |
| React PWA frontend | React SPA (Vite), not a PWA | PARTIAL |
| Django REST Framework | Django-native JSON API (no DRF) — intentional (see AD-002) | DIVERGED (intentional) |

---

## 11. Database Schema

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| ~13 tables (cases, documents, persons, organizations, properties, financial_instruments, findings, signals, audit_log, person_document, org_document, person_org, property_transaction, entity_signal, finding_entity, finding_document, government_referrals) | 21 models. All charter tables exist PLUS additions. | AHEAD |

**Models added beyond charter:**
| Model | Purpose | Notes |
|-------|---------|-------|
| FinancialSnapshot | Extracted IRS 990 financial data | Stores parsed 990 form data per tax year |
| Detection | Confirmed anomalies (automated or manual) | Intermediate step between Signal and Finding |
| InvestigatorNote | Free-form notes on any entity | Attachable to any entity type |
| Property (expanded) | Added valuation_delta GeneratedField, purchase_price, assessed_value | Charter had basic property; reality is richer |
| ExtractionStatus enum | Tracks post-OCR pipeline success/failure | Added during security hardening |

**Fields added beyond charter:**
- Document: `is_generated`, `doc_subtype`, `file_path`, `file_size`, `extraction_status`, `extraction_notes`
- Person: `address`, `phone`, `email`, `tax_id`
- Organization: `ein`, `registration_state`, `org_type`, `address`, `phone`, `email`, `formation_date`

---

## 12. Data Source Connectors

| Charter v2 Said | What Actually Exists | Status |
|-----------------|---------------------|--------|
| ProPublica Nonprofit Explorer (Phase 2) | Implemented — propublica_connector.py, 29 tests | AHEAD |
| IRS Tax Exempt Org Database (Phase 2) | Implemented — irs_connector.py, 104 tests | AHEAD |
| Ohio SOS Business Search (Phase 2) — "structured scraper" | Implemented as bulk CSV connector (not scraper — Cloudflare blocked scraping) | AHEAD (DIVERGED method) |
| Ohio UCC Search (Phase 2) | NOT STARTED | NOT STARTED |
| County Recorder / LandmarkWeb (Phase 3) | Implemented as county_recorder_connector.py — URL builder + document parser for all 88 Ohio counties. Not a scraper. | AHEAD (DIVERGED method) |
| County Auditor Parcel Systems (Phase 3) | Implemented as county_auditor_connector.py — ODNR ArcGIS API + portal URL builder for all 88 counties | AHEAD (DIVERGED method) |
| Ohio Auditor of State (Phase 3) | Implemented — ohio_aos_connector.py, HTML scraper | AHEAD |
| PACER Federal Courts (Phase 5) | NOT STARTED — fee-based, deferred | NOT STARTED |

**All Phase 2-3 connectors are complete except Ohio UCC.** Methods diverged from "structured scraper" to human-in-the-loop URL builder + bulk download patterns, which is better for legal compliance and reliability.

---

## 13. SDLC Roadmap

| Phase | Charter v2 Timeline | What's Done | Status |
|-------|-------------------|------------|--------|
| Phase 1: Foundation | March-April 2026 | Database schema, Django API, case/document CRUD, pagination, SHA-256 validation, admin layer | COMPLETE |
| Phase 2: Processing Pipeline | April-May 2026 | OCR, text extraction, classification, entity extraction/normalization/resolution, ProPublica + IRS + Ohio SOS connectors | COMPLETE |
| Phase 3: Investigation Interface | May-June 2026 | Signal engine (16 rules), county connectors (recorder + auditor + AOS), findings management. BUT: No relationship graph, no timeline view, frontend is broken (4 truncated files). | PARTIAL |
| Phase 4: Memo Generation | June-July 2026 | Basic memo endpoint exists. No PDF generation, no agency templates, no statute cross-references, no Kubernetes. | BEHIND |
| Phase 5: Evolution (Post-cert) | Post-certificate | AI features moved up to pre-release scope. No implementation yet. | NOT STARTED |

---

## 14. Security (Added Beyond Charter)

The charter specified basic security principles but no specific security audit. The codebase now includes security infrastructure that was not in the original charter:

| Addition | Description |
|----------|-------------|
| CSRF protection | Cookie + X-CSRFToken header pattern for SPA |
| Rate limiting middleware | Sliding-window per-IP (200 reads/min, 30 writes/min) |
| PDF magic bytes validation | Validates %PDF- header before processing |
| URL domain allowlists | Validates domains on all external connector responses |
| Chunked downloads with deadlines | Prevents slow-drip DoS on IRS bulk downloads |
| Path traversal prevention | Filename sanitization on uploads |
| ExtractionStatus tracking | Per-document pipeline success/failure tracking |
| Constrained audit action types | AuditAction TextChoices enum |
| Security audit document | docs/SECURITY_AUDIT.md — 38 findings across 3 phases |

---

## 15. Summary Scorecard

| Category | Items | On Track | Ahead | Behind | Not Started | Diverged |
|----------|-------|----------|-------|--------|-------------|----------|
| Document Intake (FR-1xx) | 5 | 3 | 0 | 2 | 0 | 0 |
| Processing (FR-2xx) | 5 | 4 | 0 | 0 | 0 | 1 partial |
| Entity Resolution (FR-3xx) | 5 | 4 | 0 | 1 | 0 | 0 |
| Workspace (FR-4xx) | 2 | 1 | 0 | 0 | 1 | 0 |
| Relationship Graph (FR-5xx) | 7 | 0 | 0 | 0 | 7 | 0 |
| Signal Detection (FR-6xx) | 5 | 4 | 0 | 0 | 0 | 1 partial |
| Findings (FR-7xx) | 5 | 4 | 1 | 0 | 1 | 0 |
| Memo Generation (FR-8xx) | 5 | 0 | 0 | 2 | 3 | 0 |
| **Totals** | **39** | **20** | **1** | **5** | **12** | **2 partial** |

**Bottom line:** 20 of 39 functional requirements are on track. 12 are not started (7 of those are the relationship graph). The project is strongest on the backend pipeline and weakest on the frontend and memo generation.
