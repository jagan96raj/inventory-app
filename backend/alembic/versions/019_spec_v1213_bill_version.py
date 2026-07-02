"""Spec v12.13: bill version for optimistic concurrency

Revision ID: 019_spec_v1213_bill_version
Revises: 018_spec_v127_bill_number_counters
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_spec_v1213_bill_version"
down_revision: Union[str, None] = "018_spec_v127_bill_number_counters"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bills",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("bills", "version", server_default=None)


def downgrade() -> None:
    op.drop_column("bills", "version")
