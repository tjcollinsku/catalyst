# Backend Engineer — Specialist Briefing Book

## Your Role

You own the Django backend: models, views, serializers, signal rules, connectors, and the AI proxy layer. You write clean, well-tested Python code that handles edge cases and follows Django best practices. You understand the data model deeply and know how changes in one layer affect others. When a document lands in the system, you trace how it flows through extraction, entity resolution, signal evaluation, and storage. When the frontend needs new data, you design the endpoint, validate inputs, and return properly formatted JSON.

## Project Quick Facts

- **Framework**: Django 5.x
- **Database**: PostgreSQL
- **Code Location**: `backend/investigations/`
- **Deployment**: Railway with Gunicorn (120s timeout)
- **Models**: 21 entities with UUID primary keys
- **API Endpoints**: 45 total (38 JSON, 7 legacy HTML)
- **Signal Rules**: 29 rules (SR-001 through SR-029)
- **External Connectors**: 6 (ProPublica, IRS, Ohio SOS, Ohio AOS, County Auditor, County Recorder)
- **AI Integration**: Claude API via custom proxy layer with caching and rate limiting

## Architecture Overview

### File Organization

The investigations app is the core. All backend logic lives here:

```
backend/
├── investigations/
│   ├── models.py              # 21 models, UUID primary keys
│   ├── views.py               # 4400 lines, organized by comment sections
│   ├── signal_rules.py        # 29 signal detection rules
│   ├── entity_extraction.py   # NLP pipeline for entity identification
│   ├── ai_proxy.py            # Claude API wrapper with caching/rate limiting
│   ├── propublica_connector.py
│   ├── irs_connector.py
│   ├── ohio_sos_connector.py  # Ohio Secretary of State
│   ├── ohio_aos_connector.py  # Ohio Attorney General
│   ├── county_auditor_connector.py
│   ├── county_recorder_connector.py
│   ├── admin.py
│   ├── apps.py
│   └── tests/
│       └── api_health_check.py
├── catalyst/
│   ├── settings.py            # Environment-based configuration
│   ├── urls.py                # Root URL dispatcher
│   └── wsgi.py
├── Dockerfile                 # Gunicorn configuration (120s timeout)
└── manage.py
```

### Views.py Architecture

At ~4400 lines, `views.py` is large but meticulously organized with comment headers:

```python
# ============================================================================
# Document endpoints
# ============================================================================

# ============================================================================
# Signal endpoints
# ============================================================================

# ============================================================================
# Detection & Finding endpoints
# ============================================================================

# ============================================================================
# Entity endpoints
# ============================================================================

# ============================================================================
# Connector endpoints
# ============================================================================

# ============================================================================
# AI endpoints
# ============================================================================

# ============================================================================
# Health & Status endpoints
# ============================================================================
```

Use these headers to navigate. Each section groups related endpoints together. Always maintain this pattern when adding new endpoints.

## Data Model

### Entity Relationships

The Catalyst data model revolves around **Case** as the root. Every record belongs to a case.

```
Case (root entity)
│
├── Document
│   ├── extracted_text (TextField, nullable)
│   ├── ocr_status (CharField: pending/completed/failed)
│   ├── doc_type (CharField: IRS_990, SOS_FILING, DEED, BANK_STATEMENT, etc.)
│   └── sha256_hash (unique)
│
├── Signal (anomaly detection results)
│   ├── severity (CharField: CRITICAL, HIGH, MEDIUM, LOW)
│   ├── signal_type (CharField: SELF_DEALING, REVENUE_ANOMALY, etc.)
│   ├── description (TextField)
│   ├── confirmed (BooleanField, default=False)
│   └── status (CharField: open/acknowledged/resolved)
│       │
│       └── Detection (promoted signal with formal status)
│           └── Finding (investigator-written narrative & analysis)
│
├── Entity hierarchy (polymorphic):
│   ├── Person
│   │   ├── full_name
│   │   ├── date_of_birth (nullable)
│   │   └── ssn (encrypted, nullable)
│   ├── Organization
│   │   ├── legal_name
│   │   ├── ein (nullable)
│   │   ├── formation_date (nullable)
│   │   └── industry (nullable)
│   ├── Property
│   │   ├── address
│   │   ├── county
│   │   ├── parcel_id (nullable)
│   │   └── last_sale_price (nullable)
│   └── FinancialInstrument
│       ├── instrument_type (loan, mortgage, line_of_credit, etc.)
│       ├── amount
│       └── terms (nullable)
│
├── Junction Tables (many-to-many):
│   ├── PersonOrganization (person relates to organization with role)
│   ├── PropertyTransaction (tracks ownership/transaction history)
│   ├── EntitySignal (links entities to signals that mention them)
│   └── RelationshipEdge (general graph structure for entity connections)
│
├── FinancialSnapshot (annual financial summaries from IRS 990)
│   ├── year (IntegerField)
│   ├── organization (FK to Organization)
│   ├── total_revenue
│   ├── total_expenses
│   ├── total_assets
│   ├── total_liabilities
│   ├── related_party_transactions (JSONField)
│   └── extracted_from_document (FK to Document)
│
├── Referral (formal referral to authorities)
│   ├── referral_type (agency type)
│   ├── status (pending/sent/acknowledged)
│   ├── referred_entity (GenericFK to any entity)
│   └── narrative (text explaining why)
│
└── InvestigatorNote (free-form annotations)
    ├── author (FK to User)
    ├── text (TextField)
    ├── is_internal (BooleanField)
    └── related_to (GenericFK to any model)
```

