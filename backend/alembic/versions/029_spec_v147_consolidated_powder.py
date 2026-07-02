"""Spec v14.7 — consolidated processing powder (batch powder_kg + book settings destination).

Revision ID: 029_spec_v147_consolidated_powder
Revises: 028_spec_v146_output_allocation
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029_spec_v147_consolidated_powder"
down_revision: Union[str, None] = "028_spec_v146_output_allocation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

KG = sa.Numeric(14, 3)


def upgrade() -> None:
    op.add_column(
        "processing_batches",
        sa.Column("powder_kg", KG, nullable=False, server_default="0"),
    )

    op.add_column(
        "book_settings",
        sa.Column("powder_product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
    )
    op.add_column(
        "book_settings",
        sa.Column("powder_brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=True),
    )
    op.add_column(
        "book_settings",
        sa.Column("powder_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
    )
    op.add_column(
        "book_settings",
        sa.Column("powder_bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("book_settings", "powder_bag_type_id")
    op.drop_column("book_settings", "powder_location_id")
    op.drop_column("book_settings", "powder_brand_id")
    op.drop_column("book_settings", "powder_product_id")
    op.drop_column("processing_batches", "powder_kg")
