"""Spec v14.0 — Job Work + owner-tagged inventory.

Revision ID: 025_spec_v14_job_work
Revises: 024_customer_alternate_phone
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "025_spec_v14_job_work"
down_revision: Union[str, None] = "024_customer_alternate_phone"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    owner_enum = ENUM("owned", "job_work", name="inventory_owner_type_enum", create_type=False)
    stock_enum = ENUM("owned", "job_work", name="stock_source_enum", create_type=False)
    charge_enum = ENUM("product_sale", "processing_charge", name="line_charge_type_enum", create_type=False)
    party_enum = ENUM("internal", "external", name="customer_party_type_enum", create_type=False)
    jw_status_enum = ENUM("open", "completed", "cancelled", name="job_work_order_status_enum", create_type=False)

    for enum_type, values in (
        ("inventory_owner_type_enum", ("owned", "job_work")),
        ("stock_source_enum", ("owned", "job_work")),
        ("line_charge_type_enum", ("product_sale", "processing_charge")),
        ("customer_party_type_enum", ("internal", "external")),
        ("job_work_order_status_enum", ("open", "completed", "cancelled")),
    ):
        sa.Enum(*values, name=enum_type).create(op.get_bind(), checkfirst=True)

    op.add_column(
        "customers",
        sa.Column(
            "party_type",
            party_enum,
            nullable=False,
            server_default="internal",
        ),
    )

    op.drop_constraint("uq_inventory_tuple", "inventory", type_="unique")
    op.add_column(
        "inventory",
        sa.Column("owner_type", owner_enum, nullable=False, server_default="owned"),
    )
    op.add_column("inventory", sa.Column("customer_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_inventory_customer_id", "inventory", "customers", ["customer_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_inventory_owner_customer",
        "inventory",
        "(owner_type = 'owned' AND customer_id IS NULL) OR "
        "(owner_type = 'job_work' AND customer_id IS NOT NULL)",
    )
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

    op.create_table(
        "jw_number_counters",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(sa.text("INSERT INTO jw_number_counters (id, last_number) VALUES (1, 0)"))

    op.create_table(
        "job_work_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_number", sa.String(50), nullable=False, unique=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("job_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", jw_status_enum, nullable=False, server_default="open"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "job_work_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("job_work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("ordered_bags", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ordered_loose_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("ordered_quantity_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("received_bags", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_loose_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("received_quantity_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("returned_bags", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("returned_loose_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("returned_quantity_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("line_index", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "job_work_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("job_work_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("quantity_kg", sa.Numeric(14, 3), nullable=False),
        sa.Column("vehicle_no", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "bill_lines",
        sa.Column("stock_source", stock_enum, nullable=False, server_default="owned"),
    )
    op.add_column("bill_lines", sa.Column("job_work_order_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_bill_lines_job_work_order_id",
        "bill_lines",
        "job_work_orders",
        ["job_work_order_id"],
        ["id"],
    )
    op.add_column(
        "bill_lines",
        sa.Column("line_charge_type", charge_enum, nullable=False, server_default="product_sale"),
    )

    op.add_column(
        "processing_input_lines",
        sa.Column("owner_type", owner_enum, nullable=False, server_default="owned"),
    )
    op.add_column("processing_input_lines", sa.Column("customer_id", sa.Integer(), nullable=True))
    op.add_column("processing_input_lines", sa.Column("job_work_order_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_processing_input_job_work_order_id",
        "processing_input_lines",
        "job_work_orders",
        ["job_work_order_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_processing_input_customer_id",
        "processing_input_lines",
        "customers",
        ["customer_id"],
        ["id"],
    )

    op.add_column(
        "processing_output_lines",
        sa.Column("owner_type", owner_enum, nullable=False, server_default="owned"),
    )
    op.add_column("processing_output_lines", sa.Column("customer_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_processing_output_customer_id",
        "processing_output_lines",
        "customers",
        ["customer_id"],
        ["id"],
    )

    op.add_column(
        "processing_balance_return_lines",
        sa.Column("owner_type", owner_enum, nullable=False, server_default="owned"),
    )
    op.add_column("processing_balance_return_lines", sa.Column("customer_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_processing_balance_return_customer_id",
        "processing_balance_return_lines",
        "customers",
        ["customer_id"],
        ["id"],
    )

    op.create_table(
        "processing_waste_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("processing_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_type", owner_enum, nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("dust_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("stone_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("sack_weight_waste_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("miscellaneous_waste_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("processing_waste_allocations")
    op.drop_constraint("fk_processing_balance_return_customer_id", "processing_balance_return_lines", type_="foreignkey")
    op.drop_column("processing_balance_return_lines", "customer_id")
    op.drop_column("processing_balance_return_lines", "owner_type")
    op.drop_constraint("fk_processing_output_customer_id", "processing_output_lines", type_="foreignkey")
    op.drop_column("processing_output_lines", "customer_id")
    op.drop_column("processing_output_lines", "owner_type")
    op.drop_constraint("fk_processing_input_customer_id", "processing_input_lines", type_="foreignkey")
    op.drop_constraint("fk_processing_input_job_work_order_id", "processing_input_lines", type_="foreignkey")
    op.drop_column("processing_input_lines", "job_work_order_id")
    op.drop_column("processing_input_lines", "customer_id")
    op.drop_column("processing_input_lines", "owner_type")
    op.drop_column("bill_lines", "line_charge_type")
    op.drop_constraint("fk_bill_lines_job_work_order_id", "bill_lines", type_="foreignkey")
    op.drop_column("bill_lines", "job_work_order_id")
    op.drop_column("bill_lines", "stock_source")
    op.drop_table("job_work_receipts")
    op.drop_table("job_work_lines")
    op.drop_table("job_work_orders")
    op.drop_table("jw_number_counters")
    op.drop_index("uq_inventory_job_work_tuple", table_name="inventory")
    op.drop_index("uq_inventory_owned_tuple", table_name="inventory")
    op.drop_constraint("ck_inventory_owner_customer", "inventory", type_="check")
    op.drop_constraint("fk_inventory_customer_id", "inventory", type_="foreignkey")
    op.drop_column("inventory", "customer_id")
    op.drop_column("inventory", "owner_type")
    op.create_unique_constraint(
        "uq_inventory_tuple", "inventory", ["product_id", "brand_id", "location_id", "bag_type_id"]
    )
    op.drop_column("customers", "party_type")
