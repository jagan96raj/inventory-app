"""DEV ONLY — DISABLED BY DEFAULT.

Clear all operational data; keep master records and users.

Removes: inventory, bills, payments, fulfillment, operations, processing, cash book.
Keeps: products, brands, locations, bag_types, customers, users, bank accounts,
expense categories.

Also resets customer credit/debit balances, bill number counters, and cash opening
balance to zero.

Blocked unless ALLOW_DESTRUCTIVE_SCRIPTS=true and DESTRUCTIVE_SCRIPT_CONFIRM=I_UNDERSTAND_DELETE_DATA
in .env, and DATABASE_URL points at localhost. Never enable on production.

Usage:
    cd backend
    python scripts/clear_transactional_data.py
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select, text, update

from app.database import SessionLocal
from app.core.destructive_guard import require_destructive_scripts_allowed
from app.models.entities import (
    BagChange,
    BagChangeToLine,
    BagType,
    BankAccount,
    Bill,
    BillLine,
    BillNumberCounter,
    BookSettings,
    Brand,
    CashBookEntry,
    Customer,
    ExpenseCategory,
    FulfillmentEntry,
    IdempotencyRecord,
    Inventory,
    Location,
    Payment,
    ProcessingBalanceReturnLine,
    ProcessingBatch,
    ProcessingInputLine,
    ProcessingJob,
    ProcessingOutputLine,
    Product,
    ProductTransfer,
    StockDisposal,
    User,
)

# Tables cleared in dependency order (children before parents).
DELETE_ORDER = [
    IdempotencyRecord,
    CashBookEntry,
    Payment,
    FulfillmentEntry,
    BillLine,
    Bill,
    Inventory,
    BagChangeToLine,
    BagChange,
    ProductTransfer,
    ProcessingInputLine,
    ProcessingOutputLine,
    ProcessingBalanceReturnLine,
    ProcessingBatch,
    ProcessingJob,
    StockDisposal,
]

KEEP_MODELS = [
    Product,
    Brand,
    Location,
    BagType,
    Customer,
    User,
    BankAccount,
    ExpenseCategory,
    BookSettings,
]


def clear_transactional_data(db) -> dict[str, int]:
    counts: dict[str, int] = {}

    # Self-referential payments / fulfillment: break links first (Postgres).
    db.execute(text("UPDATE payments SET linked_payment_id = NULL"))
    db.execute(text("UPDATE fulfillment_entries SET parent_entry_id = NULL"))
    db.flush()

    for model in DELETE_ORDER:
        name = model.__tablename__
        n = db.scalar(select(func.count()).select_from(model)) or 0
        if n:
            db.execute(delete(model))
        counts[name] = n

    customers_updated = db.execute(
        update(Customer).values(credit_balance=Decimal("0"), debit_balance=Decimal("0"))
    ).rowcount

    counters_reset = db.execute(update(BillNumberCounter).values(last_number=0)).rowcount

    from app.utils.time import business_today

    book_settings_reset = db.execute(
        update(BookSettings).values(
            cash_opening_balance=Decimal("0"),
            cash_opening_balance_at=business_today(),
        )
    ).rowcount

    db.commit()

    kept = {}
    for model in KEEP_MODELS:
        kept[model.__tablename__] = db.scalar(select(func.count()).select_from(model)) or 0

    return {
        "deleted": counts,
        "customers_reset": customers_updated,
        "counters_reset": counters_reset,
        "book_settings_reset": book_settings_reset,
        "kept": kept,
    }


def main() -> None:
    require_destructive_scripts_allowed("clear_transactional_data.py")
    db = SessionLocal()
    try:
        result = clear_transactional_data(db)
        print("Transactional data cleared. Master data kept.")
        print("\nDeleted rows:")
        for table, n in result["deleted"].items():
            if n:
                print(f"  {table}: {n}")
        print(f"\nCustomer balances reset: {result['customers_reset']}")
        print(f"Bill number counters reset: {result['counters_reset']}")
        print(f"Book settings cash opening reset: {result['book_settings_reset']}")
        print("\nKept:")
        for table, n in result["kept"].items():
            print(f"  {table}: {n}")
    except Exception as exc:
        db.rollback()
        print(f"Clear failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
