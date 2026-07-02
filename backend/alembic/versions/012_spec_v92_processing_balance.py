"""Spec v9.2: processing balance return and input source

Revision ID: 012_spec_v92_processing_balance
Revises: 011_spec_v9_processing
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "012_spec_v92_processing_balance"
down_revision: Union[str, None] = "011_spec_v9_processing"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

KG = sa.Numeric(14, 3)
input_source = sa.Enum("fresh", "balance_reprocess", name="processing_input_source_enum")
input_source_col = ENUM("fresh", "balance_reprocess", name="processing_input_source_enum", create_type=False)


def upgrade() -> None:
    input_source.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "processing_input_lines",
        sa.Column("input_source", input_source_col, nullable=False, server_default="fresh"),
    )

    op.create_table(
        "processing_balance_return_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("processing_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("bag_type_id", sa.Integer(), sa.ForeignKey("bag_types.id"), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_kg", KG, nullable=False, server_default="0"),
        sa.Column("quantity_kg", KG, nullable=False),
        sa.Column("line_index", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("processing_balance_return_lines")
    op.drop_column("processing_input_lines", "input_source")
    op.execute("DROP TYPE IF EXISTS processing_input_source_enum")
