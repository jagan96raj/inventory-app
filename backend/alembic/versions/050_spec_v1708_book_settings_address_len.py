"""Widen book_settings.company_address_line for detailed company addresses.



Revision ID: 050_spec_v1708_book_settings_address_len

Revises: 049_spec_v1707_bill_notes

"""



from typing import Sequence, Union



import sqlalchemy as sa

from alembic import op



revision: str = "050_spec_v1708_book_settings_address_len"

down_revision: Union[str, None] = "049_spec_v1707_bill_notes"

branch_labels: Sequence[str] | None = None

depends_on: Sequence[str] | None = None





def upgrade() -> None:

    op.alter_column(

        "book_settings",

        "company_address_line",

        existing_type=sa.String(length=500),

        type_=sa.String(length=2000),

        existing_nullable=True,

    )





def downgrade() -> None:

    op.alter_column(

        "book_settings",

        "company_address_line",

        existing_type=sa.String(length=2000),

        type_=sa.String(length=500),

        existing_nullable=True,

    )

