"""create team_members table, backfill owner rows

Revision ID: 0011_team_members
Revises: 0010_branches
Create Date: 2026-08-31

Batch 10.2 -- Step 10, requirement #4 (team members with role-based
permissions). Creates the table, then backfills one "owner" TeamMember
row per existing business (using that business's current owner_id/the
owner's email) so every business -- old and new -- has a consistent team
list. This is purely additive data: Business.owner_id is untouched, and
app.api.deps.get_owned_business's owner_id check (unchanged) means
nothing about who can already access a business changes as a result of
this backfill -- it only makes the team membership table consistent with
reality that was already true.

UUIDs for the backfilled rows are generated in Python (uuid.uuid4()),
not via Postgres's gen_random_uuid(), since that function's availability
without the pgcrypto extension depends on the exact Postgres version --
generating them here works identically on every version.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_team_members"
down_revision: Union[str, None] = "0010_branches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("invited_email", sa.String(length=255), nullable=False),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(op.f("ix_team_members_business_id"), "team_members", ["business_id"], unique=False)
    op.create_index(op.f("ix_team_members_user_id"), "team_members", ["user_id"], unique=False)
    op.create_index(op.f("ix_team_members_invited_email"), "team_members", ["invited_email"], unique=False)
    op.create_index(op.f("ix_team_members_status"), "team_members", ["status"], unique=False)

    # Backfill: one active "owner" row per existing business. Done via
    # the Python connection (not raw gen_random_uuid() SQL) so it works
    # regardless of Postgres version/extensions.
    connection = op.get_bind()
    team_members_table = sa.table(
        "team_members",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("business_id", postgresql.UUID(as_uuid=True)),
        sa.column("user_id", postgresql.UUID(as_uuid=True)),
        sa.column("invited_email", sa.String),
        sa.column("role", sa.String),
        sa.column("status", sa.String),
    )
    rows = connection.execute(
        sa.text("SELECT b.id AS business_id, b.owner_id AS owner_id, u.email AS email "
                "FROM businesses b JOIN users u ON u.id = b.owner_id")
    ).fetchall()
    if rows:
        connection.execute(
            team_members_table.insert(),
            [
                {
                    "id": uuid.uuid4(),
                    "business_id": row.business_id,
                    "user_id": row.owner_id,
                    "invited_email": row.email,
                    "role": "owner",
                    "status": "active",
                }
                for row in rows
            ],
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_team_members_status"), table_name="team_members")
    op.drop_index(op.f("ix_team_members_invited_email"), table_name="team_members")
    op.drop_index(op.f("ix_team_members_user_id"), table_name="team_members")
    op.drop_index(op.f("ix_team_members_business_id"), table_name="team_members")
    op.drop_table("team_members")
