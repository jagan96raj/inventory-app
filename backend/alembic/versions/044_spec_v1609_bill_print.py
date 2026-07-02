"""Spec v16.0.9 — bill print company header (go-live drawback #30).

Revision ID: 044_spec_v1609_bill_print
Revises: 043_spec_v1607_user_disable
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "044_spec_v1609_bill_print"
down_revision: Union[str, None] = "043_spec_v1607_user_disable"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("book_settings", sa.Column("company_name", sa.String(length=255), nullable=True))
    op.add_column("book_settings", sa.Column("company_address_line", sa.String(length=500), nullable=True))
    op.add_column("book_settings", sa.Column("company_phone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("book_settings", "company_phone")
    op.drop_column("book_settings", "company_address_line")
    op.drop_column("book_settings", "company_name")
