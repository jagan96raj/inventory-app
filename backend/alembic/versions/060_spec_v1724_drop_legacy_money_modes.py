"""Phase 5 — backfill account FKs, drop legacy cash/bank mode columns.

Spec v17.2.4 Phase 5 (Option B):
- Re-backfill any missing payment/cash-book account FKs (same rules as 059).
- Fail if a company that needs Cash lacks a kind=cash row.
- Require source_account_id on cash_book_entries.
- Drop cash_book legacy mode + bank FK columns.
- Drop payments.bank_account_id (keep payment_mode for credit/debit/setoff).

Revision ID: 060_spec_v1724_drop_legacy_money_modes
Revises: 059_spec_v1721_money_account_ids
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "060_spec_v1724_drop_legacy_money_modes"
down_revision: Union[str, None] = "059_spec_v1721_money_account_ids"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _backfill(bind, dialect: str) -> None:
    # cash_book bank mode
    bind.execute(
        sa.text(
            "UPDATE cash_book_entries "
            "SET source_account_id = source_bank_account_id "
            "WHERE source_payment_mode = 'bank' "
            "AND source_bank_account_id IS NOT NULL "
            "AND source_account_id IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE cash_book_entries "
            "SET dest_account_id = dest_bank_account_id "
            "WHERE dest_payment_mode = 'bank' "
            "AND dest_bank_account_id IS NOT NULL "
            "AND dest_account_id IS NULL"
        )
    )
    # cash_book cash mode
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

    # payments bank / cash
    bind.execute(
        sa.text(
            "UPDATE payments "
            "SET account_id = bank_account_id "
            "WHERE payment_mode = 'bank' "
            "AND bank_account_id IS NOT NULL "
            "AND account_id IS NULL"
        )
    )
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


def _assert_ready(bind) -> None:
    missing_cash = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            "  SELECT DISTINCT company_id FROM cash_book_entries "
            "  WHERE source_payment_mode = 'cash' OR dest_payment_mode = 'cash' "
            "  UNION "
            "  SELECT DISTINCT b.company_id FROM payments p "
            "  JOIN bills b ON b.id = p.bill_id "
            "  WHERE p.payment_mode = 'cash'"
            ") AS need "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM bank_accounts ba "
            "  WHERE ba.company_id = need.company_id AND ba.kind = 'cash'"
            ")"
        )
    ).scalar()
    if int(missing_cash or 0) > 0:
        raise RuntimeError(
            "Migration 060 aborted: one or more companies need a Cash account "
            "(kind=cash) before legacy money columns can be dropped."
        )

    orphan_cbe = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM cash_book_entries "
            "WHERE source_account_id IS NULL"
        )
    ).scalar()
    if int(orphan_cbe or 0) > 0:
        raise RuntimeError(
            f"Migration 060 aborted: {orphan_cbe} cash_book_entries still missing source_account_id"
        )

    orphan_pay = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM payments "
            "WHERE payment_mode IN ('cash', 'bank') AND account_id IS NULL"
        )
    ).scalar()
    if int(orphan_pay or 0) > 0:
        raise RuntimeError(
            f"Migration 060 aborted: {orphan_pay} cash/bank payments still missing account_id"
        )

    orphan_xfer = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM cash_book_entries "
            "WHERE entry_type = 'transfer' AND dest_account_id IS NULL"
        )
    ).scalar()
    if int(orphan_xfer or 0) > 0:
        raise RuntimeError(
            f"Migration 060 aborted: {orphan_xfer} transfer entries still missing dest_account_id"
        )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    _backfill(bind, dialect)
    _assert_ready(bind)

    # source_account_id required for every cash-book entry
    if dialect == "postgresql":
        op.alter_column("cash_book_entries", "source_account_id", existing_type=sa.Integer(), nullable=False)
    else:
        with op.batch_alter_table("cash_book_entries") as batch:
            batch.alter_column("source_account_id", existing_type=sa.Integer(), nullable=False)

    # Drop legacy cash_book columns
    op.drop_index("ix_cash_book_source_bank_id", table_name="cash_book_entries")
    op.drop_index("ix_cash_book_dest_bank_id", table_name="cash_book_entries")
    op.drop_constraint(
        "cash_book_entries_source_bank_account_id_fkey",
        "cash_book_entries",
        type_="foreignkey",
    )
    op.drop_constraint(
        "cash_book_entries_dest_bank_account_id_fkey",
        "cash_book_entries",
        type_="foreignkey",
    )

    if dialect == "postgresql":
        op.drop_column("cash_book_entries", "source_payment_mode")
        op.drop_column("cash_book_entries", "dest_payment_mode")
        op.drop_column("cash_book_entries", "source_bank_account_id")
        op.drop_column("cash_book_entries", "dest_bank_account_id")
    else:
        with op.batch_alter_table("cash_book_entries") as batch:
            batch.drop_column("source_payment_mode")
            batch.drop_column("dest_payment_mode")
            batch.drop_column("source_bank_account_id")
            batch.drop_column("dest_bank_account_id")

    # Drop payments.bank_account_id (keep payment_mode)
    op.drop_index("ix_payments_bank_account_id", table_name="payments")
    op.drop_constraint("fk_payments_bank_account_id", "payments", type_="foreignkey")
    if dialect == "postgresql":
        op.drop_column("payments", "bank_account_id")
    else:
        with op.batch_alter_table("payments") as batch:
            batch.drop_column("bank_account_id")


def downgrade() -> None:
    # Recreate nullable legacy columns (data not restored).
    op.add_column("payments", sa.Column("bank_account_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_payments_bank_account_id",
        "payments",
        "bank_accounts",
        ["bank_account_id"],
        ["id"],
    )
    op.create_index("ix_payments_bank_account_id", "payments", ["bank_account_id"])

    op.add_column(
        "cash_book_entries",
        sa.Column("source_payment_mode", sa.String(16), nullable=True),
    )
    op.add_column(
        "cash_book_entries",
        sa.Column("dest_payment_mode", sa.String(16), nullable=True),
    )
    op.add_column(
        "cash_book_entries",
        sa.Column("source_bank_account_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "cash_book_entries",
        sa.Column("dest_bank_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_cash_book_source_bank_account_id",
        "cash_book_entries",
        "bank_accounts",
        ["source_bank_account_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_cash_book_dest_bank_account_id",
        "cash_book_entries",
        "bank_accounts",
        ["dest_bank_account_id"],
        ["id"],
    )
    op.create_index("ix_cash_book_source_bank_id", "cash_book_entries", ["source_bank_account_id"])
    op.create_index("ix_cash_book_dest_bank_id", "cash_book_entries", ["dest_bank_account_id"])

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.alter_column("cash_book_entries", "source_account_id", existing_type=sa.Integer(), nullable=True)
    else:
        with op.batch_alter_table("cash_book_entries") as batch:
            batch.alter_column("source_account_id", existing_type=sa.Integer(), nullable=True)
