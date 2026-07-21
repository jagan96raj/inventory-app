"""Spec v12.21 — expense categories router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.permissions import Permission, require_permission
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict, paginate_select
from app.database import get_db
from app.models.entities import ExpenseCategory, ExpenseCategoryKind, User
from app.schemas import (
    ExpenseCategoryCreate,
    ExpenseCategoryOut,
    ExpenseCategoryPageOut,
    ExpenseCategoryUpdate,
)
from app.core.tenant import company_id_for_user
from app.services.expense_categories import (
    create_category,
    delete_category,
    edit_category,
)
from app.services.idempotency import hash_pydantic_body

router = APIRouter(
    prefix="/expense-categories",
    tags=["expense-categories"],
    dependencies=[Depends(require_permission(Permission.EXPENSE_CATEGORIES_MANAGE))],
)


def _to_out(c: ExpenseCategory) -> ExpenseCategoryOut:
    return ExpenseCategoryOut.model_validate(c)


@router.get("", response_model=ExpenseCategoryPageOut)
def list_categories_endpoint(
    active: str = Query("true", pattern="^(true|false|all)$"),
    kind: ExpenseCategoryKind | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    company_id = company_id_for_user(user)
    q = (
        select(ExpenseCategory)
        .where(ExpenseCategory.company_id == company_id)
        .order_by(
            ExpenseCategory.kind, ExpenseCategory.is_system.desc(), ExpenseCategory.name
        )
    )
    if active == "true":
        q = q.where(ExpenseCategory.is_active.is_(True))
    elif active == "false":
        q = q.where(ExpenseCategory.is_active.is_(False))
    if kind is not None:
        q = q.where(ExpenseCategory.kind == kind)
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [_to_out(r) for r in rows]
    return ExpenseCategoryPageOut(**page_dict(items, total, limit, offset))


@router.post("", response_model=ExpenseCategoryOut, status_code=201)
def post_category(
    body: ExpenseCategoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/expense-categories"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            record = create_category(db, company_id=company_id_for_user(user), name=body.name, kind=body.kind)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return _to_out(record), 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.patch("/{category_id}", response_model=ExpenseCategoryOut)
def patch_category(
    category_id: int,
    body: ExpenseCategoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = f"PATCH /api/expense-categories/{category_id}"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            record = edit_category(
                db,
                category_id,
                company_id=company_id_for_user(user),
                name=body.name,
                is_active=body.is_active,
            )
        except ValueError as e:
            msg = str(e)
            raise HTTPException(404 if "not found" in msg.lower() else 400, msg) from e
        return _to_out(record), 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.delete("/{category_id}")
def delete_category_endpoint(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        delete_category(db, category_id, company_id=company_id_for_user(user))
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(404, msg) from e
        status = 409 if "in use" in msg.lower() or "system" in msg.lower() else 400
        raise HTTPException(status, msg) from e
    return {"ok": True}
