"""Spec v17.0.7 — optional notes/description on bills.

Revision ID: 049_spec_v1707_bill_notes
Revises: 048_spec_v1706_company_address_details
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "049_spec_v1707_bill_notes"
down_revision: Union[str, None] = "048_spec_v1706_company_address_details"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "notes")
