"""Spec v7: bag change, product transfer, stock disposal

Revision ID: 006_spec_v7_operations
Revises: 005_spec_v61_parent_entry
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_spec_v7_operations"
down_revision: Union[str, None] = "005_spec_v61_parent_entry"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

KG = sa.Numeric(14, 3)


def upgrade() -> None:
    op.create_table(
        "bag_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("from_bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("from_bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("from_loose_kg", KG, nullable=False, server_default="0"),
        sa.Column("from_quantity_kg", KG, nullable=False),
        sa.Column("quantity_loss_kg", KG, nullable=False, server_default="0"),
        sa.Column("operation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "bag_change_to_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bag_change_id", sa.Integer(), sa.ForeignKey("bag_changes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", KG, nullable=False, server_default="0"),
        sa.Column("quantity_kg", KG, nullable=False),
        sa.Column("line_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "product_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("from_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("to_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", KG, nullable=False, server_default="0"),
        sa.Column("quantity_kg", KG, nullable=False),
        sa.Column("operation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "stock_disposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", KG, nullable=False, server_default="0"),
        sa.Column("quantity_kg", KG, nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("operation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("stock_disposals")
    op.drop_table("product_transfers")
    op.drop_table("bag_change_to_lines")
    op.drop_table("bag_changes")
