"""create import_sessions and transactions tables

Revision ID: 0002_transactions
Revises: 0001_initial
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_transactions"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_mapping"),
        sa.Column("detected_columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("suggested_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confirmed_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("total_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_row_count", sa.Integer(), nullable=True),
        sa.Column("failed_row_count", sa.Integer(), nullable=True),
        sa.Column("row_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_import_sessions_business_id"), "import_sessions", ["business_id"], unique=False
    )

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("product", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("selling_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("cost_price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["import_session_id"], ["import_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_transactions_business_id"), "transactions", ["business_id"], unique=False
    )
    op.create_index(
        op.f("ix_transactions_import_session_id"),
        "transactions",
        ["import_session_id"],
        unique=False,
    )
    op.create_index(op.f("ix_transactions_date"), "transactions", ["date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_date"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_import_session_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_business_id"), table_name="transactions")
    op.drop_table("transactions")

    op.drop_index(op.f("ix_import_sessions_business_id"), table_name="import_sessions")
    op.drop_table("import_sessions")
