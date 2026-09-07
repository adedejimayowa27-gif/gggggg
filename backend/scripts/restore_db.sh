#!/usr/bin/env bash
#
# Restores a backup produced by backup_db.sh (Step 10, Batch 10.10,
# requirement #13).
#
# Usage:
#   ./scripts/restore_db.sh path/to/backup_TIMESTAMP.dump
#
# DESTRUCTIVE: this drops and recreates every object in the target
# database (via --clean --if-exists) before restoring, so it matches
# the dump's schema and data exactly rather than merging with whatever
# is already there. Requires explicit confirmation before proceeding.
# Reads the target from $DATABASE_URL, same as backup_db.sh.
set -euo pipefail

BACKUP_FILE="${1:-}"

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: $0 path/to/backup_TIMESTAMP.dump" >&2
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "ERROR: File not found: ${BACKUP_FILE}" >&2
  exit 1
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not set. Export it (pointed at the TARGET database) and re-run." >&2
  exit 1
fi

echo "This will DROP and recreate every object in the database at:"
echo "  ${DATABASE_URL}"
echo "restoring from: ${BACKUP_FILE}"
read -r -p "Type 'yes' to continue: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

echo "Restoring ..."
pg_restore --clean --if-exists --no-owner --no-privileges --dbname="$DATABASE_URL" "$BACKUP_FILE"
echo "Restore complete. Run 'alembic upgrade head' next if this backup predates the current migrations."
