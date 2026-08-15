"""Spec v12.21 — accounts service (cash + bank balances, dashboard, customer statement)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    BankAccount,
    BankAccountKind,
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
from app.services.customer_search import apply_customer_search, sum_customer_balances


# ---------------------------------------------------------------------------
# Book settings
# ---------------------------------------------------------------------------


def get_book_settings(db: Session, company_id: int = 1) -> BookSettings:
    """Fetch (or auto-create) book settings for a company. Spec v17.0.3."""
    settings = db.scalar(
        select(BookSettings)
        .where(BookSettings.company_id == company_id)
        .options(
            joinedload(BookSettings.powder_product),
            joinedload(BookSettings.powder_brand),
            joinedload(BookSettings.powder_location),
            joinedload(BookSettings.powder_bag_type),
            joinedload(BookSettings.company),
        )
    )
    if settings is None:
        from app.utils.time import business_today

        settings = BookSettings(
            company_id=company_id,
            cash_opening_balance=Decimal("0"),
            cash_opening_balance_at=business_today(),
        )
        db.add(settings)
        db.commit()
        settings = db.scalar(
            select(BookSettings)
            .where(BookSettings.company_id == company_id)
            .options(
                joinedload(BookSettings.powder_product),
                joinedload(BookSettings.powder_brand),
                joinedload(BookSettings.powder_location),
                joinedload(BookSettings.powder_bag_type),
                joinedload(BookSettings.company),
            )
        )
        assert settings is not None
    return settings


def serialize_book_settings(settings: BookSettings) -> dict:
    # Company header for bill print — companies table is the single source of truth.
    company = getattr(settings, "company", None)
    if company is not None:
        company_name = company.name
        company_address_line = company.address_line
        company_address_line_2 = company.address_line_2
        company_district = company.district
        company_state = company.state
        company_pin_code = company.pin_code
        company_gstin = company.gstin
        company_phone = company.phone
    else:
        # Orphaned book_settings without a companies row — legacy column fallback only.
        company_name = settings.company_name
        company_address_line = settings.company_address_line
        company_address_line_2 = None
        company_district = None
        company_state = None
        company_pin_code = None
        company_gstin = None
        company_phone = settings.company_phone
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
        "company_name": company_name,
        "company_address_line": company_address_line,
        "company_address_line_2": company_address_line_2,
        "company_district": company_district,
        "company_state": company_state,
        "company_pin_code": company_pin_code,
        "company_gstin": company_gstin,
        "company_phone": company_phone,
    }


def update_book_settings(db: Session, company_id: int, updates: dict) -> BookSettings:
    from app.core.tenant import assert_entity_company
    from app.utils.time import business_today

    settings = get_book_settings(db, company_id)
    if "cash_opening_balance" in updates:
        cash_opening_balance = Decimal(updates["cash_opening_balance"])
        if cash_opening_balance < 0:
            raise ValueError("cash_opening_balance must be >= 0")
        settings.cash_opening_balance = cash_opening_balance
        settings.cash_opening_balance_at = business_today()
        # Spec v17.2.2 — keep Cash money-account opening aligned (Book Settings still the write UI).
        from app.services.bank_accounts import get_company_cash_account, seed_company_cash_account

        cash = get_company_cash_account(db, company_id)
        if cash is None:
            seed_company_cash_account(
                db,
                company_id,
                opening_balance=cash_opening_balance,
                opening_balance_at=settings.cash_opening_balance_at,
            )
        else:
            cash.opening_balance = cash_opening_balance
            cash.opening_balance_at = settings.cash_opening_balance_at
    for field, model, label in (
        ("powder_product_id", Product, "Product"),
        ("powder_brand_id", Brand, "Brand"),
        ("powder_location_id", Location, "Location"),
        ("powder_bag_type_id", BagType, "Bag type"),
    ):
        if field not in updates:
            continue
        value = updates[field]
        if value is not None:
            entity = db.get(model, value)
            assert_entity_company(entity, company_id, label)
        setattr(settings, field, value)
    # Legacy PATCH fields — write to companies (source of truth), not book_settings columns.
    header_keys = ("company_name", "company_address_line", "company_phone")
    if any(k in updates for k in header_keys):
        from app.models.entities import Company

        company = db.get(Company, company_id)
        if company is not None:
            if "company_name" in updates:
                value = updates["company_name"]
                if value is not None:
                    value = value.strip() or None
                if value:
                    company.name = value
            if "company_address_line" in updates:
                value = updates["company_address_line"]
                if value is not None:
                    value = value.strip() or None
                company.address_line = value
            if "company_phone" in updates:
                value = updates["company_phone"]
                if value is not None:
                    value = value.strip() or None
                company.phone = value
        else:
            # Orphaned tenant without a companies row — legacy column fallback only.
            for field in header_keys:
                if field not in updates:
                    continue
                value = updates[field]
                if value is not None:
                    value = value.strip() or None
                    if value == "":
                        value = None
                setattr(settings, field, value)

    db.commit()
    return get_book_settings(db, company_id)


# ---------------------------------------------------------------------------
# Money account balances (Spec v17.2.2 Phase 3)
# ---------------------------------------------------------------------------


def _payment_linked_to_account(account: BankAccount):
    return Payment.account_id == account.id


def _cash_book_source_linked(account: BankAccount):
    return CashBookEntry.source_account_id == account.id


def _cash_book_dest_linked(account: BankAccount):
    return CashBookEntry.dest_account_id == account.id


def get_account_balance(
    db: Session, account_id: int, *, company_id: int | None = None
) -> Decimal:
    """
    Balance for one money account (kind=cash|bank):

      opening_balance
      + sales payments linked to account
      − purchase payments linked to account
      + cash-book income (source)
      − cash-book expense (source)
      + transfer in (dest)
      − transfer out (source)

    Movements match ``account_id`` on payments and
    ``source_account_id`` / ``dest_account_id`` on cash-book entries.
    """
    account = db.get(BankAccount, account_id)
    if account is None:
        raise ValueError("Bank account not found")
    if company_id is not None and int(account.company_id) != int(company_id):
        raise ValueError("Bank account not found")

    opening = Decimal(account.opening_balance)
    scoped_company_id = int(account.company_id)
    linked_payment = _payment_linked_to_account(account)
    linked_source = _cash_book_source_linked(account)
    linked_dest = _cash_book_dest_linked(account)

    sales_in_expr = case(
        (and_(Bill.bill_type == BillType.sales, linked_payment), Payment.amount),
        else_=Decimal("0"),
    )
    purchase_out_expr = case(
        (and_(Bill.bill_type == BillType.purchase, linked_payment), Payment.amount),
        else_=Decimal("0"),
    )
    row = db.execute(
        select(
            func.coalesce(func.sum(sales_in_expr), 0),
            func.coalesce(func.sum(purchase_out_expr), 0),
        )
        .select_from(Payment)
        .join(Bill, Bill.id == Payment.bill_id)
        .where(Payment.voided_at.is_(None), Bill.company_id == scoped_company_id)
    ).one()
    sales_in = Decimal(str(row[0] or 0))
    purchase_out = Decimal(str(row[1] or 0))

    income_in_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.income,
                linked_source,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    expense_out_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.expense,
                linked_source,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    transfer_in_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.transfer,
                linked_dest,
            ),
            CashBookEntry.amount,
        ),
        else_=Decimal("0"),
    )
    transfer_out_expr = case(
        (
            and_(
                CashBookEntry.entry_type == CashBookEntryType.transfer,
                linked_source,
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
        ).where(
            CashBookEntry.voided_at.is_(None),
            CashBookEntry.company_id == scoped_company_id,
        )
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


def _ensure_company_cash_for_balance(db: Session, company_id: int) -> BankAccount:
    """
    Ensure Cash money-account exists and opening mirrors book_settings.

    Book Settings remains the cash-opening write path until Phase 4 UI moves
    onto the Cash account; syncing here keeps dashboard totals identical.
    """
    from app.services.bank_accounts import get_company_cash_account, seed_company_cash_account

    settings = get_book_settings(db, company_id)
    opening = Decimal(settings.cash_opening_balance)
    opening_at = settings.cash_opening_balance_at
    cash = get_company_cash_account(db, company_id)
    if cash is None:
        cash = seed_company_cash_account(
            db,
            company_id,
            opening_balance=opening,
            opening_balance_at=opening_at,
        )
        db.flush()
        return cash
    if Decimal(cash.opening_balance) != opening or cash.opening_balance_at != opening_at:
        cash.opening_balance = opening
        cash.opening_balance_at = opening_at
        db.flush()
    return cash


def get_cash_balance(db: Session, *, company_id: int = 1) -> Decimal:
    """Sum of balances for kind=cash accounts (one Cash row per company)."""
    _ensure_company_cash_for_balance(db, company_id)
    cash_accounts = list(
        db.scalars(
            select(BankAccount).where(
                BankAccount.company_id == company_id,
                BankAccount.kind == BankAccountKind.cash,
            )
        ).all()
    )
    total = sum(
        (get_account_balance(db, a.id, company_id=company_id) for a in cash_accounts),
        Decimal("0"),
    )
    return total.quantize(Decimal("0.01"))


def get_bank_account_balance(
    db: Session, bank_account_id: int, *, company_id: int | None = None
) -> Decimal:
    return get_account_balance(db, bank_account_id, company_id=company_id)


def list_bank_account_balances(
    db: Session, *, company_id: int = 1, include_inactive: bool = False
) -> list[tuple[BankAccount, Decimal]]:
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
    if not include_inactive:
        q = q.where(BankAccount.is_active.is_(True))
    banks = list(db.scalars(q).all())
    out: list[tuple[BankAccount, Decimal]] = []
    for bank in banks:
        out.append((bank, get_account_balance(db, bank.id, company_id=company_id)))
    return out


def get_total_bank_balance(db: Session, *, company_id: int = 1) -> Decimal:
    rows = list_bank_account_balances(db, company_id=company_id, include_inactive=True)
    total = sum((bal for _, bal in rows), Decimal("0"))
    return total.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Customer balances
# ---------------------------------------------------------------------------


def total_customer_credit(db: Session, *, company_id: int = 1) -> Decimal:
    credit, _ = sum_customer_balances(db, company_id=company_id)
    return credit


def total_customer_debit(db: Session, *, company_id: int = 1) -> Decimal:
    _, debit = sum_customer_balances(db, company_id=company_id)
    return debit


def get_accounts_summary(db: Session, *, company_id: int = 1, recent_limit: int = 10) -> dict:
    from app.services.cash_book import serialize_entry

    cash = get_cash_balance(db, company_id=company_id)
    bank_rows = list_bank_account_balances(db, company_id=company_id, include_inactive=True)
    total_bank = sum((b for _, b in bank_rows), Decimal("0")).quantize(Decimal("0.01"))
    total_money = (cash + total_bank).quantize(Decimal("0.01"))

    recent = db.scalars(
        select(CashBookEntry)
        .options(
            joinedload(CashBookEntry.category),
            joinedload(CashBookEntry.bill),
            joinedload(CashBookEntry.source_account),
            joinedload(CashBookEntry.dest_account),
        )
        .where(
            CashBookEntry.voided_at.is_(None),
            CashBookEntry.company_id == company_id,
        )
        .order_by(CashBookEntry.entry_date.desc(), CashBookEntry.id.desc())
        .limit(recent_limit)
    ).unique().all()

    return {
        "cash_balance": cash,
        "total_bank_balance": total_bank,
        "total_money": total_money,
        "total_customer_credit": total_customer_credit(db, company_id=company_id),
        "total_customer_debit": total_customer_debit(db, company_id=company_id),
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


def list_customer_balances_query(
    db: Session,
    *,
    company_id: int = 1,
    has_balance: str = "any",
    search: str | None = None,
):
    q = select(Customer).where(Customer.company_id == company_id).order_by(Customer.name)
    if has_balance == "positive":
        q = q.where((Customer.credit_balance > 0) | (Customer.debit_balance > 0))
    elif has_balance == "zero":
        q = q.where((Customer.credit_balance == 0) & (Customer.debit_balance == 0))
    if search and search.strip():
        q = apply_customer_search(q, search)
    return q


def customer_last_activity_at(
    db: Session, customer_id: int, *, company_id: int | None = None
) -> datetime | None:
    bill_filters = [Bill.customer_id == customer_id]
    payment_filters = [Bill.customer_id == customer_id, Payment.voided_at.is_(None)]
    if company_id is not None:
        bill_filters.append(Bill.company_id == company_id)
        payment_filters.append(Bill.company_id == company_id)
    bill_at = db.scalar(select(func.max(Bill.created_at)).where(*bill_filters))
    payment_at = db.scalar(
        select(func.max(Payment.paid_at))
        .select_from(Payment)
        .join(Bill, Bill.id == Payment.bill_id)
        .where(*payment_filters)
    )
    candidates = [d for d in (bill_at, payment_at) if d is not None]
    if not candidates:
        return None
    return max(candidates)


def customer_to_row(
    db: Session, customer: Customer, *, company_id: int | None = None
) -> dict:
    credit = Decimal(customer.credit_balance)
    debit = Decimal(customer.debit_balance)
    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "credit_balance": credit,
        "debit_balance": debit,
        "net_balance": (credit - debit).quantize(Decimal("0.01")),
        "last_activity_at": customer_last_activity_at(
            db, customer.id, company_id=company_id if company_id is not None else customer.company_id
        ),
    }


def get_customer_statement(
    db: Session,
    customer_id: int,
    *,
    company_id: int = 1,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> dict:
    customer = db.get(Customer, customer_id)
    if customer is None or int(customer.company_id) != int(company_id):
        raise ValueError("Customer not found")

    bills_q = (
        select(Bill)
        .where(Bill.customer_id == customer_id, Bill.company_id == company_id)
        .order_by(Bill.created_at.asc(), Bill.id.asc())
    )
    bills = list(db.scalars(bills_q).unique().all())
    payments_q = (
        select(Payment)
        .join(Bill, Bill.id == Payment.bill_id)
        .where(Bill.customer_id == customer_id, Bill.company_id == company_id)
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
            joinedload(CashBookEntry.source_account),
            joinedload(CashBookEntry.dest_account),
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
