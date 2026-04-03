# Data Engineer — Specialist Briefing Book

## Your Role

You own the data pipeline: document ingestion, text extraction (OCR), entity extraction (NLP), entity resolution (deduplication), financial data parsing, and data quality. You ensure that raw documents become clean, structured, queryable data. You think about data quality obsessively — garbage in, garbage out.

Your primary responsibilities:
- Keep the extraction pipeline running and tuned for accuracy
- Monitor data quality at every stage (extraction → normalization → resolution → DB)
- Build and maintain parsers for specialized document types (IRS 990s, deeds, UCCs, obituaries)
- Investigate and fix entity extraction failures (hallucinations, missed entities, bad fuzzy matches)
- Optimize extraction performance (OCR is slow; cache aggressively)
- Lead data cleanup operations when garbage data gets persisted

---

## The Extraction Pipeline (End to End)

### Stage 0: Document Upload → Storage
1. Raw file received from browser upload
2. SHA-256 hash computed (chain of custody)
3. File stored in `media/` directory with hash-based filename
4. File size checked: if > 30 MB and scanned PDF, mark `ocr_status=PENDING` for background processing

### Stage 1: PDF Text Extraction
**File: `extraction.py` — `extract_from_pdf()`**

Two-tier strategy based on file content:

**Tier 1: Direct Extraction (PyMuPDF)**
- Opens PDF and pulls embedded text layer using `page.get_text()`
- Fast: ~0.1 seconds per document
- Works on: digital PDFs (created by software), searchable PDFs with text layer
- If extracted text ≥ 100 characters (`_MIN_MEANINGFUL_LENGTH`), returns immediately with `ocr_status=NOT_NEEDED`

**Tier 2: OCR Fallback (Tesseract)**
- Triggered when: embedded text is sparse/missing AND file < 30 MB
- Renders each PDF page to image at 200 DPI (`_OCR_DPI`)
- Runs Tesseract OCR on each page with 60-second per-page timeout
- Maximum 300 seconds total per document (`_OCR_TOTAL_TIMEOUT_SECONDS`)
- Returns `ocr_status=COMPLETED` on success, `ocr_status=FAILED` on error
- Large files (> 30 MB) scanned but sparse return `ocr_status=PENDING` for async processing

**Metadata Extraction**
- `extract_pdf_metadata()` pulls PDF info dictionary: author, creator, creation date, modification date, page count, encryption status, form field presence
- This metadata is critical for forensic chain-of-custody and investigator provenance tracking

**Security Check**
- Stage 0 validation: `_validate_pdf_header()` ensures file starts with `%PDF-` magic bytes (SEC-014)
- Rejects renamed executables and malformed files before processing

### Stage 2: Entity Extraction (Rule-Based)
**File: `entity_extraction.py` — `extract_entities()`**

High-precision rule-based extraction from plain text. Returns structured candidates for downstream processing.

**What it extracts:**
- Persons: names in labeled context (GRANTOR, GRANTEE, OFFICER) + inverted format (LAST, FIRST)
- Organizations: any capitalized phrase ending in legal designator (Inc., LLC, Corp., Foundation, etc.)
- Dates: long-form, MM/DD/YYYY, ISO 8601, legal prose format
- Dollar amounts: $X,XXX,XXX with optional cents
- Parcel numbers: county auditor formats (12-001234.000, 34-0012345, A01-0001-00-000)
- Filing references: UCC numbers, SOS filings, instrument numbers

**Person Name Validation: `_is_plausible_person_name()`**

Rejects 80%+ of OCR-induced false positives. Rules:

1. Must have ≥ 2 tokens (minimum first + last)
2. Cannot be all stopwords (e.g., "SECTION PART", "SIGN HERE")
3. At least one non-stopword token must be ≥ 3 characters (rejects "A Vi", "E Iv")
4. Rejects bare Roman numerals without a plausible first name

**Stopword Set (`_PERSON_STOPWORDS`)**

Covers:
- US state abbreviations (AL, AK, CA, etc.) — because OCR reads "OH Example City" as inverted name
- Roman numerals (I–XVI) — 990 form section markers look like "Jr III"
- IRS 990 form labels (SECTION, PART, LINE, SCHEDULE, FORM)
- Common form field words (DATE, SIGN, NAME, ADDRESS, TITLE, etc.)
- Geographic/address fragments (COUNTY, ROAD, AVENUE, SUITE, etc.)
- Professional credentials (EA, CPA, JD, MD, PHD)
- Legal designators (LLC, INC, CORP)
- OCR-specific junk (EXAMPLE_CITY, EXAMPLE_TOWNSHIP, MY, HAND, AN — from Example Charity case)

**Organization Name Validation: `_is_plausible_org_name()`**

Rejects form boilerplate and legal structure labels. Rules:

1. Reject known generic phrases outright (e.g., "Domestic Limited Liability Company", "Limited Liability Partnership")
2. After stripping legal designators and stopwords, ≥ 1 substantive word (3+ chars) must remain
3. Must have ≥ 2 tokens total
4. Reject if name contains IRS section header patterns ("Section A.", "Part VII")

**Stopword Set (`_ORG_STOPWORDS`)**

Covers same categories as person stopwords, plus:
- Form identifiers (W-2G, 1099, W-2, 990, 990-T, 990-EZ, 990-PF, 1040, 1120, 8868)
- Legal structure descriptors (DOMESTIC, FOREIGN, LIMITED, LIABILITY, PROFIT, PROFESSIONAL)
- Business status words (REGISTERED, AUTHORIZED, CANCELED, DISSOLVED, ACTIVE, INACTIVE)
- OCR timestamps (PM, AM, UL, LI)

**Output Format**

