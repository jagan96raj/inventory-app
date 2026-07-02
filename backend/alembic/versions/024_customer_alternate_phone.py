"""Add alternate_phone to customers.

Revision ID: 024_customer_alternate_phone
Revises: 023_spec_v1221_accounts_cashbook
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024_customer_alternate_phone"
down_revision: Union[str, None] = "023_spec_v1221_accounts_cashbook"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("alternate_phone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "alternate_phone")