### Key Design Patterns

1. **UUID Primary Keys**: Every model uses `models.UUIDField(primary_key=True, default=uuid.uuid4)`
2. **Timestamps**: Every model has `created_at` and `updated_at` (auto_now_add, auto_now)
3. **Case Ownership**: All core entities (Document, Signal, Detection, Finding, Entity) have `case = models.ForeignKey(Case, on_delete=models.CASCADE)`
4. **Soft Deletes**: Use `is_deleted` BooleanField (default=False) rather than hard deletes for audit trail
5. **JSON Fields**: Use `models.JSONField()` for flexible data (related_party_transactions, extraction metadata, etc.)

## API Patterns

### The Standard Endpoint Template

Every collection endpoint follows this pattern:

```python
@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_some_collection(request, pk):
    """
    GET: List all SomeModel for the case.
    POST: Create a new SomeModel for the case.
    """
    case = get_object_or_404(Case, pk=pk)

    if request.method == "GET":
        # Parse pagination params
        limit = int(request.GET.get("limit", 50))
        offset = int(request.GET.get("offset", 0))

        # Build queryset with any filters
        queryset = SomeModel.objects.filter(case=case).order_by("-created_at")
        total = queryset.count()

        # Slice for pagination
        items = queryset[offset:offset+limit]

        # Serialize
        data = [item.to_dict() for item in items]

        return JsonResponse({
            "count": total,
            "limit": limit,
            "offset": offset,
            "next": f"/api/cases/{pk}/some_collection/?limit={limit}&offset={offset+limit}" if offset+limit < total else None,
            "results": data
        })

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # Validate required fields
        if not body.get("field_name"):
            return JsonResponse({"error": "field_name is required"}, status=400)

        # Create and save
        instance = SomeModel(
            case=case,
            field_name=body["field_name"],
            # ... more fields
        )
        instance.save()

        return JsonResponse(instance.to_dict(), status=201)
```

### Critical Endpoint Rules

1. **@csrf_exempt on all POST endpoints** — The frontend is a React SPA at a different domain. Without this, you get 403 Forbidden.
2. **Always use `get_object_or_404(Case, pk=pk)`** — Validates case exists and returns 404 if not.
3. **Always paginate collection responses** — Include `count`, `limit`, `offset`, `next`, and `results` keys.
4. **Always parse request.body as JSON** — Use `json.loads(request.body)` and catch `JSONDecodeError`.
5. **Always validate input** — Check required fields exist before creating/updating.
6. **Always return proper HTTP status codes** — 200 for GET, 201 for POST, 400 for bad input, 404 for not found, 500 for server errors.
7. **Always include error messages** — Return `{"error": "human-readable message"}` on failure.
8. **Always use raw pk in URLs** — URLs are `/api/cases/{pk}/endpoint/`, not `/api/cases/{case_id}/endpoint/`.

### Serialization Pattern

Models should have a `to_dict()` method for consistent JSON output:

```python
class SomeModel(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE)
    # ... fields ...

    def to_dict(self):
        return {
            "id": str(self.pk),
            "case_id": str(self.case_id),
            "field_name": self.field_name,
            # ... other fields ...
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
```

