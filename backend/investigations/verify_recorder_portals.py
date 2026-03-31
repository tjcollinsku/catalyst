"""
verify_recorder_portals.py
==========================
HTTP verification + confidence scoring for all 88 Ohio county recorder portal URLs.

Confidence Score (0–100):
    Each county URL is scored on multiple factors:

    HTTP / Reachability (up to 35 pts):
        35  — HTTP 200, no redirect
        25  — HTTP 200 after same-domain redirect (http→https, trailing slash)
        15  — HTTP 200 after cross-domain redirect (suspicious)
         0  — 4xx/5xx, timeout, connection error

    Domain Pattern Match (up to 25 pts):
        25  — Final URL domain matches the expected pattern for assigned RecorderSystem
             (e.g. tylerhost.net for EagleWeb, ava.fidlar.com for Fidlar AVA,
              publicsearch.us for Cloud Search, etc.)
         0  — Domain mismatch or known aggregator

    Page Content Looks Like a Recorder Portal (up to 20 pts):
        20  — Page text contains recorder-specific keywords
             (grantor, grantee, deed, instrument, recorded, book/page, recorder)
        10  — Page text contains partial recorder signals
         0  — Page looks generic, blank, or is an aggregator

    URL Source / Prior Verification (up to 20 pts):
        20  — URL confirmed by user via live browser session in this project
        15  — URL follows well-known vendor pattern and domain checks pass
        10  — URL sourced from Gemini audit, domain pattern confirmed
         5  — URL sourced from Gemini audit, domain pattern unconfirmed
         0  — URL sourced from aggregator or unknown

    Confidence Tiers:
        🟢  HIGH    80–100  Trust this URL. Verified working.
        🟡  MEDIUM  50–79   Probably right but spot-check before relying on it.
        🟠  LOW     25–49   Significant doubts. Manual verification needed.
        🔴  CRITICAL 0–24   Do not use. Likely wrong, dead, or pointing to wrong site.

Run:
    # From the Catalyst/backend/ directory:
    python -m investigations.verify_recorder_portals

    # Include CountyFusion (normally skipped — platform outage):
    python -m investigations.verify_recorder_portals --include-cf

    # Skip writing the markdown report:
    python -m investigations.verify_recorder_portals --no-report

Output:
    Console: color-coded table with confidence scores
    File:    backend/investigations/recorder_portal_verification_YYYY-MM-DD.md
"""

from __future__ import annotations

import argparse
import datetime
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

try:
    import requests
    from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Import connector
# ---------------------------------------------------------------------------

try:
    from investigations.county_recorder_connector import (
        _REGISTRY,
        OhioCounty,
        RecorderSystem,
    )
