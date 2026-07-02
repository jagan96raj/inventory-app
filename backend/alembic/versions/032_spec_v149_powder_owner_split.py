"""Spec v14.9 — owner-aware consolidated powder inventory split.

Revision ID: 032_spec_v149_powder_owner_split
Revises: 031_spec_v148_processing_batch_void
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models.entities import KG

revision: str = "032_spec_v149_powder_owner_split"
down_revision: Union[str, None] = "031_spec_v148_processing_batch_void"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processing_waste_allocations",
        sa.Column("powder_kg", KG, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("processing_waste_allocations", "powder_kg")
