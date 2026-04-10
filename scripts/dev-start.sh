#!/usr/bin/env bash
# dev-start.sh — start Catalyst local development server
#
# Usage:  bash scripts/dev-start.sh
#
# What it does:
#   1. Starts a local PostgreSQL container (if not already running)
#   2. Loads environment variables from the root .env file
#   3. Applies any pending Django migrations
#   4. Starts the Django development server on port 8000
#
# Requirements:
#   - Docker running
#   - Python venv at .venv/ (python -m venv .venv && pip install -r backend/requirements.txt)
#   - .env file at repo root (copy from .env.example)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
VENV_PYTHON="$REPO_ROOT/.venv/Scripts/python.exe"

# Fallback for Unix systems
if [[ ! -f "$VENV_PYTHON" ]]; then
    VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
fi

if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "ERROR: Python venv not found at $REPO_ROOT/.venv"
    echo "Run: python -m venv .venv && pip install -r backend/requirements.txt"
    exit 1
fi

if [[ ! -f "$REPO_ROOT/.env" ]]; then
    echo "ERROR: .env file not found. Copy .env.example and fill it in:"
    echo "  cp .env.example .env"
    exit 1
fi

# Load .env
set -a
source "$REPO_ROOT/.env"
set +a

# Start local DB container if not running
DB_CONTAINER="catalyst_db_pg"
if ! docker ps --format "{{.Names}}" | grep -q "^${DB_CONTAINER}$"; then
    echo "Starting local DB container ($DB_CONTAINER)..."
    docker run \
        --name "$DB_CONTAINER" \
        --rm \
        -d \
        -e POSTGRES_PASSWORD="${DB_PASSWORD:-postgres}" \
        -p "${DB_PORT:-5434}:5432" \
        postgres:16-alpine
    echo "Waiting for PostgreSQL to be ready..."
    sleep 3
else
    echo "Local DB container $DB_CONTAINER already running."
fi

# Apply migrations
echo "Applying migrations..."
cd "$BACKEND_DIR"
"$VENV_PYTHON" manage.py migrate --run-syncdb

echo ""
echo "============================================"
echo "  Catalyst API starting at http://127.0.0.1:8000"
echo "============================================"
echo ""

# Start the dev server
exec "$VENV_PYTHON" manage.py runserver
