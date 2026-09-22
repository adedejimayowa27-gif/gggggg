"""add is_email_verified to users

Revision ID: 0020_email_verification
Revises: 0019_microsoft_integrations
Create Date: 2026-09-22

Step 12, Batch 12.2 -- email verification.

Adds one nullable-never boolean, defaulted to false so every existing
account starts unverified (they'll see the "verify your email" banner
once, and can dismiss it by resending/clicking the link -- nobody is
locked out of anything, since this flag isn't enforced anywhere; see
app/api/routes/auth.py's docstring). Purely additive -- no other column
touched, no data migrated.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0020_email_verification"
down_revision: Union[str, None] = "0019_microsoft_integrations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Drop the server_default once existing rows are backfilled -- new
    # inserts always set this explicitly (see app/models/user.py's Python
    # default), so the column shouldn't silently default to false at the
    # database level for anything written outside the ORM.
    op.alter_column("users", "is_email_verified", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_email_verified")
