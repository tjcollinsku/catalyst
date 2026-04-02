# Catalyst Security Policy

**Version:** 1.0
**Last updated:** 2026-03-31
**Owner:** Tyler Collins

---

## 1. Purpose

Catalyst is a forensic document analysis and investigative case management platform.
Its outputs may be submitted to government agencies (Ohio AG, IRS, FBI) as evidence
of fraud. This means every file, every transformation, and every user action must be
**verifiable, traceable, and tamper-evident**.

This document defines the security guardrails that all Catalyst code must follow.
If a pull request violates any rule marked **MUST**, it cannot be merged.

---

## 2. Threat Model

### 2.1 What Are We Protecting?

| Asset                  | Why It Matters                                                  |
|------------------------|-----------------------------------------------------------------|
| Uploaded evidence PDFs | Original documents are irreplaceable; integrity is everything   |
| SHA-256 hash chain     | Proves a document hasn't been altered since intake              |
| Audit log              | Proves who did what and when — required for legal credibility   |
| Database records       | Findings, signals, and referrals tie evidence to conclusions    |
| API tokens / secrets   | Unauthorized access could corrupt or delete evidence            |
| PII (names, SSNs, EINs)| Subject data must not leak outside the investigation context    |

### 2.2 Who Might Attack or Misuse the System?

| Threat Actor           | Motivation                         | Example Attack                          |
|------------------------|------------------------------------|-----------------------------------------|
| Investigation subject  | Destroy or alter evidence          | Upload a malicious PDF to corrupt the DB|
| Unauthorized user      | Access confidential case data      | Brute-force API token                   |
| Developer (accidental) | Introduce bugs that lose data      | Deploy code that silently skips hashing |
| Insider (future)       | Tamper with audit trail            | Delete audit_log rows to cover tracks   |
| Automated scanner      | Exploit known vulnerabilities      | Hit exposed Django debug page           |

### 2.3 What Could Go Wrong? (Failure Scenarios)

| Scenario                              | Impact                                        | Mitigation                                         |
|---------------------------------------|-----------------------------------------------|-----------------------------------------------------|
| PDF uploaded without hashing          | Can't prove document wasn't altered later     | Hash MUST be computed before any processing         |
| Rename/move fails mid-operation       | File exists in neither old nor new location   | Atomic operations with rollback logging             |
| Corrupted PDF crashes text extraction | Entire intake pipeline halts                  | Validate before extraction; isolate failures        |
| Secret key committed to Git           | Attacker gains DB or API access               | Pre-commit hook + .gitignore enforcement            |
| Silent exception swallowed            | Data corruption goes unnoticed for weeks      | No bare `except: pass` — all errors must be logged  |
| Audit log rows deleted                | Chain of custody broken                       | Append-only table; no DELETE permission in app code |

---

## 3. Core Security Rules

These rules apply to ALL Catalyst code. No exceptions.

### Rule 1: Hash Before You Touch

```
MUST: Compute SHA-256 on the original uploaded bytes BEFORE any
      processing (scrubbing, OCR, text extraction, renaming).

MUST: Store the hash in the database immediately after computation.

MUST: If the hash of a re-uploaded file differs from the stored hash,
      log a HASH_CHANGE signal and flag for investigator review.

MUST NOT: Process a file and then hash the result — that proves nothing
          about the original.
```

**Why this matters:** If someone asks "how do you know this PDF hasn't been
tampered with?", the answer is: "We hashed it on arrival, stored the hash
in a separate database, and every subsequent operation re-verifies the hash."

### Rule 2: Validate Before Processing

```
MUST: Check file size (reject files > MAX_UPLOAD_SIZE_MB, default 100 MB).

MUST: Verify MIME type matches the claimed file extension.
      A .pdf file must have MIME type application/pdf.

MUST: Attempt to parse the file header before full processing.
      If parsing fails, log the failure and reject the file.

MUST NOT: Assume any uploaded file is safe, well-formed, or what it claims to be.
```

**Validation pipeline (in order):**

```
Upload received
    │
    ▼
┌──────────────────┐
│ 1. Size check    │──► Too large? → Reject with clear error
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 2. MIME check    │──► Wrong type? → Reject with clear error
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 3. Header parse  │──► Corrupted?  → Reject with clear error
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 4. SHA-256 hash  │──► Store hash in DB immediately
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 5. Store file    │──► Write to MinIO / filesystem
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 6. Extract text  │──► Fails? → Log error, mark OCR_FAILED,
└──────────────────┘             continue (file is still stored)
    │
    ▼
  Audit log entry written
```

### Rule 3: Log Everything, Delete Nothing

```
MUST: Write an audit log entry for every state-changing operation:
      - Document uploaded, renamed, scrubbed, deleted
      - Finding created, updated, escalated
      - Signal detected, confirmed, dismissed
      - Referral submitted, status changed

MUST: Each log entry includes:
      - WHO:   user or system process identifier
      - WHAT:  table name, record ID, action performed
      - WHEN:  ISO 8601 timestamp (UTC)
      - HOW:   before_state and after_state (JSON snapshots)
      - WHERE: IP address (when applicable)

MUST: Audit log is append-only. Application code MUST NOT contain
      DELETE or UPDATE queries against the audit_log table.

MUST: Use Python's logging module with the JsonKeyValueFormatter
      for all forensic operations. Never use print().
```

