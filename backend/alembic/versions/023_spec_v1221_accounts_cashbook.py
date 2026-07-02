"""Spec v12.21: accounts, cash book, multi-bank

Revision ID: 023_spec_v1221_accounts_cashbook
Revises: 022_spec_v1217_operations_void
"""

from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023_spec_v1221_accounts_cashbook"
down_revision: Union[str, None] = "022_spec_v1217_operations_void"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1. bank_accounts
    op.create_table(
        "bank_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("account_number_last4", sa.String(length=4), nullable=True),
        sa.Column("ifsc", sa.String(length=32), nullable=True),
        sa.Column("opening_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("opening_balance_at", sa.Date(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("opening_balance >= 0", name="ck_bank_accounts_opening_non_negative"),
    )
    op.create_index(
        "ix_bank_accounts_name_lower",
        "bank_accounts",
        [sa.text("lower(trim(name))")],
        unique=True,
    )
    if dialect == "postgresql":
        op.create_index(
            "uq_bank_accounts_one_default",
            "bank_accounts",
            ["is_default"],
            unique=True,
            postgresql_where=sa.text("is_default = TRUE"),
        )

    # 2. seed one default bank
    op.execute(
        sa.text(
            "INSERT INTO bank_accounts (name, account_number_last4, ifsc, opening_balance, "
            "opening_balance_at, is_default, is_active) "
            "VALUES ('Bank', NULL, NULL, 0, :today, TRUE, TRUE)"
        ).bindparams(today=date.today())
    )

    # 3. payments.bank_account_id
    op.add_column(
        "payments",
        sa.Column("bank_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_payments_bank_account_id",
        "payments",
        "bank_accounts",
        ["bank_account_id"],
        ["id"],
    )
    # 4. backfill existing bank-mode payments
    default_bank_id = bind.execute(
        sa.text("SELECT id FROM bank_accounts WHERE is_default = TRUE LIMIT 1")
    ).scalar()
    if default_bank_id is not None:
        op.execute(
            sa.text(
                "UPDATE payments SET bank_account_id = :bid "
                "WHERE payment_mode = 'bank' AND bank_account_id IS NULL"
            ).bindparams(bid=default_bank_id)
        )
    # 5. index on payments.bank_account_id
    op.create_index("ix_payments_bank_account_id", "payments", ["bank_account_id"])

    # 6. expense_categories + seed
    op.create_table(
        "expense_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "expense",
                "income",
                "transfer",
                name="expense_category_kind_enum",
            ),
            nullable=False,
        ),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_expense_categories_kind", "expense_categories", ["kind"])
    op.create_index(
        "ix_expense_categories_active_name_lower",
        "expense_categories",
        [sa.text("lower(trim(name))")],
    )

    seed_categories: list[tuple[str, str, bool]] = [
        ("Rent", "expense", False),
        ("Wages", "expense", False),
        ("Salary", "expense", False),
        ("Loan Repayment", "expense", False),
        ("EB Bill", "expense", False),
        ("Freight Charges", "expense", False),
        ("Other Expenses", "expense", False),
        ("Self Withdrawal", "expense", False),
        ("Capital Increase", "income", False),
        ("Cash <-> Bank Transfer", "transfer", True),
    ]
    for name, kind, is_system in seed_categories:
        if dialect == "postgresql":
            op.execute(
                sa.text(
                    "INSERT INTO expense_categories (name, kind, is_system, is_active) "
                    "VALUES (:name, CAST(:kind AS expense_category_kind_enum), :is_system, TRUE)"
                ).bindparams(name=name, kind=kind, is_system=is_system)
            )
        else:
            op.execute(
                sa.text(
                    "INSERT INTO expense_categories (name, kind, is_system, is_active) "
                    "VALUES (:name, :kind, :is_system, TRUE)"
                ).bindparams(name=name, kind=kind, is_system=is_system)
            )

    # 7. cash_book_entries
    op.create_table(
        "cash_book_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entry_type",
            sa.Enum(
                "expense",
                "income",
                "transfer",
                name="cash_book_entry_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("reference_no", sa.String(length=100), nullable=True),
        sa.Column("bill_id", sa.Integer(), nullable=True),
        sa.Column(
            "source_payment_mode",
            sa.Enum(
                "cash",
                "bank",
                name="cash_book_source_mode_enum",
            ),
            nullable=True,
        ),
        sa.Column("source_bank_account_id", sa.Integer(), nullable=True),
        sa.Column(
            "dest_payment_mode",
            sa.Enum(
                "cash",
                "bank",
                name="cash_book_dest_mode_enum",
            ),
            nullable=True,
        ),
        sa.Column("dest_bank_account_id", sa.Integer(), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["category_id"], ["expense_categories.id"]),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"]),
        sa.ForeignKeyConstraint(["source_bank_account_id"], ["bank_accounts.id"]),
        sa.ForeignKeyConstraint(["dest_bank_account_id"], ["bank_accounts.id"]),
        sa.CheckConstraint("amount > 0", name="ck_cash_book_amount_positive"),
    )
    op.create_index(
        "ix_cash_book_entry_date",
        "cash_book_entries",
        [sa.text("entry_date DESC")],
    )
    op.create_index("ix_cash_book_entry_type", "cash_book_entries", ["entry_type"])
    op.create_index("ix_cash_book_category_id", "cash_book_entries", ["category_id"])
    op.create_index(
        "ix_cash_book_source_bank_id",
        "cash_book_entries",
        ["source_bank_account_id"],
    )
    op.create_index(
        "ix_cash_book_dest_bank_id",
        "cash_book_entries",
        ["dest_bank_account_id"],
    )
    if dialect == "postgresql":
        op.create_index(
            "ix_cash_book_bill_id",
            "cash_book_entries",
            ["bill_id"],
            postgresql_where=sa.text("bill_id IS NOT NULL"),
        )
    else:
        op.create_index("ix_cash_book_bill_id", "cash_book_entries", ["bill_id"])
    op.create_index("ix_cash_book_voided_at", "cash_book_entries", ["voided_at"])

    # 8. book_settings singleton
    op.create_table(
        "book_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cash_opening_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("cash_opening_balance_at", sa.Date(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cash_opening_balance >= 0",
            name="ck_book_settings_cash_opening_non_negative",
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO book_settings (id, cash_opening_balance, cash_opening_balance_at) "
            "VALUES (1, 0, :today)"
        ).bindparams(today=date.today())
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_table("book_settings")

    op.drop_index("ix_cash_book_voided_at", table_name="cash_book_entries")
    op.drop_index("ix_cash_book_bill_id", table_name="cash_book_entries")
    op.drop_index("ix_cash_book_dest_bank_id", table_name="cash_book_entries")
    op.drop_index("ix_cash_book_source_bank_id", table_name="cash_book_entries")
    op.drop_index("ix_cash_book_category_id", table_name="cash_book_entries")
    op.drop_index("ix_cash_book_entry_type", table_name="cash_book_entries")
    op.drop_index("ix_cash_book_entry_date", table_name="cash_book_entries")
    op.drop_table("cash_book_entries")

    if dialect == "postgresql":
        op.execute("DROP TYPE IF EXISTS cash_book_dest_mode_enum")
        op.execute("DROP TYPE IF EXISTS cash_book_source_mode_enum")
        op.execute("DROP TYPE IF EXISTS cash_book_entry_type_enum")

    op.drop_index("ix_expense_categories_active_name_lower", table_name="expense_categories")
    op.drop_index("ix_expense_categories_kind", table_name="expense_categories")
    op.drop_table("expense_categories")
    if dialect == "postgresql":
        op.execute("DROP TYPE IF EXISTS expense_category_kind_enum")

    # null out the FK before dropping
    op.execute(sa.text("UPDATE payments SET bank_account_id = NULL"))
    op.drop_index("ix_payments_bank_account_id", table_name="payments")
    op.drop_constraint("fk_payments_bank_account_id", "payments", type_="foreignkey")
    op.drop_column("payments", "bank_account_id")

    if dialect == "postgresql":
        op.drop_index("uq_bank_accounts_one_default", table_name="bank_accounts")
    op.drop_index("ix_bank_accounts_name_lower", table_name="bank_accounts")
    op.drop_table("bank_accounts")
