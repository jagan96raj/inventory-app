"""Spec v12.5: fulfillment void (voided_at)

Revision ID: 017_spec_v125_fulfillment_void
Revises: 016_spec_v123_inventory_non_negative
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_spec_v125_fulfillment_void"
down_revision: Union[str, None] = "016_spec_v123_inventory_non_negative"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fulfillment_entries",
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_fulfillment_entries_bill_line_id_voided_at",
        "fulfillment_entries",
        ["bill_line_id", "voided_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fulfillment_entries_bill_line_id_voided_at",
        table_name="fulfillment_entries",
    )
    op.drop_column("fulfillment_entries", "voided_at")
