"""create google_integrations table

Revision ID: 0007_google_integrations
Revises: 0006_alerts
Create Date: 2026-08-29

Batch 9.1 -- one Google account connection per business, with encrypted
tokens and sync metadata. Purely additive: one new table, nothing
existing touched. See app/models/google_integration.py for the
encryption/exposure design.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_google_integrations"
down_revision: Union[str, None] = "0006_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "google_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("google_email", sa.String(length=255), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scopes", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="connected"),
        sa.Column("spreadsheet_id", sa.String(length=255), nullable=True),
        sa.Column("spreadsheet_name", sa.String(length=255), nullable=True),
        sa.Column("worksheet_title", sa.String(length=255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_google_integrations_business_id"),
        "google_integrations",
        ["business_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_google_integrations_business_id"), table_name="google_integrations")
    op.drop_table("google_integrations")
