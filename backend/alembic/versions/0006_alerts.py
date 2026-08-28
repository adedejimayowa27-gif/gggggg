"""create alerts table

Revision ID: 0006_alerts
Revises: 0005_simulations
Create Date: 2026-08-28

Batch 8.1 -- persistence layer for the Business Intelligence Alert
Engine (Step 8). Purely additive: one new table, nothing existing
touched. See app/models/alert.py for why alert_type/supporting_values
are loose (string / JSONB) rather than fixed columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_alerts"
down_revision: Union[str, None] = "0005_simulations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alert_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("affected_product", sa.String(length=255), nullable=True),
        sa.Column("affected_category", sa.String(length=255), nullable=True),
        sa.Column("affected_metric", sa.String(length=50), nullable=True),
        sa.Column(
            "related_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("supporting_values", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="unread"),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_alerts_business_id"), "alerts", ["business_id"], unique=False)
    op.create_index(op.f("ix_alerts_alert_type"), "alerts", ["alert_type"], unique=False)
    op.create_index(op.f("ix_alerts_severity"), "alerts", ["severity"], unique=False)
    op.create_index(op.f("ix_alerts_status"), "alerts", ["status"], unique=False)
    op.create_index(op.f("ix_alerts_dedupe_key"), "alerts", ["dedupe_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alerts_dedupe_key"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_status"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_severity"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_alert_type"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_business_id"), table_name="alerts")
    op.drop_table("alerts")
