"""add category, customer, payment_method to transactions

Revision ID: 0004_transaction_extra_fields
Revises: 0003_chat
Create Date: 2026-08-27

Batch 6.1 -- these three fields complete the 8-field standard transaction
schema (date, product, quantity, selling_price, cost_price already existed;
this adds category, customer, payment_method). All three are nullable with
no server_default, so every existing row simply gets NULL for them and no
backfill is required -- existing imports, analytics, and AI assistant
behavior are unaffected until later batches start reading these columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_transaction_extra_fields"
down_revision: Union[str, None] = "0003_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions", sa.Column("category", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("customer", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("payment_method", sa.String(length=100), nullable=True)
    )
    # Category and payment method are natural group-by/filter targets for
    # the analytics work coming in Batch 6.5, so index them now while the
    # table is still small rather than as a separate later migration.
    op.create_index(
        op.f("ix_transactions_category"), "transactions", ["category"], unique=False
    )
    op.create_index(
        op.f("ix_transactions_payment_method"),
        "transactions",
        ["payment_method"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_payment_method"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_category"), table_name="transactions")
    op.drop_column("transactions", "payment_method")
    op.drop_column("transactions", "customer")
    op.drop_column("transactions", "category")
