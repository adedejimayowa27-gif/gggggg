"""add missing indexes on alerts.related_transaction_id and subscriptions.plan_id

Revision ID: 0014_missing_indexes
Revises: 0013_audit_logs
Create Date: 2026-09-01

Batch 10.6 -- found during the tenant-isolation/performance audit: two
foreign key columns had no index, meaning a query filtering or joining
on them would force a full table scan as those tables grow. Purely
additive (an index doesn't change any query's results, only its speed),
so this carries zero behavior-change risk.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_missing_indexes"
down_revision: Union[str, None] = "0013_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_alerts_related_transaction_id"), "alerts", ["related_transaction_id"], unique=False
    )
    op.create_index(op.f("ix_subscriptions_plan_id"), "subscriptions", ["plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_subscriptions_plan_id"), table_name="subscriptions")
    op.drop_index(op.f("ix_alerts_related_transaction_id"), table_name="alerts")
