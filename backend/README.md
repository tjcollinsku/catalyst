# Catalyst Backend

## Phase 1 Scaffold

This folder contains the Django project skeleton that will own model-first schema management.

## Structure

- `manage.py`
- `catalyst/` (project settings)
- `investigations/` (app for case, document, entity, findings, audit models)
- `investigations/migrations/` (Django-generated migration files)

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and update secrets.
4. Ensure PostgreSQL is running via Docker Compose from the workspace root.
5. Run migrations:

   ```bash
   python manage.py migrate
   ```

6. After models are defined, generate migration files:

   ```bash
   python manage.py makemigrations investigations
   ```

## Developer Guardrails

Use these commands to keep the codebase clean and avoid cleanup debt.

1. Install dev tooling:

   ```bash
   pip install -r requirements-dev.txt
   ```

2. Enable pre-commit hooks:

   ```bash
   pre-commit install
   ```

3. Run checks before commit:

   ```bash
   pre-commit run --all-files
   ```

4. Manual lint/format (optional):

   ```bash
   ruff check . --fix
   ruff format .
   ```

Guardrails configured in repo root:
- `.pre-commit-config.yaml`
- `pyproject.toml`
