"""add transaction_tombstones table

Revision ID: 0023_transaction_tombstones
Revises: 0022_two_factor_auth
Create Date: 2026-09-24

Step 13, Batch 1 -- manual transaction entry, editing and deleting.

New table only; nothing existing is touched and no backfill is needed.
Remembers the fingerprint of an imported transaction that a person later
edited or deleted in the app, so the next file import / Google Sheets /
Excel sync does not bring the original row back (see
app/models/transaction_tombstone.py for the full reasoning).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0023_transaction_tombstones"
down_revision: Union[str, None] = "0022_two_factor_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transaction_tombstones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "business_id", "fingerprint", name="uq_transaction_tombstones_business_fingerprint"
        ),
    )
    op.create_index(
        "ix_transaction_tombstones_business_id", "transaction_tombstones", ["business_id"]
    )
    op.create_index(
        "ix_transaction_tombstones_fingerprint", "transaction_tombstones", ["fingerprint"]
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_tombstones_fingerprint", table_name="transaction_tombstones")
    op.drop_index("ix_transaction_tombstones_business_id", table_name="transaction_tombstones")
    op.drop_table("transaction_tombstones")
