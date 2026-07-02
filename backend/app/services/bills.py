from datetime import datetime, timezone

from decimal import Decimal



from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    Bill,
    BillLine,
    BillNumberCounter,
    BillStatus,
    BillType,
    Customer,
    DeliveryStatus,
    PaymentStatus,
    User,
)
from app.models.entities import BagType
from app.utils import calc_quantity_kg, delivery_status_from_qty


def _bill_number_prefix(bill_type: BillType) -> str:
    return "S" if bill_type == BillType.sales else "P"


def _format_bill_number(bill_type: BillType, seq: int) -> str:
    return f"{_bill_number_prefix(bill_type)}-{seq:06d}"


def _get_counter_for_update(db: Session, bill_type: BillType) -> BillNumberCounter:
    row = db.scalar(
        select(BillNumberCounter)
        .where(BillNumberCounter.bill_type == bill_type)
        .with_for_update()
    )
    if row:
        return row
    try:
        with db.begin_nested():
            row = BillNumberCounter(bill_type=bill_type, last_number=0)
            db.add(row)
            db.flush()
    except IntegrityError:
        pass
    row = db.scalar(
        select(BillNumberCounter)
        .where(BillNumberCounter.bill_type == bill_type)
        .with_for_update()
    )
    if not row:
        raise ValueError("Could not initialize bill number counter")
    return row


def preview_bill_number(db: Session, bill_type: BillType) -> str:
    """Read-only next number for UI preview (does not consume counter)."""
    row = db.scalar(select(BillNumberCounter).where(BillNumberCounter.bill_type == bill_type))
    next_seq = (row.last_number + 1) if row else 1
    return _format_bill_number(bill_type, next_seq)


def next_bill_number(db: Session, bill_type: BillType) -> str:
    """Allocate next bill number under row lock (Spec v12.7)."""
    counter = _get_counter_for_update(db, bill_type)
    counter.last_number += 1
    db.flush()
    return _format_bill_number(bill_type, counter.last_number)





ADJUSTMENT_NEGATIVE_MSG = "adjustment must be >= 0"
FINAL_PAYABLE_NEGATIVE_MSG = "Final payable cannot be negative"


def validate_adjustment_non_negative(adjustment: Decimal) -> None:
    if Decimal(adjustment) < 0:
        raise ValueError(ADJUSTMENT_NEGATIVE_MSG)


def validate_bill_final_payable(bill: Bill) -> None:
    if bill.grand_total < 0:
        raise ValueError(FINAL_PAYABLE_NEGATIVE_MSG)


def recalc_line(line: BillLine, bag_type: BagType) -> None:

    line.ordered_quantity_kg = calc_quantity_kg(bag_type, line.ordered_bags, line.ordered_loose_kg)

    line.line_total = (line.ordered_quantity_kg * line.rate_per_kg).quantize(Decimal("0.01"))





def recalc_bill_totals(db: Session, bill: Bill) -> None:
    """Write paths only (create/edit). Do not call from GET handlers.

    Sum line totals from DB rows only (avoids duplicate in-memory line collections).
    """

    db.flush()

    lines = db.scalars(

        select(BillLine).where(BillLine.bill_id == bill.id).options(joinedload(BillLine.bag_type))

    ).unique().all()

    subtotal = Decimal("0")

    for ln in lines:

        if ln.bag_type:

            recalc_line(ln, ln.bag_type)

        subtotal += ln.line_total

    bill.subtotal = subtotal

    bill.discount_amount = (subtotal * bill.discount_percent / Decimal("100")).quantize(Decimal("0.01"))

    validate_adjustment_non_negative(bill.adjustment)
    bill.grand_total = (
        subtotal - bill.discount_amount - Decimal(bill.adjustment)
    ).quantize(Decimal("0.01"))





def apply_customer_balance_on_submit(db: Session, bill: Bill) -> None:
    """
    Once per bill submit (§2.5): use grand_total (= final payable), not subtotal.
    Purchase → credit_balance only; sales → debit_balance only.
    """
    customer = db.get(Customer, bill.customer_id)
    if not customer:
        raise ValueError("Customer not found")

    amount = Decimal(bill.grand_total).quantize(Decimal("0.01"))
    if bill.bill_type == BillType.purchase:
        customer.credit_balance = (Decimal(customer.credit_balance) + amount).quantize(Decimal("0.01"))
    elif bill.bill_type == BillType.sales:
        customer.debit_balance = (Decimal(customer.debit_balance) + amount).quantize(Decimal("0.01"))
    else:
        raise ValueError(f"Unknown bill type: {bill.bill_type}")
    db.flush()


