"""Spec v15.9 — conditional bill void (go-live drawback #19).

Revision ID: 040_spec_v159_bill_void
Revises: 039_spec_v158_idempotency_atomic
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "040_spec_v159_bill_void"
down_revision: Union[str, None] = "039_spec_v158_idempotency_atomic"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE bill_status_enum ADD VALUE IF NOT EXISTS 'voided'")
    op.add_column("bills", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "voided_at")
