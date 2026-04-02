# Frontend Architecture Walkthrough

## Purpose

This frontend is a React and TypeScript dashboard that sits on top of the Django investigation API. The frontend does not contain business truth. Its main job is to request backend data, keep track of UI state, and render an interface for investigators.

## Mental Model

The simplest way to understand the frontend is:

1. `api.ts` talks to backend routes
2. `App.tsx` owns state and orchestration
3. components render parts of the UI
4. utils hold small reusable helpers
5. `styles.css` controls presentation

If you already understand the backend, think of the frontend like this:

- serializers and response shapes map to `types.ts`
- HTTP client behavior maps to `api.ts`
- controller-like orchestration maps to `App.tsx`
- templates split into React components
- CSS is the presentation layer

## File Layout

### [frontend/src/types.ts](../../frontend/src/types.ts)

Defines the data contracts used by the frontend.

Examples:

- `CaseSummary`
- `CaseDetail`
- `DocumentItem`
- `SignalItem`

This file is the closest frontend equivalent to backend serializer output definitions.

### [frontend/src/api.ts](../../frontend/src/api.ts)

Contains the functions that call the backend.

Key functions:

- `fetchCases()`
- `fetchCaseDetail()`
- `fetchCaseSignals()`
- `createCase()`
- `updateSignal()`

This file should stay the single place where frontend code knows the raw API URLs.

### [frontend/src/App.tsx](../../frontend/src/App.tsx)

Owns the main page state and behavior.

Responsibilities:

- stores selected case and filter state
- loads data from the API
- computes filtered and derived values
- handles create/save actions
- passes state and callbacks into child components

This file should remain the orchestration layer, not the place where every piece of markup lives.

### [frontend/src/components](../../frontend/src/components)

Contains page-level and section-level UI components.

Current components:

- `DashboardMetrics.tsx`
- `CasesPanel.tsx`
- `CaseDetailPanel.tsx`

These components receive props and render UI. They should avoid owning backend orchestration logic.

### [frontend/src/components/ui](../../frontend/src/components/ui)

Contains smaller reusable UI primitives.

Current shared primitives:

- `ToastStack.tsx`
- `StateBlock.tsx`
- `EmptyState.tsx`
- `Button.tsx`
- `FormInput.tsx`
- `FormSelect.tsx`
- `FormTextarea.tsx`

These help avoid repeating the same markup and visual patterns across the app.

### [frontend/src/utils](../../frontend/src/utils)

Contains small reusable helpers.

Current utilities:

- `format.ts`
- `queryParams.ts`

These keep formatting and URL synchronization code out of React render files.

## Data Flow Example

When the page loads:

1. `App.tsx` calls `fetchCases()`
2. the returned case list is stored in state
3. the selected case ID is determined
4. `App.tsx` calls `fetchCaseDetail()` and `fetchCaseSignals()` for the active case
5. child components render based on the resulting state

When the user creates a case:

1. the form lives in `CasesPanel.tsx`
2. submit handling is passed back to `App.tsx`
3. `App.tsx` calls `createCase()`
4. the returned case is inserted into the local case list
5. success or error feedback is shown in the UI

When the user updates a signal:

1. the controls render in `CaseDetailPanel.tsx`
2. signal draft edits stay in app state
3. save triggers `updateSignal()`
4. the updated signal replaces the old one in local state

## Current Design Rule

Use this rule when adding frontend code:

- if it talks to HTTP, it belongs in `api.ts`
- if it is a shared formatting or query helper, it belongs in `utils`
- if it is reusable visual markup, it belongs in `components/ui`
- if it is a section of the page, it belongs in `components`
- if it coordinates state across sections, it belongs in `App.tsx`

## Keyboard Workflow

The dashboard supports investigator productivity shortcuts:

- `j` and `k` move selection through the currently visible case list
- `1`, `2`, `3` set draft status on the active signal (`OPEN`, `REVIEWED`, `DISMISSED`)

Keyboard behavior guardrails:

- shortcuts are ignored while typing in input, select, textarea, or contenteditable elements
- signal shortcuts apply to the currently active signal card in the Signals panel

## Next Growth Path

The next clean extensions are:

1. add more reusable UI primitives
2. harden API error handling patterns
3. add basic frontend tests
4. consider React Query only if fetch complexity grows enough to justify it
