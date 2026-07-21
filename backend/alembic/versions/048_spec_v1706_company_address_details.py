"""Spec v17.0.6 — detailed company address + GSTIN on companies.

Revision ID: 048_spec_v1706_company_address_details
Revises: 047_spec_v1703_per_company_settings_counters
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "048_spec_v1706_company_address_details"
down_revision: Union[str, None] = "047_spec_v1703_per_company_settings_counters"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("address_line_2", sa.String(length=500), nullable=True))
    op.add_column("companies", sa.Column("district", sa.String(length=120), nullable=True))
    op.add_column("companies", sa.Column("state", sa.String(length=120), nullable=True))
    op.add_column("companies", sa.Column("pin_code", sa.String(length=12), nullable=True))
    op.add_column("companies", sa.Column("gstin", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "gstin")
    op.drop_column("companies", "pin_code")
    op.drop_column("companies", "state")
    op.drop_column("companies", "district")
    op.drop_column("companies", "address_line_2")
