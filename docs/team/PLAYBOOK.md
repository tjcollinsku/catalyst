# Catalyst Project Playbook

## What Is Catalyst
Catalyst is a pre-investigative intelligence triage platform built for nonprofit fraud investigation. It ingests public records (IRS 990 forms, Ohio Secretary of State filings, county auditor/recorder data), extracts entities, detects anomalous patterns via 29 automated signal rules, and generates professional referral memos for submission to the Ohio AG, IRS, or FBI. Built by Tyler Collins as part of the IBM Full-Stack Software Development certificate program. Currently deployed on Railway at catalyst-production-9566.up.railway.app.

## Architecture (30-Second Version)
- **Backend:** Django 5.x monolith, PostgreSQL, 21 models, 45 API endpoints, 29 signal rules, 6 external connectors (ProPublica, IRS, Ohio SOS, County Auditor, County Recorder, Ohio AOS), AI via Claude API (ai_proxy.py)
- **Frontend:** React 18 + TypeScript + Vite, CSS Modules with design tokens (dark/light/auto), D3.js force-directed entity graph + timeline, 11 views, 42 components
- **Deployment:** Railway (Dockerfile multi-stage build: node:20-alpine for frontend, python:3.11-slim for backend), Gunicorn with 2 workers, WhiteNoise for static files
- **No authentication in V1.** Single-user. Auth is a V2 concern.

## How Sessions Work

### At Session Start
1. Read CURRENT_STATE.md to understand where we are
2. Read this Playbook to understand how we operate
3. Identify today's goals with the product owner (Tyler)

### During a Session
- Break work into specialist tasks (see docs/team/ for specialist briefing books)
- Run specialist agents in parallel where tasks are independent
- Use the Decision Model (below) to know when to ask Tyler vs. proceed autonomously
- Run the API health check (tests/api_health_check.py) after any backend change
- Run TypeScript compilation (npx tsc --noEmit) after any frontend change

### At Session End
1. Update CURRENT_STATE.md with new counts, file changes, status
2. Write session handoff note
3. Verify build passes (npm run build for frontend)
4. Commit all work with conventional commit messages
5. Update tech debt register if new debt was found
6. Run API health check and include results in handoff

## Decision Model
Every action falls into one of three levels:

**GREEN — Just do it.** Bug fixes with obvious causes. Writing tests. Running health checks. Updating documentation. CSS/styling fixes. Adding missing decorators (like @csrf_exempt). No interruption to Tyler needed.

**YELLOW — Recommend, then confirm.** Adding new signal rules. Changing API response formats. Modifying database models (new migrations). Changing the extraction pipeline behavior. Architecture decisions. Format: "I recommend X because Y — sound good?"

**RED — Present options, Tyler decides.** Changing project priorities. Adding new external dependencies or services. Modifying the charter or scope. Anything that affects the product direction or user-facing workflow. Format: "Here are 2-3 options with trade-offs. Which direction?"

## Definition of Done

### For a Feature
- Backend endpoint works (tested with health check or manual curl)
- Frontend component renders and connects to backend
- `npx tsc --noEmit` passes with zero errors
- No hardcoded secrets or debugging console.logs
- CURRENT_STATE.md updated

### For a Bug Fix
- Root cause identified and documented
- Fix applied
- Regression test added (or health check test added) that would catch recurrence
- BUGFIX_LOG.md updated

### For a Session
- CURRENT_STATE.md updated
- Build passes
- API health check runs clean (or failures are documented with tickets)
- All changes committed with conventional commit messages

## Quality Gates
- **Build gate:** `npx tsc --noEmit` must pass. Non-negotiable.
- **API gate:** `python3 tests/api_health_check.py` must have zero unexpected failures.
- **No silent failures:** If an endpoint returns 500, it gets fixed or documented before session end.

## Conventional Commits
All commits use this format:
- feat: — new feature
- fix: — bug fix
- docs: — documentation
- test: — adding/updating tests
- refactor: — restructuring without behavior change
- chore: — build/config changes
- security: — security fixes

Keep first line under 72 characters. Imperative mood ("add" not "added").

## Specialist Team
Briefing books for specialist agents live in docs/team/. Current specialists:
- **QA Engineer** (qa-engineer.md) — testing methodology, edge cases, regression testing
- **Backend Engineer** (backend-engineer.md) — Django, API, signal rules, data model
- **IRS Domain Expert** (irs-domain-expert.md) — Form 990 structure, nonprofit law, IRS rules
- **Data Engineer** (data-engineer.md) — extraction pipelines, parsers, OCR, data quality

When launching a specialist agent, always include: (1) this Playbook summary, (2) their briefing book, (3) relevant sections of CURRENT_STATE.md, (4) the specific task with clear deliverables.

## Key File Locations
| Purpose | Path |
|---------|------|
| This playbook | docs/team/PLAYBOOK.md |
| Current state | CURRENT_STATE.md |
| Charter | docs/charter/catalyst-charter-v3.md |
| Architecture | docs/project/architecture.md |
| Design decisions | docs/project/design-decisions.md |
| Tech debt | docs/governance/tech-debt-register.md |
| Risk register | docs/governance/risk-register.md |
| Bug fix log | BUGFIX_LOG.md |
| Test report | TEST_REPORT.md |
| API health check | tests/api_health_check.py |
| Signal rules | backend/investigations/signal_rules.py |
| AI proxy | backend/investigations/ai_proxy.py |
| Entity extraction | backend/investigations/entity_extraction.py |
| Main views | backend/investigations/views.py |
| Frontend API client | frontend/src/api.ts |
| Frontend types | frontend/src/types.ts |

## What NOT To Do
- Do NOT create new files without checking if functionality already exists
- Do NOT add dependencies without a YELLOW decision check
- Do NOT skip the build gate
- Do NOT merge to main with failing tests
- Do NOT hardcode API keys, database URLs, or secrets
- Do NOT modify the charter without a RED decision
- Do NOT write new governance docs — update existing ones or add to this playbook
