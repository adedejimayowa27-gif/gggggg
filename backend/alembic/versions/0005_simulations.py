"""create simulations table

Revision ID: 0005_simulations
Revises: 0004_transaction_extra_fields
Create Date: 2026-08-27

Batch 7.1 -- persistence layer for the Business Decision Simulator (Step
7). Purely additive: one new table, nothing existing touched. See
app/models/simulation.py for why parameters/assumptions/results are
JSONB rather than fixed columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_simulations"
down_revision: Union[str, None] = "0004_transaction_extra_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "simulations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scenario_type", sa.String(length=50), nullable=False),
        sa.Column("parameters", postgresql.JSONB, nullable=False),
        sa.Column("baseline_start_date", sa.Date(), nullable=False),
        sa.Column("baseline_end_date", sa.Date(), nullable=False),
        sa.Column("assumptions", postgresql.JSONB, nullable=False),
        sa.Column("results", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_simulations_business_id"), "simulations", ["business_id"], unique=False
    )
    op.create_index(
        op.f("ix_simulations_scenario_type"), "simulations", ["scenario_type"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_simulations_scenario_type"), table_name="simulations")
    op.drop_index(op.f("ix_simulations_business_id"), table_name="simulations")
    op.drop_table("simulations")
