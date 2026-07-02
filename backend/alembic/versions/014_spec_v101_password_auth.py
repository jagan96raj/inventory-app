"""Spec v10.1: password auth — password_hash, nullable google_sub

Revision ID: 014_spec_v101_password_auth
Revises: 013_spec_v10_users_auth
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_spec_v101_password_auth"
down_revision: Union[str, None] = "013_spec_v10_users_auth"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.alter_column("users", "google_sub", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "google_sub", existing_type=sa.String(255), nullable=False)
    op.drop_column("users", "password_hash")
