"""Spec v6: nullable bill location for purchase; location on fulfillment entries

Revision ID: 004_spec_v6_purchase_location
Revises: 003_address_details
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_spec_v6_purchase_location"
down_revision: Union[str, None] = "003_address_details"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("bills", "location_id", existing_type=sa.Integer(), nullable=True)

    op.add_column(
        "fulfillment_entries",
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
    )
    op.execute(
        """
        UPDATE fulfillment_entries fe
        SET location_id = b.location_id
        FROM bill_lines bl
        JOIN bills b ON b.id = bl.bill_id
        WHERE fe.bill_line_id = bl.id AND b.location_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE bills b
        SET location_id = (
            SELECT fe.location_id
            FROM bill_lines bl
            JOIN fulfillment_entries fe ON fe.bill_line_id = bl.id
            WHERE bl.bill_id = b.id AND fe.location_id IS NOT NULL
            ORDER BY fe.id DESC
            LIMIT 1
        )
        WHERE b.bill_type = 'purchase' AND b.location_id IS NULL
        """
    )
    op.execute("UPDATE bills SET location_id = 1 WHERE location_id IS NULL")
    op.alter_column("bills", "location_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("fulfillment_entries", "location_id")
