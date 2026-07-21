"""Scope expense category active-name index by company_id.

Revision ID: 053_spec_v1711_expense_category_company_unique
Revises: 052_spec_v1710_drop_till_balances
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "053_spec_v1711_expense_category_company_unique"
down_revision: Union[str, None] = "052_spec_v1710_drop_till_balances"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_expense_categories_active_name_lower", table_name="expense_categories")
    op.create_index(
        "ix_expense_categories_active_name_lower",
        "expense_categories",
        ["company_id", sa.text("lower(trim(name))")],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
        postgresql_where=sa.text("is_active = TRUE"),
    )


def downgrade() -> None:
    op.drop_index("ix_expense_categories_active_name_lower", table_name="expense_categories")
    op.create_index(
        "ix_expense_categories_active_name_lower",
        "expense_categories",
        [sa.text("lower(trim(name))")],
    )
