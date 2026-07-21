"""Scope idempotency uniqueness by route.

Revision ID: 056_spec_v1714_idempotency_route_scoped_unique
Revises: 055_spec_v1713_seed_expense_categories_all_companies
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "056_spec_v1714_idempotency_route_scoped_unique"
down_revision: Union[str, None] = "055_spec_v1713_seed_expense_categories_all_companies"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _drop_old_uniqueness() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    unique_constraints = {uc["name"] for uc in inspector.get_unique_constraints("idempotency_records")}
    if "uq_idempotency_user_key" in unique_constraints:
        op.drop_constraint("uq_idempotency_user_key", "idempotency_records", type_="unique")

    indexes = {idx["name"] for idx in inspector.get_indexes("idempotency_records")}
    if "uq_idempotency_user_key" in indexes:
        op.drop_index("uq_idempotency_user_key", table_name="idempotency_records")


def upgrade() -> None:
    _drop_old_uniqueness()
    op.create_unique_constraint(
        "uq_idempotency_user_key_route",
        "idempotency_records",
        ["user_id", "idempotency_key", "route_key"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    unique_constraints = {uc["name"] for uc in inspector.get_unique_constraints("idempotency_records")}
    if "uq_idempotency_user_key_route" in unique_constraints:
        op.drop_constraint("uq_idempotency_user_key_route", "idempotency_records", type_="unique")
    op.create_unique_constraint(
        "uq_idempotency_user_key",
        "idempotency_records",
        ["user_id", "idempotency_key"],
    )
