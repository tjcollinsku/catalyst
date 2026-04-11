# CATALYST

Intelligence Triage Platform

*Pre-Investigative Whistleblower Software*

| Document ID | CAT-CHARTER-003 |
|:------------|:----------------|
| **Version** | 3.0 |
| **Classification** | **CONFIDENTIAL** |
| **Author** | Tyler Collins |
| **Date** | April 1, 2026 |
| **Status** | **ACTIVE DEVELOPMENT** |
| **Supersedes** | CAT-CHARTER-002 v2.1 (March 26, 2026) |

*"The most dangerous feature is the one that removes human judgment."*

> **Note (April 2026):** This charter predates the Session 32 product reframe.
> Key changes since v3 was written: the Signal/Detection/Finding three-table
> pipeline was collapsed into a single Finding model (22 models, down from 27);
> signal rules were cut from 29 to 14; AI-generated referral memo (Milestone 3)
> was replaced by a deterministic, citation-bearing PDF exporter; the
> GovernmentReferral and SocialMediaConnection models were removed; deployment
> moved from IBM Cloud to Railway. See [STATUS.md](../../STATUS.md) for the
> current state of every subsystem.

## Document Control

| Version | Date | Author | Summary of Changes |
|---------|------|--------|-------------------|
| 1.0 | 2026-03-19 | Tyler Collins | Initial charter and system design specification |
| 2.0 | 2026-03-24 | Tyler Collins | Elevated relationship graph; added signal detection rules; expanded findings; added connectors; refined AI spec |
| 2.1 | 2026-03-26 | Tyler Collins | Updated to reflect Phase 1 baseline implementation |
| 3.0 | 2026-04-01 | Tyler Collins | Major revision: locked monolith architecture, updated schema to 21 models, introduced scope boundary and Definition of Done, revised roadmap with session-based milestones, moved AI integration into main roadmap, descoped relationship graph and mobile from V1, added security infrastructure documentation |

---

## 1. Executive Summary

Catalyst is a proprietary Intelligence Triage Platform designed to transform the manual, disorganized process of public records investigation into a structured, repeatable, and professionally documented workflow. It is not an accusation engine. It is a case management tool that helps a human investigator organize publicly available documents, identify relationships between entities, detect anomalous patterns across records, and generate professional referral memos when findings warrant formal review by state or federal authorities.

The platform was born from a real investigation. In early 2026, the developer identified financial anomalies in the operations of a nonprofit organization operating in a small Ohio town. Findings were substantial enough to warrant formal referrals to the Ohio Attorney General Charitable Law Section (Reference ), the IRS (Form 13909), the FBI (IC3 and Cincinnati Field Office), and the Example Lender Administration Office of Inspector General (Case ).

Catalyst solves the organizational problems exposed by that investigation: a secure intake pipeline with cryptographic integrity verification, automated text extraction with original file preservation, a relational database for cross-document entity resolution, a signal detection engine that flags anomalous patterns automatically, and a memo generation system that produces professional, citation-backed referral documents.

### 1.1 What Changed from V2

Charter v3 reflects the project as it actually exists after 21 development sessions, not as originally imagined. Key changes:

- **Architecture locked as monolith.** The microservices aspiration from v2 is removed. The Django monolith with logical module separation is the correct architecture for this project. See AD-001 in design-decisions.md.
- **Database schema expanded.** 22 models (consolidated from 27 — Signal, Detection, GovernmentReferral, SocialMediaConnection removed; Finding, FindingEntity, FindingDocument added). See note above.
- **Connectors complete.** 6 of 7 planned connectors are built and tested (555+ tests). Only Ohio UCC remains.
- **Security infrastructure added.** CSRF, rate limiting, PDF validation, URL domain allowlists, extraction status tracking — none of this was in v2.
- **Relationship graph descoped from V1.** The graph (FR-501 through FR-507) is deferred to V2. The data model supports it, but building a graph visualization is a multi-session effort that would delay the demo-ready release.
- **AI features moved into main roadmap.** V2 placed AI in Phase 5 (post-certificate). V3 brings Claude/OpenAI API integration into the release roadmap for memo generation and entity extraction enhancement.
- **Mobile/tablet descoped.** This is a desktop investigation tool. Responsive design is a V2 concern.
- **Scope boundary defined.** See Section 10.

---

## 2. Problem Statement

*Unchanged from v2.* The investigation gap and lessons from the Example Charity Inc. investigation remain the foundational motivation. See charter v2 Section 2 for the full problem statement.

---

## 3. Functional Requirements

### 3.1 Document Intake (FR-101 through FR-105)

*Unchanged from v2.* All five requirements are implemented or in progress.

