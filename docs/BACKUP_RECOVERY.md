# Backup, Recovery & Data Retention

Step 10, Batch 10.10, requirement #13. This is the operational reference
for "what happens to this app's data over time, and how to get it back
if something goes wrong."

## What actually needs backing up

Postgres is the **only** stateful store this app has. There is no
separate file/object storage: uploaded import files are parsed in
memory on upload and never written to disk as files (see
`app/services/import_pipeline.py`) -- only the *parsed rows* are
persisted, as JSONB inside `import_sessions.raw_rows` in Postgres
itself (and see "Retention policy" below for what happens to that copy
over time). So: back up the database, and you have backed up everything.

## Production backups

This app expects to run against a managed Postgres instance in
production (e.g. Render's managed Postgres, if deploying the backend to
Render as the rest of this codebase's comments assume). Managed
Postgres providers generally provide:

- Automatic daily (or more frequent) backups
- Point-in-time recovery (PITR) within a retention window
- One-click restore to a new instance

**Action item for whoever operates this in production:** confirm which
tier/plan is in use and what backup frequency + retention window it
actually provides -- these details vary by provider and by pricing
tier, and this document can't promise a guarantee your hosting plan
doesn't itself provide. Whatever that window is, it defines this app's
practical **RPO** (Recovery Point Objective -- how much data you could
lose) and **RTO** (Recovery Time Objective -- how long a restore takes).
A reasonable target for an app at this stage: RPO of 24 hours,
RTO of a few hours. Tighten both by moving to a higher backup-frequency
plan/tier if the business needs stronger guarantees than that.

## Manual / ad-hoc backups

For a pre-migration snapshot, a local/self-hosted deployment (this
repo's `docker-compose.yml` has no automatic backups of its own), or
pulling a copy down for local debugging:

```bash
# Backup (writes to ./backups/backup_<timestamp>.dump by default)
DATABASE_URL=postgresql://user:pass@host:5432/dbname ./scripts/backup_db.sh

# Restore (DESTRUCTIVE -- drops and recreates everything in the target DB)
DATABASE_URL=postgresql://user:pass@host:5432/dbname ./scripts/restore_db.sh ./backups/backup_20260906T120000Z.dump
```

Both scripts are thin wrappers around `pg_dump`/`pg_restore` (custom
format, `-Fc` -- compressed, supports selective restore). Requires the
Postgres client tools (`pg_dump`, `pg_restore`) installed wherever
you run them; they don't need to be installed on the app server itself.

## Recovery runbook (restoring after data loss)

1. Identify the most recent good backup (provider's automatic backup,
   or the most recent `./scripts/backup_db.sh` snapshot).
2. Provision (or reuse) a Postgres instance to restore into. **Never
   restore directly over a database that's still serving traffic** --
   restore into a fresh instance, verify it, then cut over.
3. Restore: use the provider's restore tool for an automatic backup, or
   `./scripts/restore_db.sh <file>` for a manual one.
4. Run `alembic upgrade head` against the restored database -- a backup
   taken before the most recent migration(s) needs to be brought
   forward to the current schema.
5. Point `DATABASE_URL` at the restored instance and redeploy the
   backend.
6. Spot-check: log in as a test account, confirm a business's
   transactions/analytics look right, confirm `GET /health` (see
   `app/api/routes/health.py`) returns healthy.

## Retention policy

Three categories, each treated differently, implemented in
`app/services/retention.py` (scheduled daily by default -- see
`DATA_RETENTION_INTERVAL_HOURS` in `.env.example`):

| Data | Policy | Why |
|---|---|---|
| **Transactions, businesses, branches, team members, subscriptions** | Kept indefinitely; only removed if a user explicitly deletes the specific record (e.g. a single transaction) | This is the actual product data -- there's no "expiry" for a business's own sales history. |
| **AuditLog** | Kept indefinitely. No automatic pruning exists or is planned. | This is the compliance/audit trail -- "what happened and who did it." Auto-pruning it would defeat its purpose. Batch 10.10 also changed `audit_logs.business_id`'s foreign key from `CASCADE` to `SET NULL` (migration `0016_audit_log_fk_set_null`) so that if a business is ever deleted, its audit history survives (with `business_id` left null) instead of vanishing along with it. |
| **ImportSession.raw_rows** | Cleared (not deleted -- the session row and its `row_errors`/counts remain) `IMPORT_RAW_ROWS_RETENTION_DAYS` (default 30) after the import finishes | This is a duplicate copy of data that already exists as `Transaction` rows once an import completes; keeping it forever is unbounded storage growth for no benefit beyond a short post-import support-debugging window. |
| **BackgroundJob** | Deleted outright `BACKGROUND_JOB_RETENTION_DAYS` (default 90) after completion/failure | Operational/debugging records, not compliance records -- see `AuditLog` above for the record of the *outcome* (e.g. `import.completed`) that's kept separately and indefinitely. |

Nothing here is a GDPR/CCPA-style "right to be forgotten" implementation
-- there is currently no user-facing account- or business-deletion
endpoint in this app at all. If one is added later, revisit this table:
in particular, decide then whether a deleted user's/business's
`AuditLog` entries should be anonymized (e.g. `details` scrubbed) rather
than merely detached (`business_id`/`actor_user_id` set null, which is
all today's schema does).
