"""Spec v8: processing jobs and sessions

Revision ID: 008_spec_v8_processing
Revises: 007_spec_v52_setoff
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "008_spec_v8_processing"
down_revision: Union[str, None] = "007_spec_v52_setoff"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

KG = sa.Numeric(14, 3)
job_status = sa.Enum("open", "closed", name="processing_job_status_enum")
job_status_col = ENUM("open", "closed", name="processing_job_status_enum", create_type=False)


def upgrade() -> None:
    job_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("input_product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("input_brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("output_brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("status", job_status_col, nullable=False, server_default="open"),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_processing_job_open_input
        ON processing_jobs (input_product_id, input_brand_id)
        WHERE status = 'open'
        """
    )

    op.create_table(
        "processing_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("balance_kg", KG, nullable=False, server_default="0"),
        sa.Column("dust_kg", KG, nullable=False, server_default="0"),
        sa.Column("stone_kg", KG, nullable=False, server_default="0"),
        sa.Column("mud_kg", KG, nullable=False, server_default="0"),
        sa.Column("sack_weight_loss_kg", KG, nullable=False, server_default="0"),
        sa.Column("misc_loss_kg", KG, nullable=False, server_default="0"),
        sa.Column("total_input_kg", KG, nullable=False),
        sa.Column("total_output_kg", KG, nullable=False),
        sa.Column("total_waste_kg", KG, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "processing_input_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("processing_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", KG, nullable=False, server_default="0"),
        sa.Column("quantity_kg", KG, nullable=False),
        sa.Column("line_index", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "processing_waste_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("processing_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("waste_brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", KG, nullable=False, server_default="0"),
        sa.Column("quantity_kg", KG, nullable=False),
        sa.Column("line_index", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "processing_output_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("processing_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", KG, nullable=False, server_default="0"),
        sa.Column("quantity_kg", KG, nullable=False),
        sa.Column("line_index", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "processing_balance_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("processing_sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", KG, nullable=False, server_default="0"),
        sa.Column("quantity_kg", KG, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("processing_balance_returns")
    op.drop_table("processing_output_lines")
    op.drop_table("processing_waste_lines")
    op.drop_table("processing_input_lines")
    op.drop_table("processing_sessions")
    op.execute("DROP INDEX IF EXISTS uq_processing_job_open_input")
    op.drop_table("processing_jobs")
    job_status.drop(op.get_bind(), checkfirst=True)