### Rule 4: Secrets Stay in the Environment

```
MUST: All secrets (DB password, Django secret key, API tokens,
      MinIO credentials) live in .env files, loaded via python-dotenv.

MUST: .env is listed in .gitignore (already done ✓).

MUST: .env.example exists with placeholder values (already done ✓).

MUST NOT: Hardcode any of the following in Python source files:
          - Passwords or API keys
          - Absolute file paths (e.g., C:\Users\tjcol\...)
          - Database connection strings with credentials

MUST: Use os.getenv() or django.conf.settings for all config values.
```

### Rule 5: Errors Are Loud, Never Silent

```
MUST NOT: Use bare `except: pass` or `except Exception: pass`.
          Every exception must be logged with context.

MUST: Distinguish between expected errors (corrupted PDF, oversized file)
      and unexpected errors (database connection lost, disk full).

MUST: Expected errors → log at WARNING level, return structured error response.
      Unexpected errors → log at ERROR/CRITICAL level, re-raise or alert.

MUST: Failed operations must leave the system in a known state.
      If step 3 of 5 fails, steps 1-2 must be rolled back or
      the partial state must be explicitly recorded.
```

### Rule 6: Atomic Operations or Explicit Rollback

```
MUST: Multi-step database operations use Django ORM transactions:

      from django.db import transaction

      with transaction.atomic():
          doc = Document.objects.create(...)
          AuditLog.objects.create(...)
          # If either fails, both are rolled back

MUST: File operations that can fail midway must either:
      (a) Copy first, then delete original (never move directly), or
      (b) Log the intended operation before executing, so partial
          failures can be identified and recovered.

MUST NOT: Assume rename/move operations are atomic on all filesystems.
```

---

## 4. Secure Coding Checklist

Use this checklist when writing or reviewing any Catalyst code:

```
[ ] No secrets in source code (grep for passwords, keys, tokens)
[ ] No hardcoded absolute paths
[ ] All file uploads validated (size, MIME, header)
[ ] SHA-256 computed on original bytes before any transformation
[ ] Hash stored in database before file is processed
[ ] All state-changing operations write to audit_log
[ ] All exceptions are caught, logged with context, and handled
[ ] No bare except:pass blocks
[ ] Database writes wrapped in transaction.atomic() where appropriate
[ ] Django DEBUG = False in any non-local environment
[ ] ALLOWED_HOSTS is restrictive (not ["*"])
[ ] Tests exist for edge cases (corrupted file, oversized file, missing fields)
```

---

## 5. Secrets Inventory

| Secret                 | Where It Lives       | Used By                    |
|------------------------|----------------------|----------------------------|
| DJANGO_SECRET_KEY      | .env                 | Django session/CSRF signing|
| DB_PASSWORD            | .env                 | PostgreSQL connection      |
| CATALYST_API_TOKEN     | .env (when enabled)  | API authentication         |
| MINIO_ROOT_USER        | .env (Phase 2)       | MinIO object storage       |
| MINIO_ROOT_PASSWORD    | .env (Phase 2)       | MinIO object storage       |

**Rotation policy:** Secrets should be rotated if a developer's machine is
compromised, or when a team member's access is revoked. For a solo project,
rotate when moving from local dev to any hosted environment.

---

## 6. Incident Response (Solo Developer)

If you discover a security issue:

1. **Stop deploying.** Don't push more code until the issue is understood.
2. **Document the issue** in an audit log entry or a dedicated incident note.
3. **Assess impact:** Was any data exposed or corrupted? Check audit_log.
4. **Fix and verify:** Write a test that reproduces the vulnerability, then fix it.
5. **Rotate secrets** if there's any chance they were exposed.

---

## 7. File Integrity Verification Protocol

This is the specific procedure for maintaining chain of custody on evidence files:

```
INTAKE:
  1. User uploads file via API
  2. System computes SHA-256 on raw uploaded bytes
  3. System stores: (original_filename, sha256, file_size, upload_timestamp)
  4. System writes file to storage (MinIO or filesystem)
  5. System logs: "DOCUMENT_INGESTED" in audit_log

RE-VERIFICATION (periodic or on-demand):
  1. Read file from storage
  2. Compute SHA-256 on stored bytes
  3. Compare with hash stored at intake
  4. If mismatch → create HASH_CHANGE detection signal (CRITICAL severity)
  5. Log result regardless (match or mismatch)

EXPORT / REFERRAL:
  1. Before including a document in a referral package:
     - Re-verify hash matches intake hash
     - Log verification result
     - Include hash in referral metadata
```

---

## 8. Dependencies and Supply Chain

```
MUST: Pin all Python dependencies to exact versions in requirements.txt.

SHOULD: Periodically run `pip audit` or `safety check` to scan for
        known vulnerabilities in dependencies.

SHOULD: Review Dockerfile base images for security updates quarterly.
```

---

## 9. What This Document Does NOT Cover (Yet)

These topics will be addressed as Catalyst matures:

- **User authentication** (currently API token only; Django auth planned)
- **Role-based access control** (single investigator for now)
- **Network security** (firewall rules, TLS certificates for deployment)
- **Backup and disaster recovery** (database backup strategy)
- **Penetration testing** (appropriate once deployed to a live URL)

---

*This document is a living artifact. Update it whenever a new security
decision is made or a new threat is identified.*