### 3.2 Document Processing (FR-201 through FR-205)

*Unchanged from v2.* All five requirements are implemented.

### 3.3 Entity Resolution (FR-301 through FR-305)

*Unchanged from v2.* Four of five requirements are implemented. FR-304 (fuzzy match review UI) is deferred to the frontend completion milestone.

### 3.4 Investigation Workspace (FR-401 through FR-402)

*Unchanged from v2.* FR-401 (case containers) is implemented. FR-402 (timeline view) is deferred to V2.

### 3.5 Relationship Graph (FR-501 through FR-507) — DEFERRED TO V2

The relationship graph remains a valuable analytical tool, but it is not required for the V1 demo-ready release. The data model already supports entity relationships (PersonOrganization, PropertyTransaction, EntitySignal). Building the interactive graph visualization (React-Flow or D3, filtering, export) is estimated at 3-5 sessions and would delay the core Golden Path.

All seven FR-5xx requirements are deferred to V2.

### 3.6 Signal Detection (FR-601 through FR-605)

*Updated from v2, then cut in Session 32.* The signal engine now implements 14 rules (cut from 29 — only rules grounded in the founding investigation were retained). The additional types listed below from v3 were partially merged or cut:

| Rule ID | Severity | Description | Source |
|---------|----------|-------------|--------|
| SR-011 | HIGH | Revenue anomaly — total revenue changes by more than 50% year-over-year | IRS connector financial analysis |
| SR-012 | MEDIUM | Phantom officer — named in 990 but not in SOS filings | Cross-connector analysis |
| SR-013 | MEDIUM | Name reconciliation — entity name differs across data sources | Entity resolution pipeline |
| SR-014 | HIGH | Timeline compression — entity formation and major transaction within unusual proximity | Ohio SOS + recorder analysis |
| SR-015 | MEDIUM | Charter conflict — entity actions inconsistent with stated mission/purpose | 990 analysis |
| SR-016 | MEDIUM | Address nexus — multiple unrelated entities sharing the same address | Cross-entity analysis |

FR-605 (extensible rules without redeployment) is partially met — rules are extensible by adding Python functions, but require code changes rather than configuration.

### 3.7 Findings Management (FR-701 through FR-705)

*Updated from v2.* FR-701 through FR-704 are implemented. FR-705 (Patterns linking multiple Findings) is deferred to V2.

**Update (Session 32–33):** The Detection model and Signal model were removed. The three-table pipeline (Signal → Detection → Finding) was collapsed into a single Finding model with two dimensions: `status` (NEW / NEEDS_EVIDENCE / DISMISSED / CONFIRMED) and `evidence_weight` (SPECULATIVE / DIRECTIONAL / DOCUMENTED / TRACED).

### 3.8 Referral Memo Generation (FR-801 through FR-805)

*Updated from v2.* This is the primary gap in the current build.

**V1 target:**
- FR-801: AI-powered memo generation via Claude/OpenAI API. The system provides structured case data (findings, entity profiles, signal summaries, document citations) to an LLM, which generates a professional narrative. Human review and editing required before finalization.
- FR-802: Memo includes findings with citations, entity profiles, and signal summary. Timeline and graph exports deferred to V2.
- FR-805: SHA-256 hash table included in memo output for chain of custody.

**Deferred to V2:**
- FR-803: ORC and federal statute cross-references (requires a statute database)
- FR-804: Agency-specific templates (Ohio AG, IRS, FBI, FCA IG)

---

## 4. Non-Functional Requirements

### 4.1 Security

| ID | Requirement | Status |
|----|------------|--------|
| NFR-01 | Encryption at rest and TLS 1.3 in transit | Deferred to deployment (IBM Cloud handles TLS) |
| NFR-02 | Secrets in environment variables | Implemented |
| NFR-03 | Private repository | Implemented |
| NFR-04 | User authentication | Deferred to V2 — see SD-002 in design-decisions.md |
| NFR-05 | Private by Design | Implemented — connectors only fetch public data |

**Added security infrastructure (not in v2):**
- CSRF protection (cookie + header pattern)
- Sliding-window rate limiting (200 reads/min, 30 writes/min per IP)
- PDF magic bytes validation
- URL domain allowlists on connector responses
- Chunked downloads with size caps and deadlines
- Path traversal prevention
- ExtractionStatus pipeline tracking
- Constrained AuditAction types

### 4.2 Scalability

| ID | Requirement | V3 Status |
|----|------------|-----------|
| NFR-06 | Mobile/tablet/desktop responsive | **Removed from V1.** Desktop-only. This is an investigation workstation, not a mobile app. |
| NFR-07 | Horizontal scaling via microservices | **Removed.** Monolith architecture is the permanent plan. See AD-001. |
| NFR-08 | Concurrent cases | Supported in single-user mode. Multi-user deferred to V2. |

