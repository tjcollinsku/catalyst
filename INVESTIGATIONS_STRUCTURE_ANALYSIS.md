# Backend/Investigations Folder - Logical Structure Analysis

**Analysis Date:** March 28, 2026  
**Purpose:** Understand module categorization, dependencies, and interdependencies

---

## I. Module Categories

### **Category 1: External Data Connectors** 🔌
These modules fetch data from external government and nonprofit sources via public APIs or bulk file downloads. All are **stateless** (no Django imports), operate on functions that accept raw inputs and return plain Python data structures.

| Module | Purpose | Data Source | Auth | Notes |
|--------|---------|-------------|------|-------|
| `county_auditor_connector.py` | Ohio parcel ownership data | ODNR statewide parcel layer (ArcGIS REST API) | None / Public | Dual-mode: automated API + human-in-loop URL builder |
| `county_recorder_connector.py` | Ohio deed/UCC/mortgage records | 88 county recorder portals | None / Human | URL builder + structured document parser (no scraping) |
| `propublica_connector.py` | Nonprofit financial data | ProPublica Nonprofit Explorer API | None / Public | 990 filings, org profiles, EIN lookup |
| `irs_connector.py` | Tax-exempt organization status | IRS Pub78 & EO BMF bulk files | None / Public | Two tiers: deductibility check + full history |
| `ohio_aos_connector.py` | Audit findings/recovery | Ohio Auditor of State search | None / Public | Detects public money misappropriation signals |
| `ohio_sos_connector.py` | Business entity filings | Ohio SOS bulk CSV exports | None / Public | Entity formation, amendments, dissolutions |

**Connector Architecture:**
- All expose **search_*() functions** to find records by name/EIN/entity
- All include **staleness warnings** (when data was last updated)
- All return structured **dataclass results** with no DB writes
- External use pattern: fetch → search locally → return candidates
- Designed for investigator review — not auto-merged into DB

---

### **Category 2: Extraction & Entity Pipeline** 🔄
These modules implement the 3-stage entity resolution pipeline. **Stateless** (no Django imports), pure functions.

**Pipeline Architecture:**
```
PDF/Text Source
    ↓
extraction.extract_from_pdf(path, size)  [Stage 0: Text Extraction]
    ↓ extracted_text, ocr_status
    ↓
classification.classify_document(text)  [Side-step: Guess doc_type]
    ↓ DocumentType guess
    ↓
entity_extraction.extract_entities(text, doc_type)  [Stage 1: Extract Candidates]
    ↓ raw {persons, orgs, dates, amounts, parcels, filing_refs}
    ↓
entity_normalization.normalize_person_name(raw)  [Stage 2a: Normalize]
entity_normalization.normalize_org_name(raw)
entity_normalization.normalize_amount(raw)
    ↓ normalized strings/values
    ↓
entity_resolution.resolve_person(case, normalized)  [Stage 3: Resolve]
entity_resolution.resolve_org(case, normalized)
    ↓ PersonResolutionResult / OrgResolutionResult
    ↓
[FuzzyCandidate results returned for human review]
[Exact matches upserted to DB]
[Persisted to Person/Organization models]
```

| Module | Stateless? | Purpose | Returns | DB Access? |
|--------|-----------|---------|---------|----------|
| `extraction.py` | ✅ Yes | Extract text from PDF (direct+OCR) | `(text, ocr_status)` | No |
| `classification.py` | ✅ Yes | Classify doc by keyword scoring | `DocumentType` | No |
| `entity_extraction.py` | ✅ Yes | Extract raw entity candidates | `{persons, orgs, dates, amounts, parcels, filing_refs}` | No |
| `entity_normalization.py` | ✅ Yes | Normalize extracted entities to canonical form | `str` (normalized) | No |
| `entity_resolution.py` | ⚠️ Imports models | Match/create exact, surface fuzzy | `PersonResolutionResult / OrgResolutionResult` | Yes (TYPE_CHECKING only in imports) |

**Key Design Points:**
- Stages 0–2 have **zero Django dependency** — pure regexes and string manipulation
- Stage 3 imports models via `TYPE_CHECKING` for type hints, writes on caller's request via `persist_signals()`
- Fuzzy matching uses `difflib.SequenceMatcher` — returns candidates, never auto-merges
- All regex patterns compiled at import time (performance optimization)

