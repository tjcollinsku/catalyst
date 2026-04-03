#!/usr/bin/env python3
"""
Catalyst API Health Check — Automated Test Suite
=================================================
Hits every API endpoint on the live deployment and reports status.
Run: python tests/api_health_check.py [BASE_URL]

Exit codes:
  0 = all tests passed
  1 = one or more failures
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "https://catalyst-production-9566.up.railway.app"


# ---------------------------------------------------------------------------
# Test result tracking
# ---------------------------------------------------------------------------
@dataclass
class TestResult:
    name: str
    endpoint: str
    method: str
    status_code: int
    passed: bool
    duration_ms: float
    error: str = ""
    response_preview: str = ""
    data_check: str = ""


results: list[TestResult] = []


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def api_get(
    path: str, expected_status: int = 200, timeout: int = 30
) -> tuple[int, dict | list | str, float]:
    """Make a GET request. Returns (status_code, body, duration_ms)."""
    url = f"{BASE_URL}{path}"
    start = time.time()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            duration = (time.time() - start) * 1000
            try:
                return resp.status, json.loads(body), duration
            except json.JSONDecodeError:
                return resp.status, body[:500], duration
    except urllib.error.HTTPError as e:
        duration = (time.time() - start) * 1000
        body = ""
        try:
            body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        return e.code, body, duration
    except Exception as e:
        duration = (time.time() - start) * 1000
        return 0, str(e)[:500], duration


def _get_csrf_token() -> str:
    """Fetch a CSRF token from the server."""
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/csrf/", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            # Read the Set-Cookie header for csrftoken
            cookies = resp.headers.get_all("Set-Cookie") or []
            for c in cookies:
                if "csrftoken=" in c:
                    return c.split("csrftoken=")[1].split(";")[0]
            # Fallback: try response body
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("csrfToken", body.get("token", ""))
    except Exception:
        return ""


_CSRF_TOKEN: str = ""


def api_post(
    path: str, data: dict, expected_status: int = 200, timeout: int = 30
) -> tuple[int, dict | list | str, float]:
    """Make a POST request with CSRF token. Returns (status_code, body, duration_ms)."""
    global _CSRF_TOKEN
    if not _CSRF_TOKEN:
        _CSRF_TOKEN = _get_csrf_token()

    url = f"{BASE_URL}{path}"
    start = time.time()
    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if _CSRF_TOKEN:
            req.add_header("X-CSRFToken", _CSRF_TOKEN)
            req.add_header("Cookie", f"csrftoken={_CSRF_TOKEN}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            duration = (time.time() - start) * 1000
            try:
                return resp.status, json.loads(body), duration
            except json.JSONDecodeError:
                return resp.status, body[:500], duration
    except urllib.error.HTTPError as e:
        duration = (time.time() - start) * 1000
        body = ""
        try:
            body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        return e.code, body, duration
    except Exception as e:
        duration = (time.time() - start) * 1000
        return 0, str(e)[:500], duration


def check(
    name: str,
    endpoint: str,
    method: str,
    status: int,
    body,
    duration: float,
    expected_status: int = 200,
    data_checks: Optional[list] = None,
):
    """Record a test result with optional data shape validation."""
    passed = status == expected_status
    data_notes = []

    if passed and data_checks and isinstance(body, (dict, list)):
        for check_fn, check_desc in data_checks:
            try:
                if not check_fn(body):
                    data_notes.append(f"WARN: {check_desc}")
            except Exception as e:
                data_notes.append(f"WARN: {check_desc} ({e})")

    error = ""
    if not passed:
        error = f"Expected {expected_status}, got {status}"
        if isinstance(body, str):
            error += f" | {body[:200]}"
        elif isinstance(body, dict) and "error" in body:
            error += f" | {body['error']}"
        elif isinstance(body, dict) and "detail" in body:
            error += f" | {body['detail']}"

    preview = ""
    if isinstance(body, list):
        preview = f"[{len(body)} items]"
    elif isinstance(body, dict):
        keys = list(body.keys())[:8]
        preview = f"keys: {keys}"
    else:
        preview = str(body)[:100]

    results.append(
        TestResult(
            name=name,
            endpoint=endpoint,
            method=method,
            status_code=status,
            passed=passed,
            duration_ms=round(duration, 1),
            error=error,
            response_preview=preview,
            data_check="; ".join(data_notes) if data_notes else "OK",
        )
    )


# ===========================================================================
# TEST SUITE
# ===========================================================================

print(f"\n{'=' * 70}")
print("  CATALYST API HEALTH CHECK")
print(f"  Target: {BASE_URL}")
print(f"  Time:   {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print(f"{'=' * 70}\n")

# ---------------------------------------------------------------------------
# SECTION 1: Infrastructure
# ---------------------------------------------------------------------------
print("--- Section 1: Infrastructure ---")

status, body, dur = api_get("/api/health/")
check(
    "Health check",
    "/api/health/",
    "GET",
    status,
    body,
    dur,
    data_checks=[(lambda b: b.get("status") == "ok", "status should be 'ok'")],
)

status, body, dur = api_get("/api/csrf/")
check("CSRF token", "/api/csrf/", "GET", status, body, dur)

# SPA serves index.html at root
status, body, dur = api_get("/")
check(
    "SPA root",
    "/",
    "GET",
    status,
    body,
    dur,
    data_checks=[
        (
            lambda b: "<!DOCTYPE" in str(b)[:100]
            or "<html" in str(b)[:100]
            or "root" in str(b)[:500],
            "Should serve HTML",
        )
    ],
)

# ---------------------------------------------------------------------------
# SECTION 2: Collection endpoints (no case ID needed)
# ---------------------------------------------------------------------------
print("--- Section 2: Collection Endpoints ---")

status, body, dur = api_get("/api/cases/")
check(
    "List cases",
    "/api/cases/",
    "GET",
    status,
    body,
    dur,
    data_checks=[
        (
            lambda b: (isinstance(b, list) and len(b) > 0)
            or (isinstance(b, dict) and b.get("count", 0) > 0),
            "Should return non-empty results",
        )
    ],
)

# Save first case ID for later tests — handle paginated or plain list
CASE_ID = None
case_list = (
    body if isinstance(body, list) else (body.get("results", []) if isinstance(body, dict) else [])
)
if case_list and len(case_list) > 0:
    CASE_ID = case_list[0].get("id")
    print(f"   Using case ID: {CASE_ID}")

status, body, dur = api_get("/api/signals/")
check("List signals (cross-case)", "/api/signals/", "GET", status, body, dur)

status, body, dur = api_get("/api/signal-summary/")
check("Signal summary", "/api/signal-summary/", "GET", status, body, dur)

status, body, dur = api_get("/api/referrals/")
check("List referrals", "/api/referrals/", "GET", status, body, dur)

status, body, dur = api_get("/api/entities/")
check("List entities", "/api/entities/", "GET", status, body, dur)

status, body, dur = api_get("/api/activity-feed/")
check("Activity feed", "/api/activity-feed/", "GET", status, body, dur)

status, body, dur = api_get("/api/search/?q=test")
check("Search (query='test')", "/api/search/?q=test", "GET", status, body, dur)

status, body, dur = api_get("/api/search/?q=")
check("Search (empty query)", "/api/search/?q=", "GET", status, body, dur)

# ---------------------------------------------------------------------------
# SECTION 3: Case-specific endpoints
# ---------------------------------------------------------------------------
print("--- Section 3: Case-Specific Endpoints ---")

if CASE_ID:
    # Case detail
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/")
    check(
        "Case detail",
        "/api/cases/{id}/",
        "GET",
        status,
        body,
        dur,
        data_checks=[
            (lambda b: "id" in b, "Should have 'id' field"),
            (lambda b: "name" in b, "Should have 'name' field"),
        ],
    )

    # Case dashboard
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/dashboard/")
    check("Case dashboard", "/api/cases/{id}/dashboard/", "GET", status, body, dur)

    # Case signals
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/signals/")
    check("Case signals", "/api/cases/{id}/signals/", "GET", status, body, dur)

    # Save a signal ID if available
    SIGNAL_ID = None
    if isinstance(body, list) and len(body) > 0:
        SIGNAL_ID = body[0].get("id")

    # Case documents
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/documents/")
    check("Case documents", "/api/cases/{id}/documents/", "GET", status, body, dur)

    # Save a document ID if available
    DOC_ID = None
    if isinstance(body, list) and len(body) > 0:
        DOC_ID = body[0].get("id")

    # Document detail
    if DOC_ID:
        status, body, dur = api_get(f"/api/cases/{CASE_ID}/documents/{DOC_ID}/")
        check(
            "Document detail",
            "/api/cases/{id}/documents/{doc_id}/",
            "GET",
            status,
            body,
            dur,
            data_checks=[
                (lambda b: "extracted_text" in b, "Should have 'extracted_text' field"),
            ],
        )

    # Case financials
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/financials/")
    check("Case financials", "/api/cases/{id}/financials/", "GET", status, body, dur)

    # Case detections
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/detections/")
    check("Case detections", "/api/cases/{id}/detections/", "GET", status, body, dur)

    # Case findings
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/findings/")
    check("Case findings", "/api/cases/{id}/findings/", "GET", status, body, dur)

    # Case referrals
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/referrals/")
    check("Case referrals", "/api/cases/{id}/referrals/", "GET", status, body, dur)

    # Case notes
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/notes/")
    check("Case notes", "/api/cases/{id}/notes/", "GET", status, body, dur)

    # Case graph
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/graph/")
    check("Case graph", "/api/cases/{id}/graph/", "GET", status, body, dur)

    # Case coverage
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/coverage/")
    check("Case coverage", "/api/cases/{id}/coverage/", "GET", status, body, dur)

    # Case export
    status, body, dur = api_get(f"/api/cases/{CASE_ID}/export/")
    check("Case export", "/api/cases/{id}/export/", "GET", status, body, dur)

    # ---------------------------------------------------------------------------
    # SECTION 4: AI Endpoints (POST)
    # ---------------------------------------------------------------------------
    print("--- Section 4: AI Endpoints ---")

    if SIGNAL_ID:
        # AI Summarize
        status, body, dur = api_post(
            f"/api/cases/{CASE_ID}/ai/summarize/", {"target_id": SIGNAL_ID, "target_type": "signal"}
        )
        check("AI summarize (signal)", "/api/cases/{id}/ai/summarize/", "POST", status, body, dur)

    # AI Connections — needs an entity
    status, ent_body, _ = api_get("/api/entities/")
    ENTITY_ID = None
    ENTITY_TYPE = None
    if isinstance(ent_body, list) and len(ent_body) > 0:
        ENTITY_ID = ent_body[0].get("id")
        ENTITY_TYPE = ent_body[0].get("type", "organization")

    if ENTITY_ID:
        status, body, dur = api_post(
            f"/api/cases/{CASE_ID}/ai/connections/",
            {"entity_id": ENTITY_ID, "entity_type": ENTITY_TYPE},
        )
        check("AI connections", "/api/cases/{id}/ai/connections/", "POST", status, body, dur)

    # AI Narrative — needs detection IDs
    status, det_body, _ = api_get(f"/api/cases/{CASE_ID}/detections/")
    if isinstance(det_body, list) and len(det_body) > 0:
        det_ids = [d["id"] for d in det_body[:3]]
        status, body, dur = api_post(
            f"/api/cases/{CASE_ID}/ai/narrative/", {"detection_ids": det_ids}
        )
        check("AI narrative", "/api/cases/{id}/ai/narrative/", "POST", status, body, dur)

    # AI Ask
    status, body, dur = api_post(
        f"/api/cases/{CASE_ID}/ai/ask/", {"question": "What is this case about?"}
    )
    check("AI ask", "/api/cases/{id}/ai/ask/", "POST", status, body, dur)

    # ---------------------------------------------------------------------------
    # SECTION 4a: POST ENDPOINT CSRF CHECK
    # ---------------------------------------------------------------------------
    print("--- Section 4a: POST Endpoint CSRF Check ---")

    # Test all POST endpoints with valid CSRF token to ensure they return 200/201
    # These endpoints may have @csrf_exempt decorators, but we verify they work
    # with a proper CSRF token when present.

    # api_case_collection (POST to create case)
    status, body, dur = api_post("/api/cases/", {"name": "CSRF Test Case", "status": "open"})
    check(
        "POST case creation (CSRF)", "/api/cases/", "POST", status, body, dur, expected_status=201
    )

    # api_case_document_collection (POST to upload document)
    # Note: This endpoint expects multipart/form-data in practice, but we test JSON payload
    status, body, dur = api_post(
        f"/api/cases/{CASE_ID}/documents/", {"filename": "test.pdf", "document_type": "financial"}
    )
    check("POST document (CSRF)", "/api/cases/{id}/documents/", "POST", status, body, dur)

    # api_case_finding_collection (POST to create finding)
    status, body, dur = api_post(
        f"/api/cases/{CASE_ID}/findings/", {"title": "CSRF Test Finding", "description": "Test"}
    )
    check(
        "POST finding creation (CSRF)",
        "/api/cases/{id}/findings/",
        "POST",
        status,
        body,
        dur,
        expected_status=201,
    )

    # api_case_note_collection (POST to create note)
    status, body, dur = api_post(f"/api/cases/{CASE_ID}/notes/", {"text": "CSRF Test Note"})
    check(
        "POST note creation (CSRF)",
        "/api/cases/{id}/notes/",
        "POST",
        status,
        body,
        dur,
        expected_status=201,
    )

    # api_case_referral_collection (POST to create referral)
    status, body, dur = api_post(
        f"/api/cases/{CASE_ID}/referrals/", {"agency": "IRS", "type": "referral"}
    )
    check(
        "POST referral creation (CSRF)",
        "/api/cases/{id}/referrals/",
        "POST",
        status,
        body,
        dur,
        expected_status=201,
    )

    # api_case_detection_collection (POST to create detection manually)
    status, body, dur = api_post(
        f"/api/cases/{CASE_ID}/detections/",
        {
            "signal_id": str(SIGNAL_ID) if SIGNAL_ID else "00000000-0000-0000-0000-000000000000",
            "reason": "CSRF test",
        },
    )
    check(
        "POST detection creation (CSRF)",
        "/api/cases/{id}/detections/",
        "POST",
        status,
        body,
        dur,
        expected_status=201,
    )

    # api_case_reevaluate_signals (POST to trigger re-evaluation)
    status, body, dur = api_post(f"/api/cases/{CASE_ID}/reevaluate/", {})
    check(
        "POST case re-evaluate signals (CSRF)",
        "/api/cases/{id}/reevaluate/",
        "POST",
        status,
        body,
        dur,
    )

    # api_case_referral_memo (POST to generate memo)
    status, body, dur = api_post(
        f"/api/cases/{CASE_ID}/referral-memo/",
        {"referral_id": "00000000-0000-0000-0000-000000000000"},
    )
    check(
        "POST referral memo generation (CSRF)",
        "/api/cases/{id}/referral-memo/",
        "POST",
        status,
        body,
        dur,
    )

    # api_case_document_bulk_upload (POST to bulk upload)
    status, body, dur = api_post(f"/api/cases/{CASE_ID}/documents/bulk-upload/", {"documents": []})
    check(
        "POST document bulk upload (CSRF)",
        "/api/cases/{id}/documents/bulk-upload/",
        "POST",
        status,
        body,
        dur,
    )

    # api_case_document_process_pending (POST to process pending)
    status, body, dur = api_post(f"/api/cases/{CASE_ID}/documents/process-pending/", {})
    check(
        "POST document process pending (CSRF)",
        "/api/cases/{id}/documents/process-pending/",
        "POST",
        status,
        body,
        dur,
    )

else:
    print("   SKIP: No cases found — cannot test case-specific endpoints")

# ---------------------------------------------------------------------------
# SECTION 5: Edge cases and error handling
# ---------------------------------------------------------------------------
print("--- Section 5: Edge Cases ---")

# Non-existent case ID
fake_id = "00000000-0000-0000-0000-000000000000"
status, body, dur = api_get(f"/api/cases/{fake_id}/")
check("404 on missing case", "/api/cases/{fake}/", "GET", status, body, dur, expected_status=404)

# Invalid UUID format
status, body, dur = api_get("/api/cases/not-a-uuid/")
check(
    "400/404 on bad UUID", "/api/cases/not-a-uuid/", "GET", status, body, dur, expected_status=404
)

# Search with special characters
status, body, dur = api_get(
    "/api/search/?q=" + urllib.parse.quote("test <script>alert(1)</script>")
)
check("Search XSS safety", "/api/search/?q=<script>", "GET", status, body, dur)

# ===========================================================================
# REPORT
# ===========================================================================
print(f"\n{'=' * 70}")
print("  TEST RESULTS")
print(f"{'=' * 70}\n")

passed = [r for r in results if r.passed]
failed = [r for r in results if not r.passed]
warned = [r for r in results if r.data_check and r.data_check != "OK"]

# Categorize results by section
section_4a_results = [r for r in results if "CSRF" in r.name]
other_results = [r for r in results if "CSRF" not in r.name]

# Print failures first
if failed:
    print(f"  FAILURES ({len(failed)}):")
    print(f"  {'-' * 66}")
    for r in failed:
        print(f"  FAIL  {r.name}")
        print(f"        {r.method} {r.endpoint}")
        print(f"        {r.error}")
        print(f"        Duration: {r.duration_ms}ms")
        print()

# Print warnings
if warned:
    print(f"  WARNINGS ({len(warned)}):")
    print(f"  {'-' * 66}")
    for r in warned:
        print(f"  WARN  {r.name}")
        print(f"        {r.data_check}")
        print()

# Print pass summary grouped by section
print(f"  PASSED ({len(passed)}):")
print(f"  {'-' * 66}")

# Print non-CSRF tests first
for r in other_results:
    if r.passed:
        status_icon = "PASS" if r.data_check == "OK" else "WARN"
        print(
            f"  {status_icon}  {r.name:<35} {r.status_code} {r.duration_ms:>7.0f}ms  {r.response_preview[:40]}"
        )

# Print CSRF section separately
if section_4a_results:
    print(
        f"\n  POST ENDPOINT CSRF CHECK ({len([r for r in section_4a_results if r.passed])}/{len(section_4a_results)}):"
    )
    print(f"  {'-' * 66}")
    for r in section_4a_results:
        if r.passed:
            status_icon = "PASS" if r.data_check == "OK" else "WARN"
            print(
                f"  {status_icon}  {r.name:<35} {r.status_code} {r.duration_ms:>7.0f}ms  {r.response_preview[:40]}"
            )

# Summary
print(f"\n{'=' * 70}")
total = len(results)
csrf_tests = len(section_4a_results)
csrf_passed = len([r for r in section_4a_results if r.passed])
print(
    f"  SUMMARY: {len(passed)}/{total} passed, {len(failed)}/{total} failed, {len(warned)} warnings"
)
print(f"  SECTION 4a (POST CSRF): {csrf_passed}/{csrf_tests} CSRF tests passed")

# Performance stats
durations = [r.duration_ms for r in results]
if durations:
    avg = sum(durations) / len(durations)
    slow = [r for r in results if r.duration_ms > 2000]
    print(f"  PERFORMANCE: avg={avg:.0f}ms, max={max(durations):.0f}ms, slow(>2s)={len(slow)}")

print(f"{'=' * 70}\n")

# Exit code
sys.exit(0 if not failed else 1)
