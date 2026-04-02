# Catalyst Error Handling Strategy

**Version:** 1.0
**Last updated:** 2026-03-31

---

## 1. Philosophy

Catalyst handles forensic evidence. A silent failure can mean corrupted evidence,
a broken chain of custody, or a missed fraud signal. The cost of a noisy error
(an alert that turns out to be nothing) is near zero. The cost of a silent error
(evidence that disappears without a trace) could undermine an entire investigation.

**Therefore: every error is loud, logged, and recoverable.**

---

## 2. Error Classification

Every error in Catalyst falls into one of three categories. Each category has
a different handling strategy:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ERROR CATEGORIES                            │
├──────────────────┬──────────────────────┬───────────────────────────┤
│  EXPECTED        │  OPERATIONAL         │  UNEXPECTED               │
│  (User's fault)  │  (Environment)       │  (Bug in our code)        │
├──────────────────┼──────────────────────┼───────────────────────────┤
│  Oversized file  │  Database down       │  KeyError on dict access  │
│  Invalid MIME    │  Disk full           │  NoneType has no .id      │
│  Corrupted PDF   │  MinIO unreachable   │  Migration out of sync    │
│  Missing fields  │  Network timeout     │  Unhandled edge case      │
├──────────────────┼──────────────────────┼───────────────────────────┤
│  Log: WARNING    │  Log: ERROR          │  Log: CRITICAL            │
│  Response: 400   │  Response: 503       │  Response: 500            │
│  Action: Return  │  Action: Retry or    │  Action: Re-raise,        │
│  clear message   │  fail with details   │  alert, investigate       │
└──────────────────┴──────────────────────┴───────────────────────────┘
```

---

## 3. Logging Standards

### 3.1 Always Use the Logger, Never print()

```python
# BAD — invisible in production, no timestamp, no level
print(f"Processing {filename}")
print(f"Error: {e}")

# GOOD — structured, searchable, includes context automatically
import logging
logger = logging.getLogger("investigations.upload_pipeline")

logger.info("Processing document", extra={
    "filename": filename,
    "case_id": str(case.id),
    "file_size": file_size,
})

logger.error("Text extraction failed", extra={
    "filename": filename,
    "case_id": str(case.id),
    "error_type": type(e).__name__,
    "error_detail": str(e),
})
```

### 3.2 Log Levels and When to Use Them

| Level    | When to Use                                         | Example                              |
|----------|-----------------------------------------------------|--------------------------------------|
| DEBUG    | Detailed diagnostic info (off in production)        | "Parsing page 3 of 17"              |
| INFO     | Normal operations worth recording                   | "Document ingested successfully"     |
| WARNING  | Expected error the user caused                      | "File rejected: exceeds 100MB"       |
| ERROR    | Something went wrong that needs attention            | "Database connection lost"           |
| CRITICAL | System is in a broken state                          | "Audit log write failed"            |

### 3.3 What Every Log Entry Must Include

For forensic operations (anything touching documents, findings, or signals):

```python
logger.info("operation description", extra={
    "case_id":    str(case.id),      # Which investigation
    "record_id":  str(record.id),    # Which specific record
    "action":     "DOCUMENT_INGESTED",  # What happened (use AuditAction values)
    "sha256":     computed_hash,     # File hash (if applicable)
    "user":       request_user,      # Who did it
})
```

---

## 4. Exception Handling Patterns

### 4.1 The Golden Rule: No Bare Except

```python
# ──────────────────────────────────────
# NEVER DO THIS — hides bugs, loses data
# ──────────────────────────────────────
try:
    process_pdf(file)
except:
    pass

# Also never do this — same problem with a nicer hat
try:
    process_pdf(file)
except Exception:
    pass

# ──────────────────────────────────────
# ALWAYS DO THIS — catch specific, log everything
# ──────────────────────────────────────
try:
    process_pdf(file)
except PdfReadError as e:
    # EXPECTED: file is corrupted
    logger.warning("Corrupted PDF, cannot extract text", extra={
        "filename": file.name,
        "error": str(e),
    })
    mark_document_as_failed(doc, reason=str(e))
except OSError as e:
    # OPERATIONAL: disk/network issue
    logger.error("File system error during PDF processing", extra={
        "filename": file.name,
        "error": str(e),
    })
    raise  # Let the caller decide how to handle
except Exception as e:
    # UNEXPECTED: this is a bug — we need to know about it
    logger.critical("Unexpected error processing PDF", extra={
        "filename": file.name,
        "error_type": type(e).__name__,
        "error": str(e),
    })
    raise  # Never swallow surprises
```

### 4.2 Custom Exception Classes

Catalyst defines its own exceptions so callers can handle errors precisely:

```python
# investigations/exceptions.py

class CatalystError(Exception):
    """Base class for all Catalyst-specific errors."""
    pass


class IntakeValidationError(CatalystError):
    """File failed intake validation (size, MIME, corruption)."""
    def __init__(self, filename: str, reason: str):
        self.filename = filename
        self.reason = reason
        super().__init__(f"Intake rejected '{filename}': {reason}")


class HashMismatchError(CatalystError):
    """Stored hash doesn't match recomputed hash — potential tampering."""
    def __init__(self, document_id, expected: str, actual: str):
        self.document_id = document_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Hash mismatch on document {document_id}: "
            f"expected {expected[:12]}..., got {actual[:12]}..."
        )


