"""add unique constraint on alerts(business_id, dedupe_key)

Revision ID: 0017_alert_dedupe_unique
Revises: 0016_audit_log_fk_set_null
Create Date: 2026-09-07

Step 11, Batch 11.2 -- found during the financial-calculation/duplicate-
prevention re-audit: app.services.alert_engine.run_all_detectors already
de-duplicates in Python (skips any candidate whose dedupe_key already
exists for the business before inserting), but that check-then-insert
was never backed by a database-level constraint. Two runs for the same
business overlapping (the scheduled job and a manual "Run now" firing
close together, for example) could both pass the in-Python check before
either commits, producing two Alert rows with the same dedupe_key --
exactly the duplicate the existing logic was trying to prevent.

This is purely additive and safe to run on existing data: if any
business somehow already has duplicate (business_id, dedupe_key) pairs,
the migration keeps only the earliest one (by created_at) per pair
before adding the constraint, rather than failing outright.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017_alert_dedupe_unique"
down_revision: Union[str, None] = "0016_audit_log_fk_set_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Defensive cleanup before adding the constraint -- see module
    # docstring. A no-op on any database where the Python-level dedupe
    # has in fact always held (the expected, common case). Keeps the
    # earliest row per (business_id, dedupe_key) pair -- the one a user
    # is more likely to have already read/dismissed/resolved -- and
    # drops any later duplicate. `(created_at, id)` (not created_at
    # alone) breaks ties so exactly one row survives per pair even if
    # two duplicates share an identical timestamp.
    op.execute(
        """
        DELETE FROM alerts a
        USING alerts b
        WHERE a.business_id = b.business_id
          AND a.dedupe_key = b.dedupe_key
          AND (a.created_at, a.id) > (b.created_at, b.id)
        """
    )
    op.create_unique_constraint(
        "uq_alerts_business_dedupe_key", "alerts", ["business_id", "dedupe_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_alerts_business_dedupe_key", "alerts", type_="unique")