def _sum_paid(bill: Bill) -> Decimal:
    from app.services.payments import _sum_paid as sum_active_paid

    return sum_active_paid(bill)


def validate_edit_bill(bill: Bill, lines: list[BillLine]) -> None:
    """Blockers: ordered qty below net fulfilled; grand_total below amount paid."""
    from app.services.fulfillment import net_fulfilled_kg

    for line in lines:
        net = net_fulfilled_kg(line, bill.bill_type)
        if net > line.ordered_quantity_kg:
            raise ValueError(
                f"Cannot reduce qty below delivered ({net} kg) on line {line.id}; return first"
            )
    paid = _sum_paid(bill)
    validate_bill_final_payable(bill)
    if bill.grand_total < paid:
        raise ValueError("Final payable cannot be less than amount already paid")


def recalc_delivery_status_after_edit(db: Session, bill: Bill, lines: list[BillLine]) -> None:
    for line in lines:
        update_line_delivery_status(line, bill.bill_type)
    update_bill_delivery_status(db, bill)


def apply_balance_on_edit_replace(
    db: Session, customer: Customer, bill: Bill, previous_grand_total: Decimal
) -> None:
    """Replace this bill's contribution to customer balance (not double-add)."""
    old_amt = Decimal(previous_grand_total).quantize(Decimal("0.01"))
    new_amt = Decimal(bill.grand_total).quantize(Decimal("0.01"))
    if bill.bill_type == BillType.purchase:
        customer.credit_balance = (
            Decimal(customer.credit_balance) - old_amt + new_amt
        ).quantize(Decimal("0.01"))
    elif bill.bill_type == BillType.sales:
        customer.debit_balance = (
            Decimal(customer.debit_balance) - old_amt + new_amt
        ).quantize(Decimal("0.01"))
    else:
        raise ValueError(f"Unknown bill type: {bill.bill_type}")
    db.flush()


def update_line_delivery_status(line: BillLine, bill_type: BillType) -> None:

    if bill_type == BillType.sales:

        net = line.net_delivered_kg - line.net_returned_kg

    else:

        net = line.net_received_kg - line.net_returned_kg

    line.line_delivery_status = DeliveryStatus(delivery_status_from_qty(line.ordered_quantity_kg, net))





def update_bill_delivery_status(db: Session, bill: Bill) -> None:

    lines = db.scalars(select(BillLine).where(BillLine.bill_id == bill.id)).all()

    if not lines:

        bill.order_delivery_status = DeliveryStatus.not_delivered

        return

    statuses = {ln.line_delivery_status for ln in lines}

    if statuses == {DeliveryStatus.delivered}:

        bill.order_delivery_status = DeliveryStatus.delivered

    elif statuses == {DeliveryStatus.not_delivered}:

        bill.order_delivery_status = DeliveryStatus.not_delivered

    else:

        bill.order_delivery_status = DeliveryStatus.partial





def finalize_bill(db: Session, bill: Bill) -> Bill:
    """
    Finalize bill: grand_total = final payable, amount_paid = 0, Unpaid,
    customer balance once (§2.5), no inventory change. Caller must flush lines before this.
    """
    lines = db.scalars(select(BillLine).where(BillLine.bill_id == bill.id)).all()
    if not lines:
        raise ValueError("Bill must have at least one line")

    recalc_bill_totals(db, bill)
    validate_bill_final_payable(bill)

    bill.status = BillStatus.finalized
    bill.confirmed_at = datetime.now(timezone.utc)
    bill.use_balance = False
    bill.balance_applied_on_confirm = Decimal("0")
    bill.amount_paid = Decimal("0")
    bill.payment_status = PaymentStatus.unpaid
    for line in lines:
        line.line_delivery_status = DeliveryStatus.not_delivered
        line.net_delivered_kg = Decimal("0")
        line.net_received_kg = Decimal("0")
        line.net_returned_kg = Decimal("0")
    bill.order_delivery_status = DeliveryStatus.not_delivered

    apply_customer_balance_on_submit(db, bill)
    db.commit()
    db.refresh(bill)
    return bill





def load_bill(db: Session, bill_id: int) -> Bill | None:

    return db.scalar(

        select(Bill)

        .where(Bill.id == bill_id)

        .options(

            joinedload(Bill.lines).joinedload(BillLine.product),

            joinedload(Bill.lines).joinedload(BillLine.brand),

            joinedload(Bill.lines).joinedload(BillLine.bag_type),

            joinedload(Bill.customer),

            joinedload(Bill.location),

            joinedload(Bill.payments),

        )

    )





