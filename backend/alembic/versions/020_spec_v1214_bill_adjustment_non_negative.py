"""Spec v12.14: bills.adjustment non-negative CHECK constraint

Revision ID: 020_spec_v1214_bill_adjustment_non_negative
Revises: 019_spec_v1213_bill_version
"""

from typing import Sequence, Union

from alembic import op

revision: str = "020_spec_v1214_bill_adjustment_non_negative"
down_revision: Union[str, None] = "019_spec_v1213_bill_version"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_bills_adjustment_non_negative",
        "bills",
        "adjustment >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bills_adjustment_non_negative", "bills", type_="check")
