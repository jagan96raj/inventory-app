"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_products_name_lower", "products", [sa.text("lower(trim(product_name))")], unique=True)

    op.create_table(
        "brands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_brands_name_lower", "brands", [sa.text("lower(trim(name))")], unique=True)

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_locations_name_lower", "locations", [sa.text("lower(trim(name))")], unique=True)

    op.create_table(
        "bag_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("weight_per_bag_kg", sa.Numeric(14, 3), nullable=False),
        sa.Column("is_loose", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_bag_types_name_lower", "bag_types", [sa.text("lower(trim(name))")], unique=True)

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text()),
        sa.Column("phone", sa.String(50)),
        sa.Column("credit_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("debit_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_customers_name_lower", "customers", [sa.text("lower(trim(name))")], unique=True)

    op.create_table(
        "inventory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("total_quantity_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("product_id", "brand_id", "location_id", "bag_type_id", name="uq_inventory_tuple"),
    )

    bill_type = sa.Enum("sales", "purchase", name="bill_type_enum")
    bill_status = sa.Enum("draft", "confirmed", name="bill_status_enum")
    payment_status = sa.Enum("pending", "partial", "done", name="payment_status_enum")
    delivery_status = sa.Enum("pending", "partial", "done", name="delivery_status_enum")
    line_delivery_status = sa.Enum("pending", "partial", "done", name="line_delivery_status_enum")
    payment_mode = sa.Enum("cash", "bank", "credit", "debit", name="payment_mode_enum")
    fulfillment_type = sa.Enum("deliver", "receive", "return", name="fulfillment_type_enum")

    bind = op.get_bind()
    bill_type.create(bind, checkfirst=True)
    bill_status.create(bind, checkfirst=True)
    payment_status.create(bind, checkfirst=True)
    delivery_status.create(bind, checkfirst=True)
    line_delivery_status.create(bind, checkfirst=True)
    payment_mode.create(bind, checkfirst=True)
    fulfillment_type.create(bind, checkfirst=True)

    bill_type_col = ENUM("sales", "purchase", name="bill_type_enum", create_type=False)
    bill_status_col = ENUM("draft", "confirmed", name="bill_status_enum", create_type=False)
    payment_status_col = ENUM("pending", "partial", "done", name="payment_status_enum", create_type=False)
    delivery_status_col = ENUM("pending", "partial", "done", name="delivery_status_enum", create_type=False)
    line_delivery_status_col = ENUM("pending", "partial", "done", name="line_delivery_status_enum", create_type=False)
    payment_mode_col = ENUM("cash", "bank", "credit", "debit", name="payment_mode_enum", create_type=False)
    fulfillment_type_col = ENUM("deliver", "receive", "return", name="fulfillment_type_enum", create_type=False)

    op.create_table(
        "bills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bill_number", sa.String(50), unique=True, nullable=False),
        sa.Column("bill_type", bill_type_col, nullable=False),
        sa.Column("status", bill_status_col, nullable=False, server_default="draft"),
        sa.Column("bill_date", sa.Date(), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("adjustment", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("use_balance", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("amount_paid", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("payment_status", payment_status_col, nullable=False, server_default="pending"),
        sa.Column("order_delivery_status", delivery_status_col, nullable=False, server_default="pending"),
        sa.Column("balance_applied_on_confirm", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "bill_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bill_id", sa.Integer(), sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("ordered_bags", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ordered_loose_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("ordered_quantity_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("rate_per_kg", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("line_delivery_status", line_delivery_status_col, nullable=False, server_default="pending"),
        sa.Column("net_delivered_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("net_received_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("net_returned_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bill_id", sa.Integer(), sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_mode", payment_mode_col, nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "fulfillment_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bill_line_id", sa.Integer(), sa.ForeignKey("bill_lines.id"), nullable=False),
        sa.Column("entry_type", fulfillment_type_col, nullable=False),
        sa.Column("quantity_kg", sa.Numeric(14, 3), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("fulfillment_entries")
    op.drop_table("payments")
    op.drop_table("bill_lines")
    op.drop_table("bills")
    op.drop_table("inventory")
    op.drop_table("customers")
    op.drop_table("bag_types")
    op.drop_table("locations")
    op.drop_table("brands")
    op.drop_table("products")
    for name in [
        "fulfillment_type_enum",
        "payment_mode_enum",
        "line_delivery_status_enum",
        "delivery_status_enum",
        "payment_status_enum",
        "bill_status_enum",
        "bill_type_enum",
    ]:
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