```python
{
    "persons": [
        {
            "raw": "John A. Example",
            "context": "GRANTOR: John A. Example"
        }
    ],
    "orgs": [
        {
            "raw": "Example Charity Ministries, Inc.",
            "context": "..."
        }
    ],
    "dates": [
        {
            "raw": "March 2, 2022",
            "normalized": "2022-03-02"
        }
    ],
    "amounts": [
        {
            "raw": "$4,505,000",
            "normalized": 4505000.0
        }
    ],
    "parcels": [
        {
            "raw": "12-001234.000"
        }
    ],
    "filing_refs": [
        {
            "raw": "OH-2022-0012345"
        }
    ]
}
```

### Stage 3: AI-Assisted Extraction (Proposal Layer)
**File: `ai_extraction.py` — `ai_extract_entities()`, `ai_extract_990()`, `ai_extract_obituary()`**

Uses Claude 3.5 Sonnet (model: `claude-sonnet-4-20250514`) to propose higher-confidence entities with reasoning.

**Architecture: "AI proposes, human confirms, rules detect"**

- This module proposes candidates with confidence scores (0.0–1.0)
- Data quality validation filters/enriches proposals before DB insertion
- Signal rules (signal_rules.py) run fraud detection on the clean data
- AI NEVER makes detection decisions — it only extracts data

**Three Specialized Extractors:**

**1. General Document Extractor: `ai_extract_entities(text, doc_type="OTHER")`**
- Extracts: persons (name, role, title, context, confidence), organizations (name, type, EIN, state, confidence), relationships, dates, amounts, addresses
- Truncates input to 15,000 chars (~4k tokens) to control API costs
- Returns AIProposal list with confidence scores and reasoning
- Uses `_SYSTEM_PROMPT_GENERAL` — generic extraction rules

**2. IRS 990 Specialist: `ai_extract_990(text)`**
- Targets fields OCR typically mangles: officer names, compensation, Part IV checklist answers (Yes/No flags), Schedule L/B presence
- These fields are critical for signal rules: SR-006, SR-011, SR-012, SR-013, SR-025, SR-026, SR-029
- Extracts:
  - Officers: name, title, hours/week, reportable compensation, other compensation, is_former flag
  - Part IV checklist: Line 25a (related party), 25b (excess benefit), 26 (loan to officer), 27 (grant), 28a/b/c (officer relationships)
  - Financials: total revenue, expenses, net assets, program/mgmt/fundraising breakdown, compensation total
  - Contractors: name, services, compensation
  - Schedule presence: schedule_l_present, schedule_b_present (boolean flags)
- Truncates to 20,000 chars (covers most of form)
- Returns confidence_overall and per-field confidence

**3. Obituary Specialist: `ai_extract_obituary(text)`**
- Maps family relationship networks — obituaries are the #1 source for insider network discovery
- How we found the Example-FamilyMember-ExampleSeller-RelatedParty network in the Example Charity case
- Extracts: deceased (name, birth/death date, residence), family relationships (person, relationship_type: spouse|child|sibling|parent|grandchild|in_law|niece_nephew, status: living|deceased, maiden_name), organizations mentioned (employer, church, charity), locations
- Truncates to 5,000 chars (obituaries are short)
- Tracks status: "living" vs "deceased" (as of obit date)

