# Catalyst — Session Handoff Template

**Purpose:** Copy this template at the end of every session. Fill it in. Paste it into the session tracker or a new handoff file.

---

## Template

```markdown
# Session [NUMBER] — [DATE]

## What Was Done
- [List every task completed this session]
- [Be specific: "Fixed DocumentsTab.tsx truncation" not "worked on frontend"]

## Files Changed
- [List every file that was created, modified, or deleted]
- [Include the type of change: CREATED, MODIFIED, DELETED, MOVED]

## Current Milestone
- Milestone: [1/2/3/4/5]
- Status: [In Progress / Complete]
- Next task in milestone: [What's the next concrete thing to do?]

## Blockers
- [Anything preventing progress on the current milestone]
- [If none, write "None"]

## Tech Debt Added
- [Any new tech debt introduced this session]
- [If none, write "None"]

## Build Status
- Backend: [PASS / FAIL / NOT CHECKED]
- Frontend: [PASS / FAIL / NOT CHECKED]

## CURRENT_STATE.md Updated?
- [ ] Yes — updated model counts, endpoint counts, frontend status, etc.

## Notes for Next Session
- [Anything the next session needs to know that isn't captured elsewhere]
- [Context that would be lost if the AI assistant starts fresh]
```

---

## Rules

1. **Fill this out BEFORE ending the session.** Not after. Not "I'll do it next time."
2. **Be specific about files changed.** The next session may start with a different AI context. File paths are the fastest way to re-orient.
3. **Always update CURRENT_STATE.md.** If you didn't, the handoff is incomplete.
4. **Build status is mandatory.** If you touched frontend code and didn't run `npm run build`, run it now.
