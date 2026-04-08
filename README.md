# Catalyst

**A public-records investigation platform for citizen investigators.**
Catalyst ingests documents, extracts entities, pulls public records from
IRS and state data sources, flags patterns worth a closer look, and
exports a referral package a professional investigator with subpoena
power can act on.

> **Status: active development** — see [STATUS.md](STATUS.md) for what's
> working, what's being refactored, and what's planned. This project is
> currently in a scoped 2-week rebuild pass driven by a reframe of the
> product around a single deliverable: the referral package.

---

## Why it exists

Catalyst started as a set of spreadsheets I built in 2025 while
conducting a public-records investigation into an Ohio nonprofit I had
reason to believe was being used to move money in ways that didn't match
its stated charitable purpose. The investigation took months of manual
cross-referencing — 990s, property records, state filings, officer
histories — and produced formal referrals to four federal and state
agencies, including the Ohio Attorney General's Charitable Law Section,
the IRS, the FBI, and a federal agency OIG. I'm leaving the nonprofit
unnamed here while the matters are active.

Catalyst is the tool I wish I'd had when I started. It is **not** a
replacement for professional investigators. It is a structured way for a
citizen to assemble public records into a defensible referral package
that a professional can act on quickly. The customer of Catalyst's
output is the investigator with the badge, not the citizen using the
tool. Every design decision flows from that.

---

## What it does

- **Ingest** documents (990s, deeds, audit reports, news clippings) with
  SHA-256 chain of custody on every file
- **Extract** entities (persons, organizations, properties, financial
  instruments) using a rule-based pipeline with optional Claude AI
  fallback for messy text
- **Pull** public records from external sources: IRS Form 990 XML (direct
  from apps.irs.gov), Ohio Secretary of State, Ohio Auditor of State, all
  88 Ohio county recorder portals
- **Flag** patterns worth a closer look — shell entities, timeline
  compression, excessive officer compensation, address nexus, and others
  derived directly from anomalies I encountered in the founding
  investigation
- **Visualize** the entity-relationship graph and a synchronized timeline
  so the shape of the case is visible at a glance
- **Export** a referral package — the deterministic, citation-bearing
  document a professional investigator can read and act on

---

## Tech stack

**Backend:** Python 3.11 · Django 4.2 · Django REST patterns · PostgreSQL 16 · Gunicorn

**Frontend:** React 18 · TypeScript · Vite · D3.js · React Router · CSS Modules

**AI:** Anthropic Claude API (Haiku for extraction, Sonnet for analysis)

**Document processing:** PyPDF2 · Tesseract OCR · custom 990 XML parser

**Infra:** Docker (multi-stage) · Railway · GitHub Actions CI (ruff + tsc + vite)

---

## Screenshots

> Short demo video and screenshots of the case detail view, entity
> relationship graph, and referral package export are coming in v0.2
> alongside the rebuild. In the meantime, the [STATUS.md](STATUS.md)
> file is the honest summary of what's working today.

---

## How it's built

### Audit-first by design
SHA-256 hash on every uploaded document. Append-only audit log on every
mutation. Immutable timestamp guards on government referral filing dates.
This is a *legal defensibility* decision, not a "nice to have." A
referral package that can't show clean chain of custody isn't worth
submitting.

### Human-in-the-loop by design
Fuzzy entity matches surface as candidates, never silent merges. The
investigator confirms before two records become one. When the system
can't be sure, it asks instead of guessing. In an evidence chain, a
silent merge is worse than an extra click.

### Failure-isolated connectors
Six independent external data source connectors, each testable with
mocked HTTP. A 404 from one source doesn't break the ingestion pipeline
or any of the other connectors.

### Deterministic referral output
The referral package export is template-driven, not AI-generated. Every
sentence in the output traces back to a citation in the case file. AI
features exist for *triage and exploration* — inline summaries,
relationship analysis, free-text Q&A — but the deliverable a
professional investigator reads is deterministic and auditable.

---

## How to run

**Backend**

```bash
docker-compose up -d                          # PostgreSQL
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/manage.py migrate
python backend/manage.py runserver
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Vite serves on `http://127.0.0.1:5173` and proxies `/api/*` to Django on
`http://127.0.0.1:8000`.

---

## Repo map

- [`backend/`](backend) — Django project (models, views, signal rules, connectors)
- [`frontend/`](frontend) — React + Vite SPA
- [`docs/`](docs) — charter, architecture, governance, session history, resume talking points
- [`tests/`](tests) — backend tests + API health check suite
- [`STATUS.md`](STATUS.md) — current build state, in detail
- [`CLAUDE.md`](CLAUDE.md) — full system map (read first if you want the complete picture)

---

## About

Built by **Tyler Collins** — full-stack developer, IBM Full-Stack
Software Development certificate program. Catalyst is both a portfolio
project and a working tool.

- GitHub: [@tjcol](https://github.com/tjcol)
- Email: tjcollinsku@gmail.com
- LinkedIn: [tylerjcollins](https://www.linkedin.com/in/tylerjcollins/)

Catalyst is open-source under the [MIT License](LICENSE).
