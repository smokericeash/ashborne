#!/bin/sh
set -eu

: "${ASHBORNE_DB_USER:?ASHBORNE_DB_USER is required}"
: "${ASHBORNE_DB_PASSWORD:?ASHBORNE_DB_PASSWORD is required}"

if [ "$ASHBORNE_DB_USER" = "$POSTGRES_USER" ] || [ "$ASHBORNE_DB_USER" = "postgres" ]; then
  echo "ASHBORNE_DB_USER must be distinct from the PostgreSQL owner account" >&2
  exit 1
fi

# psql variables plus format(%I/%L) safely quote both identifiers and secrets.
# This script runs only while the official image initializes a fresh data volume.
psql \
  --variable=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=app_user="$ASHBORNE_DB_USER" \
  --set=app_password="$ASHBORNE_DB_PASSWORD" <<-'SQL'
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD %L',
  :'app_user',
  :'app_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'app_user'
) \gexec

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA public TO %I', :'app_user') \gexec
SQL
