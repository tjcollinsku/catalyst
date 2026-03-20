# Database Migrations

This folder contains SQL migration files mounted by Docker at startup.

- `001_initial_schema.sql`: Phase 1 baseline schema.

Note: PostgreSQL only auto-runs files in `/docker-entrypoint-initdb.d` on the first container startup for a fresh data volume.