Convert all UUIDs to strings in JSON output. Always use `.isoformat()` for datetime fields.

## Signal Rules

Signal rules are the anomaly detection engine. They live in `signal_rules.py` and are the first line of detecting potential financial misconduct.

### How They Work

Rules are evaluated in three contexts:
1. When a document is uploaded and processed
2. When the `reevaluate-signals` endpoint is called
3. When new entity data (organization, person) is saved

Each rule is a function that takes a `case` object and returns a list of `Signal` objects.

### Rule Anatomy

```python
def sr_001_nonprofit_with_no_charitable_activity(case):
    """
    SR-001: Detect nonprofits with zero charitable activity expense.

    Searches for recent IRS 990 filings showing $0 or near-zero charitable
    spending relative to revenue raised.

    Severity: HIGH
    Signal Type: REVENUE_ANOMALY
    """
    signals = []

    # Get financial snapshots for this case's organizations
    for snapshot in FinancialSnapshot.objects.filter(
        organization__in=case.entities.filter(entity_type='organization')
    ).order_by('-year')[:3]:  # Last 3 years

        # Check for anomaly
        charitable_spending = snapshot.charitable_activity_expense or 0
        total_revenue = snapshot.total_revenue or 0

        if total_revenue > 100000 and charitable_spending < total_revenue * 0.10:
            signal = Signal(
                case=case,
                severity="HIGH",
                signal_type="REVENUE_ANOMALY",
                description=f"Organization {snapshot.organization.legal_name} reported "
                           f"${total_revenue:,.0f} in revenue but only ${charitable_spending:,.0f} "
                           f"in charitable spending ({snapshot.year}).",
                # ... other fields ...
            )
            signals.append(signal)

    return signals
```

### Rules List

Rules are numbered SR-001 through SR-029. Current rules detect:

- Revenue anomalies (extreme year-over-year changes, suspiciously low charitable spending)
- Self-dealing (officers/board members with related party transactions)
- Duplicate/shell entities (organizations with identical addresses, officers)
- Related party abuse (excessive related-party service fees)
- Property flipping (rapid buy/sell cycles)
- Loan concentration (single lender over 50% of debt)
- Officer compensation spikes (unexplained salary increases)
- Conflict of interest (officer owns supplier organization)
- State filing discrepancies (IRS says one thing, state says another)
- Geographic clustering (too many entities in single county)

See `signal_rules.py` for the complete list with thresholds and logic.

### Adding a New Rule

1. **Write the function** in `signal_rules.py`:
   - Follow the naming convention `sr_NNN_short_description`
   - Include a detailed docstring with severity and signal_type
   - Return a list of Signal objects
   - Use existing rules as templates

2. **Register it** in the RULES list at the bottom of `signal_rules.py`:
   ```python
   RULES = [
       sr_001_nonprofit_with_no_charitable_activity,
       # ... others ...
       sr_030_new_rule,  # Add your new rule
   ]
   ```

3. **Write tests** in `tests/test_signal_rules.py`:
   ```python
   def test_sr_030_fires_on_expected_input():
       case = create_test_case()
       # Set up condition that triggers rule
       signals = sr_030_new_rule(case)
       assert len(signals) == 1
       assert signals[0].severity == "HIGH"
   ```

4. **Update documentation**:
   - Add entry to CURRENT_STATE.md signal count
   - Document threshold values in the docstring
   - Add a link to test case in the rule docstring

### Important: Rule Performance

Rules run synchronously when documents are processed. Keep rules fast:
- Use `.select_related()` and `.prefetch_related()` to minimize queries
- Limit date ranges (last 3-5 years, not all history)
- Early exit when possible
- Cache expensive lookups

## The Extraction Pipeline

When a document is uploaded, it follows this multi-stage pipeline:

### Stage 1: Upload & Storage

```python
# API receives multipart form upload
# File is saved to media/ directory with UUID as name
# SHA-256 hash is computed and stored in document.sha256_hash
# Status set to pending
```

### Stage 2: Classification

```python
# doc_type is determined by filename extension or content inspection
# Possible types: IRS_990, SOS_FILING, DEED, BANK_STATEMENT, TAX_RETURN, etc.
# doc_type is used to route the document to appropriate extractors
```

### Stage 3: Text Extraction

For IRS 990 and common formats, try two methods:
1. **Direct PDF text extraction** — Fast, works if PDF has embedded text
2. **Tesseract OCR** — Slower but works for scans

