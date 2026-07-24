from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    BankAccount,
    BankAccountKind,
    Bill,
    BillStatus,
    BillType,
    Customer,
    Payment,
    PaymentMode,
    PaymentStatus,
    User,
)
from app.services.bill_lock import lock_bill_for_update, lock_bills_for_update
from app.services.bill_concurrency import (
    assert_bill_version,
    bump_bill_version,
    bump_bills_version,
)
from app.utils.time import resolve_business_entry, utc_now

PAYMENT_VOID_SETOFF_MSG = (
    "Void the primary payment instead; linked set-off payments will be voided automatically."
)
PAYMENT_ALREADY_VOIDED_MSG = "Payment already voided."


def _reduce_balance(balance: Decimal, amount: Decimal) -> Decimal:
    return max(balance - amount, Decimal("0"))


def _active_payments(bill: Bill) -> list[Payment]:
    return [p for p in bill.payments if getattr(p, "voided_at", None) is None]


def _sum_paid(bill: Bill) -> Decimal:
    return sum((p.amount for p in _active_payments(bill)), Decimal("0"))





def _bill_remaining_due(bill: Bill) -> Decimal:

    return bill.grand_total - _sum_paid(bill)





def opposite_bill_type(bill_type: BillType) -> BillType:

    return BillType.sales if bill_type == BillType.purchase else BillType.purchase





def opposite_bills_due_total(
    db: Session, customer_id: int, bill_type: BillType, company_id: int | None = None
) -> Decimal:

    """Sum remaining due on finalized opposite-type bills for the customer."""

    opposite = opposite_bill_type(bill_type)

    q = (

        select(Bill)

        .where(

            Bill.customer_id == customer_id,

            Bill.bill_type == opposite,

            Bill.status == BillStatus.finalized,

        )

        .options(joinedload(Bill.payments))

        .order_by(Bill.bill_date, Bill.id)

    )
    if company_id is not None:
        q = q.where(Bill.company_id == company_id)

    bills = db.scalars(q).unique().all()

    return sum(

        (due for bill in bills if (due := _bill_remaining_due(bill)) > 0),

        Decimal("0"),

    )





def load_opposite_bills_with_due(
    db: Session, customer_id: int, bill_type: BillType, company_id: int | None = None
) -> list[tuple[Bill, Decimal]]:

    """Opposite bills with due > 0, FIFO order (bill_date, id)."""

    opposite = opposite_bill_type(bill_type)

    q = (

        select(Bill)

        .where(

            Bill.customer_id == customer_id,

            Bill.bill_type == opposite,

            Bill.status == BillStatus.finalized,

        )

        .options(joinedload(Bill.payments))

        .order_by(Bill.bill_date, Bill.id)

    )
    if company_id is not None:
        q = q.where(Bill.company_id == company_id)

    bills = db.scalars(q).unique().all()

    out: list[tuple[Bill, Decimal]] = []

    for bill in bills:

        due = _bill_remaining_due(bill)

        if due > 0:

            out.append((bill, due))

    return out





def allocate_setoff_fifo(opposite_bills: list[tuple[Bill, Decimal]], amount: Decimal) -> list[tuple[int, Decimal]]:

    """FIFO allocate amount across opposite bills → list of (bill_id, slice_amount)."""

    remaining = amount

    allocations: list[tuple[int, Decimal]] = []

    for bill, due in opposite_bills:

        if remaining <= 0:

            break

        slice_amt = min(remaining, due)

        if slice_amt > 0:

            allocations.append((bill.id, slice_amt))

            remaining -= slice_amt

    return allocations





def update_bill_payment_status(bill: Bill) -> None:

    paid = _sum_paid(bill)

    bill.amount_paid = paid

    due = bill.grand_total - paid

    if due <= 0:

        bill.payment_status = PaymentStatus.paid

    elif paid <= 0:

        bill.payment_status = PaymentStatus.unpaid

    else:

        bill.payment_status = PaymentStatus.partial





def apply_payment_balance(db: Session, bill: Bill, payment: Payment) -> None:

    """

    §7.6 / v5.2: Purchase — always credit -= amount; Debit balance mode also debit -= amount.

    Sales — always debit -= amount; Credit balance mode also credit -= amount.

    Set-off rows are inventory-neutral on customer balances (linked to primary balance payment).

    """

    if payment.payment_mode == PaymentMode.setoff:

        return



    customer = bill.customer or db.get(Customer, bill.customer_id)

    if not customer:

        raise ValueError("Customer not found")

    amount = payment.amount

    mode = payment.payment_mode



    if bill.bill_type == BillType.purchase:

        if mode == PaymentMode.credit:

            raise ValueError("Credit balance mode is not valid on purchase bills")

        customer.credit_balance = _reduce_balance(customer.credit_balance, amount)

        if mode == PaymentMode.debit:

            customer.debit_balance = _reduce_balance(customer.debit_balance, amount)

    elif bill.bill_type == BillType.sales:

        if mode == PaymentMode.debit:

            raise ValueError("Debit balance mode is not valid on sales bills")

        customer.debit_balance = _reduce_balance(customer.debit_balance, amount)

        if mode == PaymentMode.credit:

            customer.credit_balance = _reduce_balance(customer.credit_balance, amount)

    else:

        raise ValueError("Unknown bill type")





