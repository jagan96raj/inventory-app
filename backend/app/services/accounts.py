"""Spec v12.21 — accounts service (cash + bank balances, dashboard, customer statement)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    BankAccount,
    Bill,
    BillStatus,
    BillType,
    BagType,
    BookSettings,
    Brand,
    CashBookEntry,
    CashBookEntryType,
    CashBookSourceMode,
    Customer,
    Location,
    Payment,
    PaymentMode,
    Product,
)
from app.services.customer_search import apply_customer_search


# ---------------------------------------------------------------------------
# Book settings
# ---------------------------------------------------------------------------


def get_book_settings(db: Session) -> BookSettings:
    settings = db.scalar(
        select(BookSettings)
        .where(BookSettings.id == 1)
        .options(
            joinedload(BookSettings.powder_product),
            joinedload(BookSettings.powder_brand),
            joinedload(BookSettings.powder_location),
            joinedload(BookSettings.powder_bag_type),
        )
    )
    if settings is None:
        # auto-seed if missing (defensive — migration seeds it)
        from app.utils.time import business_today

        settings = BookSettings(
            id=1, cash_opening_balance=Decimal("0"), cash_opening_balance_at=business_today()
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def serialize_book_settings(settings: BookSettings) -> dict:
    return {
        "id": settings.id,
        "cash_opening_balance": settings.cash_opening_balance,
        "cash_opening_balance_at": settings.cash_opening_balance_at,
        "updated_at": settings.updated_at,
        "powder_product_id": settings.powder_product_id,
        "powder_product_name": settings.powder_product.product_name if settings.powder_product else None,
        "powder_brand_id": settings.powder_brand_id,
        "powder_brand_name": settings.powder_brand.name if settings.powder_brand else None,
        "powder_location_id": settings.powder_location_id,
        "powder_location_name": settings.powder_location.name if settings.powder_location else None,
        "powder_bag_type_id": settings.powder_bag_type_id,
        "powder_bag_type_name": settings.powder_bag_type.name if settings.powder_bag_type else None,
        "company_name": settings.company_name,
        "company_address_line": settings.company_address_line,
        "company_phone": settings.company_phone,
    }


def update_book_settings(db: Session, updates: dict) -> BookSettings:
    from app.utils.time import business_today

    settings = get_book_settings(db)
    if "cash_opening_balance" in updates:
        cash_opening_balance = Decimal(updates["cash_opening_balance"])
        if cash_opening_balance < 0:
            raise ValueError("cash_opening_balance must be >= 0")
        settings.cash_opening_balance = cash_opening_balance
        settings.cash_opening_balance_at = business_today()
    for field, model in (
        ("powder_product_id", Product),
        ("powder_brand_id", Brand),
        ("powder_location_id", Location),
        ("powder_bag_type_id", BagType),
    ):
        if field not in updates:
            continue
        value = updates[field]
        if value is not None and db.get(model, value) is None:
            raise ValueError(f"{field} not found")
        setattr(settings, field, value)
    for field in ("company_name", "company_address_line", "company_phone"):
        if field not in updates:
            continue
        value = updates[field]
        if value is not None:
            value = value.strip()
            if value == "":
                value = None
        setattr(settings, field, value)
    db.commit()
    return get_book_settings(db)


# ---------------------------------------------------------------------------
# Cash balance
# ---------------------------------------------------------------------------


def _payment_cash_delta_expr() -> tuple:
    """Returns (sales_in_expr, purchase_out_expr) for cash payments."""
    return (
        case(
            (
                and_(
                    Bill.bill_type == BillType.sales,
                    Payment.payment_mode == PaymentMode.cash,
                ),
                Payment.amount,
            ),
            else_=Decimal("0"),
        ),
        case(
            (
                and_(
                    Bill.bill_type == BillType.purchase,
                    Payment.payment_mode == PaymentMode.cash,
                ),
                Payment.amount,
            ),
            else_=Decimal("0"),
        ),
    )


def get_cash_balance(db: Session) -> Decimal:
    settings = get_book_settings(db)
    opening = Decimal(settings.cash_opening_balance)

    # bill payments (active only): sales cash adds, purchase cash subtracts
    sales_in_expr, purchase_out_expr = _payment_cash_delta_expr()
    row = db.execute(
        select(
            func.coalesce(func.sum(sales_in_expr), 0),
            func.coalesce(func.sum(purchase_out_expr), 0),
        )
        .select_from(Payment)
        .join(Bill, Bill.id == Payment.bill_id)
        .where(Payment.voided_at.is_(None))
    ).one()
    sales_in = Decimal(str(row[0] or 0))
    purchase_out = Decimal(str(row[1] or 0))

    # cash book entries
    income_in_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.income,
                CashBookEntry.source_payment_mode == CashBookSourceMode.cash,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    expense_out_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.expense,
                CashBookEntry.source_payment_mode == CashBookSourceMode.cash,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    transfer_in_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.transfer,
                CashBookEntry.dest_payment_mode == CashBookSourceMode.cash,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    transfer_out_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.transfer,
                CashBookEntry.source_payment_mode == CashBookSourceMode.cash,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    row2 = db.execute(
        select(
            func.coalesce(func.sum(income_in_expr), 0),
            func.coalesce(func.sum(expense_out_expr), 0),
            func.coalesce(func.sum(transfer_in_expr), 0),
            func.coalesce(func.sum(transfer_out_expr), 0),
        ).where(CashBookEntry.voided_at.is_(None))
    ).one()
    income_in = Decimal(str(row2[0] or 0))
    expense_out = Decimal(str(row2[1] or 0))
    transfer_in = Decimal(str(row2[2] or 0))
    transfer_out = Decimal(str(row2[3] or 0))

    total = (
        opening
        + sales_in
        - purchase_out
        + income_in
        - expense_out
        + transfer_in
        - transfer_out
    )
    return total.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Bank balances
# ---------------------------------------------------------------------------


def get_bank_account_balance(db: Session, bank_account_id: int) -> Decimal:
    bank = db.get(BankAccount, bank_account_id)
    if bank is None:
        raise ValueError("Bank account not found")
    opening = Decimal(bank.opening_balance)

    sales_in_expr = case(
        (
            and_(
                Bill.bill_type == BillType.sales,
                Payment.payment_mode == PaymentMode.bank,
                Payment.bank_account_id == bank_account_id,
            ),
            Payment.amount,
        ),
        else_=Decimal("0"),
    )
    purchase_out_expr = case(
        (
            and_(
                Bill.bill_type == BillType.purchase,
                Payment.payment_mode == PaymentMode.bank,
                Payment.bank_account_id == bank_account_id,
            ),
            Payment.amount,
        ),
        else_=Decimal("0"),
    )
    row = db.execute(
        select(
            func.coalesce(func.sum(sales_in_expr), 0),
            func.coalesce(func.sum(purchase_out_expr), 0),
        )
        .select_from(Payment)
        .join(Bill, Bill.id == Payment.bill_id)
        .where(Payment.voided_at.is_(None))
    ).one()
    sales_in = Decimal(str(row[0] or 0))
    purchase_out = Decimal(str(row[1] or 0))

    income_in_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.income,
                CashBookEntry.source_payment_mode == CashBookSourceMode.bank,
                CashBookEntry.source_bank_account_id == bank_account_id,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    expense_out_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.expense,
                CashBookEntry.source_payment_mode == CashBookSourceMode.bank,
                CashBookEntry.source_bank_account_id == bank_account_id,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    transfer_in_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.transfer,
                CashBookEntry.dest_payment_mode == CashBookSourceMode.bank,
                CashBookEntry.dest_bank_account_id == bank_account_id,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    transfer_out_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.transfer,
                CashBookEntry.source_payment_mode == CashBookSourceMode.bank,
                CashBookEntry.source_bank_account_id == bank_account_id,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    row2 = db.execute(
        select(
            func.coalesce(func.sum(income_in_expr), 0),
            func.coalesce(func.sum(expense_out_expr), 0),
            func.coalesce(func.sum(transfer_in_expr), 0),
            func.coalesce(func.sum(transfer_out_expr), 0),
        ).where(CashBookEntry.voided_at.is_(None))
    ).one()
    income_in = Decimal(str(row2[0] or 0))
    expense_out = Decimal(str(row2[1] or 0))
    transfer_in = Decimal(str(row2[2] or 0))
    transfer_out = Decimal(str(row2[3] or 0))

    total = (
        opening
        + sales_in
        - purchase_out
        + income_in
        - expense_out
        + transfer_in
        - transfer_out
    )
    return total.quantize(Decimal("0.01"))


def list_bank_account_balances(
    db: Session, *, include_inactive: bool = False
) -> list[tuple[BankAccount, Decimal]]:
    q = select(BankAccount).order_by(
        BankAccount.is_default.desc(), BankAccount.is_active.desc(), BankAccount.name
    )
    if not include_inactive:
        q = q.where(BankAccount.is_active.is_(True))
    banks = list(db.scalars(q).all())
    out: list[tuple[BankAccount, Decimal]] = []
    for bank in banks:
        out.append((bank, get_bank_account_balance(db, bank.id)))
    return out


def get_total_bank_balance(db: Session) -> Decimal:
    rows = list_bank_account_balances(db, include_inactive=True)
    total = sum((bal for _, bal in rows), Decimal("0"))
    return total.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Customer balances
# ---------------------------------------------------------------------------


def total_customer_credit(db: Session) -> Decimal:
    val = db.scalar(select(func.coalesce(func.sum(Customer.credit_balance), 0))) or 0
    return Decimal(str(val)).quantize(Decimal("0.01"))


def total_customer_debit(db: Session) -> Decimal:
    val = db.scalar(select(func.coalesce(func.sum(Customer.debit_balance), 0))) or 0
    return Decimal(str(val)).quantize(Decimal("0.01"))


def get_accounts_summary(db: Session, *, recent_limit: int = 10) -> dict:
    from app.services.cash_book import serialize_entry

    cash = get_cash_balance(db)
    bank_rows = list_bank_account_balances(db, include_inactive=True)
    total_bank = sum((b for _, b in bank_rows), Decimal("0")).quantize(Decimal("0.01"))
    total_money = (cash + total_bank).quantize(Decimal("0.01"))

    recent = db.scalars(
        select(CashBookEntry)
        .options(
            joinedload(CashBookEntry.category),
            joinedload(CashBookEntry.bill),
            joinedload(CashBookEntry.source_bank_account),
            joinedload(CashBookEntry.dest_bank_account),
        )
        .where(CashBookEntry.voided_at.is_(None))
        .order_by(CashBookEntry.entry_date.desc(), CashBookEntry.id.desc())
        .limit(recent_limit)
    ).unique().all()

    return {
        "cash_balance": cash,
        "total_bank_balance": total_bank,
        "total_money": total_money,
        "total_customer_credit": total_customer_credit(db),
        "total_customer_debit": total_customer_debit(db),
        "bank_accounts": [
            {
                "id": bank.id,
                "name": bank.name,
                "account_number_last4": bank.account_number_last4,
                "ifsc": bank.ifsc,
                "opening_balance": bank.opening_balance,
                "opening_balance_at": bank.opening_balance_at,
                "is_default": bank.is_default,
                "is_active": bank.is_active,
                "created_at": bank.created_at,
                "balance": balance,
            }
            for bank, balance in bank_rows
        ],
        "recent_entries": [serialize_entry(e) for e in recent],
    }


# ---------------------------------------------------------------------------
# Customers list + statement
# ---------------------------------------------------------------------------


def list_customer_balances_query(db: Session, *, has_balance: str = "any", search: str | None = None):
    q = select(Customer).order_by(Customer.name)
    if has_balance == "positive":
        q = q.where((Customer.credit_balance > 0) | (Customer.debit_balance > 0))
    elif has_balance == "zero":
        q = q.where((Customer.credit_balance == 0) & (Customer.debit_balance == 0))
    if search and search.strip():
        q = apply_customer_search(q, search)
    return q


def customer_last_activity_at(db: Session, customer_id: int) -> datetime | None:
    bill_at = db.scalar(
        select(func.max(Bill.created_at)).where(Bill.customer_id == customer_id)
    )
    payment_at = db.scalar(
        select(func.max(Payment.paid_at))
        .select_from(Payment)
        .join(Bill, Bill.id == Payment.bill_id)
        .where(Bill.customer_id == customer_id, Payment.voided_at.is_(None))
    )
    candidates = [d for d in (bill_at, payment_at) if d is not None]
    if not candidates:
        return None
    return max(candidates)


def customer_to_row(db: Session, customer: Customer) -> dict:
    credit = Decimal(customer.credit_balance)
    debit = Decimal(customer.debit_balance)
    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "credit_balance": credit,
        "debit_balance": debit,
        "net_balance": (credit - debit).quantize(Decimal("0.01")),
        "last_activity_at": customer_last_activity_at(db, customer.id),
    }


def get_customer_statement(
    db: Session,
    customer_id: int,
    *,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> dict:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ValueError("Customer not found")

    bills_q = (
        select(Bill)
        .where(Bill.customer_id == customer_id)
        .order_by(Bill.created_at.asc(), Bill.id.asc())
    )
    bills = list(db.scalars(bills_q).unique().all())
    payments_q = (
        select(Payment)
        .join(Bill, Bill.id == Payment.bill_id)
        .where(Bill.customer_id == customer_id)
        .order_by(Payment.paid_at.asc(), Payment.id.asc())
    )
    payments = list(db.scalars(payments_q).unique().all())

    events: list[dict] = []

    for bill in bills:
        is_sales = bill.bill_type == BillType.sales
        debit = Decimal(bill.grand_total) if is_sales else Decimal("0")
        credit = Decimal(bill.grand_total) if not is_sales else Decimal("0")
        events.append(
            {
                "event_at": bill.created_at,
                "event_date": bill.bill_date,
                "kind": "bill_created",
                "description": f"{bill.bill_type.value.capitalize()} bill {bill.bill_number}",
                "bill_id": bill.id,
                "bill_number": bill.bill_number,
                "payment_id": None,
                "debit_amount": debit,
                "credit_amount": credit,
            }
        )
        if bill.status == BillStatus.voided and bill.voided_at is not None:
            events.append(
                {
                    "event_at": bill.voided_at,
                    "event_date": bill.voided_at.date(),
                    "kind": "bill_voided",
                    "description": f"Voided {bill.bill_type.value} bill {bill.bill_number}",
                    "bill_id": bill.id,
                    "bill_number": bill.bill_number,
                    "payment_id": None,
                    "debit_amount": Decimal("0") if is_sales else Decimal(bill.grand_total),
                    "credit_amount": Decimal(bill.grand_total) if is_sales else Decimal("0"),
                }
            )

    for payment in payments:
        bill = next((b for b in bills if b.id == payment.bill_id), None)
        if bill is None:
            continue
        kind = "payment_received" if payment.payment_mode != PaymentMode.setoff else "setoff"
        if payment.voided_at is not None:
            kind = "payment_voided"
        # for the running balance, an active payment on a sales bill reduces the debit, etc.
        is_sales = bill.bill_type == BillType.sales
        if payment.voided_at is None:
            # active payment: reduces what customer owes (on sales: credit; on purchase: debit)
            debit = Decimal("0") if is_sales else Decimal(payment.amount)
            credit = Decimal(payment.amount) if is_sales else Decimal("0")
        else:
            # voided payment: reverses
            debit = Decimal(payment.amount) if is_sales else Decimal("0")
            credit = Decimal("0") if is_sales else Decimal(payment.amount)
        events.append(
            {
                "event_at": payment.paid_at if payment.voided_at is None else payment.voided_at,
                "event_date": (payment.paid_at if payment.voided_at is None else payment.voided_at).date(),
                "kind": kind,
                "description": f"{payment.payment_mode.value.capitalize()} payment on {bill.bill_number}",
                "bill_id": bill.id,
                "bill_number": bill.bill_number,
                "payment_id": payment.id,
                "debit_amount": debit,
                "credit_amount": credit,
            }
        )

    events.sort(key=lambda r: (r["event_at"], r["bill_id"] or 0, r["payment_id"] or 0))
    running = Decimal("0")
    for ev in events:
        running = running + Decimal(ev["debit_amount"]) - Decimal(ev["credit_amount"])
        ev["running_balance"] = running.quantize(Decimal("0.01"))

    if date_from is not None:
        events = [e for e in events if e["event_date"] >= date_from]
    if date_to is not None:
        events = [e for e in events if e["event_date"] <= date_to]

    total = len(events)
    page = events[offset : offset + limit]
    credit_bal = Decimal(customer.credit_balance)
    debit_bal = Decimal(customer.debit_balance)
    return {
        "items": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "customer_id": customer.id,
        "customer_name": customer.name,
        "current_credit_balance": credit_bal,
        "current_debit_balance": debit_bal,
        "current_net_balance": (debit_bal - credit_bal).quantize(Decimal("0.01")),
    }


# ---------------------------------------------------------------------------
# Bill ⇄ cash book linkage helpers
# ---------------------------------------------------------------------------


def list_linked_cash_book_entries_query(db: Session, bill_id: int):
    return (
        select(CashBookEntry)
        .options(
            joinedload(CashBookEntry.category),
            joinedload(CashBookEntry.bill),
            joinedload(CashBookEntry.source_bank_account),
            joinedload(CashBookEntry.dest_bank_account),
        )
        .where(CashBookEntry.bill_id == bill_id)
        .order_by(CashBookEntry.entry_date.desc(), CashBookEntry.id.desc())
    )


def count_active_linked_entries(db: Session, bill_id: int) -> tuple[int, Decimal]:
    count = db.scalar(
        select(func.count(CashBookEntry.id)).where(
            CashBookEntry.bill_id == bill_id, CashBookEntry.voided_at.is_(None)
        )
    ) or 0
    total = db.scalar(
        select(func.coalesce(func.sum(CashBookEntry.amount), 0)).where(
            CashBookEntry.bill_id == bill_id, CashBookEntry.voided_at.is_(None)
        )
    ) or 0
    return int(count), Decimal(str(total))
