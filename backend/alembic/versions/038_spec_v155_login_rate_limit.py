"""Spec v15.5 — login rate limit per email (go-live drawback #8).

Revision ID: 038_spec_v155_login_rate_limit
Revises: 037_processing_powder_line
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "038_spec_v155_login_rate_limit"
down_revision: Union[str, None] = "037_processing_powder_line"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_rate_limits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_login_rate_limits_email"),
    )
    op.create_index("ix_login_rate_limits_email", "login_rate_limits", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_login_rate_limits_email", table_name="login_rate_limits")
    op.drop_table("login_rate_limits")
