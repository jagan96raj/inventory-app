"""Spec v16.0.6 — login history (go-live drawback #28).

Revision ID: 042_spec_v1606_login_history
Revises: 041_spec_v1605_audit_log
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "042_spec_v1606_login_history"
down_revision: Union[str, None] = "041_spec_v1605_audit_log"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_events_created_at", "login_events", ["created_at"])
    op.create_index("ix_login_events_email", "login_events", ["email"])
    op.create_index("ix_login_events_user_id", "login_events", ["user_id"])
    op.create_index("ix_login_events_success", "login_events", ["success"])


def downgrade() -> None:
    op.drop_index("ix_login_events_success", table_name="login_events")
    op.drop_index("ix_login_events_user_id", table_name="login_events")
    op.drop_index("ix_login_events_email", table_name="login_events")
    op.drop_index("ix_login_events_created_at", table_name="login_events")
    op.drop_table("login_events")