### 4.3 Data Integrity

| ID | Requirement | Status |
|----|------------|--------|
| NFR-09 | Write-once document store | Partial — files preserved but mutable storage. MinIO/S3 is a V2 hardening step. |
| NFR-10 | Entity modifications logged | Implemented via AuditLog |
| NFR-11 | Append-only audit trail | Implemented — admin write permissions disabled |
| NFR-12 | SHA-256 verified before memo reference | To be implemented in memo generation milestone |

---

## 5. System Architecture

### 5.1 Architecture Decision: Django Monolith

Catalyst is a Django monolith. This is an intentional, permanent architectural decision — not a temporary state.

The codebase is organized into logical modules (connectors, extraction pipeline, signal engine, API layer) that maintain clear boundaries. This gives the benefits of modular design (testability, separation of concerns, independent development) without the operational complexity of microservices (service discovery, inter-service auth, distributed tracing, separate deployments).

```
React SPA (Vite + TypeScript)
        │
        │ HTTP / JSON API
        ▼
Django Backend (single process)
├── API Layer (views.py, serializers.py, urls.py)
├── Middleware (CSRF, rate limiting)
├── Processing Pipeline (extraction → classification → entities → signals)
├── External Connectors (ProPublica, IRS, Ohio SOS, County Auditor/Recorder, AOS)
├── Signal Engine (16 rules, evaluate + persist)
└── Models (21 Django ORM models)
        │
        ▼
PostgreSQL 16
```

### 5.2 Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Backend | Django 5.x, Python 3.11+ | No DRF — custom JSON serialization |
| Frontend | React 18, TypeScript, Vite | Shell + Views architecture, React Router v6 |
| Database | PostgreSQL 16 | Docker container for local dev |
| OCR | Tesseract + Pillow | Fallback for scanned PDFs |
| PDF Extraction | PyMuPDF (fitz) | Direct text extraction |
| AI Integration | Claude API or OpenAI API | Memo generation, entity extraction enhancement |
| Deployment | IBM Cloud (pay-as-you-go) | Docker containerized |
| Version Control | Git + GitHub | Private repository |

### 5.3 Data Source Connectors

| Connector | Source | Status | Tests |
|-----------|--------|--------|-------|
| ProPublica | ProPublica Nonprofit Explorer API | Complete | 29 |
| IRS | IRS Pub78 + EO BMF bulk files | Complete | 104 |
| Ohio SOS | Ohio SOS monthly CSV exports | Complete | 59 |
| County Auditor | ODNR ArcGIS API + portal URLs | Complete | 126 |
| County Recorder | 88 county portal URLs + document parser | Complete | 191 |
| Ohio AOS | Ohio Auditor of State HTML scraper | Complete | 46 |
| Ohio UCC | Ohio SOS UCC search | Not started | — |
| PACER | Federal court records | Deferred to V2 | — |

---

## 6. Database Schema

22 Django ORM models (consolidated from 27 in Session 33). Full model documentation in CLAUDE.md.

### Core Models
Case, Document, Person, Organization, Property, FinancialInstrument

### Analysis Models
Finding (consolidated — replaces Signal + Detection + old Finding), FinancialSnapshot

### Linking Models
PersonDocument, OrgDocument, PersonOrganization, PropertyTransaction, FindingEntity, FindingDocument

### Operational Models
AuditLog, InvestigatorNote

### Key Design Choices
- UUID primary keys everywhere (except GovernmentReferral — sequential for human readability)
- RESTRICT on all Case foreign keys (prevents accidental cascade deletion)
- GeneratedField for Property.valuation_delta
- Separate OcrStatus and ExtractionStatus enums
- Append-only AuditLog with immutable filing dates on GovernmentReferral

---

## 7. Security Design

### 7.1 Core Principles

*Unchanged from v2:* Least Privilege, Defense in Depth, Immutable Evidence, Audit Everything, Secrets Management, Anonymous Operation Support.

### 7.2 Implemented Security Controls

| Control | Description |
|---------|-------------|
| SHA-256 chain of custody | Hash on original bytes before any processing |
| CSRF protection | Cookie + X-CSRFToken header for SPA |
| Rate limiting | Sliding-window per-IP (configurable via env vars) |
| PDF validation | Magic bytes check before processing |
| URL allowlists | Domain validation on all external connector URLs |
| Download protection | Chunked downloads with size caps and deadline timeouts |
| Path traversal prevention | Filename sanitization on uploads |
| Audit logging | All data changes tracked with before/after state |
| Extraction tracking | Per-document pipeline success/failure status |

