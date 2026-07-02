"""Spec v15.0 — role-based access control (users.role).

Revision ID: 033_spec_v150_rbac
Revises: 032_spec_v149_powder_owner_split
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "033_spec_v150_rbac"
down_revision: Union[str, None] = "032_spec_v149_powder_owner_split"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

USER_ROLE_ENUM = sa.Enum(
    "owner",
    "writer",
    "stock_manager",
    "factory_manager",
    name="user_role_enum",
)


def upgrade() -> None:
    USER_ROLE_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("role", USER_ROLE_ENUM, nullable=True))
    op.execute(
        sa.text("UPDATE users SET role = 'owner' WHERE lower(trim(email)) = 'jaganraj@rajagro.com'")
    )


def downgrade() -> None:
    op.drop_column("users", "role")
    USER_ROLE_ENUM.drop(op.get_bind(), checkfirst=True)
