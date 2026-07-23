"""Add account_id columns to payments and cash_book_entries; backfill history.

Spec v17.2.1 Phase 2 (Option B): dual-write unified money account FKs while keeping
legacy mode + bank_account_id columns for existing UI.

Revision ID: 059_spec_v1721_money_account_ids
Revises: 058_spec_v1720_bank_account_kind_cash
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "059_spec_v1721_money_account_ids"
down_revision: Union[str, None] = "058_spec_v1720_bank_account_kind_cash"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cash_book_entries",
        sa.Column("source_account_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "cash_book_entries",
        sa.Column("dest_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_cash_book_source_account_id",
        "cash_book_entries",
        "bank_accounts",
        ["source_account_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_cash_book_dest_account_id",
        "cash_book_entries",
        "bank_accounts",
        ["dest_account_id"],
        ["id"],
    )
    op.create_index("ix_cash_book_source_account_id", "cash_book_entries", ["source_account_id"])
    op.create_index("ix_cash_book_dest_account_id", "cash_book_entries", ["dest_account_id"])

    op.add_column(
        "payments",
        sa.Column("account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_payments_account_id",
        "payments",
        "bank_accounts",
        ["account_id"],
        ["id"],
    )
    op.create_index("ix_payments_account_id", "payments", ["account_id"])

    bind = op.get_bind()
    dialect = bind.dialect.name

    # cash_book: bank mode → existing bank FK
    bind.execute(
        sa.text(
            "UPDATE cash_book_entries "
            "SET source_account_id = source_bank_account_id "
            "WHERE source_payment_mode = 'bank' AND source_bank_account_id IS NOT NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE cash_book_entries "
            "SET dest_account_id = dest_bank_account_id "
            "WHERE dest_payment_mode = 'bank' AND dest_bank_account_id IS NOT NULL"
        )
    )

    # cash_book: cash mode → company Cash account
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                "UPDATE cash_book_entries AS cbe "
                "SET source_account_id = ba.id "
                "FROM bank_accounts AS ba "
                "WHERE ba.company_id = cbe.company_id "
                "AND ba.kind = 'cash' "
                "AND cbe.source_payment_mode = 'cash' "
                "AND cbe.source_account_id IS NULL"
            )
        )
        bind.execute(
            sa.text(
                "UPDATE cash_book_entries AS cbe "
                "SET dest_account_id = ba.id "
                "FROM bank_accounts AS ba "
                "WHERE ba.company_id = cbe.company_id "
                "AND ba.kind = 'cash' "
                "AND cbe.dest_payment_mode = 'cash' "
                "AND cbe.dest_account_id IS NULL"
            )
        )
    else:
        bind.execute(
            sa.text(
                "UPDATE cash_book_entries "
                "SET source_account_id = ("
                "  SELECT ba.id FROM bank_accounts ba "
                "  WHERE ba.company_id = cash_book_entries.company_id AND ba.kind = 'cash' "
                "  LIMIT 1"
                ") "
                "WHERE source_payment_mode = 'cash' AND source_account_id IS NULL"
            )
        )
        bind.execute(
            sa.text(
                "UPDATE cash_book_entries "
                "SET dest_account_id = ("
                "  SELECT ba.id FROM bank_accounts ba "
                "  WHERE ba.company_id = cash_book_entries.company_id AND ba.kind = 'cash' "
                "  LIMIT 1"
                ") "
                "WHERE dest_payment_mode = 'cash' AND dest_account_id IS NULL"
            )
        )

    # payments: bank mode
    bind.execute(
        sa.text(
            "UPDATE payments "
            "SET account_id = bank_account_id "
            "WHERE payment_mode = 'bank' AND bank_account_id IS NOT NULL"
        )
    )

    # payments: cash mode → bill company Cash account
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                "UPDATE payments AS p "
                "SET account_id = ba.id "
                "FROM bills AS b "
                "JOIN bank_accounts AS ba ON ba.company_id = b.company_id AND ba.kind = 'cash' "
                "WHERE p.bill_id = b.id "
                "AND p.payment_mode = 'cash' "
                "AND p.account_id IS NULL"
            )
        )
    else:
        bind.execute(
            sa.text(
                "UPDATE payments "
                "SET account_id = ("
                "  SELECT ba.id FROM bank_accounts ba "
                "  JOIN bills b ON b.id = payments.bill_id "
                "  WHERE ba.company_id = b.company_id AND ba.kind = 'cash' "
                "  LIMIT 1"
                ") "
                "WHERE payment_mode = 'cash' AND account_id IS NULL"
            )
        )


def downgrade() -> None:
    op.drop_index("ix_payments_account_id", table_name="payments")
    op.drop_constraint("fk_payments_account_id", "payments", type_="foreignkey")
    op.drop_column("payments", "account_id")

    op.drop_index("ix_cash_book_dest_account_id", table_name="cash_book_entries")
    op.drop_index("ix_cash_book_source_account_id", table_name="cash_book_entries")
    op.drop_constraint("fk_cash_book_dest_account_id", "cash_book_entries", type_="foreignkey")
    op.drop_constraint("fk_cash_book_source_account_id", "cash_book_entries", type_="foreignkey")
    op.drop_column("cash_book_entries", "dest_account_id")
    op.drop_column("cash_book_entries", "source_account_id")
