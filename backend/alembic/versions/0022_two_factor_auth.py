"""add two-factor auth columns to users

Revision ID: 0022_two_factor_auth
Revises: 0021_refresh_tokens
Create Date: 2026-09-24

Step 12, Batch 12.6 -- TOTP-based two-factor login. Three new nullable/
defaulted columns on users, nothing existing touched:

- totp_secret_encrypted: Fernet-encrypted (see app/services/totp.py,
  same encrypt-before-storing pattern as the Google/Microsoft OAuth
  tokens in app/services/google_oauth.py) base32 TOTP secret. Set by
  POST /auth/2fa/setup; NOT the same as being enabled -- a user can
  have a pending, unconfirmed secret here without is_2fa_enabled being
  true yet (they haven't proven they can generate a valid code from it).
- is_2fa_enabled: only flips true once POST /auth/2fa/enable verifies a
  real code against the pending secret above.
- totp_recovery_codes_hashed: JSONB array of bcrypt-hashed one-time
  recovery codes (same hashing as passwords -- see
  app/services/totp.py), generated alongside enabling. A used code is
  removed from the array, not just marked used, since "still present"
  IS "still valid" for this list.

Purely additive -- no backfill needed, every existing user simply has
is_2fa_enabled=false and the other two columns NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0022_two_factor_auth"
down_revision: Union[str, None] = "0021_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_encrypted", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_2fa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users", sa.Column("totp_recovery_codes_hashed", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "totp_recovery_codes_hashed")
    op.drop_column("users", "is_2fa_enabled")
    op.drop_column("users", "totp_secret_encrypted")