---

### **Category 3: Core Django / ORM Models** 🗄️

| Module | Purpose | Key Models |
|--------|---------|-----------|
| `models.py` | Django ORM schema | `Case`, `Document`, `Person`, `Organization`, `PropertyTransaction`, `Signal`, `Finding`, `GovernmentReferral`, `AuditLog` + choice enums |
| `serializers.py` | Request/response serialization | `CaseIntakeSerializer`, `DocumentUploadForm`, custom `serialize_*()` functions |
| `forms.py` | Django form classes | `CaseForm`, `DocumentUploadForm` |
| `apps.py` | Django app config | `InvestigationsConfig` |
| `admin.py` | Django admin registration | Registers Case, Document, Person, Organization, etc. for admin UI |
| `urls.py` | URL routing | REST endpoints: `/api/cases/`, `/api/cases/<id>/documents/`, `/api/cases/<id>/signals/` |
| `views.py` | Django views (HTTP handlers) | `api_case_collection()`, `api_case_detail()`, `document_upload()`, `case_list()`, etc. |

**Dependencies:**
- `views.py` → imports from `serializers.py`, `models.py`, `forms.py`
- `serializers.py` → imports from `models.py`
- `admin.py` → imports all major models from `models.py`
- `urls.py` → imports `views`

---

### **Category 4: Signal Detection & Utilities** 🚨

| Module | Purpose | Dependencies | Notes |
|--------|---------|--------------|-------|
| `signal_rules.py` | Evaluate documents/cases against fraud signal rules (SR-001 through SR-010) | Imports `models` for ORM queries | **No Django view imports.** Stateless evaluators return `list[SignalTrigger]` |
| `logging_utils.py` | Custom JSON logging formatter | Django logging only | Used by `catalyst/settings.py` for `JsonKeyValueFormatter` |

**Signal Architecture:**
- `evaluate_document(case, document)` → Runs SR-001, SR-002, SR-005, SR-006 (doc-scoped)
- `evaluate_case(case)` → Runs SR-003, SR-004, SR-007–SR-010 (case-scoped cross-doc)
- `persist_signals(case, triggers)` → Deduplicates and writes to DB
- Each rule is **independent** — failure in one rule doesn't block others (logged, caught)

---

### **Category 5: Test & Utility Scripts** 🧪

