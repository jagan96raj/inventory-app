"""Null out users.password_plain — stop retaining plaintext passwords.

Spec v17.3.6: password_plain must not be stored or returned. Column kept nullable
for backward compatibility; all values cleared.

Revision ID: 061_spec_v1736_null_password_plain
Revises: 060_spec_v1724_drop_legacy_money_modes
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "061_spec_v1736_null_password_plain"
down_revision: Union[str, None] = "060_spec_v1724_drop_legacy_money_modes"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET password_plain = NULL WHERE password_plain IS NOT NULL"))


def downgrade() -> None:
    # Irreversible: plaintext values intentionally destroyed.
    pass
