"""add import_sessions.target and product_stock.unit_cost

Revision ID: 0026_expense_import_and_stock_value
Revises: 0025_stock
Create Date: 2026-09-26

Step 13, Batch 3.1 -- bulk expense import, and a per-product cost so
stock can be valued in Naira.

Two independent, additive columns:
  - import_sessions.target: which table an import session is destined
    for ("transactions" | "expenses"). Existing rows get "transactions"
    via the server default, matching their actual (and, until now, only
    possible) behaviour exactly.
  - product_stock.unit_cost: optional cost per unit, used only to value
    stock on hand (quantity_on_hand * unit_cost). Left null for an
    existing or newly-tracked product until an owner sets it; nothing
    that depends on it treats null as zero (see
    app/services/stock.py's stock_value_summary).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0026_expense_import_stock_cost"
down_revision: Union[str, None] = "0025_stock"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "import_sessions",
        sa.Column("target", sa.String(length=20), nullable=False, server_default="transactions"),
    )
    op.add_column(
        "product_stock",
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product_stock", "unit_cost")
    op.drop_column("import_sessions", "target")
