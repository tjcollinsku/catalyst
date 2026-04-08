# Catalyst — Resume & Interview Talking Points

**Last updated:** 2026-04-07 (Session 32)
**Purpose:** A standalone file for iterating on resume bullets, cover-letter
language, LinkedIn headlines, and interview answers without polluting
CLAUDE.md. Tailor per application. Keep claims accurate — if you change
the system, update this file.

---

## One-line elevator pitches

### Universal (general software recruiters)

> I built a full-stack public-records investigation platform for citizen
> investigators — Django + PostgreSQL backend, React + TypeScript frontend,
> six external data source connectors, 47 API endpoints, deployed on
> Railway — and used it to support a real fraud investigation that produced
> formal referrals to four federal and state agencies.

### Niche (fraud / forensic / compliance / legal-tech firms)

> I conducted a public-records investigation into an Ohio nonprofit that
> resulted in formal referrals to the Ohio AG, IRS, FBI, and a federal
> agency OIG, then rebuilt the manual investigation process as a full-stack
> platform with evidence-grade chain of custody, automated entity
> extraction, and a deterministic referral package exporter.

---

## LinkedIn headline options

Pick whichever frame suits the audience of the week.

- **Builder-first:** "Full-stack developer (Django / React / PostgreSQL) — building Catalyst, an evidence-grade investigation platform for citizen public-records work."
- **Story-first:** "Full-stack developer turning a real nonprofit fraud investigation into a working referral-packaging platform."
- **Plain + searchable:** "Full-stack Software Developer | Python / Django / React / TypeScript / PostgreSQL / Docker"

---

## Resume bullets (rank-ordered — strongest first)

Lift verbatim or trim to fit. The top three are the "if you only have
room for three" set.

1. **Designed and shipped a full-stack investigation platform** (Django 4.2 / PostgreSQL 16 / React 18 / TypeScript / D3.js / Docker / Railway) that ingests documents, extracts entities, and exports referral packages — built from a real fraud investigation I ran by hand.

2. **Architected an audit-first data model** with SHA-256 chain of custody on every document, append-only audit logging on every mutation, and immutable timestamp guards on government referral filing dates — treating legal defensibility as a primary requirement, not an afterthought.

3. **Built six independent, failure-isolated external data connectors** for public records (IRS Form 990 XML via TEOS range requests, Ohio Secretary of State, Ohio Auditor of State, all 88 Ohio county recorder portals, ProPublica Nonprofit Explorer, ODNR statewide parcel layer) with full mock-HTTP offline test coverage.

4. **Implemented a human-in-the-loop entity resolution pipeline** (rule-based extraction → normalization → fuzzy matching → investigator confirmation) that surfaces match candidates rather than silent-merging, as a deliberate legal defensibility decision.

5. **Integrated the Anthropic Claude API** as a fallback for messy document extraction and as a triage/exploration aid — while keeping the deliverable (referral package export) deterministic and citation-bearing rather than AI-generated.

6. **Designed a fraud signal detection engine** with pattern rules (shell entities, timeline compression, excessive officer compensation, address nexus) derived directly from anomalies I encountered in the founding investigation — not speculative.

7. **Shipped a React + TypeScript + D3 frontend** with a force-directed entity-relationship graph synchronized to a brushable timeline, dark/light/auto theming, skeleton loading states, and WCAG-aware accessibility (skip-to-content, ARIA live regions, reduced-motion support).

8. **Wrote 555+ backend tests** covering connectors, API endpoints, and signal rules, with CI running ruff, TypeScript type-check, and Vite build on every push.

9. **Reframed the product mid-build** after recognizing the right customer of the output is the professional investigator, not the citizen user — then consolidated an over-engineered three-table workflow (Signal / Detection / Finding) into a single two-dimensional model, cut speculative features, and refocused on a defensible referral package as the core deliverable.

---

## Skills / keywords (ATS keyword scanning)

Drop this as a "Skills" section and recruiters' bots will eat it up.

**Languages & Frameworks:** Python, Django, Django REST Framework, JavaScript, TypeScript, React, React Router, Node.js, SQL, HTML5, CSS3

**Data & Storage:** PostgreSQL, database design, migrations, ORMs, ETL, data pipelines

**Frontend:** React 18, TypeScript, Vite, D3.js, CSS Modules, responsive design, accessibility (WCAG 2.1), dark mode

**Infrastructure & DevOps:** Docker, Docker Compose, Railway, GitHub Actions, CI/CD, ruff, pytest

**API & Architecture:** REST API design, authentication, CSRF protection, rate limiting, pagination, failure isolation

**Document / Data Processing:** PDF text extraction, OCR (Tesseract), web scraping (requests, BeautifulSoup, ASP.NET ViewState postback), fuzzy matching, entity resolution

**AI / LLM:** Anthropic Claude API, LLM integration, prompt design, AI-assisted development

**Practices:** Chain-of-custody logging, audit logging, legal defensibility, human-in-the-loop design, agile / session-based development, technical writing, documentation

---

## Interview story beats

Answers to the five questions you'll get asked most.

### 1. "Tell me about a project you're proud of." — The origin story

"I started with a real investigation, not a product idea. In 2025 I was
looking at a nonprofit I had reason to believe was being used to move
money in ways that didn't match its charitable purpose. I spent months
cross-referencing 990s, property records, state filings, and officer
histories — all by hand, out of spreadsheets. That investigation
eventually produced formal referrals to four federal and state agencies.
Catalyst is what I wish I'd had on day one. I built it backwards from
the pain of doing the work manually."

