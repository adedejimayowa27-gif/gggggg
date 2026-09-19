"""add composite index on transactions(business_id, date)

Revision ID: 0018_transactions_business_date_idx
Revises: 0017_alert_dedupe_unique
Create Date: 2026-09-07

Step 11, Batch 11.7 -- database performance at scale.
app.services.analytics.period_filters (the single shared filter every
analytics endpoint, every alert detector, and the scenario engine
builds its query on top of) always filters by `business_id ==` combined
with a `date` range. transactions already had single-column indexes on
business_id and date separately, which Postgres can combine via a
bitmap index scan, but a single composite index matching the exact
filter shape lets it do one direct range scan instead -- meaningfully
faster once a business's transaction count grows into the hundreds of
thousands, which is exactly the point in a business's growth where
this app most needs to still feel fast.

Purely additive -- doesn't replace or require dropping either existing
single-column index (Postgres may still choose those for a query that
only filters by one of the two columns).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_transactions_business_date_idx"
down_revision: Union[str, None] = "0017_alert_dedupe_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_business_id_date", "transactions", ["business_id", "date"]
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_business_id_date", table_name="transactions")
