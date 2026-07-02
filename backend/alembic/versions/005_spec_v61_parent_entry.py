"""Spec v6.1: parent_entry_id links purchase returns to deliver entries

Revision ID: 005_spec_v61_parent_entry
Revises: 004_spec_v6_purchase_location
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_spec_v61_parent_entry"
down_revision: Union[str, None] = "004_spec_v6_purchase_location"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fulfillment_entries",
        sa.Column(
            "parent_entry_id",
            sa.Integer(),
            sa.ForeignKey("fulfillment_entries.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("fulfillment_entries", "parent_entry_id")
