"""Spec v17.3.22 — company notes board with per-note role visibility.

Revision ID: 062_spec_v17322_company_notes
Revises: 061_spec_v1736_null_password_plain
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "062_spec_v17322_company_notes"
down_revision: Union[str, None] = "061_spec_v1736_null_password_plain"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("note_date", sa.Date(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_company_notes_company_date",
        "company_notes",
        ["company_id", "note_date"],
    )

    op.create_table(
        "company_note_role_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "note_id",
            sa.Integer(),
            sa.ForeignKey("company_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("note_id", "role", name="uq_company_note_role_access_note_role"),
    )
    op.create_index(
        "ix_company_note_role_access_note_id",
        "company_note_role_access",
        ["note_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_company_note_role_access_note_id", table_name="company_note_role_access")
    op.drop_table("company_note_role_access")
    op.drop_index("ix_company_notes_company_date", table_name="company_notes")
    op.drop_table("company_notes")
