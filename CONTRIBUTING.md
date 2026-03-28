# Contributing

This project uses lightweight workflow guardrails to keep the repository clean while features are moving quickly.

## Branching

- Keep `main` stable and releasable.
- Create focused branches per concern (example: `api/case-filters`, `schema/add-signal-index`).
- Avoid mixing schema, API, tests, and docs in one branch unless they are directly tied.

## Commit Convention

Use this format for commit subjects:

`type(scope): short summary`

Allowed `type` values:
- `feat`: new behavior
- `fix`: bug fix
- `refactor`: internal change without behavior change
- `test`: test-only changes
- `docs`: documentation-only changes
- `chore`: tooling or maintenance

Examples:
- `feat(api): add case list status filters`
- `fix(signals): prevent duplicate SR-004 persistence`
- `docs(migrations): explain SQL bootstrap vs Django path`

## Commit Quality Checklist

Before commit:

1. Run checks:
   - `pre-commit run --all-files`
2. Confirm migration/doc sync when schema changed:
   - Update `database/migrations/README.md` if SQL bootstrap path changed.
   - Ensure Django migrations represent application truth.
3. Keep commit scope small and reversible.
4. Confirm no stray files:
   - notes dumps
   - temporary scripts
   - generated artifacts

## Pull Request Standards

Each PR should:

1. Explain why the change is needed.
2. Describe what changed and where.
3. Include verification steps (commands run, endpoints checked, tests run).
4. Call out risks and rollback path.
5. Include docs updates when behavior or workflow changes.

## Migrations Policy

- Django migrations are canonical for application evolution.
- SQL bootstrap migrations support fresh environment initialization.
- If both are touched, keep them in sync in the same PR.

## Testing Policy

- Connector tests should run offline with mocked network.
- API changes must include or update tests.
- Prefer deterministic tests over broad integration coupling.

## Definition of Done

A change is done when:

1. Code is linted/formatted.
2. Tests for changed behavior pass.
3. Docs are updated.
4. PR template is fully completed.