def _is_balance_mode(bill_type: BillType, mode: PaymentMode) -> bool:

    return (bill_type == BillType.purchase and mode == PaymentMode.debit) or (

        bill_type == BillType.sales and mode == PaymentMode.credit

    )





def _balance_for_mode(bill_type: BillType, customer: Customer) -> Decimal:

    if bill_type == BillType.purchase:

        return customer.debit_balance

    return customer.credit_balance





def max_setoff_payment_amount(

    bill: Bill, customer: Customer, remaining_due: Decimal, opposite_due: Decimal

) -> Decimal:

    return min(_balance_for_mode(bill.bill_type, customer), remaining_due, opposite_due)





def preview_setoff_allocation(

    db: Session,
    bill_id: int,
    amount: Decimal,
    payment_mode: PaymentMode,
    company_id: int | None = None,

) -> dict:

    if payment_mode == PaymentMode.setoff:

        raise ValueError("Set-off is not a user-selectable payment mode")

    q = (
        select(Bill)
        .where(Bill.id == bill_id)
        .options(joinedload(Bill.payments), joinedload(Bill.customer))
    )
    if company_id is not None:
        q = q.where(Bill.company_id == company_id)

    bill = db.scalar(q)

    if not bill:

        raise ValueError("Bill not found")

    if bill.status != BillStatus.finalized:

        raise ValueError("Payments only on finalized bills")

    if not _is_balance_mode(bill.bill_type, payment_mode):

        raise ValueError("Set-off preview only applies to debit/credit balance modes")



    customer = bill.customer

    if not customer:

        raise ValueError("Customer not found")



    remaining = _bill_remaining_due(bill)

    opposite_due = opposite_bills_due_total(db, bill.customer_id, bill.bill_type, company_id=company_id)

    max_amount = max_setoff_payment_amount(bill, customer, remaining, opposite_due)



    opposite_bills = load_opposite_bills_with_due(
        db, bill.customer_id, bill.bill_type, company_id=company_id
    )

    effective_amount = min(amount, max_amount) if amount > 0 else max_amount

    allocations = allocate_setoff_fifo(opposite_bills, effective_amount)



    return {

        "bill_id": bill_id,

        "amount": effective_amount,

        "payment_mode": payment_mode,

        "opposite_due_total": opposite_due,

        "max_amount": max_amount,

        "allocations": [

            {"bill_id": bid, "bill_number": next(b.bill_number for b, _ in opposite_bills if b.id == bid), "amount": amt}

            for bid, amt in allocations

        ],

    }





PAYMENT_ACCOUNT_REQUIRED_MSG = "account_id is required for cash and bank payments"
PAYMENT_ACCOUNT_FORBIDDEN_MSG = "account_id is only allowed when payment_mode is cash or bank"
PAYMENT_ACCOUNT_INACTIVE_MSG = "Money account is inactive"
PAYMENT_ACCOUNT_NOT_FOUND_MSG = "Money account not found"
PAYMENT_ACCOUNT_KIND_MISMATCH_MSG = "account_id does not match payment_mode"


def _resolve_money_account_id(
    db: Session,
    payment_mode: PaymentMode,
    account_id: int | None,
    company_id: int | None = None,
) -> int | None:
    """Resolve account_id for cash|bank payments; None for credit/debit."""
    if payment_mode in (PaymentMode.cash, PaymentMode.bank):
        if account_id is None:
            if payment_mode == PaymentMode.cash and company_id is not None:
                from app.services.bank_accounts import require_company_cash_account

                return require_company_cash_account(db, company_id).id
            if payment_mode == PaymentMode.bank:
                q = select(BankAccount).where(
                    BankAccount.is_default.is_(True),
                    BankAccount.is_active.is_(True),
                    BankAccount.kind == BankAccountKind.bank,
                )
                if company_id is not None:
                    q = q.where(BankAccount.company_id == company_id)
                default_bank = db.scalar(q)
                if default_bank is None:
                    raise ValueError(PAYMENT_ACCOUNT_REQUIRED_MSG)
                return default_bank.id
            raise ValueError(PAYMENT_ACCOUNT_REQUIRED_MSG)
        q = select(BankAccount).where(BankAccount.id == account_id)
        if company_id is not None:
            q = q.where(BankAccount.company_id == company_id)
        account = db.scalar(q)
        if not account:
            raise ValueError(PAYMENT_ACCOUNT_NOT_FOUND_MSG)
        if not account.is_active:
            raise ValueError(PAYMENT_ACCOUNT_INACTIVE_MSG)
        expected = BankAccountKind.cash if payment_mode == PaymentMode.cash else BankAccountKind.bank
        if account.kind != expected:
            raise ValueError(PAYMENT_ACCOUNT_KIND_MISMATCH_MSG)
        return account.id
    if account_id is not None:
        raise ValueError(PAYMENT_ACCOUNT_FORBIDDEN_MSG)
    return None


