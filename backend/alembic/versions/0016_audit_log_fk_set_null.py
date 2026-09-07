"""change audit_logs.business_id FK from CASCADE to SET NULL

Revision ID: 0016_audit_log_fk_set_null
Revises: 0015_background_jobs
Create Date: 2026-09-06

Batch 10.10 -- Step 10, requirement #13 (data-retention considerations).
audit_logs.business_id previously cascade-deleted along with its
business, which would silently destroy the compliance/audit trail for
that business at the exact moment it might matter most (investigating
what happened before/around a deletion). Changed to SET NULL, matching
the existing actor_user_id column's behavior. No app-visible behavior
changes for any *existing* action -- there is no business-deletion
endpoint in this app yet, so no row has ever actually been cascade-
deleted this way; this only changes what would happen if/when one is
added.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016_audit_log_fk_set_null"
down_revision: Union[str, None] = "0015_background_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT_NAME = "audit_logs_business_id_fkey"  # Postgres' default name for this FK


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "audit_logs", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT_NAME, "audit_logs", "businesses", ["business_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "audit_logs", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT_NAME, "audit_logs", "businesses", ["business_id"], ["id"], ondelete="CASCADE"
    )
