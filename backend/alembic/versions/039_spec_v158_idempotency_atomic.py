"""Spec v15.8 — atomic idempotency claim (go-live drawback #14).

Revision ID: 039_spec_v158_idempotency_atomic
Revises: 038_spec_v155_login_rate_limit
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "039_spec_v158_idempotency_atomic"
down_revision: Union[str, None] = "038_spec_v155_login_rate_limit"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_idempotency_status = sa.Enum("in_progress", "completed", name="idempotency_status")


def upgrade() -> None:
    _idempotency_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "idempotency_records",
        sa.Column(
            "status",
            _idempotency_status,
            nullable=False,
            server_default="completed",
        ),
    )
    op.alter_column("idempotency_records", "response_status", existing_type=sa.Integer(), nullable=True)
    op.alter_column("idempotency_records", "response_body", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("idempotency_records", "response_body", existing_type=sa.Text(), nullable=False)
    op.alter_column("idempotency_records", "response_status", existing_type=sa.Integer(), nullable=False)
    op.drop_column("idempotency_records", "status")
    _idempotency_status.drop(op.get_bind(), checkfirst=True)
