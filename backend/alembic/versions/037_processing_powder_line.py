"""Per-batch powder storage line (location, brand, bag type, qty).

Revision ID: 037_processing_powder_line
Revises: 036_spec_v154_logout_revoke
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "037_processing_powder_line"
down_revision: Union[str, None] = "036_spec_v154_logout_revoke"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

KG = sa.Numeric(14, 3)


def upgrade() -> None:
    op.add_column("processing_batches", sa.Column("powder_brand_id", sa.Integer(), nullable=True))
    op.add_column("processing_batches", sa.Column("powder_location_id", sa.Integer(), nullable=True))
    op.add_column("processing_batches", sa.Column("powder_bag_type_id", sa.Integer(), nullable=True))
    op.add_column("processing_batches", sa.Column("powder_bag_count", sa.Integer(), nullable=True))
    op.add_column("processing_batches", sa.Column("powder_loose_kg", KG, nullable=True))
    op.create_foreign_key(
        "fk_processing_batches_powder_brand_id",
        "processing_batches",
        "brands",
        ["powder_brand_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_processing_batches_powder_location_id",
        "processing_batches",
        "locations",
        ["powder_location_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_processing_batches_powder_bag_type_id",
        "processing_batches",
        "bag_types",
        ["powder_bag_type_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_processing_batches_powder_bag_type_id", "processing_batches", type_="foreignkey")
    op.drop_constraint("fk_processing_batches_powder_location_id", "processing_batches", type_="foreignkey")
    op.drop_constraint("fk_processing_batches_powder_brand_id", "processing_batches", type_="foreignkey")
    op.drop_column("processing_batches", "powder_loose_kg")
    op.drop_column("processing_batches", "powder_bag_count")
    op.drop_column("processing_batches", "powder_bag_type_id")
    op.drop_column("processing_batches", "powder_location_id")
    op.drop_column("processing_batches", "powder_brand_id")
