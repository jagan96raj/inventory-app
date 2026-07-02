"""Spec v5.2: cross-bill set-off payments

Revision ID: 007_spec_v52_setoff
Revises: 006_spec_v7_operations
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_spec_v52_setoff"
down_revision: Union[str, None] = "006_spec_v7_operations"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE payment_mode_enum ADD VALUE IF NOT EXISTS 'setoff'")
    op.add_column(
        "payments",
        sa.Column("linked_payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "linked_payment_id")
    # PostgreSQL enum values cannot be removed safely; leave 'setoff' in payment_mode_enum.
