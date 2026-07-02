"""Spec v12.15: idempotency_records table for mutation POST replay protection

Revision ID: 021_spec_v1215_idempotency_keys
Revises: 020_spec_v1214_bill_adjustment_non_negative
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_spec_v1215_idempotency_keys"
down_revision: Union[str, None] = "020_spec_v1214_bill_adjustment_non_negative"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("route_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_idempotency_user_key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
