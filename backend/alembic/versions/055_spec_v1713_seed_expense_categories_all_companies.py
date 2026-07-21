"""Seed expense categories for every company and rename transfer label.

Revision ID: 055_spec_v1713_seed_expense_categories_all_companies
Revises: 054_spec_v1712_bank_default_per_company
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "055_spec_v1713_seed_expense_categories_all_companies"
down_revision: Union[str, None] = "054_spec_v1712_bank_default_per_company"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_SEED_ROWS: list[tuple[str, str, bool]] = [
    ("Rent", "expense", False),
    ("Wages", "expense", False),
    ("Salary", "expense", False),
    ("Loan Repayment", "expense", False),
    ("EB Bill", "expense", False),
    ("Freight Charges", "expense", False),
    ("Other Expenses", "expense", False),
    ("Self Withdrawal", "expense", False),
    ("Capital Increase", "income", False),
    ("Transfer", "transfer", True),
]


def _insert_category(company_id: int, name: str, kind: str, is_system: bool) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "INSERT INTO expense_categories (company_id, name, kind, is_system, is_active) "
                "VALUES (:company_id, :name, CAST(:kind AS expense_category_kind_enum), :is_system, TRUE)"
            ).bindparams(company_id=company_id, name=name, kind=kind, is_system=is_system)
        )
    else:
        op.execute(
            sa.text(
                "INSERT INTO expense_categories (company_id, name, kind, is_system, is_active) "
                "VALUES (:company_id, :name, :kind, :is_system, TRUE)"
            ).bindparams(company_id=company_id, name=name, kind=kind, is_system=is_system)
        )


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE expense_categories "
            "SET name = 'Transfer' "
            "WHERE is_system = TRUE AND kind = 'transfer' "
            "AND lower(trim(name)) = 'cash <-> bank transfer'"
        )
    )

    company_ids = [row[0] for row in op.get_bind().execute(sa.text("SELECT id FROM companies")).all()]
    for company_id in company_ids:
        existing_count = op.get_bind().execute(
            sa.text(
                "SELECT COUNT(1) FROM expense_categories WHERE company_id = :company_id"
            ).bindparams(company_id=company_id)
        ).scalar_one()
        if int(existing_count) > 0:
            continue
        existing_names = {
            row[0]
            for row in op.get_bind().execute(
                sa.text(
                    "SELECT lower(trim(name)) FROM expense_categories WHERE company_id = :company_id"
                ).bindparams(company_id=company_id)
            ).all()
            if row[0]
        }
        for name, kind, is_system in _SEED_ROWS:
            normalized = name.lower()
            if normalized in existing_names:
                continue
            _insert_category(company_id, name, kind, is_system)
            existing_names.add(normalized)


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE expense_categories "
            "SET name = 'Cash <-> Bank Transfer' "
            "WHERE is_system = TRUE AND kind = 'transfer' "
            "AND lower(trim(name)) = 'transfer'"
        )
    )
