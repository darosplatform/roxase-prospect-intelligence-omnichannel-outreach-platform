#!/usr/bin/env bash
# ROXASE PostgreSQL backup.
#
# Usage:
#   ./scripts/backup.sh                       # backups/roxase-YYYYmmdd-HHMMSS.sql
#   ./scripts/backup.sh /custom/backup/dir
#
# Produces a plain SQL dump against the local docker Postgres (host port 5433).
# For production, point DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME at the live
# instance and secure the destination (object storage / encrypted volume).

set -euo pipefail

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5433}"
DB_USER="${DB_USER:-roxase}"
DB_PASSWORD="${DB_PASSWORD:-roxase}"
DB_NAME="${DB_NAME:-roxase}"

OUT_DIR="${1:-./backups}"
mkdir -p "${OUT_DIR}"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="${OUT_DIR}/roxase-${STAMP}.sql"

if command -v pg_dump >/dev/null 2>&1; then
  PGPASSWORD="${DB_PASSWORD}" pg_dump \
    -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
    -d "${DB_NAME}" -Fc -f "${OUT_FILE}"
else
  # Fall back to a dockerized pg_dump from the compose cluster.
  docker compose exec -T postgres \
    sh -c "pg_dump -U ${DB_USER} -d ${DB_NAME}" > "${OUT_FILE}"
fi

echo "Backup written: ${OUT_FILE}"
echo "Keep this file encrypted and off the host (object storage / volume)."