def bags_delivered_count(line: BillLine, bill_type: BillType) -> int:

    """Cumulative bags delivered/received minus returns (bagged lines only)."""

    if line.bag_type and line.bag_type.is_loose:

        return 0

    weight = line.bag_type.weight_per_bag_kg if line.bag_type else Decimal("0")

    if weight <= 0:

        return 0

    if bill_type == BillType.sales:

        net_kg = line.net_delivered_kg - line.net_returned_kg

    else:

        net_kg = line.net_received_kg - line.net_returned_kg

    if net_kg <= 0:

        return 0

    return int(net_kg / weight)


BILL_ALREADY_VOIDED_MSG = "Bill is already voided"
BILL_VOID_NOT_FINALIZED_MSG = "Only finalized bills can be voided"
BILL_VOID_HAS_PAYMENTS_MSG = "Cannot void bill: active payments exist. Void all payments first."
BILL_VOID_HAS_FULFILLMENT_MSG = (
    "Cannot void bill: fulfillment activity exists. Void all fulfillment entries first."
)
BILL_VOID_HAS_LINKED_CASHBOOK_MSG = (
    "Cannot void bill: active linked cash-book entries exist. Void or unlink them first."
)


def bill_void_blockers(db: Session, bill: Bill) -> list[str]:
    if bill.status == BillStatus.voided:
        return [BILL_ALREADY_VOIDED_MSG]
    if bill.status != BillStatus.finalized:
        return [BILL_VOID_NOT_FINALIZED_MSG]

    from app.models.entities import Payment
    from app.services.accounts import count_active_linked_entries
    from app.services.fulfillment import net_fulfilled_kg

    reasons: list[str] = []
    active_payments = db.scalar(
        select(func.count()).select_from(Payment).where(
            Payment.bill_id == bill.id,
            Payment.voided_at.is_(None),
        )
    ) or 0
    if active_payments > 0:
        reasons.append(BILL_VOID_HAS_PAYMENTS_MSG)

    lines = db.scalars(select(BillLine).where(BillLine.bill_id == bill.id)).all()
    for line in lines:
        if net_fulfilled_kg(line, bill.bill_type) > Decimal("0"):
            reasons.append(BILL_VOID_HAS_FULFILLMENT_MSG)
            break

    linked_count, _ = count_active_linked_entries(db, bill.id)
    if linked_count > 0:
        reasons.append(BILL_VOID_HAS_LINKED_CASHBOOK_MSG)

    return reasons


def reverse_customer_balance_on_void(db: Session, bill: Bill) -> None:
    customer = db.get(Customer, bill.customer_id)
    if not customer:
        raise ValueError("Customer not found")
    amount = Decimal(bill.grand_total).quantize(Decimal("0.01"))
    if bill.bill_type == BillType.purchase:
        customer.credit_balance = (Decimal(customer.credit_balance) - amount).quantize(Decimal("0.01"))
    elif bill.bill_type == BillType.sales:
        customer.debit_balance = (Decimal(customer.debit_balance) - amount).quantize(Decimal("0.01"))
    else:
        raise ValueError(f"Unknown bill type: {bill.bill_type}")
    db.flush()


def void_bill(
    db: Session,
    bill_id: int,
    *,
    expected_version: int | None,
    actor: User | None = None,
) -> Bill:
    from app.services.bill_concurrency import assert_bill_version, bump_bill_version
    from app.services.bill_lock import lock_bill_for_update

    locked = lock_bill_for_update(db, bill_id)
    if not locked:
        raise ValueError("Bill not found")
    assert_bill_version(locked, expected_version)
    bill = load_bill(db, bill_id)
    if not bill:
        raise ValueError("Bill not found")

    reasons = bill_void_blockers(db, bill)
    if reasons:
        raise ValueError(reasons[0])

    reverse_customer_balance_on_void(db, bill)
    bill.status = BillStatus.voided
    bill.voided_at = datetime.now(timezone.utc)
    bump_bill_version(bill)
    db.commit()
    db.refresh(bill)
    if actor is not None:
        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

        record_audit_event(
            db,
            user=actor,
            action=AuditAction.BILL_VOIDED,
            entity_type=AuditEntityType.BILL,
            entity_id=bill.id,
            entity_label=bill.bill_number,
            metadata={"bill_type": bill.bill_type.value},
        )
    return bill

