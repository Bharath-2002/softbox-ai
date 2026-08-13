#!/usr/bin/env bash
# Provisions the Postgres cluster: two login roles and two databases.
#
# This is cluster bootstrap, not schema migration, and deliberately sits
# outside Alembic (see CLAUDE.md §8 and migrations/env.py's header comment):
# creating a role needs superuser/CREATEROLE, which the application must never
# hold, and a database must exist before Alembic has anywhere to connect.
# Everything schema-shaped — tables, RLS, grants — is an Alembic migration.
#
# Idempotent: safe to run repeatedly, locally or in CI, against a fresh
# cluster or one this script already provisioned.
#
# Roles created (D3 — three distinct roles, three distinct capabilities):
#   softbox_owner  owns the tables, runs migrations. Bypasses RLS on its own
#                  tables unless FORCE is set — never used by the app.
#   softbox_app    no BYPASSRLS. What the application and the isolation tests
#                  connect as.
#
# Databases created:
#   softbox        local development
#   softbox_test   the isolation and integration test suite (TEST_DATABASE_URL)
#
# Usage:
#   PGHOST=localhost PGUSER=postgres ./scripts/bootstrap_local_db.sh
#
# Connection to the superuser is taken from the standard PG* environment
# variables / libpq defaults, exactly like `psql` itself — nothing here is
# hardcoded to "run on my machine".

set -euo pipefail

SOFTBOX_OWNER_PASSWORD="${SOFTBOX_OWNER_PASSWORD:-softbox_owner_dev_only}"
SOFTBOX_APP_PASSWORD="${SOFTBOX_APP_PASSWORD:-softbox_app_dev_only}"

# The maintenance database, not the app's — psql defaults to a database named
# after the connecting user, which does not exist on a fresh cluster.
export PGDATABASE="${PGDATABASE:-postgres}"

psql -v ON_ERROR_STOP=1 --quiet <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'softbox_owner') THEN
        CREATE ROLE softbox_owner LOGIN PASSWORD '${SOFTBOX_OWNER_PASSWORD}';
    END IF;

    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'softbox_app') THEN
        -- NOBYPASSRLS is the default for a non-superuser role, spelled out
        -- explicitly so the isolation guarantee is not resting on a default.
        CREATE ROLE softbox_app LOGIN PASSWORD '${SOFTBOX_APP_PASSWORD}' NOBYPASSRLS;
    END IF;
END
\$\$;
SQL

for db in softbox softbox_test; do
    exists="$(psql -tAc "SELECT 1 FROM pg_database WHERE datname = '${db}'")"
    if [[ "${exists}" != "1" ]]; then
        # OWNER at creation time, not via a later ALTER: a database created by
        # the superuser and never handed off would let softbox_owner's own
        # FORCE RLS policies be bypassed by the superuser forever, which is a
        # harmless footgun locally but a bad habit to script.
        createdb --owner=softbox_owner "${db}"
    fi
    psql -d "${db}" -v ON_ERROR_STOP=1 --quiet -c \
        "GRANT CONNECT ON DATABASE ${db} TO softbox_app;"
done

echo "softbox and softbox_test are ready (owner: softbox_owner, app: softbox_app)."