| Module | Purpose |
|--------|---------|
| `tests/` | Unit tests for connectors (no DB mocking needed — they're stateless) |
| `verify_recorder_portals.py` | Script: validates Ohio county recorder portal URLs are reachable |
| `county_recorder_portal_checklist.md` | Documentation: human-readable checklist of required recorder URLs |

---

## II. Interdependencies Map

### **Within investigations/ (Internal Dependencies)**

```
EXTERNAL DATA CONNECTORS (Leaf nodes — no internal dependencies)
  ├─ county_auditor_connector.py
  ├─ county_recorder_connector.py
  ├─ propublica_connector.py
  ├─ irs_connector.py
  ├─ ohio_aos_connector.py
  └─ ohio_sos_connector.py

EXTRACTION PIPELINE (Stages 0–2: no Django, no connectors)
  ├─ extraction.py
  │   └─ imports: fitz (PyMuPDF), pytesseract, PIL
  │   └─ calls: models.OcrStatus (enum only, imported inside function)
  ├─ classification.py
  │   └─ imports: re
  │   └─ local regex rules, no external calls
  ├─ entity_extraction.py
  │   └─ imports: re, datetime
  │   └─ local regex + pattern matching
  ├─ entity_normalization.py
  │   └─ imports: re, unicodedata
  │   └─ string normalization primitives
  └─ entity_resolution.py
      ├─ imports: entity_normalization
      ├─ TYPE_CHECKING imports: models for type hints
      ├─ calls: normalize_person_name(), normalize_org_name() [from entity_normalization]
      └─ uses: difflib for fuzzy matching

SIGNAL DETECTION
  └─ signal_rules.py
      ├─ imports: models (Case, Document, Person, Organization for ORM queries)
      ├─ calls: entity_normalization helpers
      └─ returns: list[SignalTrigger] (no writes directly, caller persists)

DJANGO CORE
  ├─ models.py
  │   └─ imports: django, uuid
  │   └─ defines: Choice enums and ORM model classes
  ├─ serializers.py
  │   ├─ imports: models (for Case, Document, Signal)
  │   └─ calls: _serialize_datetime()
  ├─ forms.py
  │   ├─ imports: models (Case, Document, DocumentType)
  │   └─ pure Django forms
  ├─ views.py
  │   ├─ imports: serializers, models, forms
  │   ├─ calls: extraction functions
  │   ├─ calls: signal_rules.evaluate_document()
  │   └─ potential calls to: entity_resolution, classification (not confirmed in views excerpt)
  └─ urls.py
      └─ imports: views

UTILITIES
  ├─ logging_utils.py
  │   └─ imports: json, logging
  ├─ admin.py
  │   └─ imports: models (all major model classes)
  ├─ apps.py
  │   └─ imports: django
  └─ __init__.py
      └─ empty

CONFIGURATION (external to investigations/)
  └─ catalyst/settings.py
      ├─ imports: "investigations.logging_utils.JsonKeyValueFormatter"
      └─ imports: "investigations" as INSTALLED_APP
```

### **External Dependencies on investigations/**

**From Django Project (catalyst/):**
- `catalyst/settings.py` references:
  - `investigations.logging_utils.JsonKeyValueFormatter` (for logging)
  - `"investigations"` in `INSTALLED_APPS`

**Outside investigations/, but in backend/:**
- No other Django apps import from investigations (grep confirms)

---

## III. Key Findings: Logical Grouping

### **Tier 1: Stateless Utilities (Reusable Outside Django)**
These can be used in CLI scripts, background tasks, or other projects:
- `extraction.py`
- `classification.py`
- `entity_extraction.py`
- `entity_normalization.py`
- All 6 connectors: `county_auditor_*`, `county_recorder_*`, `propublica_*`, `irs_*`, `ohio_aos_*`, `ohio_sos_*`

**Why This Matters:** These modules have **zero Django coupling**, making them:
- Easy to unit test (no DB, no ORM mocking)
- Reusable in CLI scripts, batch jobs, or other tools
- Safe to import from tests without Django setup

### **Tier 2: Pipeline Integration (Needs Django ORM)**
These need the database and models:
- `entity_resolution.py` (writes Person/Organization records)
- `signal_rules.py` (reads entities, queries DB for pattern detection)
- `views.py` (orchestrates extraction + signal detection)

### **Tier 3: Django Infrastructure**
These are standard Django components:
- `models.py` (ORM schema)
- `serializers.py` (request/response handling)
- `forms.py` (form validation)
- `views.py` (HTTP handlers)
- `urls.py` (routing)
- `admin.py` (Django admin UI)

---

## IV. Data Flow Across Tiers

### **Typical Document Ingestion Flow**

```
1. REST API: POST /api/cases/<case>/documents/upload
   ↓ views.py
   
2. Extract Text from PDF
   → extraction.extract_from_pdf(file_path)
   → extraction.py (Tier 1: stateless)
   ↓ (text, ocr_status)
   
3. Classify Document Type
   → classification.classify_document(text)
   → classification.py (Tier 1: stateless)
   ↓ DocumentType guess
   
4. Extract Entity Candidates
   → entity_extraction.extract_entities(text, doc_type)
   → entity_extraction.py (Tier 1: stateless)
   ↓ (persons, orgs, dates, amounts, parcels, filing_refs)
   
5. Normalize Entities
   → entity_normalization.normalize_person_name(raw)
   → entity_normalization.py (Tier 1: stateless)
   ↓ normalized_name
   
6. Resolve Entities (Tier 2: needs DB)
   → entity_resolution.resolve_person(case, normalized_name)
   → entity_resolution.py (may write to Person model)
   ↓ PersonResolutionResult (matched/created + fuzzy candidates)
   
7. Evaluate Signals
   → signal_rules.evaluate_document(case, document)
   → signal_rules.py (Tier 2: ORM queries)
   ↓ list[SignalTrigger]
   
8. Persist Results (Tier 2: writes)
   → signal_rules.persist_signals(case, triggers)
   → Creates Signal model instances
   
9. Return Response
   ← serializers.py (format for JSON)
   ← views.py
   ↓ HTTP 200 + JSON response
```

### **Connector Usage Pattern (Async/Background)**

```
Investigator clicks: "Search IRS for organization name"
   ↓
views.py receives request
   ↓
propublica_connector.search_organizations(query, state)
   or
irs_connector.search_pub78(query, records)
   ↓ (Tier 1: stateless, no DB access)
   return: list[OrganizationSummary] with staleness_warning
   ↓
API returns results to frontend for investigator review
   ↓
Investigator can manually associate/create Organization record
```

---

## V. Design Principles Observed

### **1. Statelessness Where Possible**
- **Tier 1 modules are pure functions:** Connectors, extraction, normalization
- **Advantage:** Easy to test, reusable, no hidden state
- **Exception:** `entity_resolution.py` imports models for type hints (TYPE_CHECKING only)

### **2. Human-in-Loop Architecture**
- Connectors surface **candidates** for investigator review, not auto-merged
- Fuzzy matches flagged (never auto-merged) with `FuzzyCandidate` objects
- URL builders (county recorder, AOS) let humans click and decide

### **3. Staleness Warnings**
- External data files are timestamped with "last downloaded" + days elapsed
- Investigator warned when data is >3 weeks old
- **Principle:** No auto-trust of old data; humans verify recent changes

### **4. Clear Error Types**
- Each connector defines its own error class: `RecorderError`, `ProPublicaError`, `AOSError`, `IRSError`
- Errors include context (e.g., which county failed)
- Caller can decide how to handle

### **5. No Cross-Connector Dependencies**
- Each connector is **independent**
- No connector imports another
- All stand alone or are called from `views.py` / `signal_rules.py`

### **6. Signal Rules are Evaluators, Not Writers**
- `signal_rules.evaluate_document()` returns `list[SignalTrigger]` (no side effects)
- DB writes happen explicitly via `persist_signals()` (caller responsible)
- Makes testing easier (no mocking DB writes)

---

## VI. Potential Refactoring / Improvement Areas

### **Current Strengths**
✅ Clear separation of concerns (Tier 1 vs Tier 2)  
✅ Stateless utilities are testable and reusable  
✅ Explicit error handling with domain-specific exceptions  
✅ Staleness warnings prevent silent data rot  

### **Potential Improvements**
- [ ] `entity_resolution.py` uses TYPE_CHECKING imports but still touches models — could move DB writes to a separate `models.py` function (would be pure factory pattern)
- [ ] `signal_rules.py` could be split: evaluation rules (stateless) vs. persistence layer (DB-aware)
- [ ] Add explicit "pipeline orchestrator" module to document the exact flow (currently loose in `views.py`)
- [ ] Consider connector **registry pattern** if more states/sources are added (currently scattered imports in `views.py`)

---

## VII. Summary Table

| Category | Modules | Stateless? | Django Used? | DB Writes? | Primary Purpose |
|----------|---------|-----------|------|----------|---------|
| **Connectors** | county_*, irs_, propublica_, ohio_* | ✅ Yes | ❌ No | ❌ No | Fetch external data |
| **Extraction** | extraction, classification | ✅ Yes | ❌ No | ❌ No | Text → structured candidates |
| **Normalization** | entity_normalization | ✅ Yes | ❌ No | ❌ No | Canonicalize raw values |
| **Resolution** | entity_resolution | ⚠️ Partial | ⚠️ TYPE_CHECKING | ✅ Yes | Exact match + fuzzy surface |
| **Signals** | signal_rules | ⚠️ Partial | ⚠️ models only | ⚠️ via caller | Evaluate fraud patterns |
| **Django Core** | models, views, serializers, forms | ❌ No | ✅ Yes | ✅ Yes | HTTP API + persistence |
| **Utilities** | logging_utils, admin, apps | ⚠️ Partial | ✅ Yes | ❌ No | Framework integration |

---

## VIII. External Integration Points

**What imports investigations/ from outside:**
- `catalyst/settings.py` → uses `investigations.logging_utils.JsonKeyValueFormatter`
- No other Django apps reference investigations (isolated app)

**What investigations/ imports from outside:**
- Django ORM (models, forms, serializers)
- External libraries: `fitz`, `pytesseract`, `PIL`, `requests`, `difflib`
- Standard library: `re`, `datetime`, `logging`, `json`, etc.

**Coupling Direction:** ✅ **Acyclic** (no circular imports detected)
