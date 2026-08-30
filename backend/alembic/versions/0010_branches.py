"""create branches table, add branch_id to transactions

Revision ID: 0010_branches
Revises: 0009_sync_tracking
Create Date: 2026-08-31

Batch 10.1 -- Step 10, requirement #3 (multiple branches per business).
Purely additive: a new table, plus one nullable column on transactions.
Every existing transaction gets NULL (meaning "not assigned to any
branch"), and nothing anywhere in the app currently requires branch_id
to be set, so no existing behavior changes for any business that
doesn't opt into using branches.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_branches"
down_revision: Union[str, None] = "0009_sync_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(op.f("ix_branches_business_id"), "branches", ["business_id"], unique=False)

    op.add_column(
        "transactions",
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("branches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_transactions_branch_id"), "transactions", ["branch_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_branch_id"), table_name="transactions")
    op.drop_column("transactions", "branch_id")
    op.drop_index(op.f("ix_branches_business_id"), table_name="branches")
    op.drop_table("branches")
