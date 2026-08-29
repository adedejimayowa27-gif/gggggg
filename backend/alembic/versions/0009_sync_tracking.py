"""add source/skipped_duplicate_count to import_sessions, confirmed_mapping to google_integrations

Revision ID: 0009_sync_tracking
Revises: 0008_transaction_fingerprint
Create Date: 2026-08-29

Batch 9.4 -- reuses ImportSession itself to represent one Google Sheets
sync run (its own docstring already anticipated this: "straightforward
to later add other sources... that produce the same raw_rows shape").
`source` distinguishes a sync-created session from a file upload;
existing rows get 'file' via server_default so nothing about the
existing importer's behavior or history changes. `skipped_duplicate_count`
is nullable/unused by the file path -- only sync populates it.
`confirmed_mapping` on google_integrations is the one-time-saved column
mapping every subsequent "Sync Now" reuses automatically.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_sync_tracking"
down_revision: Union[str, None] = "0008_transaction_fingerprint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "import_sessions",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="file"),
    )
    op.add_column(
        "import_sessions", sa.Column("skipped_duplicate_count", sa.Integer(), nullable=True)
    )
    op.add_column(
        "google_integrations", sa.Column("confirmed_mapping", postgresql.JSONB, nullable=True)
    )


def downgrade() -> None:
    op.drop_column("google_integrations", "confirmed_mapping")
    op.drop_column("import_sessions", "skipped_duplicate_count")
    op.drop_column("import_sessions", "source")
