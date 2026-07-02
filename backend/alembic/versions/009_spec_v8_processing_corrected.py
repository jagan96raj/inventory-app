"""Spec v8 correction: no output_brand on job; brand per output line; multi balance return lines

Revision ID: 009_spec_v8_processing_corrected
Revises: 008_spec_v8_processing
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_spec_v8_processing_corrected"
down_revision: Union[str, None] = "008_spec_v8_processing"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("processing_output_lines", sa.Column("brand_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE processing_output_lines pol
        SET brand_id = pj.output_brand_id
        FROM processing_sessions ps
        JOIN processing_jobs pj ON pj.id = ps.job_id
        WHERE pol.session_id = ps.id AND pol.brand_id IS NULL
        """
    )
    op.alter_column("processing_output_lines", "brand_id", nullable=False)
    op.create_foreign_key(
        "processing_output_lines_brand_id_fkey",
        "processing_output_lines",
        "brands",
        ["brand_id"],
        ["id"],
    )

    op.drop_constraint("processing_jobs_output_brand_id_fkey", "processing_jobs", type_="foreignkey")
    op.drop_column("processing_jobs", "output_brand_id")

    op.rename_table("processing_balance_returns", "processing_balance_return_lines")
    op.drop_constraint("processing_balance_returns_session_id_key", "processing_balance_return_lines", type_="unique")
    op.add_column(
        "processing_balance_return_lines",
        sa.Column("line_index", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("processing_balance_return_lines", "line_index")
    op.create_unique_constraint(
        "processing_balance_returns_session_id_key",
        "processing_balance_return_lines",
        ["session_id"],
    )
    op.rename_table("processing_balance_return_lines", "processing_balance_returns")

    op.add_column("processing_jobs", sa.Column("output_brand_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE processing_jobs pj
        SET output_brand_id = pol.brand_id
        FROM processing_sessions ps
        JOIN processing_output_lines pol ON pol.session_id = ps.id
        WHERE ps.job_id = pj.id AND pj.output_brand_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE processing_jobs
        SET output_brand_id = input_brand_id
        WHERE output_brand_id IS NULL
        """
    )
    op.alter_column("processing_jobs", "output_brand_id", nullable=False)
    op.create_foreign_key(
        "processing_jobs_output_brand_id_fkey",
        "processing_jobs",
        "brands",
        ["output_brand_id"],
        ["id"],
    )

    op.drop_constraint("processing_output_lines_brand_id_fkey", "processing_output_lines", type_="foreignkey")
    op.drop_column("processing_output_lines", "brand_id")
