"""Spec v15.1 — store owner-visible password for admin user management.

Revision ID: 035_spec_v151_password_plain
Revises: 034_spec_v151_login_otp
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "035_spec_v151_password_plain"
down_revision: Union[str, None] = "034_spec_v151_login_otp"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_plain", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_plain")
