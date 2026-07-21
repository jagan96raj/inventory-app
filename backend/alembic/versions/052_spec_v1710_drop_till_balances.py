"""Drop payment/cash-book till opening/closing snapshot columns.

Revision ID: 052_spec_v1710_drop_till_balances
Revises: 051_spec_v1709_till_balances
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "052_spec_v1710_drop_till_balances"
down_revision: Union[str, None] = "051_spec_v1709_till_balances"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

MONEY = sa.Numeric(14, 2)


def upgrade() -> None:
    op.drop_column("cash_book_entries", "dest_closing_balance")
    op.drop_column("cash_book_entries", "dest_opening_balance")
    op.drop_column("cash_book_entries", "closing_balance")
    op.drop_column("cash_book_entries", "opening_balance")
    op.drop_column("payments", "closing_balance")
    op.drop_column("payments", "opening_balance")


def downgrade() -> None:
    op.add_column("payments", sa.Column("opening_balance", MONEY, nullable=True))
    op.add_column("payments", sa.Column("closing_balance", MONEY, nullable=True))
    op.add_column("cash_book_entries", sa.Column("opening_balance", MONEY, nullable=True))
    op.add_column("cash_book_entries", sa.Column("closing_balance", MONEY, nullable=True))
    op.add_column("cash_book_entries", sa.Column("dest_opening_balance", MONEY, nullable=True))
    op.add_column("cash_book_entries", sa.Column("dest_closing_balance", MONEY, nullable=True))
