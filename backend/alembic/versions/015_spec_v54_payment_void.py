"""Spec v5.4: payment void (voided_at)

Revision ID: 015_spec_v54_payment_void
Revises: 014_spec_v101_password_auth
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_spec_v54_payment_void"
down_revision: Union[str, None] = "014_spec_v101_password_auth"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_payments_bill_id_voided_at", "payments", ["bill_id", "voided_at"])


def downgrade() -> None:
    op.drop_index("ix_payments_bill_id_voided_at", table_name="payments")
    op.drop_column("payments", "voided_at")
