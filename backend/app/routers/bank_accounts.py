"""Spec v12.21 — bank accounts router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.permissions import Permission, require_permission
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict, paginate_select
from app.database import get_db
from app.models.entities import BankAccount, BankAccountKind, User
from app.schemas import (
    BankAccountBalanceOut,
    BankAccountCreate,
    BankAccountOut,
    BankAccountPageOut,
    BankAccountUpdate,
)
from app.core.tenant import company_id_for_user
from app.services.accounts import get_bank_account_balance
from app.services.bank_accounts import (
    create_bank_account,
    delete_bank_account,
    edit_bank_account,
    make_default_bank_account,
)
from app.services.idempotency import hash_empty_body, hash_pydantic_body

router = APIRouter(
    prefix="/bank-accounts",
    tags=["bank-accounts"],
    dependencies=[Depends(require_permission(Permission.BANK_ACCOUNTS_MANAGE))],
)


def _to_out(b: BankAccount) -> BankAccountOut:
    return BankAccountOut.model_validate(b)


def _to_balance_out(b: BankAccount, db: Session) -> BankAccountBalanceOut:
    base = _to_out(b)
    return BankAccountBalanceOut(
        **base.model_dump(),
        balance=get_bank_account_balance(db, b.id, company_id=b.company_id),
    )


@router.get("", response_model=BankAccountPageOut)
def list_bank_accounts(
    active: str = Query("true", pattern="^(true|false|all)$"),
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    company_id = company_id_for_user(user)
    q = (
        select(BankAccount)
        .where(
            BankAccount.company_id == company_id,
            BankAccount.kind == BankAccountKind.bank,
        )
        .order_by(
            BankAccount.is_default.desc(), BankAccount.is_active.desc(), BankAccount.name
        )
    )
    if active == "true":
        q = q.where(BankAccount.is_active.is_(True))
    elif active == "false":
        q = q.where(BankAccount.is_active.is_(False))
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [_to_balance_out(r, db) for r in rows]
    return BankAccountPageOut(**page_dict(items, total, limit, offset))


@router.post("", response_model=BankAccountOut, status_code=201)
def post_bank_account(
    body: BankAccountCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/bank-accounts"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            record = create_bank_account(
                db,
                company_id=company_id_for_user(user),
                name=body.name,
                account_number_last4=body.account_number_last4,
                ifsc=body.ifsc,
                opening_balance=body.opening_balance,
                is_default=body.is_default,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return _to_out(record), 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.patch("/{bank_id}", response_model=BankAccountOut)
def patch_bank_account(
    bank_id: int,
    body: BankAccountUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = f"PATCH /api/bank-accounts/{bank_id}"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            record = edit_bank_account(
                db,
                bank_id,
                company_id=company_id_for_user(user),
                name=body.name,
                account_number_last4=body.account_number_last4,
                ifsc=body.ifsc,
                is_active=body.is_active,
            )
        except ValueError as e:
            msg = str(e)
            raise HTTPException(404 if "not found" in msg.lower() else 400, msg) from e
        return _to_out(record), 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.delete("/{bank_id}")
def delete_bank_account_endpoint(
    bank_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        delete_bank_account(db, bank_id, company_id=company_id_for_user(user))
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(404, msg) from e
        status = 409 if "in use" in msg.lower() else 400
        raise HTTPException(status, msg) from e
    return {"ok": True}


@router.post("/{bank_id}/make-default", response_model=BankAccountOut)
def make_default_endpoint(
    bank_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = f"POST /api/bank-accounts/{bank_id}/make-default"
    request_hash = hash_empty_body()

    def execute():
        try:
            record = make_default_bank_account(
                db, bank_id, company_id=company_id_for_user(user)
            )
        except ValueError as e:
            msg = str(e)
            raise HTTPException(404 if "not found" in msg.lower() else 400, msg) from e
        return _to_out(record), 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)