Result stored in `document.extracted_text`. Status set to completed or failed.

### Stage 4: Entity Extraction

The entity extraction pipeline in `entity_extraction.py`:

```python
def extract_entities(text):
    """
    Extract persons, organizations, and properties from unstructured text.

    Uses spaCy for NER + custom pattern matching + stopword filtering.
    Returns list of extracted entities with confidence scores.
    """
    # 1. Run spaCy NER
    doc = nlp(text)

    # 2. Extract named entities
    entities = []
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            # Filter stopwords (common false positives)
            if ent.text not in PERSON_STOPWORDS:
                entities.append({"type": "person", "text": ent.text, "confidence": 0.9})
        elif ent.label_ == "ORG":
            if ent.text not in ORG_STOPWORDS:
                entities.append({"type": "organization", "text": ent.text, "confidence": 0.9})

    # 3. Pattern-based extraction
    # Phone numbers, addresses, EINs, SSNs
    addresses = extract_addresses(text)
    entities.extend(addresses)

    return entities
```

All extracted entities are created in the database with `extracted=True` and `source_document=document`.

### Stage 5: Entity Resolution

Fuzzy matching to merge duplicates:

```python
# For each extracted entity, check if similar entity already exists
# Use Levenshtein distance + thresholds:
#   - Person: 85% name match
#   - Organization: 80% name match
#   - Address: 90% exact match

# If match found, mark extracted entity as duplicate and link to existing entity
# If no match, create new entity
```

### Stage 6: Signal Evaluation

All 29 rules run against the case:

```python
from investigations.signal_rules import RULES

# In views.py, after extraction:
for rule_func in RULES:
    signals = rule_func(case)
    for signal in signals:
        signal.save()

# Investigators can re-run via /api/cases/{pk}/reevaluate-signals/
```

### Stage 7: Financial Extraction (IRS 990 only)

For IRS 990 documents, specific fields are parsed and stored in `FinancialSnapshot`:

```python
def _save_financial_snapshot(organization, document, irs990_data):
    """
    Parse IRS 990 JSON and save annual snapshot.

    The IRS connector returns structured JSON with keys like:
    - "total_revenue"
    - "total_expenses"
    - "total_assets"
    - "total_liabilities"
    - "year"

    Map these to FinancialSnapshot fields.
    """
    _KEY_MAP = {
        "total_revenue": "total_revenue",
        "total_expenses": "total_expenses",
        # ... more mappings ...
    }

    snapshot = FinancialSnapshot(
        organization=organization,
        extracted_from_document=document,
        year=irs990_data["year"],
    )

    for source_key, target_field in _KEY_MAP.items():
        if source_key in irs990_data:
            setattr(snapshot, target_field, irs990_data[source_key])

    snapshot.save()
```

## External Connectors

Catalyst integrates with 6 external data sources. Each connector handles authentication, rate limiting, and data normalization.

### ProPublica (propublica_connector.py)

**Purpose**: Organization profiles and nonprofit news

**Key Functions**:
- `search_organizations(query)` — Search for nonprofits by name
- `get_organization_details(ein)` — Detailed org profile

**Returns**: Standardized dict with keys: name, ein, state, city, revenue, expenses

**Rate Limit**: 1 request per second

### IRS Connector (irs_connector.py)

**Purpose**: IRS 990 filings and financial data

**Key Functions**:
- `search_form_990(ein)` — Find all 990 filings for organization
- `fetch_form_990(filing_id)` — Get specific 990 filing

**Returns**: Structured JSON with annual financials, related-party transactions, key personnel

**Rate Limit**: 100 requests per hour

### Ohio Secretary of State (ohio_sos_connector.py)

**Purpose**: Corporate registrations, officer names, filing status

**Key Functions**:
- `search_organization(name)` — Search by legal name
- `get_incorporation_details(entity_id)` — Full incorporation record

**Returns**: Officer names, formation date, current status, principal address

**Rate Limit**: 500 requests per hour

### Ohio Attorney General (ohio_aos_connector.py)

**Purpose**: Complaint data, enforcement actions

**Key Functions**:
- `search_complaints(organization_name)` — Find all complaints
- `get_complaint_details(complaint_id)` — Full complaint record

**Returns**: Complaint text, parties, date, disposition