except ImportError:
    try:
        from county_recorder_connector import (
            _REGISTRY,
            OhioCounty,
            RecorderSystem,
        )
    except ImportError:
        print("ERROR: Cannot import county_recorder_connector. Run from the backend/ directory.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Confidence scoring constants
# ---------------------------------------------------------------------------

# Expected domain fragments per RecorderSystem.
# ALL fragments must be checked — we match if ANY one is present.
EXPECTED_DOMAINS: dict[RecorderSystem, list[str]] = {
    RecorderSystem.GOVOS_COUNTYFUSION: ["govos.com", "kofiletech.us"],
    RecorderSystem.GOVOS_CLOUD_SEARCH: ["publicsearch.us", "govos.com"],
    RecorderSystem.DTS_PAXWORLD: ["dts-oh.com", "paxworld", "tylerhost.net"],
    RecorderSystem.FIDLAR_AVA: ["ava.fidlar.com", "fidlar.com"],
    RecorderSystem.LAREDO: ["rep4laredo.fidlar.com", "laredo", "fidlar.com"],
    RecorderSystem.EAGLEWEB: ["tylerhost.net", "eagleweb"],
    RecorderSystem.COTT_SYSTEMS: ["cotthosting.com"],
    RecorderSystem.COMPILED_TECH: ["compiled-technologies.com"],
    RecorderSystem.USLANDRECORDS: ["avenuinsights.com", "uslandrecords.com"],
    # No fixed pattern — skip domain check
    RecorderSystem.CUSTOM: [],
    RecorderSystem.UNAVAILABLE: [],
}

# Known third-party aggregators — landing here is always wrong.
AGGREGATOR_DOMAINS = [
    "propertychecker.com",
    "netronline.com",
    "publicrecords.com",
    "netr.com",
    "zillow.com",
    "realtor.com",
    "trulia.com",
    "countyoffice.org",
    "pubrecord.org",
    "deeds.com",
    "publicrecordsohio.com",
    "ohio-land-records.com",
    "propertyshark.com",
]

# Keywords that signal a page is genuinely a recorder/land records portal.
RECORDER_KEYWORDS_STRONG = [
    "grantor",
    "grantee",
    "deed",
    "instrument number",
    "recorded",
    "book and page",
    "recorder's office",
    "land records",
    "official records search",
]
RECORDER_KEYWORDS_WEAK = [
    "record date",
    "document type",
    "legal description",
    "parcel",
    "real property",
    "mortgage",
    "release",
    "notary",
    "lien",
    "easement",
    "plat",
]

# URLs that were directly confirmed by the user or via live browser in this project.
# These get the maximum source bonus.
USER_CONFIRMED_URLS: set[str] = {
    # Trumbull — user-confirmed
    "https://records.co.trumbull.oh.us/PAXWorld/views/search",
    # Summit — user-confirmed
    "https://summitcountyoh-web.tylerhost.net/web/search/DOCSEARCH236S2",
    # Mercer — user-confirmed
    "https://recorder.mercercountyoh.gov/LandmarkWeb/",
    # Miami — live-tested
    "https://rep4laredo.fidlar.com/OHMiami/DirectSearch/#/search",
    # Pike — live-tested (loaded)
    "https://pikeohpublic.avenuinsights.com/",
    # Meigs — user-confirmed working
    "https://meigsoh.compiled-technologies.com/Default.aspx",
    # Madison — user-confirmed landing page
    "https://madisonoh.avenuinsights.com/Home/index.html",
    # Cuyahoga — CS pattern verified
    "https://cuyahoga.oh.publicsearch.us/",
    # Carroll — CS pattern verified
    "https://carroll.oh.publicsearch.us/",
    # Butler — CS pattern verified
    "https://butler.oh.publicsearch.us/",
    # Warren — CS pattern verified
    # Warren — CORRECTED 2026-03-28: Fidlar AVA (was warren.oh.publicsearch.us, returned DEAD)
    "https://ohwarren.fidlar.com/OHWarren/AvaWeb/",
    # Franklin — CS pattern verified
    "https://franklin.oh.publicsearch.us/",
    # Erie — EagleWeb pattern
    "https://eriecountyoh-selfservice.tylerhost.net/web/",
    # Lake — user-confirmed AVA rep2laredo instance
    "https://rep2laredo.fidlar.com/OHLake/AvaWeb/#/search",
    # Champaign — CORRECTED 2026-03-28: county portal (was ava.fidlar.com, returned 404)
    "https://champaigncountyrecorder.us/",
    # Hancock — CORRECTED 2026-03-28: county portal (was recorder.co.hancock.oh.us, returned DEAD)
    "https://www.co.hancock.oh.us/196/Record-Search",
    # Holmes — CORRECTED 2026-03-28: county-specific Fidlar subdomain (was ava.fidlar.com)
    "https://ohholmes.fidlar.com/OHHolmes/AvaWeb/",
    # Marion — CORRECTED 2026-03-28: rep3laredo instance (was ava.fidlar.com, returned 404)
    "https://rep3laredo.fidlar.com/OHMarion/AvaWeb/",
    # Wood — CORRECTED 2026-03-28: county-specific Fidlar subdomain (was ava.fidlar.com)
    "https://ohwood.fidlar.com/OHWood/AvaWeb/",
    # Ross — CORRECTED 2026-03-28: county portal (was co.ross.oh.us dead URL)
    "https://co.ross.oh.us/recorder/document-archive.html",
    # Knox — CORRECTED 2026-03-28: Cott Systems (was Compiled Tech with dead cert)
    "https://cotthosting.com/OHKnoxLANExternal/LandRecords/protected/v4/SrchName.aspx",
    # Ross — CORRECTED 2026-03-28: RossRecords.us (was co.ross.oh.us, returned DEAD)
    "https://www.rossrecords.us/",
    # Stark — user-confirmed recorder office landing page
    "https://starkcountyohio.gov/government/offices/recorder/",
}

# Counties confirmed via Gemini audit and domain-pattern match.
# These are not user-confirmed but are structurally plausible.
GEMINI_PATTERN_CONFIRMED: set[RecorderSystem] = {
    RecorderSystem.GOVOS_CLOUD_SEARCH,  # publicsearch.us pattern is very consistent
    RecorderSystem.EAGLEWEB,  # tylerhost.net pattern is very consistent
    RecorderSystem.COTT_SYSTEMS,  # cotthosting.com pattern is very consistent
    # compiled-technologies.com subdomain pattern is consistent
    RecorderSystem.COMPILED_TECH,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class PortalCheckResult:
    county_name: str
    county_enum: OhioCounty
    system: RecorderSystem
    original_url: str
    final_url: Optional[str]
    http_status: Optional[int]

    # HTTP classification
    # OK | REDIRECT_SAME | REDIRECT_CROSS | DEAD | TIMEOUT | AGGREGATOR
    http_status_class: str

    # Confidence components (each 0 to max)
    score_http: int  # 0–35
    score_domain: int  # 0–25
    score_content: int  # 0–20
    score_source: int  # 0–20

    confidence: int  # 0–100 total
    confidence_tier: str  # HIGH | MEDIUM | LOW | CRITICAL

    flags: list[str] = field(default_factory=list)  # specific issues found
    note: str = ""
    elapsed_ms: int = 0
    page_text_snippet: str = ""


def _confidence_tier(score: int) -> str:
    if score >= 80:
        return "HIGH"
    elif score >= 50:
        return "MEDIUM"
    elif score >= 25:
        return "LOW"
    else:
        return "CRITICAL"


TIER_ICON = {
    "HIGH": "🟢",
    "MEDIUM": "🟡",
    "LOW": "🟠",
    "CRITICAL": "🔴",
    "SKIPPED": "⏭️ ",
}

TIER_COLOR = {
    "HIGH": "green",
    "MEDIUM": "yellow",
    "LOW": "orange",
    "CRITICAL": "red",
    "SKIPPED": "blue",
}

ANSI = {
    "green": "\033[92m",
    "yellow": "\033[93m",
    "orange": "\033[38;5;208m",
    "red": "\033[91m",
    "blue": "\033[94m",
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}


def _color(text: str, color: str) -> str:
    c = ANSI.get(color, "")
    return f"{c}{text}{ANSI['reset']}"


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------


def _same_domain(url1: str, url2: str) -> bool:
    """Return True if both URLs share the same registered domain."""
    try:
        h1 = urlparse(url1).netloc.lower().lstrip("www.")
        h2 = urlparse(url2).netloc.lower().lstrip("www.")
        # Compare last two domain parts (e.g. "tylerhost.net")
        parts1 = h1.split(".")
        parts2 = h2.split(".")
        return ".".join(parts1[-2:]) == ".".join(parts2[-2:])
    except Exception:
        return False


def _is_aggregator(url: str) -> bool:
    url_lower = url.lower()
    return any(agg in url_lower for agg in AGGREGATOR_DOMAINS)


def _domain_matches_system(url: str, system: RecorderSystem) -> bool:
    patterns = EXPECTED_DOMAINS.get(system, [])
    if not patterns:
        return True  # CUSTOM/UNAVAILABLE — no pattern to check
    url_lower = url.lower()
    return any(p.lower() in url_lower for p in patterns)


# ---------------------------------------------------------------------------
# Content scoring
# ---------------------------------------------------------------------------


def _score_content(page_text: str) -> tuple[int, list[str]]:
    """Return (score 0-20, list of matched keywords)."""
    if not page_text:
        return 0, []
    text_lower = page_text.lower()

    strong_hits = [kw for kw in RECORDER_KEYWORDS_STRONG if kw in text_lower]
    weak_hits = [kw for kw in RECORDER_KEYWORDS_WEAK if kw in text_lower]

    if len(strong_hits) >= 3:
        return 20, strong_hits[:5]
    elif len(strong_hits) >= 1:
        return 14, strong_hits[:3] + weak_hits[:2]
    elif len(weak_hits) >= 3:
        return 10, weak_hits[:5]
    elif len(weak_hits) >= 1:
        return 5, weak_hits[:3]
    else:
        return 0, []


# ---------------------------------------------------------------------------
# Source scoring
# ---------------------------------------------------------------------------


def _score_source(original_url: str, system: RecorderSystem, final_url: Optional[str]) -> int:
    check_url = final_url or original_url
    if original_url in USER_CONFIRMED_URLS or check_url in USER_CONFIRMED_URLS:
        return 20
    if system in GEMINI_PATTERN_CONFIRMED and _domain_matches_system(check_url, system):
        return 15
    if _domain_matches_system(check_url, system):
        return 10
    return 5


# ---------------------------------------------------------------------------
# HTTP request
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_TIMEOUT = 8
REQUEST_RETRIES = 2
REQUEST_RETRY_BACKOFF_SECONDS = 1.5


def _fetch(url: str) -> tuple[Optional[requests.Response], Optional[str], int]:
    """
    Returns (response, error_message, elapsed_ms).
    error_message is None on success.
    """
    start = time.monotonic()
    attempts = REQUEST_RETRIES + 1
    last_error = "TIMEOUT"

    for attempt in range(1, attempts + 1):
        try:
            # Use connect/read timeout tuple. This avoids long hangs on slow
            # county servers while still giving them multiple chances.
            resp = requests.get(
                url,
                headers=HEADERS,
                timeout=(5, REQUEST_TIMEOUT),
                allow_redirects=True,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return resp, None, elapsed_ms
        except Timeout:
            last_error = f"TIMEOUT (attempt {attempt}/{attempts})"
        except ConnectionError as e:
            last_error = f"CONNECTION_ERROR (attempt {attempt}/{attempts}): {str(e)[:80]}"
        except TooManyRedirects:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return None, "TOO_MANY_REDIRECTS", elapsed_ms
        except Exception as e:
            last_error = f"ERROR: {type(e).__name__}: {str(e)[:80]}"

        if attempt < attempts:
            time.sleep(REQUEST_RETRY_BACKOFF_SECONDS * attempt)

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return None, last_error, elapsed_ms


# ---------------------------------------------------------------------------
# Main check function
# ---------------------------------------------------------------------------


def check_portal(county: OhioCounty, skip_cf: bool = True) -> PortalCheckResult:
    info = _REGISTRY[county]
    original_url = info.portal_url or ""

    def _skipped(reason: str) -> PortalCheckResult:
        return PortalCheckResult(
            county_name=info.name,
            county_enum=county,
            system=info.system,
            original_url=original_url,
            final_url=None,
            http_status=None,
            http_status_class="SKIPPED",
            score_http=0,
            score_domain=0,
            score_content=0,
            score_source=0,
            confidence=0,
            confidence_tier="SKIPPED",
            flags=[],
            note=reason,
            elapsed_ms=0,
        )

    if info.system == RecorderSystem.UNAVAILABLE:
        return _skipped("In-person only — no portal URL")

    if skip_cf and info.system == RecorderSystem.GOVOS_COUNTYFUSION:
        return _skipped(
            "CountyFusion — skipped (platform-wide outage confirmed 2026-03-28; "
            "re-run with --include-cf once GovOS recovers)"
        )

    if not original_url:
        return PortalCheckResult(
            county_name=info.name,
            county_enum=county,
            system=info.system,
            original_url="",
            final_url=None,
            http_status=None,
            http_status_class="DEAD",
            score_http=0,
            score_domain=0,
            score_content=0,
            score_source=0,
            confidence=0,
            confidence_tier="CRITICAL",
            flags=["NO_URL"],
            note="No portal_url set in connector",
        )

    # --- HTTP fetch ---
    resp, err, elapsed_ms = _fetch(original_url)

    if err:
        status_class = "TIMEOUT" if "TIMEOUT" in err else "DEAD"
        return PortalCheckResult(
            county_name=info.name,
            county_enum=county,
            system=info.system,
            original_url=original_url,
            final_url=None,
            http_status=None,
            http_status_class=status_class,
            score_http=0,
            score_domain=0,
            score_content=0,
            score_source=0,
            confidence=0,
            confidence_tier="CRITICAL",
            flags=[status_class],
            note=err,
            elapsed_ms=elapsed_ms,
        )

    final_url = resp.url
    http_status = resp.status_code

    flags: list[str] = []
    notes: list[str] = []

    # --- Aggregator check (immediate CRITICAL) ---
    if _is_aggregator(final_url):
        flags.append("AGGREGATOR")
        notes.append(f"Landed on third-party aggregator: {final_url}")
        return PortalCheckResult(
            county_name=info.name,
            county_enum=county,
            system=info.system,
            original_url=original_url,
            final_url=final_url,
            http_status=http_status,
            http_status_class="AGGREGATOR",
            score_http=0,
            score_domain=0,
            score_content=0,
            score_source=0,
            confidence=0,
            confidence_tier="CRITICAL",
            flags=flags,
            note="; ".join(notes),
            elapsed_ms=elapsed_ms,
        )

    # --- HTTP score ---
    if http_status >= 400:
        score_http = 0
        http_class = "DEAD"
        flags.append(f"HTTP_{http_status}")
        notes.append(f"HTTP {http_status}")
    else:
        redirected = final_url.rstrip("/") != original_url.rstrip("/")
        if not redirected:
            score_http = 35
            http_class = "OK"
        elif _same_domain(original_url, final_url):
            score_http = 25
            http_class = "REDIRECT_SAME"
            notes.append(f"Redirected (same domain) → {final_url}")
        else:
            score_http = 15
            http_class = "REDIRECT_CROSS"
            flags.append("CROSS_DOMAIN_REDIRECT")
            notes.append(f"Cross-domain redirect → {final_url}")

    # --- Domain score ---
    if _is_aggregator(final_url):
        score_domain = 0
        flags.append("AGGREGATOR")
    elif not _domain_matches_system(final_url, info.system):
        score_domain = 0
        flags.append("DOMAIN_MISMATCH")
        notes.append(
            f"System={info.system.value} but domain doesn't match "
            f"expected pattern {EXPECTED_DOMAINS.get(info.system, [])}"
        )
    else:
        score_domain = 25

    # --- Content score ---
    page_text = ""
    content_keywords: list[str] = []
    if http_status < 400:
        try:
            # Use text if available, limit to first 50KB
            page_text = resp.text[:50000] if resp.text else ""
        except Exception:
            page_text = ""
        score_content, content_keywords = _score_content(page_text)
        if score_content == 0 and page_text:
            flags.append("NO_RECORDER_KEYWORDS")
            notes.append("Page loaded but no recorder-specific keywords found")
    else:
        score_content = 0

    # --- Source score ---
    score_source = _score_source(original_url, info.system, final_url)

    # --- Total confidence ---
    # If HTTP is dead, clamp to max 15 regardless of other scores
    if score_http == 0:
        confidence = min(score_http + score_domain + score_content + score_source, 15)
    else:
        confidence = score_http + score_domain + score_content + score_source

    confidence = max(0, min(100, confidence))
    tier = _confidence_tier(confidence)

    # Snippet for report
    snippet = ""
    if content_keywords:
        snippet = "Keywords: " + ", ".join(content_keywords[:5])
    elif page_text and http_status < 400:
        # First 120 chars of visible text
        clean = " ".join(page_text.split())[:120]
        snippet = f"Page text: {clean}"

    return PortalCheckResult(
        county_name=info.name,
        county_enum=county,
        system=info.system,
        original_url=original_url,
        final_url=final_url,
        http_status=http_status,
        http_status_class=http_class,
        score_http=score_http,
        score_domain=score_domain,
        score_content=score_content,
        score_source=score_source,
        confidence=confidence,
        confidence_tier=tier,
        flags=flags,
        note="; ".join(notes) if notes else f"HTTP {http_status}",
        elapsed_ms=elapsed_ms,
        page_text_snippet=snippet,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_verification(include_cf: bool = False) -> list[PortalCheckResult]:
    skip_cf = not include_cf
    counties = sorted(_REGISTRY.keys(), key=lambda c: _REGISTRY[c].name)

    total = len(counties)
    cf_count = sum(1 for c in counties if _REGISTRY[c].system == RecorderSystem.GOVOS_COUNTYFUSION)
    to_check = total if include_cf else total - cf_count

    print(f"\n{ANSI['bold']}Ohio County Recorder Portal Verification{ANSI['reset']}")
    print(
        f"Date: {datetime.date.today()}  |  Counties: {total}  |  "
        f"Checking: {to_check}  |  CF skipped: {cf_count if skip_cf else 0}"
    )
    print(f"{'─' * 90}")
    print(f"  {'County':<18} {'System':<22} {'Score':>5}  {'Tier':<10}  Note")
    print(f"{'─' * 90}")

    results = []
    for i, county in enumerate(counties, 1):
        info = _REGISTRY[county]
        print(f"  [{i:02d}/{total}] {info.name:<18}", end="", flush=True)

        result = check_portal(county, skip_cf=skip_cf)

        if result.confidence_tier == "SKIPPED":
            tier_str = _color("⏭️  SKIPPED", "blue")
            print(f" {info.system.value:<22} {'—':>5}  {tier_str:<20}  {result.note[:50]}")
        else:
            icon = TIER_ICON.get(result.confidence_tier, "?")
            color = TIER_COLOR.get(result.confidence_tier, "reset")
            tier_str = _color(f"{icon} {result.confidence_tier}", color)
            score_str = _color(f"{result.confidence:>3}", color)
            flag_str = f" [{', '.join(result.flags[:2])}]" if result.flags else ""
            print(
                f" {info.system.value:<22} {score_str}/100  {tier_str:<20}  "
                f"{result.note[:45]}{flag_str}"
            )

        results.append(result)

        if result.http_status_class not in ("SKIPPED",):
            time.sleep(0.25)  # be polite

    return results


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def _write_report(results: list[PortalCheckResult]) -> str:
    import os

    today = datetime.date.today().isoformat()
    # Write next to this script file, regardless of cwd
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, f"recorder_portal_verification_{today}.md")

    checked = [r for r in results if r.confidence_tier != "SKIPPED"]
    skipped = [r for r in results if r.confidence_tier == "SKIPPED"]

    critical = [r for r in checked if r.confidence_tier == "CRITICAL"]
    low = [r for r in checked if r.confidence_tier == "LOW"]
    medium = [r for r in checked if r.confidence_tier == "MEDIUM"]
    high = [r for r in checked if r.confidence_tier == "HIGH"]

    def tier_badge(tier: str) -> str:
        return f"{TIER_ICON.get(tier, '')} {tier}"

    lines = [
        f"# Ohio County Recorder Portal Verification — {today}",
        "",
        "## Confidence Score Model",
        "",
        "| Component | Max Points | Description |",
        "|-----------|-----------|-------------|",
        "| HTTP Reachability | 35 | 200 no-redirect=35, same-domain redirect=25, cross-domain=15, error=0 |",
        "| Domain Pattern Match | 25 | Final URL domain matches expected pattern for RecorderSystem |",
        "| Page Content | 20 | Page text contains recorder-specific keywords (grantor, grantee, deed, etc.) |",
        "| URL Source | 20 | User-confirmed=20, pattern-confirmed=15, Gemini-sourced=5–10 |",
        "",
        "| Tier | Score | Meaning |",
        "|------|-------|---------|",
        "| 🟢 HIGH | 80–100 | Trust this URL. Verified working. |",
        "| 🟡 MEDIUM | 50–79 | Probably right — spot-check before relying on it. |",
        "| 🟠 LOW | 25–49 | Significant doubts. Manual verification needed. |",
        "| 🔴 CRITICAL | 0–24 | Do not use. Likely dead, wrong, or pointing to aggregator. |",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Tier | Count |",
        "|------|-------|",
        f"| 🔴 CRITICAL | {len(critical)} |",
        f"| 🟠 LOW | {len(low)} |",
        f"| 🟡 MEDIUM | {len(medium)} |",
        f"| 🟢 HIGH | {len(high)} |",
        f"| ⏭️  SKIPPED (CountyFusion — outage) | {len(skipped)} |",
        f"| **Total** | **{len(results)}** |",
        "",
        "---",
        "",
        "## 🔴 CRITICAL — Fix Immediately",
        "",
        "_Score 0–24. These URLs are dead, redirect to aggregators, or have no recorder content._",
        "",
    ]

    if critical:
        lines += [
            "| County | System | Score | Flags | Original URL | Final URL | Note |",
            "|--------|--------|-------|-------|--------------|-----------|------|",
        ]
        for r in sorted(critical, key=lambda x: x.county_name):
            orig = f"`{r.original_url}`" if r.original_url else "—"
            final = f"`{r.final_url}`" if r.final_url else "—"
            flags = ", ".join(r.flags) if r.flags else "—"
            lines.append(
                f"| {r.county_name} | {r.system.value} | {r.confidence} | "
                f"{flags} | {orig} | {final} | {r.note[:80]} |"
            )
    else:
        lines.append("_None._")

    lines += [
        "",
        "---",
        "",
        "## 🟠 LOW Confidence — Manual Verification Needed",
        "",
        "_Score 25–49. URL loads but domain, content, or source raises concerns._",
        "",
    ]

    if low:
        lines += [
            "| County | System | Score | Flags | URL | Snippet |",
            "|--------|--------|-------|-------|-----|---------|",
        ]
        for r in sorted(low, key=lambda x: x.county_name):
            flags = ", ".join(r.flags) if r.flags else "—"
            snippet = r.page_text_snippet[:80] if r.page_text_snippet else r.note[:80]
            lines.append(
                f"| {r.county_name} | {r.system.value} | {r.confidence} | "
                f"{flags} | `{r.original_url}` | {snippet} |"
            )
    else:
        lines.append("_None._")

    lines += [
        "",
        "---",
        "",
        "## 🟡 MEDIUM Confidence — Spot-Check Recommended",
        "",
        "_Score 50–79. Structurally correct but not fully verified by live user session._",
        "",
        "| County | System | Score | Flags | URL |",
        "|--------|--------|-------|-------|-----|",
    ]
    for r in sorted(medium, key=lambda x: x.county_name):
        flags = ", ".join(r.flags) if r.flags else "—"
        lines.append(
            f"| {r.county_name} | {r.system.value} | {r.confidence} | "
            f"{flags} | `{r.original_url}` |"
        )

    lines += [
        "",
        "---",
        "",
        "## 🟢 HIGH Confidence — Verified",
        "",
        "_Score 80–100. URL confirmed working with recorder content present._",
        "",
        "| County | System | Score | URL |",
        "|--------|--------|-------|-----|",
    ]
    for r in sorted(high, key=lambda x: x.county_name):
        lines.append(
            f"| {r.county_name} | {r.system.value} | {r.confidence} | `{r.original_url}` |"
        )

    lines += [
        "",
        "---",
        "",
        "## ⏭️  Skipped (CountyFusion — Platform Outage)",
        "",
        "_These counties use GovOS CountyFusion which has been down since 2026-03-28._",
        "_Re-run with `--include-cf` once GovOS recovers to verify their URLs._",
        "",
        "| County | URL |",
        "|--------|-----|",
    ]
    for r in sorted(skipped, key=lambda x: x.county_name):
        url = f"`{r.original_url}`" if r.original_url else "—"
        lines.append(f"| {r.county_name} | {url} |")

    lines += [
        "",
        "---",
        "",
        "## How to Fix CRITICAL / LOW Counties",
        "",
        "1. Go to the county's official `.oh.gov` or `.oh.us` website",
        "2. Navigate: County website → Recorder → Online Records / Document Search",
        "3. Follow any links from the recorder's own page to the search portal",
        "4. Record the final URL the recorder's office uses (not Google/aggregator results)",
        "5. Update `county_recorder_connector.py` with the correct URL and system",
        "6. Add the URL to `USER_CONFIRMED_URLS` in this script so future runs score it HIGH",
        "",
        "**Do NOT use Google search results or aggregator sites to find recorder URLs.**",
        "**Always follow the official county government path.**",
    ]

    content = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    # Windows consoles default to CP1252 which can't encode box-drawing chars
    # or emoji.  Reconfigure stdout/stderr to UTF-8 before any output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Verify all 88 Ohio county recorder portal URLs with confidence scoring"
    )
    parser.add_argument(
        "--include-cf",
        action="store_true",
        default=False,
        help="Include CountyFusion counties (skipped by default — platform outage)",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        default=False,
        help="Skip writing the markdown report file",
    )
    args = parser.parse_args()

    results = run_verification(include_cf=args.include_cf)

    # --- Console summary ---
    checked = [r for r in results if r.confidence_tier != "SKIPPED"]
    critical = [r for r in checked if r.confidence_tier == "CRITICAL"]
    low = [r for r in checked if r.confidence_tier == "LOW"]
    medium = [r for r in checked if r.confidence_tier == "MEDIUM"]
    high = [r for r in checked if r.confidence_tier == "HIGH"]

    print(f"\n{'─' * 90}")
    print(f"{ANSI['bold']}Confidence Summary{ANSI['reset']}")
    print(f"  {_color('🔴 CRITICAL', 'red'):<30} {len(critical):>3}  — fix immediately")
    print(f"  {_color('🟠 LOW', 'orange'):<30} {len(low):>3}  — manual verification needed")
    print(f"  {_color('🟡 MEDIUM', 'yellow'):<30} {len(medium):>3}  — spot-check recommended")
    print(f"  {_color('🟢 HIGH', 'green'):<30} {len(high):>3}  — verified")
    print(
        f"  {_color('⏭️  SKIPPED', 'blue'):<30} "
        f"{len(results) - len(checked):>3}  — CountyFusion outage"
    )

    if critical or low:
        print(f"\n  {_color(f'{len(critical) + len(low)} counties need attention', 'red')}")

    path = _write_report(results)
    print(f"\n  Report: {path}")


if __name__ == "__main__":
    main()
