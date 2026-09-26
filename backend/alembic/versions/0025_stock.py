"""add product_stock, stock_adjustments, and Business.auto_deduct_stock_on_sale

Revision ID: 0025_stock
Revises: 0024_expenses
Create Date: 2026-09-24

Step 13, Batch 3 -- inventory and stock.

New tables, plus one new column on an existing table with a server
default, so nothing existing needs a backfill: every current business
gets auto_deduct_stock_on_sale=false, i.e. behaves exactly as before
until an owner opts in.

Uniqueness note: product_stock intentionally has NO unique constraint on
(business_id, branch_id, product). Products here are free text (see
app/models/product_stock.py's docstring), and Postgres unique constraints
treat every NULL branch_id as distinct from every other NULL -- so a
constraint on the raw columns would still let two "no branch" records
for the same product slip in. A constraint on a case-folded, NULL-
coalesced expression would close that gap, but would need an equally
unusual (and separately-tested) matching expression at read time to stay
in sync with it. app.services.stock's case-insensitive lookup, used
before every insert, gives the same guarantee without that duplication.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0025_stock"
down_revision: Union[str, None] = "0024_expenses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("auto_deduct_stock_on_sale", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "product_stock",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "branch_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("product", sa.String(length=255), nullable=False),
        sa.Column("quantity_on_hand", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("reorder_level", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_product_stock_business_id", "product_stock", ["business_id"])
    op.create_index("ix_product_stock_branch_id", "product_stock", ["branch_id"])
    op.create_index("ix_product_stock_business_id_product", "product_stock", ["business_id", "product"])

    op.create_table(
        "stock_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # See app/models/stock_adjustment.py's docstring on `seq`: the
        # reliable ordering column, since created_at can tie within one
        # request/transaction.
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "business_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "product_stock_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_stock.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("delta", sa.Numeric(14, 3), nullable=False),
        sa.Column("resulting_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column(
            "related_transaction_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "created_by_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stock_adjustments_seq", "stock_adjustments", ["seq"])
    op.create_index("ix_stock_adjustments_business_id", "stock_adjustments", ["business_id"])
    op.create_index("ix_stock_adjustments_product_stock_id", "stock_adjustments", ["product_stock_id"])
    op.create_index(
        "ix_stock_adjustments_related_transaction_id", "stock_adjustments", ["related_transaction_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_stock_adjustments_related_transaction_id", table_name="stock_adjustments")
    op.drop_index("ix_stock_adjustments_seq", table_name="stock_adjustments")
    op.drop_index("ix_stock_adjustments_product_stock_id", table_name="stock_adjustments")
    op.drop_index("ix_stock_adjustments_business_id", table_name="stock_adjustments")
    op.drop_table("stock_adjustments")

    op.drop_index("ix_product_stock_business_id_product", table_name="product_stock")
    op.drop_index("ix_product_stock_branch_id", table_name="product_stock")
    op.drop_index("ix_product_stock_business_id", table_name="product_stock")
    op.drop_table("product_stock")

    op.drop_column("businesses", "auto_deduct_stock_on_sale")
