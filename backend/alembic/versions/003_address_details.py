"""Structured address on customers and locations

Revision ID: 003_address_details
Revises: 002_spec_v3
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_address_details"
down_revision: Union[str, None] = "002_spec_v3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _add_address_columns(table: str) -> None:
    op.add_column(table, sa.Column("address_line", sa.String(500), nullable=True))
    op.add_column(table, sa.Column("district", sa.String(120), nullable=True))
    op.add_column(table, sa.Column("state", sa.String(120), nullable=True))
    op.add_column(table, sa.Column("pin_code", sa.String(12), nullable=True))
    op.execute(
        f"UPDATE {table} SET address_line = address WHERE address IS NOT NULL AND TRIM(address) <> ''"
    )
    op.drop_column(table, "address")


def upgrade() -> None:
    _add_address_columns("customers")
    _add_address_columns("locations")


def downgrade() -> None:
    for table in ("customers", "locations"):
        op.add_column(table, sa.Column("address", sa.Text(), nullable=True))
        op.execute(
            f"""
            UPDATE {table} SET address = TRIM(CONCAT_WS(', ',
                NULLIF(TRIM(address_line), ''),
                NULLIF(TRIM(district), ''),
                NULLIF(TRIM(state), ''),
                NULLIF(TRIM(pin_code), '')
            ))
            """
        )
        op.drop_column(table, "pin_code")
        op.drop_column(table, "state")
        op.drop_column(table, "district")
        op.drop_column(table, "address_line")