def create_payment(
    db: Session, bill_id: int, amount: Decimal, payment_mode: PaymentMode,
    *, expected_version: int | None, account_id: int | None = None,
    paid_date: date | None = None,
    company_id: int | None = None,
) -> Payment:
    _, paid_at = resolve_business_entry(paid_date)

    if payment_mode == PaymentMode.setoff:

        raise ValueError("Set-off payments cannot be created directly")

    locked_bill = lock_bill_for_update(db, bill_id)
    if not locked_bill:
        raise ValueError("Bill not found")
    if company_id is not None and int(getattr(locked_bill, "company_id", company_id) or company_id) != int(company_id):
        raise ValueError("Bill not found")
    assert_bill_version(locked_bill, expected_version)

    q = (
        select(Bill)
        .where(Bill.id == bill_id)
        .options(joinedload(Bill.payments), joinedload(Bill.customer))
    )
    if company_id is not None:
        q = q.where(Bill.company_id == company_id)
    bill = db.scalar(q)

    if not bill:

        raise ValueError("Bill not found")

    money_company_id = int(getattr(bill, "company_id", None) or company_id or 1)
    resolved_account_id = _resolve_money_account_id(
        db, payment_mode, account_id, company_id=money_company_id
    )

    if bill.status != BillStatus.finalized:

        raise ValueError("Payments only on finalized bills")

    if amount <= 0:

        raise ValueError("Payment amount must be positive")



    paid_so_far = _sum_paid(bill)

    remaining = bill.grand_total - paid_so_far

    if amount > remaining:

        raise ValueError(f"Payment exceeds amount due ({remaining})")



    customer = bill.customer

    if not customer:

        raise ValueError("Customer not found")



    is_balance = _is_balance_mode(bill.bill_type, payment_mode)



    if bill.bill_type == BillType.purchase:

        if payment_mode == PaymentMode.credit:

            raise ValueError("Credit balance mode is not valid on purchase bills")

        if payment_mode == PaymentMode.debit:

            if customer.debit_balance <= 0:

                raise ValueError("Customer has no debit balance to apply")

            opposite_due = opposite_bills_due_total(
                db, bill.customer_id, bill.bill_type, company_id=company_id
            )

            if opposite_due <= 0:

                raise ValueError("No unpaid opposite bills available for set-off")

            max_amt = max_setoff_payment_amount(bill, customer, remaining, opposite_due)

            if amount > max_amt:

                raise ValueError(f"Payment exceeds allowed set-off amount ({max_amt})")

    elif bill.bill_type == BillType.sales:

        if payment_mode == PaymentMode.debit:

            raise ValueError("Debit balance mode is not valid on sales bills")

        if payment_mode == PaymentMode.credit:

            if customer.credit_balance <= 0:

                raise ValueError("Customer has no credit balance to apply")

            opposite_due = opposite_bills_due_total(
                db, bill.customer_id, bill.bill_type, company_id=company_id
            )

            if opposite_due <= 0:

                raise ValueError("No unpaid opposite bills available for set-off")

            max_amt = max_setoff_payment_amount(bill, customer, remaining, opposite_due)

            if amount > max_amt:

                raise ValueError(f"Payment exceeds allowed set-off amount ({max_amt})")

    else:

        raise ValueError("Unknown bill type")

    payment = Payment(
        bill_id=bill_id,
        amount=amount,
        payment_mode=payment_mode,
        account_id=resolved_account_id,
        paid_at=paid_at,
    )

    db.add(payment)

    db.flush()

    bill.payments.append(payment)

    apply_payment_balance(db, bill, payment)

    update_bill_payment_status(bill)



    opposite_bills_to_bump: list[Bill] = []

    if is_balance:

        opposite_bills = load_opposite_bills_with_due(
            db, bill.customer_id, bill.bill_type, company_id=company_id
        )
        lock_bills_for_update(db, [b.id for b, _ in opposite_bills])

        allocations = allocate_setoff_fifo(opposite_bills, amount)

        allocated_total = sum((amt for _, amt in allocations), Decimal("0"))

        if allocated_total != amount:

            raise ValueError("Set-off allocation could not cover the full payment amount")



        bill_by_id = {b.id: b for b, _ in opposite_bills}

        for opp_bill_id, slice_amt in allocations:

            opp_bill = bill_by_id.get(opp_bill_id) or db.scalar(

                select(Bill).where(Bill.id == opp_bill_id).options(joinedload(Bill.payments))

            )

            if not opp_bill:

                raise ValueError("Opposite bill not found for set-off")

            setoff = Payment(

                bill_id=opp_bill_id,

                amount=slice_amt,

                payment_mode=PaymentMode.setoff,

                paid_at=paid_at,

                linked_payment_id=payment.id,

            )

            db.add(setoff)

            db.flush()

            opp_bill.payments.append(setoff)

            apply_payment_balance(db, opp_bill, setoff)

            update_bill_payment_status(opp_bill)
            opposite_bills_to_bump.append(opp_bill)



    bump_bill_version(bill)
    bump_bills_version(opposite_bills_to_bump)
    db.commit()

    db.refresh(payment)

    return payment




