"""Spec v16.0.7 — disable user / soft ban (go-live drawback #29).

Revision ID: 043_spec_v1607_user_disable
Revises: 042_spec_v1606_login_history
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "043_spec_v1607_user_disable"
down_revision: Union[str, None] = "042_spec_v1606_login_history"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.alter_column("users", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_active")
