"""Spec v14.8 — processing batch void.

Revision ID: 031_spec_v148_processing_batch_void
Revises: 030_seed_powder_destination
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031_spec_v148_processing_batch_void"
down_revision: Union[str, None] = "030_seed_powder_destination"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processing_batches",
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("processing_batches", "voided_at")
