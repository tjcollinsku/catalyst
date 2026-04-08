# Catalyst

**A public-records investigation platform that turns scattered evidence into a referral package a professional investigator can act on.**

Built backwards from a real fraud investigation. The hand-rolled version of this work — pulling 990 filings, deeds, UCC filings, audit reports, and county records by hand and stitching them together in folders and spreadsheets — produced formal referrals to the Ohio Attorney General, the IRS, the FBI, and a federal agency Office of Inspector General. The process worked, but it was organizationally fragile. Catalyst is the systematic version of that process.

The customer of the output is the investigator with the badge and the subpoena power, not the citizen who assembled the case. Every design decision flows from that.

---

## Contact

- **GitHub:** [tjcollinsku](https://github.com/tjcollinsku)
- **LinkedIn:** [tylerjcollins](https://www.linkedin.com/in/tylerjcollins/)
- **Email:** tjcollinsku@gmail.com

---

## Why this project exists

Most investigation tooling falls into one of two traps:

- **Too manual to scale.** Folders, spreadsheets, ad-hoc Python scripts. Works once, breaks on the second case.
- **Too automated to be legally defensible.** Silent fuzzy merges, AI-generated narratives, opaque chains of inference. Useful for triage, useless as evidence.

Catalyst is built for the middle path: automate the grinding parts (extraction, normalization, fuzzy matching, signal detection), preserve investigator control over every consequential decision, and keep a clean chain of evidence from the source document to the final referral.

The deliverable is a **deterministic, citation-bearing referral package** — not an AI summary. Every sentence in the output traces back to a specific document in the case file.

---

## What's in the box

### Backend
Django 4.2 + PostgreSQL 16. Investigation-centered data model with cases, documents, persons, organizations, properties, financial instruments, findings, append-only audit log, and link tables for the relationships that matter.

### Document processing pipeline
PDF text extraction with OCR fallback (PyPDF2 + Tesseract), rule-based document classification, three-stage entity pipeline (extraction → normalization → resolution), and a signal detection engine driven by patterns observed in the founding investigation.

### External data connectors
Six independent, failure-isolated connectors for public records:

- IRS Form 990 e-file XML via direct TEOS range requests
- Ohio Secretary of State business filings
- Ohio Auditor of State audit reports
- Ohio county recorder portals (88-county coverage)
- Ohio Department of Natural Resources statewide parcel layer
- ProPublica Nonprofit Explorer (retained as a fallback)

Each connector is independently testable with mocked HTTP and degrades gracefully — a partial failure in one source does not collapse intake.

### Frontend
React 18 + TypeScript + Vite, with a force-directed entity-relationship graph (D3.js) synchronized to a brushable timeline, dark/light/auto theming, skeleton loading states, and WCAG-aware accessibility (skip-to-content, ARIA live regions, reduced-motion support).

### Test surface
500+ backend tests covering connectors, API endpoints, and signal rules. CI runs ruff, TypeScript type-check, and Vite build on every push.

---

## Engineering decisions worth defending in an interview

**1. Audit-first data model.** SHA-256 chain of custody on every document, append-only audit logging on every mutation, immutable timestamp guards on government referral filing dates. Legal defensibility is a primary requirement of this domain, not a nice-to-have.

**2. Human-in-the-loop entity resolution.** Fuzzy matching surfaces candidates rather than silent-merging. An investigator must confirm before two records become one. A silent merge in an evidence chain is worse than an extra click.

**3. AI as a triage aid, not a deliverable.** Anthropic Claude API handles messy document extraction and assists with exploration. The deliverable — the referral package — is template-driven and citation-bearing. Generated text never goes into the file an investigator with subpoena power reads.

**4. Failure-isolated connectors.** Each external source is its own module with its own tests. A 404 from one ArcGIS endpoint does not take down the IRS pipeline.

**5. Backwards from a real case.** Every signal rule, every data model field, every UI affordance traces back to an actual pain point I hit running the founding investigation by hand. Nothing in here is speculative.

---

## Project status

Catalyst is in an active rebuild as of April 2026, refactoring toward the referral-package framing described above. For a current snapshot of what's working, what's being refactored, and what's planned, see [STATUS.md](STATUS.md).

---

## Repo map

- [backend](backend) — Django app, models, views, signal rules, connectors
- [frontend](frontend) — React + TypeScript + Vite
- [docs](docs) — charter, architecture, governance, session history
- [STATUS.md](STATUS.md) — current state of every subsystem

---

## How to run

**Backend**

1. Start PostgreSQL: `docker-compose up`
2. Create and activate a Python virtual environment
3. Install dependencies: `pip install -r backend/requirements.txt`
4. Run migrations: `python manage.py migrate`
5. Start server: `python manage.py runserver`

**Frontend**

1. `cd frontend`
2. `npm install`
3. `npm run dev`

Vite runs on `http://127.0.0.1:5173`. API requests to `/api/*` proxy to Django at `http://127.0.0.1:8000`. Keep Django running in parallel.

---

## Workflow guardrails

- Contributor standards: [CONTRIBUTING.md](CONTRIBUTING.md)
- PR checklist: [.github/pull_request_template.md](.github/pull_request_template.md)
- Commit template: [.gitmessage.txt](.gitmessage.txt)

One-time setup:
```bash
git config commit.template .gitmessage.txt
pip install -r backend/requirements-dev.txt
bash ./pc install
```

Daily usage:
```bash
bash ./pc           # run checks before committing
bash ./pc run --all-files
```

---

## A note on the founding investigation

This platform was built from a real public-records investigation into a nonprofit organization, conducted using only publicly available filings (IRS Form 990s, Secretary of State records, county recorder filings, audit reports). The investigation produced formal referrals to four federal and state agencies. Identifying details have been intentionally removed from this public repository; verification documentation is available on request.
