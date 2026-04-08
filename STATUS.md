# Catalyst — Build Status

**Last updated:** 2026-04-07

This project is in active development. This file is updated every time
the state of a major component changes. If something looks half-built,
that's because part of it is — see "In active refactor" below. The
current focus is a scoped 2-week rebuild pass driven by a product
reframe around a single central deliverable: the referral package.

---

## Working

These are the parts of Catalyst that are wired end-to-end and currently
running on Railway.

| Component | What it does | Notes |
|-----------|-------------|-------|
| Document upload + OCR | Multi-file upload, SHA-256 hashing, PyPDF2 → Tesseract OCR fallback | Chain of custody verified on every file |
| Entity extraction pipeline | Rule-based extraction → normalization → fuzzy resolution with Claude AI fallback | Surfaces match candidates, never silent-merges |
| IRS TEOS 990 XML connector | Fetches Form 990 XML directly from apps.irs.gov via HTTP range requests (~5KB per filing) | Replaced earlier bulk-download approach. Parses Parts I, IV, VI, VII. |
| Ohio Auditor of State connector | Scrapes audit reports, finds Findings for Recovery | ASP.NET ViewState postback |
| County Recorder connector | All 88 Ohio counties mapped to recorder portals; auto-parses uploaded deeds | URL builder + document parser |
| Ohio Secretary of State connector | Local CSV search (admin uploads CSVs from publicfiles.ohiosos.gov) | Switched from runtime download after SOS started returning 403s |
| Case detail UI | 6 tabs: Overview, Documents, Research, Financials, Pipeline, Referrals | React + Vite, dark/light/auto themes, keyboard shortcuts |
| Entity relationship graph | D3 force-directed graph synchronized with a brushable timeline | Click a node to select; drag to reposition; brush the timeline to filter |
| AI assistant panel | Claude-powered case summary, relationship analysis, free-text Q&A | Triage tool only — not part of the final deliverable |
| Audit log | Append-only log on every mutation | Never updated or deleted |
| Backend test suite | 555+ backend tests covering connectors, API endpoints, and signal rules | CI runs ruff + tsc + vite on every push |

---

## In active refactor

These are the parts being rebuilt right now. Calling them out openly because
the right answer when something is mid-refactor is to say so.

| Component | Why it's being refactored |
|-----------|---------------------------|
| Signal / Detection / Finding three-table pipeline | Conflates two different concepts (automatic ingestion vs. manual triage workbench). Collapsing to a single `Finding` model with `status` (NEW / NEEDS_EVIDENCE / DISMISSED / CONFIRMED) and `evidence_weight` (SPECULATIVE / DIRECTIONAL / DOCUMENTED / TRACED) fields. |
| Signal rule set | Currently 29 rules. Many were built speculatively, not grounded in real cases. Cutting back to a focused set of ~5–7 rules derived from patterns I actually encountered in the founding investigation. |
| Referral package exporter | Currently a placeholder. Being rebuilt as a deterministic, citation-bearing, template-driven export — not AI-generated narrative. This is the central deliverable of the whole system. |
| `SocialMediaConnection` model | Being removed. A bot can't reliably scan social media the way I originally imagined; the use case is better served by ingesting screenshots as `Document` records and linking them via the existing `Relationship` table. |
| `GovernmentReferral` model | Being removed. Referral tracking is out of scope for the portfolio version — the system's job is to *produce* the package, not track what happens to it afterward. |
| Repo presentation | This file. `README.md`. `CLAUDE.md`. Cleaning up stale stats and surface-level cruft as part of the same pass. |

---

## Planned

In rough priority order. Subject to change as the rebuild progresses.

1. **Deterministic referral package exporter** — the central deliverable. Template-driven, citation-bearing, traceable sentence-by-sentence back to source documents in the case file. This is the thing a professional investigator actually reads.
2. **Pre-loaded demo case** — the founding investigation, anonymized, available on first launch so anyone (recruiter, interviewer, sample user) can see what a finished case looks like without having to upload their own documents.
3. **Short demo video + README screenshots** — paired with the demo case.
4. **Inline notes on entities** — currently only signals support investigator notes.
5. **Saved searches** — recurring queries on the entity browser.
6. **Document annotation** — highlight and comment on PDFs in-app.
7. **ODNR parcel API recovery** — external API has been unreachable from Railway for weeks; monitoring for upstream fix.

---

## Known issues

- **ODNR statewide parcel API** (county auditor connector) is unreachable from Railway. Both the primary and fallback URLs return 404 / time out. External API issue, tracking upstream. Not blocking the referral-package rebuild.
- **Ohio SOS connector requires manual CSV upload** via an admin endpoint — automated download was blocked by SOS returning 403s. Documented in the connector file.
- **`form990_parser.py`** exists but isn't yet wired into the post-classification pipeline. May be partially superseded by the new IRS TEOS XML parser, which extracts Parts IV / VI / VII directly. Revisit after rebuild.

---

## How to read this file

If you're a recruiter or hiring manager: this file exists so you can see
the *real* state of the project in under sixty seconds, instead of
having to guess from commit history. The "In active refactor" column is
a feature, not a confession — it shows that I know my own system and
can name what needs to change and why. If the rebuild outlined here has
landed since you last checked, this file will reflect that.

If you're a contributor or future maintainer: start with
[CLAUDE.md](CLAUDE.md) for the full system map, then this file for the
current state of the refactor.
