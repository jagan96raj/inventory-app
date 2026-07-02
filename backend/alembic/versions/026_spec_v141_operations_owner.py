"""Spec v14.1 — owner-tagged bag change, transfer, disposal.

Revision ID: 026_spec_v141_operations_owner
Revises: 025_spec_v14_job_work
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "026_spec_v141_operations_owner"
down_revision: Union[str, None] = "025_spec_v14_job_work"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_OWNER_CHECK = (
    "(owner_type = 'owned' AND customer_id IS NULL) OR "
    "(owner_type = 'job_work' AND customer_id IS NOT NULL)"
)


def _add_owner_columns(table: str) -> None:
    owner_enum = ENUM("owned", "job_work", name="inventory_owner_type_enum", create_type=False)
    op.add_column(
        table,
        sa.Column("owner_type", owner_enum, nullable=False, server_default="owned"),
    )
    op.add_column(table, sa.Column("customer_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        f"fk_{table}_customer_id",
        table,
        "customers",
        ["customer_id"],
        ["id"],
    )
    op.create_check_constraint(f"ck_{table}_owner_customer", table, _OWNER_CHECK)


def upgrade() -> None:
    for table in ("bag_changes", "product_transfers", "stock_disposals"):
        _add_owner_columns(table)


def downgrade() -> None:
    for table in ("stock_disposals", "product_transfers", "bag_changes"):
        op.drop_constraint(f"ck_{table}_owner_customer", table, type_="check")
        op.drop_constraint(f"fk_{table}_customer_id", table, type_="foreignkey")
        op.drop_column(table, "customer_id")
        op.drop_column(table, "owner_type")
