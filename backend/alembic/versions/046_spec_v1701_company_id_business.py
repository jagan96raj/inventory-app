"""Spec v17.0.1 — multi-tenant Phase 2: company_id on business tables + backfill.

Revision ID: 046_spec_v1701_company_id_business
Revises: 045_spec_v1700_companies
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "046_spec_v1701_company_id_business"
down_revision: Union[str, None] = "045_spec_v1700_companies"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

BUSINESS_TABLES = (
    "products",
    "brands",
    "locations",
    "bag_types",
    "customers",
    "inventory",
    "bills",
    "processing_jobs",
    "job_work_orders",
    "bag_changes",
    "product_transfers",
    "stock_disposals",
    "cash_book_entries",
    "bank_accounts",
    "expense_categories",
)


def _add_company_id(table: str) -> None:
    op.add_column(table, sa.Column("company_id", sa.Integer(), nullable=True))
    op.execute(sa.text(f"UPDATE {table} SET company_id = 1"))
    op.alter_column(table, "company_id", nullable=False)
    op.create_index(f"ix_{table}_company_id", table, ["company_id"], unique=False)
    op.create_foreign_key(
        f"fk_{table}_company_id_companies", table, "companies", ["company_id"], ["id"]
    )


def upgrade() -> None:
    for table in BUSINESS_TABLES:
        _add_company_id(table)

    op.add_column("audit_events", sa.Column("company_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE audit_events ae
            SET company_id = u.company_id
            FROM users u
            WHERE ae.user_id = u.id
            """
        )
    )
    op.execute(sa.text("UPDATE audit_events SET company_id = 1 WHERE company_id IS NULL"))
    op.alter_column("audit_events", "company_id", nullable=False)
    op.create_index("ix_audit_events_company_id", "audit_events", ["company_id"], unique=False)
    op.create_foreign_key(
        "fk_audit_events_company_id_companies",
        "audit_events",
        "companies",
        ["company_id"],
        ["id"],
    )

    # Per-company unique indexes (masters)
    op.drop_index("ix_products_name_lower", table_name="products")
    op.create_index(
        "ix_products_name_lower",
        "products",
        ["company_id", sa.text("lower(trim(product_name))")],
        unique=True,
    )
    op.drop_index("ix_brands_name_lower", table_name="brands")
    op.create_index(
        "ix_brands_name_lower",
        "brands",
        ["company_id", sa.text("lower(trim(name))")],
        unique=True,
    )
    op.drop_index("ix_locations_name_lower", table_name="locations")
    op.create_index(
        "ix_locations_name_lower",
        "locations",
        ["company_id", sa.text("lower(trim(name))")],
        unique=True,
    )
    op.drop_index("ix_bag_types_name_lower", table_name="bag_types")
    op.create_index(
        "ix_bag_types_name_lower",
        "bag_types",
        ["company_id", sa.text("lower(trim(name))")],
        unique=True,
    )
    op.drop_index("ix_customers_name_lower", table_name="customers")
    op.create_index(
        "ix_customers_name_lower",
        "customers",
        ["company_id", sa.text("lower(trim(name))")],
        unique=True,
    )

    op.drop_index("ix_bank_accounts_name_lower", table_name="bank_accounts")
    op.create_index(
        "ix_bank_accounts_name_lower",
        "bank_accounts",
        ["company_id", sa.text("lower(trim(name))")],
        unique=True,
    )

    # Bills + job work numbers
    op.drop_constraint("bills_bill_number_key", "bills", type_="unique")
    op.create_unique_constraint(
        "uq_bills_company_bill_number", "bills", ["company_id", "bill_number"]
    )
    op.drop_constraint("job_work_orders_job_number_key", "job_work_orders", type_="unique")
    op.create_unique_constraint(
        "uq_job_work_orders_company_job_number",
        "job_work_orders",
        ["company_id", "job_number"],
    )

    # Inventory partial unique indexes
    op.drop_index("uq_inventory_owned_tuple", table_name="inventory")
    op.drop_index("uq_inventory_job_work_tuple", table_name="inventory")
    op.create_index(
        "uq_inventory_owned_tuple",
        "inventory",
        ["company_id", "product_id", "brand_id", "location_id", "bag_type_id"],
        unique=True,
        sqlite_where=sa.text("owner_type = 'owned'"),
        postgresql_where=sa.text("owner_type = 'owned'"),
    )
    op.create_index(
        "uq_inventory_job_work_tuple",
        "inventory",
        [
            "company_id",
            "product_id",
            "brand_id",
            "location_id",
            "bag_type_id",
            "customer_id",
        ],
        unique=True,
        sqlite_where=sa.text("owner_type = 'job_work'"),
        postgresql_where=sa.text("owner_type = 'job_work'"),
    )


def downgrade() -> None:
    op.drop_index("uq_inventory_job_work_tuple", table_name="inventory")
    op.drop_index("uq_inventory_owned_tuple", table_name="inventory")
    op.create_index(
        "uq_inventory_owned_tuple",
        "inventory",
        ["product_id", "brand_id", "location_id", "bag_type_id"],
        unique=True,
        sqlite_where=sa.text("owner_type = 'owned'"),
        postgresql_where=sa.text("owner_type = 'owned'"),
    )
    op.create_index(
        "uq_inventory_job_work_tuple",
        "inventory",
        ["product_id", "brand_id", "location_id", "bag_type_id", "customer_id"],
        unique=True,
        sqlite_where=sa.text("owner_type = 'job_work'"),
        postgresql_where=sa.text("owner_type = 'job_work'"),
    )

    op.drop_constraint("uq_job_work_orders_company_job_number", "job_work_orders", type_="unique")
    op.create_unique_constraint("job_work_orders_job_number_key", "job_work_orders", ["job_number"])
    op.drop_constraint("uq_bills_company_bill_number", "bills", type_="unique")
    op.create_unique_constraint("bills_bill_number_key", "bills", ["bill_number"])

    op.drop_index("ix_bank_accounts_name_lower", table_name="bank_accounts")
    op.create_index(
        "ix_bank_accounts_name_lower",
        "bank_accounts",
        [sa.text("lower(trim(name))")],
        unique=True,
    )
    op.drop_index("ix_customers_name_lower", table_name="customers")
    op.create_index(
        "ix_customers_name_lower",
        "customers",
        [sa.text("lower(trim(name))")],
        unique=True,
    )
    op.drop_index("ix_bag_types_name_lower", table_name="bag_types")
    op.create_index(
        "ix_bag_types_name_lower",
        "bag_types",
        [sa.text("lower(trim(name))")],
        unique=True,
    )
    op.drop_index("ix_locations_name_lower", table_name="locations")
    op.create_index(
        "ix_locations_name_lower",
        "locations",
        [sa.text("lower(trim(name))")],
        unique=True,
    )
    op.drop_index("ix_brands_name_lower", table_name="brands")
    op.create_index(
        "ix_brands_name_lower",
        "brands",
        [sa.text("lower(trim(name))")],
        unique=True,
    )
    op.drop_index("ix_products_name_lower", table_name="products")
    op.create_index(
        "ix_products_name_lower",
        "products",
        [sa.text("lower(trim(product_name))")],
        unique=True,
    )

    op.drop_constraint("fk_audit_events_company_id_companies", "audit_events", type_="foreignkey")
    op.drop_index("ix_audit_events_company_id", table_name="audit_events")
    op.drop_column("audit_events", "company_id")

    for table in reversed(BUSINESS_TABLES):
        op.drop_constraint(f"fk_{table}_company_id_companies", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_company_id", table_name=table)
        op.drop_column(table, "company_id")
