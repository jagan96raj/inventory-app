"""Add opening/closing till balances on payments and cash book entries.

Superseded by 052_spec_v1710_drop_till_balances (feature removed).
Backfill removed so this revision stays runnable without the deleted service.

Revision ID: 051_spec_v1709_till_balances
Revises: 050_spec_v1708_book_settings_address_len
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "051_spec_v1709_till_balances"
down_revision: Union[str, None] = "050_spec_v1708_book_settings_address_len"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

MONEY = sa.Numeric(18, 2)


def upgrade() -> None:
    op.add_column("payments", sa.Column("opening_balance", MONEY, nullable=True))
    op.add_column("payments", sa.Column("closing_balance", MONEY, nullable=True))
    op.add_column("cash_book_entries", sa.Column("opening_balance", MONEY, nullable=True))
    op.add_column("cash_book_entries", sa.Column("closing_balance", MONEY, nullable=True))
    op.add_column("cash_book_entries", sa.Column("dest_opening_balance", MONEY, nullable=True))
    op.add_column("cash_book_entries", sa.Column("dest_closing_balance", MONEY, nullable=True))


def downgrade() -> None:
    op.drop_column("cash_book_entries", "dest_closing_balance")
    op.drop_column("cash_book_entries", "dest_opening_balance")
    op.drop_column("cash_book_entries", "closing_balance")
    op.drop_column("cash_book_entries", "opening_balance")
    op.drop_column("payments", "closing_balance")
    op.drop_column("payments", "opening_balance")
