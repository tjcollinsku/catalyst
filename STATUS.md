# Catalyst — Build Status

**Last updated:** 2026-04-10

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
| Referral package PDF exporter | Deterministic, citation-bearing PDF generation with cover page, findings, financial summary, and document index with SHA-256 chain of custody | The central deliverable — what a professional investigator reads |
| Fraud signal detection engine | 14 pattern rules (cut from 29) grounded in real investigation patterns — valuation anomalies, insider swaps, false disclosures, revenue spikes | Each rule tied to a real anomaly source |
| Demo case ("Bright Future Foundation") | Pre-loaded investigation with 4 persons, 2 orgs, 2 properties, 6 years of financials, 7 documents, and 9 confirmed findings | `python manage.py seed_demo` — shows the full pipeline working |
| AI assistant panel | Claude-powered case summary, relationship analysis, free-text Q&A | Triage tool only — not part of the final deliverable |
| Audit log | Append-only log on every mutation | Never updated or deleted |
| Backend test suite | 555+ backend tests covering connectors, API endpoints, and signal rules | CI runs ruff + tsc + vite on every push |

---

## In active refactor

These are the parts being rebuilt right now. Calling them out openly because
the right answer when something is mid-refactor is to say so.

| Component | Why it's being refactored |
|-----------|---------------------------|
| Repo presentation | This file. `README.md`. `CLAUDE.md`. Keeping surface-level docs in sync with the rebuild as it lands. |

**Recently completed (Session 33):**
- ~~Signal / Detection / Finding three-table pipeline~~ → Collapsed to single `Finding` model with `status` + `evidence_weight` dimensions. Frontend fully updated.
- ~~Signal rule set~~ → Cut from 29 to 14 rules, all grounded in real investigation patterns.
- ~~Referral package exporter~~ → Shipped. Deterministic PDF with citations, financial tables, and document index.
- ~~`SocialMediaConnection` model~~ → Removed. Use `Document` + `Relationship` instead.
- ~~`GovernmentReferral` model~~ → Removed. The system produces the package; tracking what happens afterward is out of scope.

---

## Planned

In rough priority order. Subject to change as the rebuild progresses.

1. ~~**Deterministic referral package exporter**~~ — **DONE.** PDF with cover page, executive summary, findings with citations, financial tables, and document index with SHA-256 hashes.
2. ~~**Pre-loaded demo case**~~ — **DONE.** "Bright Future Foundation" — fictional scenario with 9 findings across 6 signal rules, exercising the full pipeline.
3. **Short demo video + README screenshots** — paired with the demo case.
4. **Inline notes on entities** — currently only findings support investigator notes.
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
