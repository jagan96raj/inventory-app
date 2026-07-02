"""Drop processing module tables (v8 removed)

Revision ID: 010_drop_processing
Revises: 009_spec_v8_processing_corrected
"""

from typing import Sequence, Union

from alembic import op

revision: str = "010_drop_processing"
down_revision: Union[str, None] = "009_spec_v8_processing_corrected"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("processing_balance_return_lines")
    op.drop_table("processing_input_lines")
    op.drop_table("processing_waste_lines")
    op.drop_table("processing_output_lines")
    op.drop_table("processing_sessions")
    op.drop_table("processing_jobs")
    op.execute("DROP TYPE IF EXISTS processing_job_status_enum")


def downgrade() -> None:
    raise NotImplementedError("Processing tables were removed in v8 rollback; restore from migration 008/009.")
