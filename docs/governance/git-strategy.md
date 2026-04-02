# Catalyst — Git Strategy and Repo Presentation

**Last Updated:** 2026-04-01
**Purpose:** Clean up the git workflow and make the repo employer-ready.

---

## Current State

The repository is on GitHub with messy commit history. We are NOT rewriting history — that's risky and dishonest. Instead, we establish clean practices going forward and make the repo presentation professional.

---

## Commit Conventions (Starting Now)

Use conventional commits with these prefixes:

| Prefix | When to Use | Example |
|--------|------------|---------|
| `feat:` | New feature or capability | `feat: add AI memo generation endpoint` |
| `fix:` | Bug fix | `fix: restore truncated CaseDetailView.tsx` |
| `docs:` | Documentation only | `docs: add charter v3` |
| `refactor:` | Code restructuring, no behavior change | `refactor: split views.py into modules` |
| `test:` | Adding or updating tests | `test: add memo generation integration test` |
| `chore:` | Build, config, dependency changes | `chore: add Dockerfile for IBM Cloud deployment` |
| `style:` | CSS, formatting, no logic change | `style: improve loading state animations` |
| `security:` | Security-related changes | `security: add rate limiting middleware` |

**Rules:**
- One logical change per commit. Don't bundle "fix truncated files + add new feature" in one commit.
- Commit message is imperative mood: "add feature" not "added feature" or "adding feature"
- Keep the first line under 72 characters
- Add a blank line + body for complex changes

---

## Branching Strategy

For a single-developer project, keep it simple:

- `main` — the stable branch. Should always compile.
- `dev` — working branch for active development. Merge to main when a milestone gate passes.
- Feature branches (optional) — `feat/memo-generation`, `fix/truncated-files`. Use when a change might take multiple sessions.

**Before starting Milestone 1 work:**
```bash
git checkout -b dev
# Do all work on dev
# When Milestone 1 gate passes (npm run build succeeds):
git checkout main
git merge dev
```

---

## Repo Presentation (Milestone 5)

When an employer clicks your GitHub link, they should see:

### README.md (root level)
- Project name + one-line description
- Screenshot or GIF of the app in action
- "What is this?" section (2-3 sentences about the problem it solves)
- Tech stack badges (Django, React, PostgreSQL, TypeScript, Python)
- "Quick Start" instructions (git clone, docker-compose up, npm install, etc.)
- Architecture diagram (text or image)
- "Features" section with the Golden Path highlighted
- Link to deployed instance
- Link to charter and documentation

### What NOT to include in README
- Session logs or development diary
- Security audit details (keep those in docs/)
- Internal governance docs (keep those in docs/governance/)

### .gitignore verification
Make sure these are excluded:
- `.env` (secrets)
- `__pycache__/`
- `node_modules/`
- `media/` (uploaded files)
- `.DS_Store`
- `*.pyc`

### Files that should exist at root
- `README.md` — professional project overview
- `LICENSE` — choose one (MIT for portfolio, or proprietary notice)
- `docker-compose.yml` — dev environment setup
- `.env.example` — template without secrets
- `CURRENT_STATE.md` — living project state (this shows professionalism)

---

## What We Are NOT Doing

- **No git rebase or history rewriting.** The messy history stays. Clean commits going forward show growth.
- **No squashing old commits.** An employer who digs into history will see real development progression, which is fine.
- **No separate "portfolio" branch.** Main is the presentation branch.
