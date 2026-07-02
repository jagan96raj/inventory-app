"""Spec v3: status enums, finalized bills, fulfillment fields

Revision ID: 002_spec_v3
Revises: 001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_spec_v3"
down_revision: Union[str, None] = "001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE fulfillment_entries SET entry_type = 'deliver' WHERE entry_type = 'receive'")

    op.execute("ALTER TYPE payment_status_enum RENAME VALUE 'pending' TO 'unpaid'")
    op.execute("ALTER TYPE payment_status_enum RENAME VALUE 'done' TO 'paid'")

    op.execute("ALTER TYPE delivery_status_enum RENAME VALUE 'pending' TO 'not_delivered'")
    op.execute("ALTER TYPE delivery_status_enum RENAME VALUE 'done' TO 'delivered'")

    op.execute("ALTER TYPE line_delivery_status_enum RENAME VALUE 'pending' TO 'not_delivered'")
    op.execute("ALTER TYPE line_delivery_status_enum RENAME VALUE 'done' TO 'delivered'")

    op.execute("DELETE FROM bills WHERE status = 'draft'")
    op.execute("ALTER TYPE bill_status_enum RENAME VALUE 'confirmed' TO 'finalized'")

    op.add_column("fulfillment_entries", sa.Column("vehicle_no", sa.String(50), nullable=True))
    op.add_column(
        "fulfillment_entries",
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.execute("UPDATE fulfillment_entries SET fulfilled_at = created_at WHERE fulfilled_at IS NULL")


def downgrade() -> None:
    op.drop_column("fulfillment_entries", "fulfilled_at")
    op.drop_column("fulfillment_entries", "vehicle_no")
