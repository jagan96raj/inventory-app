"""Seed consolidated powder destination from existing Powder masters.

Revision ID: 030_seed_powder_destination
Revises: 029_spec_v147_consolidated_powder
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030_seed_powder_destination"
down_revision: Union[str, None] = "029_spec_v147_consolidated_powder"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE book_settings bs
            SET
              powder_product_id = (
                SELECT id FROM products WHERE lower(product_name) = 'powder' ORDER BY id LIMIT 1
              ),
              powder_brand_id = (
                SELECT id FROM brands WHERE lower(name) = 'powder' ORDER BY id LIMIT 1
              ),
              powder_location_id = (
                SELECT id FROM locations ORDER BY id LIMIT 1
              ),
              powder_bag_type_id = (
                SELECT id FROM bag_types WHERE lower(name) = 'loose' ORDER BY id LIMIT 1
              )
            WHERE bs.id = 1
              AND bs.powder_product_id IS NULL
              AND bs.powder_brand_id IS NULL
              AND bs.powder_location_id IS NULL
              AND bs.powder_bag_type_id IS NULL
              AND EXISTS (SELECT 1 FROM products WHERE lower(product_name) = 'powder')
              AND EXISTS (SELECT 1 FROM brands WHERE lower(name) = 'powder')
              AND EXISTS (SELECT 1 FROM locations)
              AND EXISTS (SELECT 1 FROM bag_types WHERE lower(name) = 'loose')
            """
        )
    )


def downgrade() -> None:
    pass
