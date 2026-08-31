"""create plans and subscriptions tables, seed free plan, backfill

Revision ID: 0012_billing
Revises: 0011_team_members
Create Date: 2026-08-31

Batch 10.3 -- Step 10, requirement #1 (subscription plans, billing,
usage limits).

The seeded "free" plan is deliberately generous -- max_businesses_per_user
and max_branches_per_business get real (if roomy) caps since those are
new features nobody has bulk-created yet, but max_team_members_per_business
and max_transactions_per_month are left NULL (unlimited). This app had
real businesses and real transaction volume before billing tiers
existed; a newly-introduced "free tier" must never retroactively break
something that was already working. Tightening these into real
commercial limits is a deliberate future data change (update the Plan
row), not something this migration should impose by default.

Every existing business is backfilled onto this free plan with status
"active", exactly mirroring how Batch 10.2 backfilled owner
TeamMember rows -- so "this business has a subscription" is always true
after this migration, never a case calling code has to special-case.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_billing"
down_revision: Union[str, None] = "0011_team_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("price_ngn", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("max_businesses_per_user", sa.Integer(), nullable=True),
        sa.Column("max_branches_per_business", sa.Integer(), nullable=True),
        sa.Column("max_team_members_per_business", sa.Integer(), nullable=True),
        sa.Column("max_transactions_per_month", sa.Integer(), nullable=True),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(op.f("ix_plans_key"), "plans", ["key"], unique=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(
        op.f("ix_subscriptions_business_id"), "subscriptions", ["business_id"], unique=True
    )

    connection = op.get_bind()
    free_plan_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO plans (id, key, name, price_ngn, max_businesses_per_user, "
            "max_branches_per_business, max_team_members_per_business, "
            "max_transactions_per_month, is_active) "
            "VALUES (:id, 'free', 'Free', 0, 10, 10, NULL, NULL, true)"
        ),
        {"id": free_plan_id},
    )

    business_ids = [row.id for row in connection.execute(sa.text("SELECT id FROM businesses")).fetchall()]
    if business_ids:
        subscriptions_table = sa.table(
            "subscriptions",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("business_id", postgresql.UUID(as_uuid=True)),
            sa.column("plan_id", postgresql.UUID(as_uuid=True)),
            sa.column("status", sa.String),
        )
        connection.execute(
            subscriptions_table.insert(),
            [
                {"id": uuid.uuid4(), "business_id": business_id, "plan_id": free_plan_id, "status": "active"}
                for business_id in business_ids
            ],
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_subscriptions_business_id"), table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index(op.f("ix_plans_key"), table_name="plans")
    op.drop_table("plans")
