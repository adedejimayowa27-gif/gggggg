#!/usr/bin/env bash
#
# Manual on-demand Postgres backup (Step 10, Batch 10.10, requirement #13).
#
# This is a supplement to your hosting provider's automatic backups
# (see docs/BACKUP_RECOVERY.md), not a replacement for them -- useful
# for an ad-hoc pre-migration snapshot, a local/self-hosted deployment
# (this app's docker-compose.yml setup) that has no managed-Postgres
# backups at all, or pulling a copy down for local debugging.
#
# Usage:
#   ./scripts/backup_db.sh [output_dir]
#
# Reads the connection string from $DATABASE_URL (same variable the app
# itself uses -- see app/core/config.py) unless overridden by passing it
# directly as $DATABASE_URL in the environment.
#
# Produces a single custom-format (-Fc) dump file, timestamped, which
# pg_restore (or restore_db.sh) can restore from. Custom format is used
# instead of plain SQL because it's compressed and supports selective/
# parallel restore -- see restore_db.sh.
set -euo pipefail

OUTPUT_DIR="${1:-./backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_FILE="${OUTPUT_DIR}/backup_${TIMESTAMP}.dump"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not set. Export it (same value as your .env) and re-run." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "Backing up database to ${OUTPUT_FILE} ..."
pg_dump --format=custom --file="$OUTPUT_FILE" "$DATABASE_URL"
echo "Done. $(du -h "$OUTPUT_FILE" | cut -f1) written."
echo ""
echo "To restore this backup: ./scripts/restore_db.sh ${OUTPUT_FILE}"
