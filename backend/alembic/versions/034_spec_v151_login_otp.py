"""Spec v15.1 — owner-issued login OTP for password recovery.

Revision ID: 034_spec_v151_login_otp
Revises: 033_spec_v150_rbac
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034_spec_v151_login_otp"
down_revision: Union[str, None] = "033_spec_v150_rbac"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("login_otp_hash", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("login_otp_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("login_otp_created_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "login_otp_created_at")
    op.drop_column("users", "login_otp_expires_at")
    op.drop_column("users", "login_otp_hash")
