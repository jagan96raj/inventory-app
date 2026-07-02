"""Spec v12.3: inventory non-negative CHECK constraints

Revision ID: 016_spec_v123_inventory_non_negative
Revises: 015_spec_v54_payment_void
"""

from typing import Sequence, Union

from alembic import op

revision: str = "016_spec_v123_inventory_non_negative"
down_revision: Union[str, None] = "015_spec_v54_payment_void"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_inventory_bag_count_non_negative",
        "inventory",
        "bag_count >= 0",
    )
    op.create_check_constraint(
        "ck_inventory_loose_kg_non_negative",
        "inventory",
        "loose_kg >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_inventory_loose_kg_non_negative", "inventory", type_="check")
    op.drop_constraint("ck_inventory_bag_count_non_negative", "inventory", type_="check")