### 2. "How do you think about quality / reliability?" — The audit-first decision

"Chain of custody isn't a nice-to-have when the output of your system
will be read by an AG investigator. I put SHA-256 hashing on every
uploaded document from day one, an append-only audit log on every
mutation, and immutable timestamp guards on anything that gets filed
with an agency. A referral package that can't show clean provenance
isn't worth submitting, so I treated that as a primary requirement."

### 3. "Tell me about a tradeoff you made." — The human-in-the-loop decision

"I could have silently auto-merged fuzzy entity matches — the rule is
'if the similarity is above 0.9, treat them as the same person.' I
chose to surface match candidates to the investigator instead. It's
slower. It's more clicks. But in an evidence chain, a silent merge is
worse than an extra click — if it's wrong, you've quietly corrupted
the case. I wanted the system to ask when it wasn't sure, not guess."

### 4. "Tell me about a time you changed your mind about something." — The reframe

"I was four months into building this thinking of it as 'investigation
software.' Then I realized the customer of the output isn't the
citizen using the tool — it's the professional investigator with the
badge, the one who can actually issue subpoenas. That reframe changed
everything. I consolidated a three-table Signal/Detection/Finding
workflow into one Finding model with a status and an evidence-weight
dimension, cut a third of the speculative signal rules, killed an
AI-generated narrative memo feature, and refocused the whole output on
a deterministic, citation-bearing referral package. Recognizing the
real customer saved me from shipping an over-engineered system that
nobody needed."

### 5. "How do you work with AI coding tools?" — The working-with-AI story

"Honestly, a lot of the early scaffmain on this project was written
by an AI coding assistant. I learned the hard way that I had to be
able to explain every file in the codebase before I built another
one — otherwise I was going to get asked about something in an
interview and not know my own code. So I paused feature work and did a
guided walk-through of models.py and views.py end to end. I can now
explain the data model, the ORM patterns, the upload pipeline, the
audit logging, and the signal engine line by line. The lesson I take
out of that: AI is great at scaffmain, but if you don't own the
code after, you're just a user of a tool, not a developer. The
discipline is making sure the human stays in the loop on the code,
not just the output."

---

## What to leave out (until you decide)

- **The specific Ohio nonprofit name** — stays out while matters are active.
- **The referral case numbers** ( and ) — currently pulled from public materials. Putting them in makes the case identifiable to anyone willing to look them up. Acceptable on a resume sent privately to a fraud/forensic firm; not recommended on LinkedIn or a public README.
- **"Vibe-coded by AI" framing** — never use this. Use "AI-assisted development with deliberate ownership of the codebase" or the interview answer above. There is a huge difference in how those two phrases land with a hiring manager.
- **Exact dollar amounts from the investigation** ($XK → $X.XM) — powerful in a cover letter to a niche firm, dangerous on a public resume because it narrows the identifiable universe of cases.

---

## Tailoring guide

### For a general full-stack role
- Lead with bullets 1, 3, 7 (platform, connectors, frontend)
- Use universal elevator pitch
- Emphasize React, TypeScript, D3, testing, CI/CD
- Use interview beat 1 (origin story) and 5 (working-with-AI)

### For a fraud / forensic / compliance / legal-tech role
- Lead with bullets 2, 4, 9 (audit-first, human-in-the-loop, the reframe)
- Use niche elevator pitch
- Emphasize chain of custody, legal defensibility, deterministic output
- Use interview beats 2 (audit-first) and 4 (the reframe)
- It is safe to name the four referral agencies without naming the nonprofit

### For a data / pipeline / ETL role
- Lead with bullets 3, 4, 6 (connectors, entity resolution, signal detection)
- Emphasize six connectors, fuzzy matching, failure isolation, 555+ tests
- Use interview beat 3 (tradeoffs / human-in-the-loop)

### For an AI / ML / LLM-adjacent role
- Lead with bullets 1, 5, 9 (platform, Claude integration, the reframe)
- Emphasize the *boundary* you drew between AI (triage, exploration)
  and deterministic output (the referral package). That's the story: you
  used AI where it was useful and refused to use it where it wasn't.
- Use interview beat 5 (working-with-AI) as the centerpiece

---

## Accuracy checklist

Before sending a resume that references this file, verify these claims
are still true. Update this file the same day you change any of them.

- [ ] 6 connectors exist (IRS TEOS XML, Ohio SOS, Ohio AOS, County Recorder, County Auditor, ProPublica)
- [ ] 47 API endpoints
- [ ] 555+ backend tests
- [ ] SHA-256 chain of custody on Document model
- [ ] Append-only AuditLog model
- [ ] Immutable timestamp guard on GovernmentReferral filing date (note: GovernmentReferral being CUT in rebuild — update this bullet when that lands)
- [ ] D3 force-directed graph + synchronized timeline on Overview tab
- [ ] React + TypeScript + Vite + dark/light/auto theming
- [ ] CI pipeline runs ruff + tsc + vite build
- [ ] Deployed on Railway

If a rebuild drops any of these (e.g. cutting a connector, removing the
GovernmentReferral model, trimming signal rules from 29 to ~5-7), come
back here and update the relevant bullets *before* the next application
goes out.