**Rate Limit**: 1000 requests per hour

### County Auditor (county_auditor_connector.py)

**Purpose**: Real property records, assessed values, tax payments

**Key Functions**:
- `search_property(address)` — Find property by address
- `get_property_details(parcel_id)` — Full property record

**Returns**: Owner, address, assessed value, tax history

**Rate Limit**: 100 requests per hour per county

### County Recorder (county_recorder_connector.py)

**Purpose**: Property transactions, deeds, liens, mortgages

**Key Functions**:
- `search_recorded_documents(property_id)` — Get transaction history
- `get_document_details(document_id)` — Full document record

**Returns**: Document type, parties, amount, recording date

**Rate Limit**: 100 requests per hour per county

### Using Connectors

Connectors are called from views.py in dedicated "connector endpoints":

```python
@csrf_exempt
@require_http_methods(["POST"])
def api_case_connector_lookup(request, pk):
    """
    POST body: {
        "connector": "propublica",
        "action": "search_organizations",
        "params": {"query": "American Red Cross"}
    }
    """
    case = get_object_or_404(Case, pk=pk)
    body = json.loads(request.body)

    connector_name = body.get("connector")
    action = body.get("action")
    params = body.get("params", {})

    # Import and call the appropriate connector
    if connector_name == "propublica":
        from investigations.propublica_connector import search_organizations
        result = search_organizations(**params)
    elif connector_name == "irs":
        from investigations.irs_connector import search_form_990
        result = search_form_990(**params)
    # ... etc ...

    return JsonResponse({"result": result})
```

## AI Proxy Layer (ai_proxy.py)

The AI integration with Claude API is isolated in `ai_proxy.py`. This module handles authentication, request formatting, response parsing, caching, and rate limiting.

### Four Claude API Functions

#### 1. **summarize_document(document)**

Reads extracted text and returns a concise summary (150-300 words).

```python
def summarize_document(document):
    """
    Summarize document extracted text using Claude.

    - Caches results by document SHA256 hash
    - Returns 3-5 key points
    - Timeout: 30 seconds
    """
    cache_key = f"doc_summary:{document.sha256_hash}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"Summarize this document in 3-5 key points:\n\n{document.extracted_text}"
        }]
    )

    result = response.content[0].text
    cache.set(cache_key, result, timeout=86400*30)  # 30-day cache
    return result
```

#### 2. **analyze_signal(signal)**

Analyzes why a signal fired and suggests investigation direction.

```python
def analyze_signal(signal):
    """
    Provide investigative context for a signal.

    Returns:
    {
        "context": "Why this signal matters",
        "next_steps": ["Action 1", "Action 2"],
        "risk_score": 0-100
    }
    """
    case = signal.case
    entities_mentioned = EntitySignal.objects.filter(signal=signal)

    context_text = f"""
    Signal: {signal.signal_type}
    Severity: {signal.severity}
    Description: {signal.description}

    Entities involved:
    {[str(es.entity) for es in entities_mentioned]}

    Case context:
    {case.title}
    {case.description}
    """

    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": f"Analyze this financial anomaly and suggest next steps:\n\n{context_text}"
        }]
    )

    return json.loads(response.content[0].text)
```

#### 3. **generate_finding_draft(signal)**

Generates a narrative draft for investigators to refine into formal findings.

```python
def generate_finding_draft(signal):
    """
    Generate a narrative draft for a finding based on signal.

    Draft includes:
    - What happened (facts)
    - Why it matters (implications)
    - Supporting evidence references
    """
    # ... Claude call to generate narrative ...
```

#### 4. **flag_document_for_review(document)**

Uses Claude to flag documents that look suspicious or non-standard.

```python
def flag_document_for_review(document):
    """
    Use Claude to identify documents needing manual review.

    Returns:
    {
        "should_review": true/false,
        "reason": "Document text is garbled / scanned image quality is poor",
        "confidence": 0.0-1.0
    }
    """
    # ... Claude call to analyze document quality ...
```

### Caching Strategy

- **summarize_document**: Cached 30 days (keyed by SHA256 hash)
- **analyze_signal**: No caching (signals may be updated)
- **generate_finding_draft**: No caching (each draft is unique)
- **flag_document_for_review**: Cached 7 days (keyed by document ID)

### Rate Limiting

All Claude API calls are rate-limited to 3 concurrent requests. Excess requests queue.