def reverse_payment_balance(db: Session, bill: Bill, payment: Payment) -> None:
    """Mirror of apply_payment_balance — restore customer balances on void (primary only)."""
    if payment.payment_mode == PaymentMode.setoff:
        return

    customer = bill.customer or db.get(Customer, bill.customer_id)
    if not customer:
        raise ValueError("Customer not found")

    amount = payment.amount
    mode = payment.payment_mode

    if bill.bill_type == BillType.purchase:
        customer.credit_balance = (customer.credit_balance + amount).quantize(Decimal("0.01"))
        if mode == PaymentMode.debit:
            customer.debit_balance = (customer.debit_balance + amount).quantize(Decimal("0.01"))
    elif bill.bill_type == BillType.sales:
        customer.debit_balance = (customer.debit_balance + amount).quantize(Decimal("0.01"))
        if mode == PaymentMode.credit:
            customer.credit_balance = (customer.credit_balance + amount).quantize(Decimal("0.01"))
    else:
        raise ValueError("Unknown bill type")




def void_payment(
    db: Session,
    payment_id: int,
    *,
    expected_version: int | None,
    actor: User | None = None,
    company_id: int | None = None,
) -> Payment:
    payment = db.scalar(
        select(Payment)
        .where(Payment.id == payment_id)
        .options(
            joinedload(Payment.bill).joinedload(Bill.customer),
            joinedload(Payment.bill).joinedload(Bill.payments),
            joinedload(Payment.linked_payments).joinedload(Payment.bill).joinedload(Bill.payments),
        )
    )
    if not payment:
        raise ValueError("Payment not found")
    if company_id is not None:
        bill = payment.bill
        if bill is None or int(getattr(bill, "company_id", company_id) or company_id) != int(company_id):
            raise ValueError("Payment not found")
    if payment.voided_at is not None:
        raise ValueError(PAYMENT_ALREADY_VOIDED_MSG)
    if payment.payment_mode == PaymentMode.setoff or payment.linked_payment_id is not None:
        raise ValueError(PAYMENT_VOID_SETOFF_MSG)

    now = datetime.now(timezone.utc)
    affected_bill_ids: set[int] = set()
    primary_bill = payment.bill
    if not primary_bill:
        raise ValueError("Bill not found")
    affected_bill_ids.add(primary_bill.id)
    for child in payment.linked_payments or []:
        affected_bill_ids.add(child.bill_id)
    lock_bills_for_update(db, list(affected_bill_ids))
    primary_bill = db.get(Bill, primary_bill.id)
    if not primary_bill:
        raise ValueError("Bill not found")
    assert_bill_version(primary_bill, expected_version)

    for child in payment.linked_payments or []:
        if child.voided_at is not None:
            continue
        child.voided_at = now
        affected_bill_ids.add(child.bill_id)

    reverse_payment_balance(db, primary_bill, payment)
    payment.voided_at = now
    affected_bill_ids.add(payment.bill_id)

    for bill_id in affected_bill_ids:
        bill = db.scalar(
            select(Bill).where(Bill.id == bill_id).options(joinedload(Bill.payments))
        )
        if bill:
            update_bill_payment_status(bill)
            bump_bill_version(bill)

    db.commit()
    db.refresh(payment)
    if actor is not None:
        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        record_audit_event(
            db,
            user=actor,
            action=AuditAction.PAYMENT_VOIDED,
            entity_type=AuditEntityType.PAYMENT,
            entity_id=payment.id,
            entity_label=f"Payment #{payment.id}",
            metadata={"amount": str(payment.amount), "bill_id": payment.bill_id},
        )
    return payment

