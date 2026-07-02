"""Spec v12.17: operations void (voided_at on bag change, transfer, disposal)

Revision ID: 022_spec_v1217_operations_void
Revises: 021_spec_v1215_idempotency_keys
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_spec_v1217_operations_void"
down_revision: Union[str, None] = "021_spec_v1215_idempotency_keys"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    for table in ("bag_changes", "product_transfers", "stock_disposals"):
        op.add_column(
            table,
            sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    for table in ("stock_disposals", "product_transfers", "bag_changes"):
        op.drop_column(table, "voided_at")
