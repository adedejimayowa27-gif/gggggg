"""add expenses table

Revision ID: 0024_expenses
Revises: 0023_transaction_tombstones
Create Date: 2026-09-24

Step 13, Batch 2 -- operating expenses (rent, salaries, transport, ...).

New table only; nothing existing is touched and no backfill is needed. A
business with no expenses behaves exactly as before, except that net
profit then equals gross profit.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0024_expenses"
down_revision: Union[str, None] = "0023_transaction_tombstones"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("branches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_expenses_business_id", "expenses", ["business_id"])
    op.create_index("ix_expenses_branch_id", "expenses", ["branch_id"])
    op.create_index("ix_expenses_business_id_date", "expenses", ["business_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_expenses_business_id_date", table_name="expenses")
    op.drop_index("ix_expenses_branch_id", table_name="expenses")
    op.drop_index("ix_expenses_business_id", table_name="expenses")
    op.drop_table("expenses")
