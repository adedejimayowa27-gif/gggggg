"""add is_sample flag to transactions, expenses, product_stock

Revision ID: 0027_sample_data_flags
Revises: 0026_expense_import_stock_cost
Create Date: 2026-09-28

Step 13, Batch 4 -- onboarding sample data.

One additive boolean per table, defaulting to false, so every existing
row is (correctly) "real data" and nothing needs a backfill. Rows the
"load sample data" action inserts are flagged true so they can be
removed later without touching anything the person entered themselves,
and so they can be excluded from plan-limit counting.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0027_sample_data_flags"
down_revision: Union[str, None] = "0026_expense_import_stock_cost"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("transactions", "expenses", "product_stock")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "is_sample")
