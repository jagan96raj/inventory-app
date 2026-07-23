"""Add bank_accounts.kind and seed a Cash account per company.

Spec v17.2.0 Phase 1 (Option B): unify cash into bank_accounts as kind=cash while
keeping book_settings cash opening as the live source until later phases.

Revision ID: 058_spec_v1720_bank_account_kind_cash
Revises: 057_spec_v1715_jw_counter_company_pk
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "058_spec_v1720_bank_account_kind_cash"
down_revision: Union[str, None] = "057_spec_v1715_jw_counter_company_pk"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

BANK_ACCOUNT_KIND = sa.Enum("cash", "bank", name="bank_account_kind_enum")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        BANK_ACCOUNT_KIND.create(bind, checkfirst=True)
        op.add_column(
            "bank_accounts",
            sa.Column(
                "kind",
                BANK_ACCOUNT_KIND,
                nullable=False,
                server_default="bank",
            ),
        )
    else:
        op.add_column(
            "bank_accounts",
            sa.Column(
                "kind",
                sa.String(length=16),
                nullable=False,
                server_default="bank",
            ),
        )

    # One cash account per company (partial unique).
    op.create_index(
        "uq_bank_accounts_one_cash",
        "bank_accounts",
        ["company_id"],
        unique=True,
        sqlite_where=sa.text("kind = 'cash'"),
        postgresql_where=sa.text("kind = 'cash'"),
    )

    companies = list(
        bind.execute(
            sa.text(
                "SELECT c.id, "
                "COALESCE(bs.cash_opening_balance, 0) AS cash_opening_balance, "
                "bs.cash_opening_balance_at "
                "FROM companies c "
                "LEFT JOIN book_settings bs ON bs.company_id = c.id"
            )
        ).mappings()
    )

    for row in companies:
        company_id = int(row["id"])
        cash_count = bind.execute(
            sa.text(
                "SELECT COUNT(1) FROM bank_accounts "
                "WHERE company_id = :company_id AND kind = 'cash'"
            ).bindparams(company_id=company_id)
        ).scalar_one()
        if int(cash_count) > 0:
            continue

        opening = row["cash_opening_balance"]
        opening_at = row["cash_opening_balance_at"]
        if opening_at is None:
            opening_at = bind.execute(sa.text("SELECT CURRENT_DATE")).scalar_one()

        named_cash = bind.execute(
            sa.text(
                "SELECT id, is_default FROM bank_accounts "
                "WHERE company_id = :company_id AND lower(trim(name)) = 'cash' "
                "LIMIT 1"
            ).bindparams(company_id=company_id)
        ).mappings().first()

        if named_cash:
            was_default = bool(named_cash["is_default"])
            if dialect == "postgresql":
                bind.execute(
                    sa.text(
                        "UPDATE bank_accounts "
                        "SET kind = CAST('cash' AS bank_account_kind_enum), "
                        "is_default = FALSE, "
                        "opening_balance = :opening, "
                        "opening_balance_at = :opening_at "
                        "WHERE id = :id"
                    ).bindparams(
                        id=named_cash["id"],
                        opening=opening,
                        opening_at=opening_at,
                    )
                )
            else:
                bind.execute(
                    sa.text(
                        "UPDATE bank_accounts "
                        "SET kind = 'cash', is_default = 0, "
                        "opening_balance = :opening, opening_balance_at = :opening_at "
                        "WHERE id = :id"
                    ).bindparams(
                        id=named_cash["id"],
                        opening=opening,
                        opening_at=opening_at,
                    )
                )
            if was_default:
                # Promote another bank-kind row so default uniqueness still works.
                other = bind.execute(
                    sa.text(
                        "SELECT id FROM bank_accounts "
                        "WHERE company_id = :company_id AND kind = 'bank' AND is_active = TRUE "
                        "ORDER BY id LIMIT 1"
                    ).bindparams(company_id=company_id)
                ).first()
                if other:
                    bind.execute(
                        sa.text(
                            "UPDATE bank_accounts SET is_default = TRUE WHERE id = :id"
                        ).bindparams(id=other[0])
                    )
            continue

        if dialect == "postgresql":
            bind.execute(
                sa.text(
                    "INSERT INTO bank_accounts "
                    "(company_id, name, kind, account_number_last4, ifsc, "
                    "opening_balance, opening_balance_at, is_default, is_active) "
                    "VALUES ("
                    ":company_id, 'Cash', CAST('cash' AS bank_account_kind_enum), "
                    "NULL, NULL, :opening, :opening_at, FALSE, TRUE)"
                ).bindparams(
                    company_id=company_id,
                    opening=opening,
                    opening_at=opening_at,
                )
            )
        else:
            bind.execute(
                sa.text(
                    "INSERT INTO bank_accounts "
                    "(company_id, name, kind, account_number_last4, ifsc, "
                    "opening_balance, opening_balance_at, is_default, is_active) "
                    "VALUES ("
                    ":company_id, 'Cash', 'cash', NULL, NULL, :opening, :opening_at, 0, 1)"
                ).bindparams(
                    company_id=company_id,
                    opening=opening,
                    opening_at=opening_at,
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index("uq_bank_accounts_one_cash", table_name="bank_accounts")
    op.execute(sa.text("DELETE FROM bank_accounts WHERE kind = 'cash'"))
    op.drop_column("bank_accounts", "kind")
    if dialect == "postgresql":
        BANK_ACCOUNT_KIND.drop(bind, checkfirst=True)
