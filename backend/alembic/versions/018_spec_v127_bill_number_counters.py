"""Spec v12.7: bill number counters (concurrent-safe)

Revision ID: 018_spec_v127_bill_number_counters
Revises: 017_spec_v125_fulfillment_void
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "018_spec_v127_bill_number_counters"
down_revision: Union[str, None] = "017_spec_v125_fulfillment_void"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _max_bill_seq(connection, bill_type: str) -> int:
    rows = connection.execute(
        sa.text("SELECT bill_number FROM bills WHERE bill_type = :bt"),
        {"bt": bill_type},
    ).fetchall()
    max_n = 0
    for (bill_number,) in rows:
        try:
            max_n = max(max_n, int(str(bill_number).rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return max_n


def upgrade() -> None:
    bill_type_enum = ENUM("sales", "purchase", name="bill_type_enum", create_type=False)
    op.create_table(
        "bill_number_counters",
        sa.Column("bill_type", bill_type_enum, primary_key=True),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
    )
    connection = op.get_bind()
    for bill_type in ("sales", "purchase"):
        last_number = _max_bill_seq(connection, bill_type)
        connection.execute(
            sa.text(
                "INSERT INTO bill_number_counters (bill_type, last_number) VALUES (:bt, :ln)"
            ),
            {"bt": bill_type, "ln": last_number},
        )


def downgrade() -> None:
    op.drop_table("bill_number_counters")