class AuditLogWriteError(CatalystError):
    """Failed to write to audit log — this is always critical."""
    pass
```

### 4.3 When to Catch vs. When to Raise

```
Should I catch this exception here?

    Is this the RIGHT PLACE to handle it?
    ├── YES: I can fix the problem or give the user a clear error
    │        → Catch it, log it, handle it
    │
    └── NO:  Someone higher up the call stack should decide
             → Let it propagate (or re-raise after logging)
```

**Rule of thumb:** Catch at boundaries (API views, Celery tasks, management commands).
Let library/utility code raise exceptions up to the boundary.

---

## 5. API Error Response Format

All API error responses follow a consistent JSON structure:

```python
# Successful response
{
    "data": { ... },
    "meta": {
        "request_id": "abc-123",
        "timestamp": "2026-03-31T14:23:45Z"
    }
}

# Error response (client error — 4xx)
{
    "errors": {
        "file": ["File exceeds maximum size of 100MB."],
        "mime_type": ["Expected application/pdf, got image/jpeg."]
    },
    "meta": {
        "request_id": "abc-124",
        "timestamp": "2026-03-31T14:23:46Z"
    }
}

# Error response (server error — 5xx)
{
    "errors": {
        "server": ["An internal error occurred. Reference ID: abc-125"]
    },
    "meta": {
        "request_id": "abc-125",
        "timestamp": "2026-03-31T14:23:47Z"
    }
}
```

**Key principle:** Client errors (400) give the user enough detail to fix the
problem. Server errors (500) give the user a reference ID but NOT internal
details (no stack traces, no file paths, no database info).

---

## 6. Transaction Safety Pattern

For any operation that creates or modifies multiple records:

```python
from django.db import transaction
from investigations.models import AuditAction, AuditLog, Document

def ingest_document(*, file, case, performed_by, ip_address=None):
    """
    Ingest a document with full audit trail.

    If ANY step fails, the entire operation is rolled back —
    no partial records, no orphaned files, no missing audit entries.
    """
    # Step 1: Validate OUTSIDE the transaction (no DB work yet)
    validate_file_size(file)
    validate_mime_type(file)
    sha256 = compute_sha256(file)

    # Step 2: All-or-nothing database writes
    with transaction.atomic():
        doc = Document.objects.create(
            case=case,
            filename=file.name,
            sha256_hash=sha256,
            file_size=file.size,
            # ... other fields
        )

        AuditLog.log(
            action=AuditAction.DOCUMENT_INGESTED,
            table_name="documents",
            record_id=doc.id,
            case_id=case.id,
            sha256_hash=sha256,
            file_size=file.size,
            performed_by=performed_by,
            ip_address=ip_address,
        )

    # Step 3: File storage AFTER transaction succeeds
    # (If storage fails, we have a DB record but no file —
    #  this is detectable and recoverable. The reverse is worse.)
    try:
        store_file(file, doc.file_path)
    except OSError as e:
        logger.error("File storage failed after DB commit", extra={
            "document_id": str(doc.id),
            "error": str(e),
        })
        # Mark document as needing attention, don't delete the DB record
        AuditLog.log(
            action=AuditAction.DOCUMENT_INGESTED,
            table_name="documents",
            record_id=doc.id,
            case_id=case.id,
            success=False,
            notes=f"DB record created but file storage failed: {e}",
            performed_by=performed_by,
        )
        raise

    return doc
```

**Why this order matters:**

```
Validation → DB Transaction → File Storage

If validation fails   → Nothing happened (clean)
If DB transaction fails → Nothing happened (rolled back)
If file storage fails  → DB record exists, file doesn't
                          → This is DETECTABLE (query for docs without files)
                          → Better than: file exists, DB doesn't know about it
```

---

## 7. Failure Recovery Checklist

When something goes wrong, use this decision tree:

```
ERROR OCCURRED
    │
    ├── Is it an expected validation error?
    │   └── YES → Return 400 with clear message. Log at WARNING. Done.
    │
    ├── Is it a temporary environment issue (DB down, network timeout)?
    │   └── YES → Return 503. Log at ERROR. Retry if in a Celery task.
    │
    ├── Is it a data integrity issue (hash mismatch, missing record)?
    │   └── YES → Return 500. Log at CRITICAL. Create a detection signal.
    │            Do NOT proceed with processing.
    │
    └── Is it an unexpected bug?
        └── YES → Return 500. Log at CRITICAL with full context.
                 Re-raise so the stack trace is captured.
                 Fix the bug. Write a test for the edge case.
```

---

## 8. Anti-Patterns to Avoid

### 8.1 The Silent Swallower
```python
# BAD: If scrubbing fails, you'll never know
scrubbed, failed = scrub_pdf_metadata(base_dir)
# script continues regardless of failure count
```

### 8.2 The Optimistic Renamer
```python
# BAD: If this fails midway, file is in unknown state
src.rename(dest)
```

### 8.3 The Assumption Artist
```python
# BAD: Assumes every file in the folder is a valid PDF
for pdf in folder.glob("*.pdf"):
    reader = PdfReader(str(pdf))
    text = reader.pages[0].extract_text()
```

### 8.4 The Generic Catcher
```python
# BAD: Catches everything, handles nothing
try:
    complex_operation()
except Exception as e:
    return {"status": "error"}  # What error? Which operation? What now?
```

---

*This document should be read alongside SECURITY.md. Together they define
how Catalyst code must behave when things go right AND when things go wrong.*