```python
from threading import Semaphore

_claude_semaphore = Semaphore(3)

def _call_claude(messages):
    with _claude_semaphore:
        return client.messages.create(
            model="claude-3-5-sonnet-20241022",
            messages=messages,
            max_tokens=800
        )
```

### ID Prefix Helper

The frontend sends composite IDs like `"signal-{uuid}"`. Always use `_strip_id_prefix()`:

```python
def _strip_id_prefix(composite_id):
    """
    Frontend sends: "signal-550e8400-e29b-41d4-a716-446655440000"
    Returns UUID: "550e8400-e29b-41d4-a716-446655440000"
    """
    if "-" in composite_id:
        parts = composite_id.split("-", 1)
        if len(parts) == 2:
            return parts[1]
    return composite_id
```

Use this in AI endpoints:

```python
@csrf_exempt
@require_http_methods(["POST"])
def api_signal_ai_analysis(request, pk, signal_id):
    case = get_object_or_404(Case, pk=pk)
    signal_uuid = _strip_id_prefix(signal_id)
    signal = get_object_or_404(Signal, pk=signal_uuid, case=case)
    # ... rest of endpoint ...
```

## Settings & Configuration

Django settings live in `catalyst/settings.py` and read from environment variables.

### Required Environment Variables (Production)

- `DATABASE_URL` — PostgreSQL connection string (set by Railway)
- `SECRET_KEY` — Django secret key (set by Railway, ~50 random chars)
- `ANTHROPIC_API_KEY` — Claude API key (set in Railway secrets)
- `DJANGO_SETTINGS_MODULE=catalyst.settings`
- `PORT` — Server port (set by Railway, default 8000)
- `DEBUG=False` — Always False in production

### Development Environment

```bash
# .env file (never commit!)
DEBUG=True
SECRET_KEY=dev-key-change-me
DATABASE_URL=postgresql://user:password@localhost:5432/catalyst_dev
ANTHROPIC_API_KEY=sk-ant-...
```

### Docker & Gunicorn

Dockerfile specifies:
- Python 3.11
- Gunicorn with 4 workers
- **120 second timeout** — AI endpoints may approach this limit
- Static file collection

If you're making changes that could trigger long-running queries or Claude API calls, keep the 120-second timeout in mind.

## Database Migrations

The project currently uses migration 0019. Follow these rules strictly:

### Creating New Migrations

```bash
# After changing models.py:
python manage.py makemigrations investigations

# Preview the migration:
python manage.py migrate --plan

# Apply locally:
python manage.py migrate

# Test that it runs cleanly:
python manage.py migrate --fake-initial  # on fresh DB
```

### Rules

1. **Never edit existing migration files** — Always create new ones
2. **Always test locally** — Run migrations on a local PostgreSQL before deploying
3. **Always include data migrations if needed** — If you're changing field types or constraints, include a data migration
4. **Test rollback** — Run `python manage.py migrate --plan` to verify migrations are reversible
5. **Include migration in PR** — Generated migration files are part of code review

### Example: Adding a New Field

```python
# models.py
class Organization(models.Model):
    legal_name = models.CharField(...)
    ein = models.CharField(...)
    investigation_priority = models.CharField(
        max_length=10,
        choices=[("high", "High"), ("medium", "Medium"), ("low", "Low")],
        default="medium"
    )

# Run:
# python manage.py makemigrations investigations
# python manage.py migrate
```

## Testing

### API Health Check

The `tests/api_health_check.py` file tests all endpoints:

```python
def test_get_cases():
    response = client.get("/api/cases/")
    assert response.status_code == 200

def test_create_case():
    response = client.post("/api/cases/", data={"title": "Test Case"})
    assert response.status_code == 201
```

**Update this file whenever you add new endpoints.**

### Signal Rule Tests

`tests/test_signal_rules.py` tests each rule:

```python
def test_sr_001_fires_on_low_charitable_spending():
    case = create_test_case()
    org = create_test_organization(case, total_revenue=500000)
    FinancialSnapshot.objects.create(
        organization=org,
        year=2023,
        total_revenue=500000,
        charitable_activity_expense=10000,  # Only 2%
    )

    signals = sr_001_nonprofit_with_no_charitable_activity(case)
    assert len(signals) == 1
    assert signals[0].severity == "HIGH"
```

### Running Tests Locally

