

**CATALYST**

Intelligence Triage Platform

*Pre-Investigative Whistleblower Software*

| Document ID | CAT-CHARTER-002 |
| :---- | :---- |
| **Version** | 2.0 |
| **Classification** | **CONFIDENTIAL** |
| **Author** | Tyler Collins |
| **Date** | March 24, 2026 |
| **Status** | **ACTIVE DEVELOPMENT** |
| **Supersedes** | CAT-CHARTER-001 v1.0 (March 19, 2026\) |

*"The most dangerous feature is the one that removes human judgment."*

# **Document Control**

| Version | Date | Author | Summary of Changes |
| ----- | ----- | ----- | ----- |
| 1.0 | 2026-03-19 | Tyler Collins | Initial charter and system design specification |
| 2.0 | 2026-03-24 | Tyler Collins | Elevated relationship graph to core subsystem; added Section 3.6 Signal Detection with enumerated rules SR-001 through SR-010; expanded findings table schema; added Section 5.3 Data Source Connectors; refined Phase 5 AI specification; strengthened security design; added Catalyst Principle as governing design philosophy |
| 2.1 | 2026-03-26 | Tyler Collins | Updated charter to reflect implemented Phase 1 baseline: Django-native case/document JSON API, pagination/filter/sort contract, PATCH and DELETE operations, strict SHA-256 validation, API documentation, and current monolithic deployment posture |

# **1\. Executive Summary**

Catalyst is a proprietary Intelligence Triage Platform designed to transform the manual, disorganized process of public records investigation into a structured, repeatable, and professionally documented workflow. It is not an accusation engine. It is a case management tool that helps a human investigator organize publicly available documents, identify relationships between entities, detect anomalous patterns across records, and generate professional referral memos when findings warrant formal review by state or federal authorities.

The platform was born from a real investigation. In early 2026, the developer identified financial anomalies in the operations of a nonprofit organization operating in a small Ohio town. Over several intensive days of manual document review across county recorder systems, Ohio Secretary of State filings, IRS Form 990 returns, UCC financing statements, building permit records, and county auditor parcel databases, a significant and interconnected pattern of irregularities was uncovered. Findings included:

* A UCC financing statement bearing the typed signature of an individual who had died 153 days before the filing date, submitted electronically through the Ohio Secretary of State portal — constituting wire fraud under 18 U.S.C. § 1343 and identity fraud under 18 U.S.C. § 1028

* $4,505,000 in commercial construction permits on property owned by a private LLC controlled by the nonprofit's sole officer — with no competitive bidding, no independent board oversight, and no Schedule L disclosure across seven consecutive IRS Form 990 filings

* A series of zero-consideration real estate transfers between related parties — including a $700,000 net benefit to a single family — prepared repeatedly by the same attorney with an explicit "without benefit of title search" disclaimer

* A charity operating as the dominant economic actor in a small village — generating 94% of all nonprofit revenue — while the statutory community improvement corporation sat dormant for eight consecutive years with zero reported assets, revenue, or expenses

* Five UCC financing statement amendments adding family members to a blanket agricultural lien within a 12-minute window on August 2, 2022, correlated with a major charitable asset transfer six weeks later