### 7.3 Authentication

Deferred to V2. The frontend is designed for multi-user from the start (user context provider, role labels in the shell). Auth can be added without restructuring. CSRF is implemented as defense-in-depth for when token auth is disabled in dev mode.

---

## 8. The Catalyst Principle

**The human investigator is always the decision-maker.**

*Catalyst organizes, structures, and presents. It never accuses, concludes, or acts autonomously.*

***The most dangerous feature is the one that removes human judgment.***

This principle governs every design decision:
- Signals require investigator confirmation before becoming Findings
- Findings require investigator narrative before appearing in memos
- AI-generated content requires human review and editing before finalization
- Fuzzy entity matches are surfaced, never auto-merged
- Connector results are presented for review, never auto-imported
- Memos cite sources and describe patterns — they do not assert guilt

---

## 9. SDLC Roadmap

Development follows a milestone-based approach organized around the Golden Path — the critical user flow that must work flawlessly for demo and real-world use:

```
Upload PDF → SHA-256 hash → OCR/extract text → Entities identified
    → Signals fire → Investigator reviews → Creates findings
        → AI generates referral memo → Human reviews/edits → Export
```

### Milestone 1: Frontend Compilation (1-2 sessions)
- Fix 4 truncated files (types.ts, CaseDetailView.tsx, DocumentsTab.tsx, PdfViewer.tsx)
- Add missing fetchDocumentDetail() API function
- Verify all views render correctly
- **Gate:** `npm run build` succeeds with zero errors

### Milestone 2: Golden Path Wiring (3-5 sessions)
- Upload flow works end-to-end in the UI (drag-and-drop → progress → document appears)
- Signal triage view connected and functional
- Detection → Finding workflow works in UI
- Activity feed shows pipeline events
- **Gate:** Demo the full path from upload to finding creation

### Milestone 3: AI Memo Generation (2-3 sessions)
- Claude/OpenAI API integration for memo narrative generation
- Structured case data (findings, entities, signals, document citations) passed to LLM
- Human review/edit interface for generated memo
- PDF or DOCX export with SHA-256 hash table
- **Gate:** Generate a professional-quality memo from a real case

### Milestone 4: Polish and Deploy (2-3 sessions)
- Loading states, error handling, empty states across all views
- Professional visual polish
- Docker containerization for IBM Cloud
- PostgreSQL provisioning on IBM Cloud
- Static file serving configuration
- **Gate:** Deployed and accessible via URL

### Milestone 5: GitHub and Documentation (1-2 sessions)
- Clean README with screenshots, architecture diagram, setup instructions
- Conventional commit discipline going forward
- License file
- Contributing guide (for portfolio presentation)
- **Gate:** An employer clicking the repo link sees a professional project

### V2 Backlog (Post-V1 Release)
- Relationship graph visualization (FR-501 through FR-507)
- Timeline view (FR-402)
- Pattern linking for Findings (FR-705)
- Agency-specific memo templates (FR-804)
- ORC/statute cross-references (FR-803)
- User authentication and RBAC
- Ohio UCC connector
- Mobile/responsive design
- Write-once document store (MinIO/S3)
- Multi-user support

---

## 10. Scope Boundary

**If it is not on the roadmap, it does not get built.**

This is the most important governance rule in v3. The project drifted from v2 because there was no mechanism to say "that's out of scope." The following rules apply:

1. **No new features** are added until the current milestone is complete and the roadmap is consciously updated.
2. **Scope changes** require updating this charter, the roadmap, and CURRENT_STATE.md before any code is written.
3. **Tech debt** is tracked in docs/governance/tech-debt-register.md and prioritized during roadmap updates, not addressed ad-hoc.
4. **Session discipline:** Every session starts by reading CURRENT_STATE.md and ends by updating it.

---

## 11. Portfolio and Professional Value

*Updated from v2.* Catalyst demonstrates:

- **Real-world problem domain** with verifiable outcomes (5 agency referrals)
- **Complete SDLC documentation** (charter, architecture, design decisions, security audit, roadmap)
- **Modern full-stack skills** (React, Django, PostgreSQL, Docker, AI API integration)
- **Security-conscious design** (SHA-256 chain of custody, audit logging, rate limiting, CSRF)
- **AI integration** (LLM-powered memo generation with human-in-the-loop)
- **Comprehensive testing** (555+ backend tests across 6 test files)
- **Data engineering** (6 external data connectors, 3-stage entity resolution pipeline)
- **Ethical engineering** (The Catalyst Principle — human judgment at every decision point)

For investigator/developer hybrid roles specifically, Catalyst demonstrates the ability to both build investigation tools AND use domain knowledge to design systems that reflect how real investigations work.