**API Configuration**
- Model: Claude 3.5 Sonnet
- Temperature: 0.0 (deterministic extraction, no creativity)
- Max tokens: 4,096
- Lazy client initialization: anthropic package only imported when AI extraction called
- Handles markdown code fences in response (Claude sometimes wraps JSON in ```)

**Confidence Tracking: `AIProposal` dataclass**

Every proposal carries:
- `entity_type`: "person", "org", "relationship", "date", "amount", "address", "financial"
- `data`: extracted fields (dict)
- `confidence`: 0.0–1.0 (set by Claude itself)
- `source_text`: snippet of text the AI extracted from
- `reasoning`: why the AI thinks this entity exists

**Error Handling**
- Graceful degradation: API failures don't crash pipeline
- Returns `AIExtractionResult(error="...")` on API call failure
- Fallback: regex-based extraction remains the primary output; AI proposals are enhancement layer

### Stage 4: Entity Normalization (Standardization)
**File: `entity_normalization.py`** (mentioned but not read in detail)

Applied before resolution. Rules normalize names across different formats/spellings so exact matching works correctly.

**Person normalization:**
- Lowercase
- Strip titles, credentials, suffixes
- Consistent spacing
- Remove punctuation

**Organization normalization:**
- Lowercase
- Strip legal designators (Inc, LLC, Corp, etc.)
- Strip common prefixes (The, A, An)
- Collapse multiple spaces
- Consistent separators

### Stage 5: Entity Resolution (Deduplication)
**File: `entity_resolution.py` — `resolve_person()`, `resolve_org()`, `resolve_all_entities()`**

Two-tier matching strategy: exact match (automatic) → fuzzy match (human review).

**Tier 1: Exact Match (Automatic)**

1. Normalize incoming name
2. Compare normalized incoming name against all existing Person/Organization records in the case
3. Check both `full_name` and `aliases` list
4. If match found: return existing record, no insert
5. If match found on alias: track which alias matched
6. Enrich existing record with new data (address, phone, roles)

Example: "John A. Example" matches existing record's alias "EXAMPLE, JOHN A." → return existing Person, log `matched_alias="EXAMPLE, JOHN A."`

**Tier 2: Fuzzy Match (Human Review)**

After exact match fails, compute similarity for all existing records.

**Similarity Algorithm: Python `difflib.SequenceMatcher` (Ratcliff/Obershelp)**
- Returns ratio 0.0–1.0 (identical = 1.0, completely different = 0.0)
- Lightweight, no external dependencies (important for Phase 2)
- Can be swapped for rapidfuzz later if performance becomes issue

**Thresholds:**

| Similarity | Action | Meaning |
|-----------|--------|---------|
| ≥ 0.92 | HIGH-CONFIDENCE flag + log info | Very likely same person (typo, missing initial) |
| 0.75–0.91 | Review candidate | Possibly same person (review recommended) |
| < 0.75 | Ignore | Probably different people |

**Fuzzy candidates are NEVER auto-merged.** Returned to caller (upload pipeline) for investigator review.

**PersonResolutionResult dataclass:**
```python
{
    "person": Person,           # The matched or created Person
    "created": bool,            # True if newly inserted
    "matched_alias": str|None,  # Which alias matched (if Tier 1 hit)
    "fuzzy_candidates": [       # Tier 2 near-matches for review
        {
            "incoming_raw": "Jon A. Example",
            "incoming_normalized": "jon a example",
            "existing_id": "uuid",
            "existing_raw": "John A. Example",
            "existing_normalized": "john a example",
            "similarity": 0.87,
            "entity_type": "person"
        }
    ]
}
```

**Organization Resolution: `resolve_org()`**

Same two-tier strategy as persons. No alias list for orgs (only full_name). Enrichment fields: EIN, address, phone, org_type, registration_state.

**Batch Resolution: `resolve_all_entities(extraction_result, case, document)`**

Entry point called by upload pipeline. Processes full `extract_entities()` output and resolves all persons + orgs against the case's existing entity records.

**Special Handling:**

- **IRS 990 preparers:** If `source="990_preparer"` and `meta["preparer_firm"]` present, links person to firm org via PersonOrganization with role="Tax Preparer"
- **Organization EIN enrichment:** If `meta["org_ein"]` present (from 990), attempts to enrich the case's main org record

**ResolutionSummary output:**
```python
{
    "persons_created": 3,
    "persons_matched": 2,
    "orgs_created": 1,
    "orgs_matched": 2,
    "fuzzy_candidates": [...]  # Sorted by similarity descending
}
```

---

## Entity Extraction Deep Dive

### How Organizations Are Identified

1. **Regex anchor on legal designators:** Inc., LLC, Corp., Foundation, Ministries, Association, Trust, Company, Partners, Management, Services, Group, Enterprises, Ventures, CIC, Nonprofit, etc.

2. **Capture surrounding words:** Match one or more capitalized words before the designator

3. **Example matches:**
   - "Example Charity Ministries, Inc." → captured because ends in "Inc"
   - "Ohio Department of Commerce" → NOT captured (no legal designator)
   - "ABC Trust" → captured because ends in "Trust"

4. **Validation filter (`_is_plausible_org_name`):**
   - Reject if ALL tokens are stopwords
   - Require at least one non-stopword 3+ chars long
   - Reject known generic phrases ("Domestic Limited Liability Company")

### How Persons Are Identified

1. **Labeled context (high confidence):**
   - Look for labels: GRANTOR, GRANTEE, DEBTOR, SECURED PARTY, SIGNER, OFFICER, INCORPORATOR, REGISTERED AGENT, NOTARY, TRUSTEE, ATTORNEY, WITNESS, SIGNED BY, PREPARED BY, ACKNOWLEDGED BY
   - Pattern: `LABEL: First Middle? Last [Jr/Sr/II/III/IV]?`
   - Example: `GRANTOR: John A. Example` → captures "John A. Example"

2. **Inverted format (legal documents):**
   - Pattern: `LAST, First Middle? [Jr/Sr/II/III/IV]?`
   - Example: `EXAMPLE, JOHN A.` → captures as person
   - ALL-CAPS last name + title-case first name

3. **Validation filter (`_is_plausible_person_name`):**
   - Reject if < 2 tokens
   - Reject if ALL tokens are stopwords
   - Require ≥ 1 non-stopword 3+ chars long
   - This filters out 80%+ of OCR junk

### The Stopword Lists and Why They Exist

**Design philosophy:** IRS 990 forms (especially OCR'd) are the primary source of junk extractions. They use English words as section headers and field labels that get misread as names.

**Person stopwords (`_PERSON_STOPWORDS` — 274 words):**

| Category | Examples | Why |
|----------|----------|-----|
| US states | AL, AK, CA, OH, etc. | OCR reads "OH Example City" as inverted name |
| Roman numerals | I, II, III, IV, V, etc. | "Section IV", "Part VII" look like suffixes |
| Form labels | SECTION, PART, LINE, SCHEDULE, FORM | 990 boilerplate |
| Form fields | DATE, SIGN, NAME, ADDRESS, TITLE | Captured around actual name |
| Address parts | COUNTY, TOWNSHIP, ROAD, AVE, ST | Address context |
| Credentials | EA, CPA, JD, MD, PHD | After names: "BROERING, EA" |
| Legal designators | LLC, INC, CORP | Org spillover |
| Case-specific junk | EXAMPLE_CITY, EXAMPLE_TOWNSHIP, MARIA, STEIN | Example Charity case city names |

**Organization stopwords (`_ORG_STOPWORDS` — 150+ words):**

Same pattern, plus:
- Form identifiers: 990, 990-T, 990-EZ, 1040, 1120
- Legal structure: DOMESTIC, FOREIGN, LIMITED, LIABILITY, PROFIT
- Business status: REGISTERED, AUTHORIZED, CANCELED, DISSOLVED, ACTIVE, INACTIVE

**Organization reject phrases (`_ORG_REJECT_PHRASES`):**

Exact phrases that are 100% false positives:
- "Domestic Limited Liability Company"
- "Domestic For-Profit Limited Liability Company"
- "Limited Liability Partnership"
- "Professional Corporation"
- "Tax Canceled Corp"

### Known Patterns That Produce Bad Extractions

1. **"SECTION A" → Person name**
   - OCR: "SECTION A" inverted to "A, SECTION"
   - Stopword filter catches it

2. **Legal structure as org name**
   - OCR reads: "Organization Exempt From Inc"
   - Captured as "Organization Exempt From Inc."
   - Reject phrases filter catches it

3. **Address as person name**
   - OCR reads: "123 MAIN STREET, EXAMPLE_CITY"
   - Inverted pattern reads as: "STREET, EXAMPLE_CITY" (person) or "MAIN, EXAMPLE_CITY" (person)
   - MAIN, EXAMPLE_CITY both in stopword set

4. **Geographic words**
   - "HARDIN County" captured as "HARDIN County" org
   - But HARDIN rejected by stopword (too short, or suffix)
   - COUNTY is stopword for orgs

### Fixing Bad Extractions: Best Practices

1. **Don't patch the regex** — changes break other cases
2. **Add to stopword set** if pattern is systematic (confirm with 2+ cases)
3. **For one-off cases:** Use fuzzy match review → manually reject candidate → investigator learning
4. **For OCR artifacts:** Improve input quality (better scan, pre-processing) before extraction

### Difference: Rule-Based vs AI-Assisted Extraction

| Aspect | Rule-Based | AI-Assisted |
|--------|-----------|-----------|
| Speed | ~0.01 sec | ~1-2 sec (API call) |
| Precision | High | Very high |
| Recall | Lower | Higher |
| Cost | $0 | ~$0.01–0.05 per document |
| Hallucination | Low (can't invent) | Possible (needs validation) |
| Relationships | No | Yes |
| Confidence scores | No | Yes, 0.0–1.0 |
| Use case | Primary extraction | Proposal/enhancement layer |
| Failure mode | Safe (missing data) | Unsafe (false entities) |

**Merge strategy:**
- Rule-based output is the primary source
- AI proposals augment/confirm rule extraction
- Investigator sees both + confidence scores → can compare

---

## Entity Resolution Deep Dive

### Exact Match Strategy

1. **Normalize both sides** of the comparison
   - Incoming name normalization
   - Existing record normalization
   - Both use same normalization function (from entity_normalization.py)

2. **Compare against:**
   - Person: `full_name` + all entries in `aliases` list
   - Organization: `name` only (no alias list)

3. **On match:**
   - Return existing record (no insert)
   - Optionally enrich with new data (address, phone, roles)
   - Create PersonDocument or OrgDocument link to track document appearance

4. **Enrichment rules (don't overwrite existing):**
   - Address: only if existing person.address is empty
   - Phone: only if existing person.phone is empty
   - Role tags: append new tag if not already present
   - EIN: only if existing org.ein is empty
   - All updates trigger `.save()`

### Fuzzy Match Strategy

1. **Compute similarity** for every existing record that didn't exact-match
   - Algorithm: SequenceMatcher (Ratcliff/Obershelp)
   - Input: normalized incoming name vs normalized existing full_name
   - Output: ratio 0.0–1.0

2. **Filter by threshold** (≥ 0.75)
   - Build FuzzyCandidate list
   - Store raw names, normalized names, similarity, entity type

3. **Log and return**
   - HIGH-CONFIDENCE (≥ 0.92): log at INFO level
   - REVIEW (0.75–0.91): log at INFO level
   - Return all to caller, sorted by similarity descending

4. **Absolutely NO auto-merge** of fuzzy candidates
   - Human must confirm in UI
   - This is a hard requirement for Phase 2

### Resolved Entities Merging

**When exact match occurs:**
- Existing record is returned as-is
- New data enriches fields (if provided and field is empty)
- PersonDocument link is created (idempotent via get_or_create)

**No field overwrite:** If person already has `address="123 Main St"` and new extraction provides `address="456 Oak Ave"`, existing address is preserved. This is intentional — first source wins.

**Alias matching:** If incoming name matches an alias, `matched_alias` field in result tracks which alias it was. Example:
- Existing Person: full_name="John A. Example", aliases=["EXAMPLE, JOHN A.", "J.A. Example"]
- Incoming: "EXAMPLE, JOHN A."
- Result: matched=True, matched_alias="EXAMPLE, JOHN A."

### Known Limitations

1. **No phonetic matching** (Soundex, Levenshtein distance)
   - SequenceMatcher is character-based
   - Misses "Smith" vs "Smythe" type variations
   - Mitigated by AI extraction (Claude catches semantic similarity)

2. **Case sensitivity** in SequenceMatcher
   - Normalization happens before comparison (converts to lowercase)
   - But SequenceMatcher is case-sensitive on normalized strings
   - Example: normalized "john a example" vs "JOHN A EXAMPLE" (won't match if not pre-normalized)
   - Fix: ensure normalization function is consistent

3. **Alias list is manual**
   - No automatic detection of alternate spellings
   - Fuzzy match candidates must be manually approved + added to aliases
   - This is slow for large entity sets

4. **Single case boundary**
   - Resolution happens within one case (case=case filter)
   - Cannot match across cases
   - Intentional design (cases are investigative silos)

---

## Financial Data Extraction

### How IRS 990 Financial Fields Are Extracted

**Primary source: `ai_extract_990()` in ai_extraction.py**

Uses Claude with specialized system prompt to extract:

**Officers & Compensation (Part VII):**
```json
{
  "name": "John Doe",
  "title": "President",
  "hours_per_week": 40.0,
  "reportable_compensation": 50000,
  "other_compensation": 5000,
  "is_former": false,
  "confidence": 0.90
}
```

**Part IV Checklist (Yes/No answers critical for signal rules):**
```json
{
  "line_25a_related_party_transaction": {
    "answer": "No",
    "confidence": 0.95
  },
  "line_25b_excess_benefit_transaction": {
    "answer": "No",
    "confidence": 0.95
  },
  "line_26_loan_to_officer": {
    "answer": "No",
    "confidence": 0.90
  },
  "line_27_grant_to_officer": {
    "answer": "No",
    "confidence": 0.90
  },
  "line_28a_officer_is_entity_officer": {
    "answer": "No",
    "confidence": 0.85
  },
  "line_28b_officer_family_relationship": {
    "answer": "No",
    "confidence": 0.85
  },
  "line_28c_entity_with_officer": {
    "answer": "No",
    "confidence": 0.85
  },
  "line_5_independent_contractors": {
    "answer": "Yes",
    "confidence": 0.90
  }
}
```

**Financial Totals (Income statement):**
```json
{
  "total_revenue": 500000,
  "total_expenses": 450000,
  "net_assets_eoy": 250000,
  "program_service_expenses": 400000,
  "management_expenses": 30000,
  "fundraising_expenses": 20000,
  "total_compensation": 75000,
  "number_voting_members": 5,
  "number_independent_members": 3,
  "number_employees": 12,
  "number_volunteers": 25,
  "unrelated_business_revenue": 0,
  "confidence": 0.80
}
```

**Contractors (1099 recipients):**
```json
{
  "name": "Contractor Name",
  "services": "What they were paid for",
  "compensation": 25000,
  "confidence": 0.85
}
```

**Schedule Presence Flags:**
```json
{
  "schedule_l_present": true,   # Has Schedule L (Related party transactions)
  "schedule_b_present": false,  # Has Schedule B (Contributors)
  "confidence": 0.95
}
```

### The _KEY_MAP (If Present)

Maps extraction keys to model fields. **Note: Not fully visible in ai_extraction.py read, but inferred structure:**

Example (hypothetical):
```python
_KEY_MAP = {
    "line_25a_related_party_transaction": "part_iv_related_party",
    "line_26_loan_to_officer": "part_iv_loan_to_officer",
    "total_revenue": "financial_total_revenue",
    "total_expenses": "financial_total_expenses",
}
```

Used by persistence layer to map AI proposal fields → Django model fields.

### The _save_financial_snapshot() Function

**Responsibility:** Persist extracted 990 financials to FinancialSnapshot model

**Process (inferred from code structure):**
1. Receives AIProposal with `data_type="990_financials"`
2. Extracts fields: tax_year, ein, total_revenue, total_expenses, net_assets_eoy, etc.
3. Validates field types (no strings where numbers expected)
4. Creates FinancialSnapshot record linked to Document
5. Handles linking to Organization (via EIN or case org)

**Error cases to watch:**
- Tax year not parseable → fallback to document creation year
- Revenue = 0 but expenses > 0 → log warning (possibly bad OCR)
- All fields zero → flag as low-confidence extraction

### Known Issues with Data Format Contract

**OCR-induced inconsistencies:**

1. **Financial totals don't reconcile**
   - OCR reads: revenue=500000, expenses=600000 (mathematically impossible without loss)
   - Confidence should be low (~0.65)
   - Investigator must check raw PDF

2. **Compensation fields are garbage**
   - OCR reads: reportable_compensation=999999999999 (clearly wrong)
   - AI catches this with low confidence (< 0.50)
   - Data validation layer rejects before persistence

3. **Missing tax years**
   - Organization uploaded 990s for 2019–2024
   - But only 2020, 2021, 2022 have financial data
   - Gap suggests OCR failures or missing forms
   - Investigate before accepting as fact

4. **Part IV answers misread**
   - Critical for signal rules
   - OCR often reads "Yes" as "No" (especially checked vs unchecked boxes)
   - AI extraction mitigates with confidence scoring
   - If confidence < 0.80, flag for manual review

### FinancialSnapshot Model Fields

**Typical structure (inferred):**
```python
class FinancialSnapshot(models.Model):
    document = ForeignKey(Document)
    organization = ForeignKey(Organization, null=True)

    tax_year = IntegerField()  # 2022
    ein = CharField()           # "82-4458479"

    # Income statement
    total_revenue = DecimalField()
    total_expenses = DecimalField()
    net_assets_eoy = DecimalField()

    # Breakdown
    program_service_expenses = DecimalField()
    management_expenses = DecimalField()
    fundraising_expenses = DecimalField()

    # Compensation
    total_compensation = DecimalField()
    officer_compensation_count = IntegerField()

    # Governance
    voting_members = IntegerField()
    independent_members = IntegerField()
    employees = IntegerField()
    volunteers = IntegerField()

    # Derived
    unrelated_business_revenue = DecimalField()

    # Metadata
    extraction_confidence = FloatField()
    extraction_source = CharField()  # "ai_extract_990", "regex_fallback"
    created_at = DateTimeField(auto_now_add=True)
```

---

## Data Quality Rules

When evaluating data quality, use these checks at every stage:

### Entity Quality Checks

**Red flags for persons:**

1. Name is a single stopword
   - Examples: "Date", "Sign", "The", "And"
   - Action: Delete (false positive)

2. Name is a legal structure description
   - Examples: "Domestic Limited Liability Company", "Professional Corporation"
   - Action: Delete

3. Name < 3 characters
   - Examples: "AB", "Jo"
   - Action: Delete (likely initials or OCR artifact)

4. Name is a section header or form label
   - Examples: "Section A", "Part IV", "Line 25a"
   - Action: Delete

5. Duplicate persons that should have merged
   - Example: Case has both "John A. Example" and "EXAMPLE, JOHN A." as separate records
   - Symptoms: two Person records with fuzzy_candidate between them (similarity > 0.90)
   - Action: Merge manually or re-run resolution

**Red flags for organizations:**

1. Name is all stopwords
   - Examples: "The For-Profit Limited Liability"
   - Action: Delete

2. Name is a legal designator only
   - Examples: "LLC", "Corporation", "Inc."
   - Action: Delete

3. Name contains form section header
   - Examples: "Section A Trust", "Schedule L Association"
   - Action: Delete

4. Name is an address or place
   - Examples: "123 Main Street", "Ohio County", "Example City Ohio"
   - Action: Delete or re-extract with better context

### Financial Data Quality Checks

1. **All-zero financials**
   - Check: total_revenue=0 AND total_expenses=0 AND net_assets_eoy=0
   - Verdict: Either small org or OCR failure
   - Action: If extraction_confidence < 0.75, flag for manual PDF review

2. **Revenue/expense mismatch**
   - Check: total_expenses > total_revenue + net_assets_beginning
   - Verdict: Mathematically impossible (unless org has losses)
   - Action: Review extraction confidence; if < 0.70, re-extract

3. **Missing years in sequence**
   - Check: Case has 990s uploaded for years 2019, 2020, 2021, 2023, 2024 (missing 2022)
   - Verdict: Either form missing or extraction failed for 2022
   - Action: Search for 2022 990 in uploaded documents; if found, re-run extraction

4. **Negative values where impossible**
   - Check: total_revenue < 0 OR total_expenses < 0
   - Verdict: OCR error or AI hallucination
   - Action: If confidence < 0.80, delete financial snapshot and re-extract

5. **Compensation exceeds revenue**
   - Check: total_compensation > total_revenue * 0.40
   - Verdict: Suspicious (but possible for restricted-revenue orgs)
   - Action: Log warning; investigator reviews manually

6. **Officer count mismatch**
   - Check: Part VII lists 3 officers, but FinancialSnapshot.officer_compensation_count=5
   - Verdict: Possible duplicate extraction or incomplete AI parsing
   - Action: Re-run ai_extract_990()

### Document Quality Checks

1. **Pending OCR (status=PENDING)**
   - Symptom: `ocr_status=PENDING` but created_at > 24 hours ago
   - Verdict: Background OCR task failed or stalled
   - Action: Retry OCR; if fails again, mark as FAILED + investigate

2. **Empty text despite completion**
   - Symptom: `ocr_status=COMPLETED` but `extracted_text=""` or `extracted_text=None`
   - Verdict: Tesseract produced zero output (blank scanned PDF?)
   - Action: Inspect source PDF; if truly blank, mark as FAILED

3. **Wrong document type**
   - Symptom: Document filename is "Form990_2022.pdf" but doc_type="DEED"
   - Verdict: Classifier error
   - Action: Manually update doc_type; re-run extraction

4. **Metadata missing**
   - Symptom: pdf_metadata is empty dict despite extraction succeeding
   - Verdict: Metadata extraction failed (rare but possible)
   - Action: Re-run extract_pdf_metadata(); inspect PDF for corruption

---

## Data Cleanup Operations

When cleaning up bad data, follow this protocol:

### 1. Query the API First
Always understand the current state before making changes:
```python
# Example: Find all persons named "Section"
GET /api/cases/{case_id}/persons?name__icontains=section

# Example: Find all orgs with no EIN
GET /api/cases/{case_id}/organizations?ein=""

# Example: Find all financial snapshots with confidence < 0.70
GET /api/cases/{case_id}/financial_snapshots?confidence_lt=0.70
```

### 2. Document What Will Change
Before deletion/modification, save a snapshot:
```python
# Export to CSV for audit trail
Case.objects.filter(id=case_id).export_persons_csv("persons_before_cleanup.csv")
```

### 3. Entity Cleanup: Delete Bad Entities

**Before deleting, check:**
- Is this person referenced by any Detection records?
- Is this person referenced by any Signal hit?
- Is this org referenced by any PersonOrganization links?

If yes, you MUST:
- Delete/update the referencing records first
- OR preserve the entity + mark as archived instead

**Safe delete flow:**
```python
# Step 1: Check references
person = Person.objects.get(id=uuid)
detections = Detection.objects.filter(associated_person=person)
signals = SignalHit.objects.filter(data__contains={'person_id': str(person.id)})

if detections.count() > 0 or signals.count() > 0:
    print(f"UNSAFE: {detections.count()} detections, {signals.count()} signals")
    # Don't delete!
else:
    # Step 2: Safe to delete
    person.delete()
```

### 4. Financial Re-extraction: Reprocess Existing 990s

When you fix the extraction logic (e.g., improve AI prompt), reprocess:

```python
# Get all 990 documents in case
docs = Document.objects.filter(case=case_id, doc_type="990")

for doc in docs:
    # Step 1: Delete old financial snapshots
    FinancialSnapshot.objects.filter(document=doc).delete()

    # Step 2: Re-run AI extraction
    result = ai_extract_990(doc.extracted_text)

    # Step 3: Validate + persist
    if result.error:
        print(f"Failed to re-extract {doc.id}: {result.error}")
    else:
        _save_financial_snapshot(doc, result)
```

### 5. Run API Health Check After Cleanup

Always verify data integrity post-cleanup:
```python
# Check for dangling references
GET /api/cases/{case_id}/health_check

# Expected response:
{
    "status": "healthy",
    "orphaned_documents": 0,
    "persons_without_names": 0,
    "financial_snapshots_with_negative_revenue": 0,
    "fuzzy_candidates_exceeding_100": false
}
```

If health check fails, rollback from backup.

---

## Building New Parsers

When building a parser for a new data source (e.g., new 990 section, new document type):

### 1. Understand the Source Format

**For 990s:** Read IRS instructions and sample forms
- Part IV: Checklist (Yes/No questions)
- Part VII: Officers and directors (table with name, title, hours, compensation)
- Schedule L: Transactions with interested persons (table)
- Schedule B: Schedule of contributors (if present)

**For deeds:** Understand legal document structure
- Grantor vs grantee
- Consideration (price)
- Legal description (parcel info)
- Recording information (filing references)

### 2. Collect Sample Documents

Use existing uploaded documents:
```python
# Get all 990s uploaded for a case
samples = Document.objects.filter(
    case=case_id,
    doc_type="990"
).order_by('-created_at')[:5]

# Extract text for analysis
for doc in samples:
    print(f"\n=== {doc.filename} ===")
    print(doc.extracted_text[:2000])  # First 2000 chars
```

### 3. Extract Patterns

Read raw extracted text. Identify patterns:

**Example 990 Part VII (officers):**
```
PART VII. OFFICERS, DIRECTORS, TRUSTEES, AND KEY EMPLOYEES
Name and Title                  Average Hours    Reportable     Other
                               per week (List   Compensation   Comp.
                               any hours for    (Forms W-2/
                               professional     1099-MISC)
JOHN DOE                            40            $50,000        $0
JANE SMITH                          30            $35,000        $5,000
```

**Patterns to extract:**
- Name: ALL-CAPS after line number
- Title: text after name on same line
- Hours: number in second column
- Compensation: currency value in third column
- Other comp: currency value in fourth column

### 4. Write Regex or Structured Extraction Logic

```python
def parse_990_officers(text: str) -> list[dict]:
    """Extract officers from 990 Part VII."""

    # Look for "PART VII" section marker
    part_vii_match = re.search(r'PART VII.*?OFFICERS', text, re.IGNORECASE)
    if not part_vii_match:
        return []

    # Extract section from Part VII to next part
    start = part_vii_match.end()
    next_part = re.search(r'PART VIII', text[start:], re.IGNORECASE)
    end = start + next_part.start() if next_part else len(text)
    part_vii_text = text[start:end]

    # Split by likely officer rows (NAME pattern)
    officers = []
    for line in part_vii_text.split('\n'):
        match = re.search(
            r'([A-Z][A-Z\s]+)\s+(\d+)\s+\$?([\d,]+)\s+\$?([\d,]+)',
            line
        )
        if match:
            officers.append({
                'name': match.group(1).strip(),
                'hours': int(match.group(2)),
                'compensation': int(match.group(3).replace(',', '')),
                'other_comp': int(match.group(4).replace(',', ''))
            })

    return officers
```

### 5. Test Against ALL Sample Documents

**Do NOT test against one sample. Test all:**

```python
# Test parser against all samples
for doc in samples:
    officers = parse_990_officers(doc.extracted_text)
    print(f"{doc.filename}: {len(officers)} officers extracted")
    if len(officers) == 0:
        print(f"  WARNING: No officers found!")
        # Inspect sample
        print(doc.extracted_text[1000:2000])
```

**Expected outcome:**
- Should extract 1-10 officers per 990
- Should handle OCR noise (misread characters)
- Should gracefully handle missing sections (return empty list, not crash)

### 6. Handle OCR Noise

OCR introduces systematic errors. Account for:

1. **Missing spaces:** "JOHNDOE" instead of "JOHN DOE"
   - Looser regex: `[A-Z]+(?:\s+[A-Z]+)*`

2. **Misread characters:** "0" as "O", "l" as "1", "S" as "5"
   - Apply fuzzy matching before and after extraction
   - Use AI extraction as second tier (Claude handles OCR better)

3. **Line breaks in wrong places:** "JOHN\nDOE" instead of "JOHN DOE"
   - Normalize whitespace: `text.replace('\n', ' ')`

4. **Table alignment issues:** Amounts shifted to wrong column
   - Extract by position (column index) rather than regex
   - Example: extract compensation from column 60-70 (character range)

### 7. Return Structured Data in Expected Format

Match the format that persistence layer expects:

```python
# Bad format (too loose)
return [{'name': 'John Doe', 'data': 'lots of stuff'}]

# Good format (matches FinancialSnapshot schema)
return [
    {
        'name': 'John Doe',
        'title': 'President',
        'hours_per_week': 40,
        'reportable_compensation': 50000,
        'other_compensation': 0,
        'confidence': 0.85
    }
]
```

### 8. Add Data Validation

Reject extractions that don't look plausible:

```python
def validate_officer(officer: dict) -> bool:
    """Check if extracted officer looks real."""

    # Name must exist and not be stopword
    if not officer.get('name') or officer['name'].lower() in _PERSON_STOPWORDS:
        return False

    # Hours must be 0-168 (hours in week)
    hours = officer.get('hours_per_week', 0)
    if not (0 <= hours <= 168):
        return False

    # Compensation must be non-negative
    comp = officer.get('reportable_compensation', 0)
    if comp < 0:
        return False

    # Compensation > $1M is suspicious (but possible)
    if comp > 1_000_000:
        logger.warning(f"Unusually high compensation: {comp}")

    return True
```

---

## Known Issues

### Current Limitations

1. **OCR-induced false positives still escape stopword filters**
   - Reason: Some legitimate org names match boilerplate patterns
   - Mitigation: Fuzzy match review + AI extraction layer
   - Long-term fix: Improve stopword prioritization (weights vs hard rejects)

2. **Entity resolution is slow on large case entity sets**
   - For 1000+ existing persons/orgs, resolution can take 10+ seconds
   - Reason: SequenceMatcher compares every incoming vs every existing (O(n²))
   - Mitigation: Batch process in background; cache normalized names
   - Long-term fix: Switch to rapidfuzz with vectorized matching

3. **Fuzzy match threshold too strict**
   - Threshold 0.75 misses some real matches (e.g., "Robert" vs "Bob")
   - Reason: Character-based similarity doesn't capture semantic similarity
   - Mitigation: AI extraction catches these
   - Long-term fix: Add phonetic similarity layer

4. **AI extraction cost/latency**
   - Claude API calls ~1–2 seconds per document
   - Cost: $0.01–0.05 per document (adds up for large cases)
   - Mitigation: Cache aggressively; skip AI if regex confidence > 0.90
   - Long-term fix: Local model (llama) or batch API calls

5. **Financial data extraction unreliable on OCR'd 990s**
   - Part IV checklist: OCR can't reliably read checked boxes
   - Part VII compensation: Numbers often misread or shifted
   - Reason: Tables don't survive OCR well
   - Mitigation: AI extraction with low confidence flags; investigator review
   - Long-term fix: Template matching (align to IRS form template before extraction)

### Improvement Opportunities

1. **Add phonetic similarity layer** (SoundEx, Metaphone)
   - Would catch "Smith" vs "Smythe" variant names
   - Cost: minimal; use only for fuzzy candidates

2. **Implement batch AI extraction**
   - Instead of API call per document, batch 10–20 documents per call
   - Reduce latency 5x; reduce cost 3x

3. **Cache normalized entity names**
   - Pre-compute normalization for all existing entities at case startup
   - Eliminate repeated normalization during resolution loop

4. **Switch to rapidfuzz**
   - 100x faster than difflib for large sets
   - Drop-in replacement; same interface
   - Cost: one new dependency

5. **Add document-level quality scoring**
   - Score: (entities_extracted / expected_for_doc_type) * confidence_avg
   - Flag low-score documents for investigator review before investigation starts

6. **Template-based 990 extraction**
   - Align OCR'd 990 to IRS form structure (known positions for Part VII, Part IV)
   - Extract by fixed column positions rather than OCR text
   - Dramatically improves accuracy on scanned forms

---

## Performance Considerations

### OCR is Slow

- **Direct extraction (digital PDF):** ~0.1 seconds
- **Tesseract OCR (scanned PDF):** 5–15 seconds per document
- **Per page:** 60-second timeout (environment-configurable via `OCR_PAGE_TIMEOUT`)
- **Total timeout:** 300 seconds max per document (`OCR_TOTAL_TIMEOUT`)

**Optimization:**
- Don't re-OCR unnecessarily
- If `ocr_status=COMPLETED`, skip re-run
- For large documents, consider pre-processing: crop to text-heavy areas, deskew, enhance contrast

### Entity Resolution with Fuzzy Matching

- **Small sets (< 100 entities):** < 100 ms
- **Large sets (1000+ entities):** 10+ seconds
- **Algorithm:** SequenceMatcher is O(n²) where n = existing entity count

**Optimization:**
- Batch resolution (combine 10 documents' extractions before resolving)
- Cache normalized names (don't re-normalize in loop)
- Use rapidfuzz library (100x faster)
- Implement exact-match cache (fast path for common names)

### AI Extraction is Most Expensive

- **Cost:** ~$0.01–0.05 per document (depends on document length)
- **Latency:** 1–2 seconds per API call
- **Per token:** Input ~$0.003/1M, Output ~$0.015/1M (Claude 3.5 Sonnet pricing)

**Optimization:**
- Cache aggressively: if rule-based extraction is high-confidence (> 0.95), skip AI
- Batch API calls: combine 10 documents per request (if API supports)
- Truncate input: 15k char limit controls token usage
- Async processing: run AI extraction in background, don't block upload request
- Monitor token usage: `input_tokens`, `output_tokens` in AIExtractionResult

### Database Queries

- Resolution loop issues 1 query per entity type (list all existing persons/orgs)
- For 1000+ entities, this is fast (< 100 ms)
- Batch operations (bulk_create, bulk_update) 10x faster than individual saves

**Optimization:**
- Use QuerySet.values() for read-only lookups
- Denormalize frequently-accessed fields (e.g., cache "org count by case")
- Index on (case_id, full_name) for person lookups

---

## Quick Reference: Key Files

| File | Responsibility |
|------|-----------------|
| `extraction.py` | PDF text extraction (direct + OCR) |
| `entity_extraction.py` | Rule-based entity extraction (regex) |
| `ai_extraction.py` | Claude-powered entity proposal layer |
| `entity_resolution.py` | Fuzzy matching + deduplication |
| `entity_normalization.py` | Name standardization (not fully read) |
| `models.py` | Document, Person, Organization, FinancialSnapshot (not fully read) |
| `signal_rules.py` | Fraud detection rules (downstream consumer) |
| `data_quality.py` | Validation before persistence (downstream) |

---

## Quick Reference: Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `_MIN_MEANINGFUL_LENGTH` | 100 chars | Threshold for "digital PDF has text" |
| `MAX_SYNC_OCR_BYTES` | 30 MB | Files larger skip sync OCR |
| `_OCR_DPI` | 200 | Resolution for rendering pages |
| `_OCR_PAGE_TIMEOUT_SECONDS` | 60 | Max seconds per page OCR |
| `_OCR_TOTAL_TIMEOUT_SECONDS` | 300 | Max seconds total per document |
| `FUZZY_REVIEW_THRESHOLD` | 0.75 | Min similarity for fuzzy candidate |
| `FUZZY_HIGH_CONFIDENCE_THRESHOLD` | 0.92 | Very likely same entity |
| `MAX_TOKENS` (AI) | 4,096 | Max response size for Claude |
| `TEMPERATURE` (AI) | 0.0 | Deterministic extraction (no creativity) |

---

## You Own This

The extraction pipeline is the foundation. Every downstream system (signals, detections, investigator UI) depends on clean, accurate data from here. When data quality breaks, the entire investigation breaks.

Monitor. Optimize. Clean. Validate. Improve.
