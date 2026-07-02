"""Spec v14.6 — processing job output allocation mode (proportional vs single owner).

Revision ID: 028_spec_v146_output_allocation
Revises: 027_spec_v143_jw_activity_type
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "028_spec_v146_output_allocation"
down_revision: Union[str, None] = "027_spec_v143_jw_activity_type"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ALLOC_MODE_ENUM = ENUM(
    "proportional",
    "single_owner",
    name="processing_output_allocation_mode_enum",
    create_type=False,
)
OWNER_ENUM = ENUM("owned", "job_work", name="inventory_owner_type_enum", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    ALLOC_MODE_ENUM.create(bind, checkfirst=True)

    op.add_column(
        "processing_jobs",
        sa.Column("output_allocation_mode", ALLOC_MODE_ENUM, nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("single_allocation_owner_type", OWNER_ENUM, nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column(
            "single_allocation_customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_processing_jobs_output_allocation_owner",
        "processing_jobs",
        """
        output_allocation_mode IS NULL
        OR (
            output_allocation_mode = 'proportional'
            AND single_allocation_owner_type IS NULL
            AND single_allocation_customer_id IS NULL
        )
        OR (
            output_allocation_mode = 'single_owner'
            AND single_allocation_owner_type IS NOT NULL
            AND (
                (single_allocation_owner_type = 'owned' AND single_allocation_customer_id IS NULL)
                OR (single_allocation_owner_type = 'job_work' AND single_allocation_customer_id IS NOT NULL)
            )
        )
        """,
    )


def downgrade() -> None:
    op.drop_constraint("ck_processing_jobs_output_allocation_owner", "processing_jobs", type_="check")
    op.drop_column("processing_jobs", "single_allocation_customer_id")
    op.drop_column("processing_jobs", "single_allocation_owner_type")
    op.drop_column("processing_jobs", "output_allocation_mode")
    ALLOC_MODE_ENUM.drop(op.get_bind(), checkfirst=True)
