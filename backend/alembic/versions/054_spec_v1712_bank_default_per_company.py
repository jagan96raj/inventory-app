"""Scope default bank uniqueness by company.

Revision ID: 054_spec_v1712_bank_default_per_company
Revises: 053_spec_v1711_expense_category_company_unique
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "054_spec_v1712_bank_default_per_company"
down_revision: Union[str, None] = "053_spec_v1711_expense_category_company_unique"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    index_names = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if index_name in index_names:
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    _drop_index_if_exists("uq_bank_accounts_one_default", "bank_accounts")
    op.create_index(
        "uq_bank_accounts_one_default",
        "bank_accounts",
        ["company_id"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
        postgresql_where=sa.text("is_default = TRUE"),
    )


def downgrade() -> None:
    _drop_index_if_exists("uq_bank_accounts_one_default", "bank_accounts")
    op.create_index(
        "uq_bank_accounts_one_default",
        "bank_accounts",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default = TRUE"),
    )
