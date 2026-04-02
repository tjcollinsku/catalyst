# Catalyst — Definition of Done

**Last Updated:** 2026-04-01
**Purpose:** The quality gate every feature must pass before it's marked complete.

---

## Feature-Level Definition of Done

A feature is "done" when ALL of the following are true:

### Code
- [ ] Backend endpoint works (tested manually or with automated tests)
- [ ] Frontend component renders correctly and connects to the backend
- [ ] `npm run build` passes with zero errors
- [ ] No new `console.log` debugging statements (error logging is fine)
- [ ] No hardcoded values that should be in environment variables

### Testing
- [ ] Backend: at minimum, a manual test confirms the endpoint works
- [ ] For connectors: mocked unit tests exist and pass
- [ ] For API endpoints: basic request/response test exists
- [ ] Frontend: component renders without errors (visual check is acceptable for V1)

### Documentation
- [ ] If a new model was added: docs/project/architecture.md is updated
- [ ] If a design decision was made: docs/project/design-decisions.md is updated
- [ ] If tech debt was introduced: docs/governance/tech-debt-register.md is updated
- [ ] CURRENT_STATE.md reflects the change

### Integration
- [ ] The feature works within the Golden Path flow (if applicable)
- [ ] No existing features were broken (check other views still render)

---

## Milestone-Level Definition of Done

A milestone is "done" when ALL of the following are true:

- [ ] All tasks in the milestone are individually "done" per the checklist above
- [ ] The milestone gate condition is met (defined in charter v3 Section 9)
- [ ] CURRENT_STATE.md is updated with new model/endpoint/component counts
- [ ] Tech debt register is reviewed — any new debt is logged
- [ ] A session handoff note is written

---

## Session-Level Definition of Done

Every session ends with:

- [ ] CURRENT_STATE.md updated
- [ ] Session handoff note written (using template in docs/governance/session-handoff-template.md)
- [ ] `npm run build` passes (if frontend was touched)
- [ ] No uncommitted work that would be lost
- [ ] Tech debt register updated if new debt was found

---

## What "Done" Does NOT Mean

- It does NOT mean "perfect." V1 quality is: it works, it doesn't crash, it looks professional enough for a demo.
- It does NOT mean "tested at scale." Single-user, single-case testing is sufficient for V1.
- It does NOT mean "production-hardened." Error recovery, retry logic, and edge case handling are V2 concerns unless they affect the demo.