These findings were substantial enough to warrant formal referrals to the Ohio Attorney General Charitable Law Section (Reference \#113628), the IRS (Form 13909), the FBI (IC3 and Cincinnati Field Office), and the Farm Credit Administration Office of Inspector General (Case \#OIGC-394T2MR8). However, the investigation process itself was organizationally fragile: files accumulated across directories with no naming convention, Python extraction scripts were written ad-hoc, and extracted data had no relational structure linking entities across document types.

Catalyst solves this problem permanently. It provides the structured environment that was missing: a secure intake pipeline with cryptographic integrity verification, automated text extraction with original file preservation, a relational database for cross-document entity resolution, a signal detection engine that flags anomalous patterns automatically, and a memo generation system that produces professional, citation-backed referral documents formatted for specific agencies.

# **2\. Problem Statement**

## **2.1 The Investigation Gap**

Public records investigations involving nonprofit organizations, property transactions, and financial instruments require an investigator to synthesize information across dozens of documents from multiple jurisdictions and source systems. County auditor records, Secretary of State filings, IRS 990 returns, property deeds, UCC filings, building permit records, and state audit reports each contain fragments of a larger picture. The investigator must manually identify connections between people, organizations, properties, and financial transactions — connections that become meaningful only when viewed across the full document set.

No affordable, purpose-built tool exists for citizen investigators, small nonprofit watchdog organizations, or individual whistleblowers to manage this workflow. Current options fall into two categories: expensive enterprise forensic suites designed for law enforcement that are out of reach for individuals, or general-purpose tools like spreadsheets and file folders that are insufficient for the complexity of entity resolution across document types, jurisdictions, and time periods.

## **2.2 Lessons from the Do Good Inc. Investigation**

The founding investigation exposed specific, documentable pain points that directly drove Catalyst's requirements:

**File Disorganization.**

Source documents — PDFs, screenshots, downloaded records — were saved in ad-hoc folder structures with no consistent naming convention. Locating a specific document required searching through multiple directories. Critical evidence was nearly lost in manual folder chaos.

**Script Sprawl.**

Python scripts for data extraction were written on the fly and stored in the same directories as source files, with no version control, no documentation, and no separation of tools from data. Scripts that produced critical analytical output could not be reliably reproduced.

**Data Fragmentation.**

Extracted data landed in CSV files with no relational linkage. Connecting a person from a UCC filing to the same person on a property deed to the same person in a 990 filing required manual cross-referencing across multiple files. The Brenda Mescher / Farm Credit connection — a Farm Credit loan officer with the same surname as parties in a related property exchange — was identified only by recognizing a name across disparate documents read hours apart.

**No Systematic Audit Trail.**

There was no systematic record of when documents were acquired, what was extracted from them, or how conclusions were reached. This creates risk in any formal proceeding where the provenance of evidence must be demonstrated.

**No Integrity Verification.**

Original documents were not hashed at intake, meaning there was no cryptographic proof that source materials had not been altered between collection and referral. Any serious investigation requires demonstrable chain of custody.

**Manual Pattern Recognition.**

The most analytically significant finding in the founding investigation — five UCC amendments filed to the same master financing statement within a 12-minute window on August 2, 2022, correlated with a major property transfer six weeks later — was identified only because a human investigator happened to read the timestamps carefully. A systematic signal detection layer would have flagged this automatically on intake. The same applies to the August 2023 survey date on land not acquired until January 2024, the LLC formation date falling 721 days after the deed that named it as a grantee, and the deceased person's signature on a March 2026 electronic filing.

Despite these limitations, the investigation produced findings significant enough for formal referrals to five separate agencies. Catalyst exists to ensure the next investigation is conducted with professional-grade organization and systematic signal detection from day one.

# **3\. Functional Requirements**

## **3.1 Document Intake**

1. FR-101: The system shall accept PDF file uploads via drag-and-drop interface.

2. FR-102: Upon upload, the system shall store the original file in an immutable document store without modification.

3. FR-103: Upon upload, the system shall compute and store a SHA-256 hash of the original file for integrity verification.

4. FR-104: The system shall record metadata for each uploaded document: filename, upload timestamp, file size, hash value, source type, source URL, and user-assigned case.

5. FR-105: The system shall support bulk upload of multiple files assigned to a single case in a single operation.

## **3.2 Document Processing**

6. FR-201: The system shall extract text from digital PDF files using text extraction libraries.

7. FR-202: The system shall extract text from scanned PDF files using OCR (Optical Character Recognition).

8. FR-203: The system shall classify documents by type: property deed, UCC filing, IRS 990, county auditor record, building permit, state audit report, corporate filing, obituary, or other (user-defined).

9. FR-204: The system shall parse extracted text into structured fields based on document type templates.

10. FR-205: The system shall identify and extract dates, dollar amounts, personal names, organization names, parcel numbers, and filing reference numbers from document text.

## **3.3 Entity Resolution**

11. FR-301: The system shall maintain a relational database of entities: Persons, Organizations, Properties, Financial Instruments, and Government Actions.

12. FR-302: The system shall link entities to their source documents with page-level and section-level citation tracking.

13. FR-303: The system shall detect and flag potential entity matches across documents — for example, the same individual appearing in a UCC filing, a property deed, and a 990 filing under the same or similar name.

14. FR-304: The system shall allow the user to confirm, reject, or merge entity matches.

15. FR-305: The system shall track deceased status for persons, including date of death, and flag any document signed or filed by that person after their recorded date of death.

## **3.4 Investigation Workspace**

16. FR-401: The system shall organize all work within Case containers that group related documents, entities, findings, and signals.

17. FR-402: The system shall provide a timeline view showing all events in chronological order across all documents in a case, with the ability to filter by entity, document type, or date range.

## **3.5 Relationship Graph**

The relationship graph is the analytical core of Catalyst. It is elevated in this version from a line item to a primary subsystem, reflecting its demonstrated importance in the founding investigation. The Homan/Baumer/Winner/Guillozet network — involving a nonprofit, a private LLC, a construction contractor, a law firm, a family farm lender, a veterans center, and a meat processor — was not visible as a coherent network until documents from five separate jurisdictions were synthesized. The graph makes this synthesis automatic.

18. FR-501: The system shall provide an interactive relationship graph showing connections between all entities in a case.

19. FR-502: Node types shall include: Person, Organization (Nonprofit), Organization (LLC/Corp), Organization (Government), Property, Financial Instrument, and Government Action.

20. FR-503: Edge types shall include: OFFICER\_OF, ATTORNEY\_FOR, GRANTOR\_IN, GRANTEE\_IN, DEBTOR\_ON, SECURED\_PARTY\_ON, PERMIT\_APPLICANT, CONTRACTOR\_ON, INCORPORATOR\_OF, SURVEYOR\_FOR, and FAMILY\_MEMBER\_OF.

21. FR-504: The graph shall support filtering by node type, edge type, date range, and signal status.

22. FR-505: The graph shall visually distinguish nodes that carry active signal flags — for example, a person with DECEASED\_SIGNER status shall render with a distinct visual indicator.

23. FR-506: The graph shall support export to PNG and to a structured JSON format for use in referral memos.

24. FR-507: The system shall allow the investigator to annotate edges with source document citations.

## **3.6 Signal Detection**

Signal detection is the automated pattern recognition layer. The system evaluates documents and entity relationships against a defined rule set and flags anomalies for investigator review. Signals are not conclusions — they are structured prompts for human judgment. Every signal can be confirmed, dismissed, or escalated to a Finding by the investigator.

The following signal rules are derived directly from patterns identified in the founding investigation. Each rule has a severity level (CRITICAL, HIGH, MEDIUM, LOW) and a source citation requirement.

| Rule ID | Severity | Description | Founding Case Pattern |
| ----- | ----- | ----- | ----- |
| SR-001 | **CRITICAL** | Document signed or electronically filed by an individual whose recorded date of death precedes the filing date. | Homan AG Mgmt LLP, filed 153 days post-mortem |
| SR-002 | **CRITICAL** | Entity named as grantee or party in a document predates the entity's formation date as recorded with the Secretary of State. | Do Good RE LLC deed Sept 2017; LLC formed Aug 2019 |
| SR-003 | **HIGH** | Purchase price deviates more than 50% from county-assessed value, in either direction. | $300K paid for $37,490 appraised property |
| SR-004 | **HIGH** | Three or more UCC amendments to the same master financing statement file number occur within a 24-hour window. | 5 amendments in 12 minutes, Aug 2 2022 |
| SR-005 | **HIGH** | Zero-consideration transfer between parties who share a common officer, attorney, or family relationship in other documents in the case. | Winner deed ($0), Veterans Center deed ($0) |
| SR-006 | **HIGH** | IRS Form 990 Part IV Line 28a, 28b, or 28c answered Yes with no corresponding Schedule L present in the filing. | 2018-2024 990 filings, 7 consecutive years |
| SR-007 | **HIGH** | Building permit applicant differs from the recorded owner of the parcel on which construction is permitted. | Do Good Ministries permits on LLC-owned land |
| SR-008 | **MEDIUM** | Survey or plat recorded for a property more than 90 days before the recorded purchase date for the same parcel. | Mescher survey Aug 2023; Bohman purchase Jan 2024 |
| SR-009 | **MEDIUM** | Single contractor named on 100% of permits for a given applicant across multiple years with no evidence of competitive bidding. | Baumer Construction on all 5 Do Good permits 2018-2025 |
| SR-010 | **MEDIUM** | Tax-exempt organization has not filed a required Form 990 for one or more years in which it held tax-exempt status. | Veterans Center: no 990 filed, tax-exempt since July 2023 |

25. FR-601: The system shall evaluate all uploaded documents and entities against the signal rule set upon intake completion.

26. FR-602: Each triggered signal shall record: rule ID, severity, triggering entity or document, supporting source citations, timestamp of detection, and current status (OPEN, CONFIRMED, DISMISSED, ESCALATED).

27. FR-603: The investigator shall be able to confirm a signal (elevating it to a Finding), dismiss it with a note, or escalate it to a CRITICAL flag visible in the case dashboard.

28. FR-604: Dismissed signals shall be retained in the audit log with the investigator's dismissal rationale.

29. FR-605: The signal rule set shall be extensible — new rules can be added by the system administrator without requiring application redeployment.

## **3.7 Findings Management**

A Finding is the core unit of investigative output. It is a structured, citation-backed observation that links specific entities and documents to a pattern of concern, with the investigator's analytical narrative and applicable legal references. Findings become the substance of referral memos.

30. FR-701: The system shall allow the investigator to create Findings that link one or more entities, one or more documents with page citations, a signal rule (if applicable), investigator narrative, applicable ORC or federal statute references, a severity rating, a confidence level, and a current status.

31. FR-702: Findings shall support the following severity ratings: CRITICAL, HIGH, MEDIUM, LOW, and INFORMATIONAL.

32. FR-703: Findings shall support the following confidence levels: CONFIRMED (documented in official records), PROBABLE (strong inferential basis), POSSIBLE (suggestive but requiring further investigation).

33. FR-704: Finding status values shall include: DRAFT, REVIEWED, INCLUDED\_IN\_MEMO, EXCLUDED, and REFERRED.

34. FR-705: The investigator shall be able to link multiple Findings to form a Pattern — a named, higher-order observation connecting related findings across entities and time periods.

## **3.8 Referral Memo Generation**

35. FR-801: The system shall generate standardized PDF referral memos from case findings.

36. FR-802: Each memo shall include: executive summary, findings with source citations, entity profiles, timeline of relevant events, relationship graph export, signal detection summary, and document integrity verification (SHA-256 hash values).

37. FR-803: The memo generator shall cross-reference findings with relevant Ohio Revised Code sections and applicable federal statutes (18 U.S.C. § 1341, § 1343, § 1028; 26 U.S.C. § 4941, § 4958; 12 CFR Part 612).

38. FR-804: The system shall support agency-specific memo templates: Ohio AG Charitable Law, IRS Form 13909 supplement, FBI white collar crime referral, and Farm Credit Administration IG.

39. FR-805: All source documents cited in a memo shall be verifiable against their stored SHA-256 hash values, providing cryptographic chain of custody.

# **4\. Non-Functional Requirements**

## **4.1 Security**

40. NFR-01: All data at rest shall be encrypted. All data in transit shall use TLS 1.3.

41. NFR-02: Sensitive identifiers, credentials, and API keys shall be stored in environment variables, never in source code or version control.

42. NFR-03: The source code repository shall be private. Catalyst is not open-source software.

43. NFR-04: User authentication shall be required for all system access.

44. NFR-05: The system shall implement a "Private by Design" philosophy — no case data, entity data, or document content shall be transmitted to external services except through explicitly configured, user-authorized integrations.

## **4.2 Scalability and Accessibility**

45. NFR-06: The application shall be fully functional on desktop, tablet, and mobile browsers.

46. NFR-07: The architecture shall support horizontal scaling via containerized microservices.

47. NFR-08: The system shall support concurrent cases without performance degradation.

## **4.3 Data Integrity**

48. NFR-09: Original uploaded documents shall never be modified after intake. The file store is write-once.

49. NFR-10: All entity modifications shall be logged with timestamp and user attribution.

50. NFR-11: The system shall maintain a complete, append-only audit trail of all investigator actions.

51. NFR-12: SHA-256 hashes shall be verified against stored values before any document is referenced in a generated memo.

# **5\. System Architecture**

## **5.1 Architecture Overview**

Catalyst's target architecture remains a containerized microservices platform, but the current implementation baseline is intentionally a Django-first modular monolith backed by PostgreSQL. This gives Phase 1 a working case/document system with lower operational complexity while preserving clear subsystem boundaries for later extraction into dedicated services. Docker remains part of the development environment today; Kubernetes and service decomposition remain planned hardening and scale steps rather than present-state infrastructure.

As of March 26, 2026, the implemented backend provides a Django-native JSON API for case and document management, including collection and detail endpoints, PATCH and DELETE support, pagination, allowlisted filtering/sorting, and strict SHA-256 validation on document intake. This is sufficient for a usable investigative intake foundation and accurately reflects the repository's current state.

| Service | Responsibility | Technology | IBM Course |
| ----- | ----- | ----- | ----- |
| **API / Gateway Layer** | Current Django-native JSON API for cases and documents; future request routing, authentication, and rate limiting boundary | Django | Course 9 |
| **Frontend** | Responsive PWA, graph visualization, case dashboard | React | Course 5 |
| **Intake Module** | Case/document intake, metadata capture, SHA-256 validation, upload workflow | Python / Django | Course 9 |
| **Processing Service** | OCR, text extraction, document classification, field parsing | Python / Tesseract / PyPDF | Course 9 |
| **Entity Service** | Entity CRUD, cross-document matching, relationship management | Python / Django ORM | Course 9 |
| **Signal Service** | Pattern detection rule engine, anomaly flagging, signal lifecycle | Python / Rules Engine | Course 11 |
| **Graph Service** | Entity relationship graph, network analysis, graph export | Python / NetworkX / React-Flow | Course 5 / 11 |
| **Memo Service** | PDF referral memo generation, ORC cross-reference, hash verification | Python / ReportLab | Course 11 |
| **Database** | Relational data store for all case, entity, and signal data | PostgreSQL | Course 9 |
| **File Store** | Immutable, write-once document storage with hash verification | Django media storage now; MinIO (S3-compatible) target | Course 10 |

## **5.1.1 Current Implemented API Baseline**

The current backend implementation covers the minimum viable investigative intake layer and already supports the following workflows:

* Case collection endpoint: create, list, paginate, filter by status/text/date, and sort using allowlisted fields

* Case detail endpoint: retrieve, update selected fields, and delete with conflict protection when related records exist

* Case-scoped document collection endpoint: create, list, paginate, filter by document metadata/date, and sort using allowlisted fields

* Case-scoped document detail endpoint: retrieve, update selected metadata fields, and delete

* Serializer-based validation without Django REST Framework, including strict SHA-256 format validation on document intake

* Repository documentation for the live API contract and usage examples

## **5.2 Data Source Connectors**

The data source connector layer is Catalyst's primary competitive advantage over general-purpose tools. The founding investigation required navigating eight separate public data systems manually — each with a different interface, search logic, and download format. Connectors eliminate this friction and make systematic multi-jurisdiction investigation tractable for a single investigator.

Phase 1 connectors (planned for Phases 2-3):

| Data Source | Data Type | Access Method | Phase |
| ----- | ----- | ----- | ----- |
| ProPublica Nonprofit Explorer | IRS Form 990 filings, financial data | Public REST API (documented, free) | Phase 2 |
| IRS Tax Exempt Org Database | EIN lookup, exemption status, filing history | Public API / bulk data download | Phase 2 |
| Ohio SOS Business Search | Entity filings, incorporators, registered agents, status | Structured scraper | Phase 2 |
| Ohio UCC Search | Financing statements, amendments, continuations | Structured scraper | Phase 2 |
| LandmarkWeb (County Recorder) | Deeds, mortgages, instruments by grantor/grantee | Structured scraper (multi-county) | Phase 3 |
| County Auditor Parcel Systems | Parcel records, valuations, sales history, lender IDs | Structured scraper (per-county) | Phase 3 |
| Ohio Auditor of State | Public entity audit reports, findings for recovery | Structured scraper | Phase 3 |
| PACER (Federal Courts) | Federal civil and bankruptcy filings | PACER API (fee-based) | Phase 5 |

## **5.3 IBM Coursework Mapping**

Every major technology choice in Catalyst maps directly to a course in the IBM Full-Stack Software Developer Certificate program. This is not coincidental — the platform was designed to demonstrate complete, applied competency across the full curriculum.

| IBM Certificate Course | Catalyst Application |
| ----- | ----- |
| Course 5: React | Frontend UI, component architecture, state management, relationship graph visualization |
| Course 9: Django & Databases | ORM models, PostgreSQL schema design, REST API, document intake and processing pipelines |
| Course 10: Docker & Kubernetes | Service containerization, orchestration, deployment, file store (MinIO) |
| Course 11: Microservices | Service decomposition, API gateway, inter-service communication, signal service architecture |
| Course 12: Capstone | Full integration, end-to-end testing, CI/CD pipeline, complete SDLC documentation package |

# **6\. Database Schema**

## **6.1 Design Philosophy**

The database is designed around five core entity types identified during the founding investigation, plus supporting tables for signal detection, findings management, case orchestration, and audit logging. Every entity links back to its source documents with page-level citation resolution, enabling full traceability from a line in a referral memo back to a specific page in a specific document with a verified SHA-256 hash.

## **6.2 Core Tables**

### **cases**

| Column | Type | Description |
| ----- | ----- | ----- |
| id | UUID | Primary key |
| name | VARCHAR(255) | Case name (e.g., "Do Good Inc. Investigation") |
| status | ENUM | ACTIVE, PAUSED, REFERRED, CLOSED |
| created\_at | TIMESTAMP | Case creation date |
| notes | TEXT | Investigator case-level notes |
| referral\_ref | VARCHAR(100) | External referral IDs (e.g., AG \#113628, FCA \#OIGC-394T2MR8) |

### **documents**

| Column | Type | Description |
| ----- | ----- | ----- |
| id | UUID | Primary key |
| case\_id | UUID (FK) | Reference to parent case |
| filename | VARCHAR(255) | Original filename |
| sha256\_hash | CHAR(64) | SHA-256 hash computed at intake — never changes |
| doc\_type | ENUM | DEED, UCC, IRS\_990, AUDITOR, PERMIT, CORP\_FILING, OBITUARY, OTHER |
| source\_url | VARCHAR(500) | URL where document was obtained (if applicable) |
| extracted\_text | TEXT | Full extracted text content from OCR or direct extraction |
| ocr\_status | ENUM | PENDING, COMPLETED, FAILED, NOT\_NEEDED |

### **persons**

| Column | Type | Description |
| ----- | ----- | ----- |
| id | UUID | Primary key |
| full\_name | VARCHAR(255) | Full legal name as found in documents |
| aliases | TEXT\[\] | Alternative names/spellings found across documents |
| role\_tags | TEXT\[\] | BOARD\_MEMBER, SIGNER, OFFICER, DEBTOR, ATTORNEY, CONTRACTOR, DECEASED, etc. |
| date\_of\_death | DATE | Recorded date of death — triggers SR-001 on any subsequent filing |
| notes | TEXT | Investigator notes about this person |

### **findings**

The findings table is the primary output table of the investigation. Each finding represents a confirmed investigator observation backed by source citations and legal references, and becomes a paragraph in the referral memo.

| Column | Type | Description |
| ----- | ----- | ----- |
| id | UUID | Primary key |
| case\_id | UUID (FK) | Reference to parent case |
| title | VARCHAR(255) | Short descriptive title (e.g., "Deceased Signer — Homan AG Management LLP") |
| severity | ENUM | CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL |
| signal\_type | VARCHAR(50) | Category: VALUATION\_ANOMALY, DATE\_ANOMALY, DISCLOSURE\_OMISSION, CONCENTRATION\_FLAG, IDENTITY\_FRAUD, etc. |
| confidence | ENUM | CONFIRMED, PROBABLE, POSSIBLE |
| signal\_rule\_id | VARCHAR(10) | Originating signal rule (e.g., SR-001) if applicable |
| narrative | TEXT | Investigator's analytical narrative — becomes memo paragraph |
| legal\_refs | TEXT\[\] | ORC sections and federal statutes (e.g., 18 U.S.C. § 1343, ORC § 1702.80) |
| status | ENUM | DRAFT, REVIEWED, INCLUDED\_IN\_MEMO, EXCLUDED, REFERRED |
| created\_at | TIMESTAMP | When this finding was created |

### **signals**

| Column | Type | Description |
| ----- | ----- | ----- |
| id | UUID | Primary key |
| case\_id | UUID (FK) | Reference to parent case |
| rule\_id | VARCHAR(10) | Signal rule that triggered (SR-001 through SR-010, extensible) |
| severity | ENUM | CRITICAL, HIGH, MEDIUM, LOW |
| trigger\_entity\_id | UUID (FK) | Entity that triggered the signal |
| trigger\_doc\_id | UUID (FK) | Document that triggered the signal |
| status | ENUM | OPEN, CONFIRMED, DISMISSED, ESCALATED |
| investigator\_note | TEXT | Required when dismissed — rationale for dismissal |
| detected\_at | TIMESTAMP | When signal was automatically generated |

## **6.3 Relationship Tables**

| Table | Purpose |
| ----- | ----- |
| person\_document | Links a person to every document where they appear, with page and section reference |
| org\_document | Links an organization to every document where it appears |
| person\_org | Maps people to organizations with role (BOARD\_MEMBER, OFFICER, ATTORNEY, AGENT, INCORPORATOR, etc.) |
| property\_transaction | Records each transfer event: buyer, seller, date, price, consideration type, source document |
| entity\_signal | Links signals to all entities involved in the triggering pattern |
| finding\_entity | Links findings to all entities cited in the finding narrative |
| finding\_document | Links findings to source documents with specific page citations |
| audit\_log | Append-only log of all system actions: who did what, when, with before/after state — itself immutable |

# **7\. Security Design**

Catalyst is designed with a "Private by Design" philosophy. The platform handles sensitive investigative data involving real individuals and organizations under active regulatory review. Integrity, confidentiality, and auditability are non-negotiable at every layer.

## **7.1 Core Security Principles**

* Least Privilege: Each microservice has access only to the resources it requires. The processing service reads from the file store but cannot modify original documents. The signal service reads entity and document data but cannot alter it.

* Defense in Depth: Encryption at rest, encryption in transit (TLS 1.3), application-level authentication, and container isolation provide layered protection with no single point of failure.

* Immutable Evidence: Original documents are write-once. SHA-256 hashes are computed at intake, stored immutably, and verified before any document is referenced in a generated memo. This provides cryptographic chain of custody equivalent to evidence handling standards.

* Audit Everything: Every action in the system is logged with timestamp, user, action type, and before/after state. The audit log is append-only and cannot be modified or deleted by any user, including administrators.

* Secrets Management: All credentials, API keys, and environment-specific configuration values are stored in .env files excluded from version control. No sensitive values appear in source code or repository history.

* Anonymous Operation Support: The system shall support case operation under conditions where the investigator's identity is sensitive. No identifying metadata shall be embedded in generated output documents unless explicitly enabled by the user.

## **7.2 Authentication and Access**

Phase 1 implements single-user authentication. The architecture supports future multi-user access with role-based permissions (Investigator, Reviewer, Administrator) as the platform evolves. OAuth 2.0 / OIDC is the target authentication protocol for multi-user deployments.

# **8\. SDLC Roadmap**

Development follows a phased approach aligned with the IBM certificate coursework timeline and real-world investigative readiness. Each phase produces a working, usable increment of the system — not a collection of stubs.

## **Phase 1: Foundation — March–April 2026**

* Project charter and system design specification (completed)

* PostgreSQL database schema design and migration scripts (completed)

* Docker development environment with service scaffolding (completed for local development)

* Django-native case and document JSON API baseline (implemented)

* Document intake metadata workflow with strict SHA-256 validation (implemented; immutable object storage remains a hardening step)

* Pagination, filtering, sorting, PATCH, and DELETE support for case/document endpoints (implemented)

* API contract documentation and request cookbook for developer/operator use (implemented)

* Minimal React case dashboard (planned; not yet implemented)

## **Phase 2: Processing Pipeline — April–May 2026**

* OCR integration (Tesseract) for scanned documents

* Text extraction pipeline for digital PDFs

* Document type classification and structured field parsing

* Entity extraction, deduplication, and initial entity resolution

* ProPublica Nonprofit Explorer API connector (990 data)

* Ohio SOS business search connector

## **Phase 3: Investigation Interface — May–June 2026**

* Full React frontend with responsive design (mobile / tablet / desktop)

* Interactive relationship graph (React-Flow / D3) with node and edge type support

* Timeline view for chronological analysis across all case documents

* Signal detection engine: SR-001 through SR-010, extensible rule set

* Findings creation, management, and status workflow

* County recorder and county auditor data connectors (LandmarkWeb)

## **Phase 4: Memo Generation and Hardening — June–July 2026**

* PDF referral memo generator with citation tracking and SHA-256 verification

* Agency-specific memo templates (Ohio AG, IRS, FBI, FCA IG)

* ORC and federal statute cross-reference integration

* Kubernetes deployment configuration

* Security audit and penetration testing

* Complete SDLC documentation package for portfolio submission

## **Phase 5: Evolution — Post-Certificate**

* AI-assisted document reading: cross-document entity and relationship extraction using LLM APIs, with human confirmation required before any extracted data is used in a Finding

* Cross-case pattern detection: signal patterns that span multiple cases over time, identifying systematic actors or recurring schemes

* Multi-user support with role-based access control

* ISO 27037 compliance pathway for forensic-grade digital evidence handling

* Integration with additional state filing APIs as they become available

* PACER federal court records connector

A note on the Phase 5 AI specification: the AI layer in Catalyst is not general anomaly detection. The specific capability is cross-document relationship identification — given a set of extracted text documents, identify named entities, dates, and dollar amounts that appear in multiple documents and surface relationships not visible within any single document. This is a well-defined, achievable capability using current LLM APIs. It augments the rule-based signal engine; it does not replace it. Human confirmation is required at every step before any AI-identified relationship becomes a Finding.

# **9\. Portfolio and Professional Value**

Catalyst is designed to function simultaneously as a working investigative tool and as a comprehensive portfolio piece demonstrating full-stack development competency at a professional level. An employer or evaluator reviewing this project will find evidence of technical skill, domain knowledge, product thinking, and engineering ethics — a combination that distinguishes serious engineering from tutorial completion.

## **9.1 What Makes This Different**

* Real-World Problem Domain: Not a tutorial project or toy application. Built to solve a documented, genuine need with verifiable outcomes — formal referrals to five separate agencies, confirmed case numbers, and an active investigation. The problem domain is documented in public records.

* Evidence-Driven Requirements: Every requirement in this specification traces back to a specific failure mode or analytical gap identified in a real investigation. The database schema fields — date\_of\_death on persons, valuation\_delta on properties, DECEASED\_SIGNER in anomaly\_flags — did not come from a textbook. They came from reading primary source documents.

* Complete SDLC Documentation: Project charter, requirements specification, architecture design, database schema, sprint plans, test cases, deployment documentation, and retrospective. The documentation package is itself a demonstration of professional practice.

* Modern Technology Stack: React, Django, PostgreSQL, Docker, Kubernetes, Python, REST APIs — all industry-standard tools applied to a complex, multi-service domain with real data integrity requirements.

* Security-First Design: Encryption, immutable storage, audit logging, secrets management, and anonymous operation support demonstrate awareness of production security requirements in a sensitive domain.

* Ethical Engineering: The design explicitly and deliberately requires human judgment at every consequential decision point. The platform assists investigation; it does not automate accusations. Signal detection produces flags, not conclusions. Findings require investigator narrative. Memos cite sources, not verdicts. This demonstrates mature engineering judgment about the limits and responsibilities of automated systems.

## **9.2 The Catalyst Principle**

**The human investigator is always the decision-maker.**

*Catalyst organizes, structures, and presents. It never accuses, concludes, or acts autonomously.*

***The most dangerous feature is the one that removes human judgment.***

This principle is not a disclaimer. It is a design constraint that shapes every architectural decision in the platform. Signals require investigator confirmation before becoming Findings. Findings require investigator narrative before appearing in memos. Memos cite sources and describe patterns — they do not assert guilt. The platform is software built by someone who understands that in investigative work, the difference between a well-documented referral and a dangerous accusation is human judgment, applied carefully, at every step.

