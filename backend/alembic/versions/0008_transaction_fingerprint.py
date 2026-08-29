"""add fingerprint to transactions

Revision ID: 0008_transaction_fingerprint
Revises: 0007_google_integrations
Create Date: 2026-08-29

Batch 9.3 -- a stable hash of each transaction's identifying fields,
used by the Google Sheets sync (Batch 9.4) to skip rows it has already
imported on a repeat sync. Nullable, no server_default, so every
existing row simply gets NULL and no backfill is required -- both
existing behavior and the file importer's behavior are unaffected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008_transaction_fingerprint"
down_revision: Union[str, None] = "0007_google_integrations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions", sa.Column("fingerprint", sa.String(length=64), nullable=True)
    )
    op.create_index(
        op.f("ix_transactions_fingerprint"), "transactions", ["fingerprint"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_fingerprint"), table_name="transactions")
    op.drop_column("transactions", "fingerprint")
