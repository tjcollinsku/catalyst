# Frontend Plan

## Current State

The frontend already includes:

- Case list and active case selection
- Case detail loading
- Documents and signals views
- Case creation
- Signal triage updates
- URL-persisted filters
- Dark enterprise visual theme
- Toast notifications for success/error events
- Case sorting controls in the queue panel
- Keyboard shortcuts for case navigation and triage draft status

The initial plan phases have now been implemented and validated. The next work can focus on new feature scope rather than frontend stabilization.

## Completion Snapshot (2026-03-29)

Completed:

- Phase 1: Stabilize the prototype
- Phase 2: Refactor app structure
- Phase 3: UX speed and clarity (core subset)
- Phase 4: Shared UI patterns (core subset)
- Phase 5: Basic frontend test suite

Validated:

- Frontend build passes
- Vitest suite passes (API + key component tests)

## Phase 1: Stabilize The Existing Prototype

Goal: improve the current experience without changing the overall app shape.

Tasks:

- Add success feedback for create and save actions
- Improve inline form validation for new case creation
- Tighten loading states for case list and case detail
- Improve empty states for documents and signals
- Clear stale feedback when a newer action succeeds or fails

Why first:

- High user-visible value
- Low implementation risk
- Makes the current dashboard feel more complete

## Phase 2: Refactor The Frontend Structure

Goal: make the code easier to understand and easier to grow.

Tasks:

- Split App.tsx into smaller components
- Move formatting and query helper functions out of App.tsx
- Keep API access centralized in api.ts

Suggested components:

- CasesPanel
- NewCaseForm
- CaseDetailPanel
- DocumentsCard
- SignalsCard

Why second:

- The current App.tsx works, but it is doing too much in one file
- Breaking responsibilities apart will make the frontend easier to teach and maintain

## Phase 3: Improve UX Speed And Clarity

Goal: make common workflows faster and clearer.

Tasks:

- Add toast-style notifications
- Add one-click triage status actions
- Improve selected-state clarity in the case list
- Add better sorting or quick filters where useful

Why third:

- These improvements are valuable, but they are easier to add cleanly after the refactor

## Phase 4: Move Toward Production Shape

Goal: establish consistent frontend patterns.

Tasks:

- Introduce shared UI primitives
- Normalize loading, error, and success handling
- Consider React Query later if the app starts to grow quickly

Why later:

- The current app is still small enough to improve without introducing heavier abstractions yet

## Phase 5: Add Basic Frontend Tests

Goal: protect the important flows from regressions.

Tasks:

- Test case filtering behavior
- Test create-case validation
- Test signal triage save behavior
- Test loading and empty states

## Recommended Execution Order

1. Finish Phase 1
2. Refactor App.tsx in Phase 2
3. Add UX speed improvements in Phase 3
4. Introduce shared patterns in Phase 4
5. Add tests in Phase 5

## Immediate Next Step

Use the stabilized frontend baseline to begin the next product feature scope (for example: referral memo generation UI, government referral lifecycle workflow, or investigator review queue enhancements).