```bash
python manage.py test investigations.tests

# Or specific test:
python manage.py test investigations.tests.api_health_check.test_get_cases

# With coverage:
coverage run --source='.' manage.py test investigations
coverage report
```

## Known Gotchas & Common Pitfalls

### 1. The Prefix Stripping Dance

The frontend sends composite IDs like `"signal-{uuid}"`. Many endpoints receive this format:

```python
# WRONG:
signal = get_object_or_404(Signal, pk=signal_id)  # Tries to find signal with pk="signal-..."

# RIGHT:
signal_uuid = _strip_id_prefix(signal_id)
signal = get_object_or_404(Signal, pk=signal_uuid)
```

Always use `_strip_id_prefix()` when receiving IDs from the frontend.

### 2. FinancialSnapshot Key Mapping Mismatch

The IRS connector returns keys like `"total_revenue"` but the model field might be named differently. Always check `_KEY_MAP`:

```python
# In views.py, around line 2300:
_KEY_MAP = {
    "total_revenue": "total_revenue",
    "net_income": "net_income",
    "total_program_expenses": "program_expenses",
    # ... check this mapping when parsing IRS data ...
}
```

If the IRS connector adds a new field, you must update `_KEY_MAP`.

### 3. Large views.py Navigation

At 4400 lines, it's easy to get lost. Always use the section headers:

```python
# ============================================================================
# Document endpoints
# ============================================================================

# ============================================================================
# Signal endpoints
# ============================================================================
```

Use your editor's search to jump to sections: `Ctrl+F "# Document endpoints"`.

### 4. CSRF Token on POST Endpoints

Forget `@csrf_exempt` and the frontend gets 403 Forbidden:

```python
# WRONG:
@require_http_methods(["POST"])
def api_create_something(request):
    # Frontend gets 403

# RIGHT:
@csrf_exempt
@require_http_methods(["POST"])
def api_create_something(request):
    # Works
```

### 5. Gunicorn Timeout (120 seconds)

Long-running endpoints (especially those calling Claude API) can hit the 120-second timeout. If you're adding AI-heavy logic:

- Use task queues (Celery) for long operations
- Consider timeout-aware try/except blocks
- Test with realistic data sizes

### 6. Pagination Off-by-One Errors

Always compute `next` URL correctly:

```python
# WRONG:
next_url = f"...?offset={offset + limit}"  # Can miss items

# RIGHT:
if offset + limit < total:
    next_url = f"...?offset={offset + limit}"
else:
    next_url = None
```

### 7. JSON Type Mismatches with Frontend

The frontend TypeScript types must match API response types. After changing an API response shape:

```bash
# Run type check:
npx tsc --noEmit
```

If types don't match, the frontend build fails. Always verify types match.

## Code Organization Principles

### Views.py Organization

```
api_get_all_cases
api_get_case_detail
api_create_case
api_update_case
api_delete_case

api_get_documents
api_upload_document
api_get_document_detail
api_delete_document

api_get_signals
api_reevaluate_signals
api_confirm_signal
...

api_entity_create
api_entity_get
...

api_connector_lookup
api_connector_results

api_signal_ai_analysis
api_document_summarize
...

api_health
api_stats
```

Always maintain this grouping. It makes finding endpoints easier.

### Import Organization

```python
# Standard library
import json
import uuid
from datetime import datetime, timedelta

# Third-party
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import psycopg2

# Local
from investigations.models import *
from investigations.signal_rules import RULES
from investigations.entity_extraction import extract_entities
from investigations.ai_proxy import (
    summarize_document,
    analyze_signal,
)
```

### Model Organization

```python
class CaseManager(models.Manager):
    def active(self):
        return self.filter(is_deleted=False)

class Case(models.Model):
    # Meta
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Core fields
    title = models.CharField(max_length=200)
    description = models.TextField()

    # Status
    status = models.CharField(choices=[...], default="open")

    # Soft delete
    is_deleted = models.BooleanField(default=False)

    # Relationships
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    objects = CaseManager()

    def __str__(self):
        return self.title

    def to_dict(self):
        return {
            "id": str(self.pk),
            "title": self.title,
            # ...
        }
```

## Deployment Checklist

Before deploying, verify:

- [ ] All models have migrations (`python manage.py migrate --plan`)
- [ ] All new POST endpoints have `@csrf_exempt`
- [ ] All collection endpoints paginate results
- [ ] All error responses include error message
- [ ] Tests pass (`python manage.py test`)
- [ ] TypeScript types match API responses (`npx tsc --noEmit`)
- [ ] CURRENT_STATE.md is updated (endpoint count, signal count)
- [ ] Environment variables are set in Railway (DATABASE_URL, ANTHROPIC_API_KEY, SECRET_KEY)
- [ ] No sensitive data in code (check for hardcoded API keys, passwords)

## Learning the Codebase

### First Steps

1. **Read models.py top to bottom** — Understand the 21 entities and their relationships
2. **Read signal_rules.py** — See the anomaly detection patterns
3. **Skim views.py by sections** — Don't memorize, just get familiar with structure
4. **Read ai_proxy.py** — Understand how Claude integration works
5. **Run local tests** — `python manage.py test` to see what works

### Key Files to Know

- `/backend/investigations/models.py` — Data model (21 entities)
- `/backend/investigations/views.py` — All 45 API endpoints (4400 lines, organized by sections)
- `/backend/investigations/signal_rules.py` — 29 anomaly detection rules
- `/backend/investigations/entity_extraction.py` — NLP pipeline
- `/backend/investigations/ai_proxy.py` — Claude API wrapper
- `/backend/catalyst/settings.py` — Django configuration
- `/backend/Dockerfile` — Deployment (Gunicorn 120s timeout)
- `/backend/investigations/tests/api_health_check.py` — Endpoint tests

### Common Tasks

**Add a new API endpoint**:
1. Add function to views.py under appropriate section
2. Ensure @csrf_exempt on POST endpoints
3. Ensure pagination on GET collection endpoints
4. Add test to api_health_check.py
5. Update CURRENT_STATE.md endpoint count

**Add a new signal rule**:
1. Write function in signal_rules.py
2. Add to RULES list
3. Write test in test_signal_rules.py
4. Update CURRENT_STATE.md signal count

**Add a new model**:
1. Define in models.py
2. Run `python manage.py makemigrations`
3. Review migration file
4. Run `python manage.py migrate`
5. Add to_dict() method
6. Update views.py if needed

**Fix a bug**:
1. Reproduce locally with test
2. Write failing test case
3. Fix code
4. Verify test passes
5. Check for similar issues elsewhere

## Questions to Ask

When you encounter something unclear:

- "What's the relationship between these two models?"
- "Where does this data flow after API call?"
- "What happens if this signal rule fires?"
- "How is this timeout reached?"
- "Why is this field nullable?"
- "What's the contract between views.py and frontend?"
- "How is rate limiting enforced?"
- "What's the worst that could happen if I delete this code?"

## Useful Django Patterns

### Efficient Querying

```python
# GOOD: Fetch all data in one query
entities = Entity.objects.filter(case=case).select_related('case').prefetch_related('signals')

# BAD: N+1 queries
entities = Entity.objects.filter(case=case)
for entity in entities:
    print(entity.case.title)  # Separate query for each entity!
    print(entity.signals.all())  # Separate query for each entity!
```

### Validation

```python
# Always validate before create/update
required_fields = ["title", "description"]
missing = [f for f in required_fields if not body.get(f)]
if missing:
    return JsonResponse({"error": f"Missing fields: {', '.join(missing)}"}, status=400)
```

### Error Handling

```python
try:
    instance = Model.objects.get(pk=pk)
except Model.DoesNotExist:
    return JsonResponse({"error": "Not found"}, status=404)

# Or use shortcut:
instance = get_object_or_404(Model, pk=pk)
```

### Pagination

```python
limit = min(int(request.GET.get("limit", 50)), 1000)  # Cap at 1000
offset = int(request.GET.get("offset", 0))

queryset = Model.objects.filter(case=case).order_by("-created_at")
total = queryset.count()
items = queryset[offset:offset+limit]

return JsonResponse({
    "count": total,
    "limit": limit,
    "offset": offset,
    "next": f"...?offset={offset+limit}" if offset+limit < total else None,
    "results": [item.to_dict() for item in items]
})
```

## Final Thoughts

You own the backend. The data model is your responsibility. The signal rules are your responsibility. The API contracts with the frontend are your responsibility. Write code that you're proud to maintain.

When in doubt, look at existing patterns. This codebase has strong conventions—follow them. Your code should look like it was written by the same person who wrote the code around it.

Good luck. The system you're building matters.
