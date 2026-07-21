"""Spec v17.0.3 — multi-tenant Phase 4: per-company book settings + bill/JW counters.

Revision ID: 047_spec_v1703_per_company_settings_counters
Revises: 046_spec_v1701_company_id_business
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "047_spec_v1703_per_company_settings_counters"
down_revision: Union[str, None] = "046_spec_v1701_company_id_business"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # --- book_settings: one row per company (keep id PK) ---
    op.add_column("book_settings", sa.Column("company_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE book_settings SET company_id = 1"))
    op.alter_column("book_settings", "company_id", nullable=False)
    op.create_index("ix_book_settings_company_id", "book_settings", ["company_id"], unique=True)
    op.create_foreign_key(
        "fk_book_settings_company_id_companies",
        "book_settings",
        "companies",
        ["company_id"],
        ["id"],
    )

    # --- bill_number_counters: composite PK (company_id, bill_type) ---
    op.add_column("bill_number_counters", sa.Column("company_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE bill_number_counters SET company_id = 1"))
    op.alter_column("bill_number_counters", "company_id", nullable=False)
    op.drop_constraint("bill_number_counters_pkey", "bill_number_counters", type_="primary")
    op.create_primary_key(
        "bill_number_counters_pkey",
        "bill_number_counters",
        ["company_id", "bill_type"],
    )
    op.create_foreign_key(
        "fk_bill_number_counters_company_id_companies",
        "bill_number_counters",
        "companies",
        ["company_id"],
        ["id"],
    )

    # --- jw_number_counters: one row per company (keep id PK) ---
    op.add_column("jw_number_counters", sa.Column("company_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE jw_number_counters SET company_id = 1"))
    op.alter_column("jw_number_counters", "company_id", nullable=False)
    op.create_index("ix_jw_number_counters_company_id", "jw_number_counters", ["company_id"], unique=True)
    op.create_foreign_key(
        "fk_jw_number_counters_company_id_companies",
        "jw_number_counters",
        "companies",
        ["company_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_jw_number_counters_company_id_companies", "jw_number_counters", type_="foreignkey")
    op.drop_index("ix_jw_number_counters_company_id", table_name="jw_number_counters")
    op.drop_column("jw_number_counters", "company_id")

    op.drop_constraint(
        "fk_bill_number_counters_company_id_companies", "bill_number_counters", type_="foreignkey"
    )
    op.drop_constraint("bill_number_counters_pkey", "bill_number_counters", type_="primary")
    # Downgrade assumes only company_id=1 rows remain (or collapses to bill_type PK).
    op.execute(sa.text("DELETE FROM bill_number_counters WHERE company_id <> 1"))
    op.create_primary_key("bill_number_counters_pkey", "bill_number_counters", ["bill_type"])
    op.drop_column("bill_number_counters", "company_id")

    op.drop_constraint("fk_book_settings_company_id_companies", "book_settings", type_="foreignkey")
    op.drop_index("ix_book_settings_company_id", table_name="book_settings")
    op.execute(sa.text("DELETE FROM book_settings WHERE company_id <> 1"))
    op.drop_column("book_settings", "company_id")
