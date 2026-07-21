"""Spec v17.0.0 — multi-tenant Phase 1: companies + users.company_id.

Revision ID: 045_spec_v1700_companies
Revises: 044_spec_v1609_bill_print
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "045_spec_v1700_companies"
down_revision: Union[str, None] = "044_spec_v1609_bill_print"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address_line", sa.String(length=500), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO companies (id, name, address_line, phone, is_active)
            SELECT 1,
                   COALESCE(NULLIF(TRIM(company_name), ''), 'Raj Agro'),
                   company_address_line,
                   company_phone,
                   true
            FROM book_settings
            WHERE id = 1
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO companies (id, name, is_active)
            SELECT 1, 'Raj Agro', true
            WHERE NOT EXISTS (SELECT 1 FROM companies WHERE id = 1)
            """
        )
    )

    op.add_column("users", sa.Column("company_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE users SET company_id = 1"))
    op.alter_column("users", "company_id", nullable=False)
    op.create_index("ix_users_company_id", "users", ["company_id"], unique=False)
    op.create_foreign_key("fk_users_company_id_companies", "users", "companies", ["company_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_users_company_id_companies", "users", type_="foreignkey")
    op.drop_index("ix_users_company_id", table_name="users")
    op.drop_column("users", "company_id")
    op.drop_table("companies")
