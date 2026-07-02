from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.auth import get_current_user
from app.core.permissions import Permission, require_permission, require_void_user
from app.core.void_auth import VOID_AUTH_HEADER, verify_void_authorization
from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict, paginate_select
from app.database import get_db
from app.models.entities import Bill, Customer, Payment, PaymentMode, User, BankAccount
from app.services.idempotency import hash_empty_body, hash_pydantic_body
from app.schemas import PaymentCreate, PaymentOut, PaymentPageOut, SetoffPreviewOut
from app.services.payments import create_payment, preview_setoff_allocation, void_payment
from app.services.bill_concurrency import EXPECTED_BILL_VERSION_HEADER, http_exception_for_value_error

router = APIRouter(tags=["payments"])

MANAGE = [Depends(require_permission(Permission.PAYMENTS_MANAGE))]


def payment_to_out(p: Payment, bill: Bill | None, include_linked: bool = False) -> PaymentOut:
    grand = bill.grand_total if bill else None
    paid = bill.amount_paid if bill else None
    due = (grand - paid) if grand is not None and paid is not None else None
    linked: list[PaymentOut] = []
    if include_linked and p.linked_payments:
        for child in p.linked_payments:
            child_bill = child.bill
            linked.append(payment_to_out(child, child_bill, include_linked=False))
    bank = getattr(p, "bank_account", None)
    return PaymentOut(
        id=p.id,
        bill_id=p.bill_id,
        amount=p.amount,
        payment_mode=p.payment_mode,
        bank_account_id=p.bank_account_id,
        bank_account_name=bank.name if bank else None,
        paid_at=p.paid_at,
        voided_at=p.voided_at,
        linked_payment_id=p.linked_payment_id,
        bill_number=bill.bill_number if bill else None,
        customer_name=bill.customer.name if bill and bill.customer else None,
        bill_type=bill.bill_type.value if bill else None,
        grand_total=grand,
        amount_paid=paid,
        amount_due=due,
        bill_version=bill.version if bill else None,
        linked_payments=linked,
    )


@router.get("/payments", response_model=PaymentPageOut, dependencies=MANAGE)
def list_payments(
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = (
        select(Payment)
        .where(Payment.voided_at.is_(None))
        .join(Payment.bill)
        .outerjoin(Bill.customer)
        .options(
            joinedload(Payment.bill).joinedload(Bill.customer),
            joinedload(Payment.bank_account),
        )
        .order_by(Payment.id.desc())
    )
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(
            or_(
                func.lower(Bill.bill_number).like(term),
                func.lower(Customer.name).like(term),
            )
        )
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [payment_to_out(p, p.bill) for p in rows]
    return PaymentPageOut(**page_dict(items, total, limit, offset))


@router.get("/payments/setoff-preview", response_model=SetoffPreviewOut, dependencies=MANAGE)
def setoff_preview(
    bill_id: int = Query(...),
    amount: Decimal = Query(Decimal("0")),
    payment_mode: PaymentMode = Query(...),
    db: Session = Depends(get_db),
):
    try:
        data = preview_setoff_allocation(db, bill_id, amount, payment_mode)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return SetoffPreviewOut(**data)


@router.post("/payments", response_model=PaymentOut, status_code=201, dependencies=MANAGE)
def add_payment(
    body: PaymentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/payments"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            p = create_payment(
                db,
                body.bill_id,
                body.amount,
                body.payment_mode,
                expected_version=body.expected_version,
                bank_account_id=body.bank_account_id,
            )
        except ValueError as e:
            raise http_exception_for_value_error(e) from e
        bill = db.scalar(
            select(Bill)
            .where(Bill.id == body.bill_id)
            .options(joinedload(Bill.customer), joinedload(Bill.payments))
        )
        payment = db.scalar(
            select(Payment)
            .where(Payment.id == p.id)
            .options(
                joinedload(Payment.bill).joinedload(Bill.customer),
                joinedload(Payment.bank_account),
                joinedload(Payment.linked_payments).joinedload(Payment.bill).joinedload(Bill.customer),
            )
        )
        out = payment_to_out(payment or p, bill, include_linked=True)
        return out, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.post("/payments/{payment_id}/void", response_model=PaymentOut)
def void_payment_endpoint(
    payment_id: int,
    expected_bill_version: int | None = Header(None, alias=EXPECTED_BILL_VERSION_HEADER),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
    db: Session = Depends(get_db),
    user: User = Depends(require_void_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    verify_void_authorization(void_password, user)
    route_key = f"POST /api/payments/{payment_id}/void"
    request_hash = hash_empty_body()

    def execute():
        try:
            p = void_payment(db, payment_id, expected_version=expected_bill_version, actor=user)
        except ValueError as e:
            raise http_exception_for_value_error(e) from e
        bill = db.scalar(
            select(Bill)
            .where(Bill.id == p.bill_id)
            .options(joinedload(Bill.customer), joinedload(Bill.payments))
        )
        payment = db.scalar(
            select(Payment)
            .where(Payment.id == p.id)
            .options(
                joinedload(Payment.bill).joinedload(Bill.customer),
                joinedload(Payment.bank_account),
                joinedload(Payment.linked_payments).joinedload(Payment.bill).joinedload(Bill.customer),
            )
        )
        out = payment_to_out(payment or p, bill, include_linked=True)
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)
