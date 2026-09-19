"""create microsoft_integrations table

Revision ID: 0019_microsoft_integrations
Revises: 0018_transactions_business_date_idx
Create Date: 2026-09-07

Step 11, Batch 11.9 -- Excel/OneDrive integration, mirroring
0007_google_integrations's shape (one connection per business,
encrypted tokens, sync metadata). Unlike google_integrations (built up
across several migrations as that feature grew), this table is created
complete in one migration -- confirmed_mapping included from the start
rather than added later -- since there's no existing production data to
stay compatible with. Purely additive: one new table, nothing existing
touched. See app/models/microsoft_integration.py for the encryption/
exposure design.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0019_microsoft_integrations"
down_revision: Union[str, None] = "0018_transactions_business_date_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "microsoft_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("microsoft_email", sa.String(length=255), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scopes", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="connected"),
        sa.Column("workbook_item_id", sa.String(length=500), nullable=True),
        sa.Column("workbook_name", sa.String(length=255), nullable=True),
        sa.Column("worksheet_id", sa.String(length=255), nullable=True),
        sa.Column("worksheet_name", sa.String(length=255), nullable=True),
        sa.Column("confirmed_mapping", postgresql.JSONB, nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(
        "ix_microsoft_integrations_business_id", "microsoft_integrations", ["business_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_microsoft_integrations_business_id", table_name="microsoft_integrations")
    op.drop_table("microsoft_integrations")
