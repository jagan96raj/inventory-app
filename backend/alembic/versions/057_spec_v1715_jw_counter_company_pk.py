"""Make jw_number_counters use company_id as PK.

The original singleton table used id INTEGER PRIMARY KEY DEFAULT 1 (literal 1,
not a sequence). After multi-tenant company_id was added, INSERT for a second
company still received id=1 and failed with UniqueViolation — which the UI
misreported as a Docker/DB-down error.

Align with bill_number_counters: one row per company, PK = company_id.

Revision ID: 057_spec_v1715_jw_counter_company_pk
Revises: 056_spec_v1714_idempotency_route_scoped_unique
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "057_spec_v1715_jw_counter_company_pk"
down_revision: Union[str, None] = "056_spec_v1714_idempotency_route_scoped_unique"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("jw_number_counters") as batch_op:
            batch_op.drop_constraint("jw_number_counters_pkey", type_="primary")
            batch_op.drop_index("ix_jw_number_counters_company_id")
            batch_op.drop_column("id")
            batch_op.create_primary_key("jw_number_counters_pkey", ["company_id"])
        return

    op.drop_constraint("jw_number_counters_pkey", "jw_number_counters", type_="primary")
    op.drop_index("ix_jw_number_counters_company_id", table_name="jw_number_counters")
    op.drop_column("jw_number_counters", "id")
    op.create_primary_key("jw_number_counters_pkey", "jw_number_counters", ["company_id"])


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("jw_number_counters") as batch_op:
            batch_op.drop_constraint("jw_number_counters_pkey", type_="primary")
            batch_op.add_column(sa.Column("id", sa.Integer(), nullable=True))
        op.execute(sa.text("UPDATE jw_number_counters SET id = company_id"))
        with op.batch_alter_table("jw_number_counters") as batch_op:
            batch_op.alter_column("id", nullable=False)
            batch_op.create_primary_key("jw_number_counters_pkey", ["id"])
            batch_op.create_index("ix_jw_number_counters_company_id", ["company_id"], unique=True)
        return

    op.drop_constraint("jw_number_counters_pkey", "jw_number_counters", type_="primary")
    op.add_column(
        "jw_number_counters",
        sa.Column("id", sa.Integer(), nullable=True),
    )
    op.execute(sa.text("UPDATE jw_number_counters SET id = company_id"))
    op.alter_column("jw_number_counters", "id", nullable=False, server_default="1")
    op.create_primary_key("jw_number_counters_pkey", "jw_number_counters", ["id"])
    op.create_index("ix_jw_number_counters_company_id", "jw_number_counters", ["company_id"], unique=True)
