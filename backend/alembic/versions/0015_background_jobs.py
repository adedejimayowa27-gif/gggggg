"""create background_jobs table

Revision ID: 0015_background_jobs
Revises: 0014_missing_indexes
Create Date: 2026-09-06

Batch 10.9 -- Step 10, requirement #9 (background jobs for expensive
tasks). Purely additive: one new table, nothing existing touched. The
transaction-import confirm flow is the first consumer (see
app/services/jobs.py + app/services/import_pipeline.py) -- it moves from
running inline in the request to being enqueued here and picked up by an
in-process worker thread, so a large file no longer risks a request
timeout.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_background_jobs"
down_revision: Union[str, None] = "0014_missing_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_background_jobs_business_created", "background_jobs", ["business_id", "created_at"]
    )
    op.create_index("ix_background_jobs_status", "background_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_background_jobs_status", table_name="background_jobs")
    op.drop_index("ix_background_jobs_business_created", table_name="background_jobs")
    op.drop_table("background_jobs")
