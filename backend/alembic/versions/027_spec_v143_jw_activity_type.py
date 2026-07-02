"""Spec v14.3 — job work receipt entry_type (receive | return).

Revision ID: 027_spec_v143_jw_activity_type
Revises: 026_spec_v141_operations_owner
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "027_spec_v143_jw_activity_type"
down_revision: Union[str, None] = "026_spec_v141_operations_owner"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ENTRY_ENUM = ENUM("receive", "return", name="job_work_receipt_entry_type_enum")


def upgrade() -> None:
    ENTRY_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "job_work_receipts",
        sa.Column(
            "entry_type",
            ENTRY_ENUM,
            nullable=False,
            server_default="receive",
        ),
    )
    op.execute("UPDATE job_work_receipts SET entry_type = 'receive' WHERE entry_type IS NULL")
    op.create_index(
        "ix_jw_receipts_line_entry_at",
        "job_work_receipts",
        ["line_id", "entry_type", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_jw_receipts_line_entry_at", table_name="job_work_receipts")
    op.drop_column("job_work_receipts", "entry_type")
    ENTRY_ENUM.drop(op.get_bind(), checkfirst=True)
