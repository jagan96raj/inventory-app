"""Spec v12.2 — master delete reference guards."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    BagChange,
    BagChangeToLine,
    BagType,
    Bill,
    BillLine,
    Brand,
    Customer,
    FulfillmentEntry,
    Inventory,
    Location,
    ProcessingBalanceReturnLine,
    ProcessingInputLine,
    ProcessingJob,
    ProcessingOutputLine,
    Product,
    ProductTransfer,
    StockDisposal,
)


def _exists(db: Session, stmt) -> bool:
    return db.scalar(stmt.limit(1)) is not None


def assert_customer_deletable(db: Session, customer: Customer) -> None:
    if customer.credit_balance > 0 or customer.debit_balance > 0:
        raise ValueError("Cannot delete customer with non-zero balance")
    bill_count = db.scalar(select(func.count(Bill.id)).where(Bill.customer_id == customer.id)) or 0
    if bill_count > 0:
        raise ValueError(f"Cannot delete customer: used on {bill_count} bill(s)")


def assert_product_deletable(db: Session, product: Product) -> None:
    pid = product.id
    if _exists(db, select(Inventory).where(Inventory.product_id == pid)):
        raise ValueError("Product in use (inventory)")
    if _exists(db, select(BillLine).where(BillLine.product_id == pid)):
        raise ValueError("Product in use (bills)")
    if _exists(db, select(ProcessingJob).where(ProcessingJob.input_product_id == pid)):
        raise ValueError("Product in use (processing)")
    if _exists(db, select(ProductTransfer).where(ProductTransfer.product_id == pid)):
        raise ValueError("Product in use (transfers)")
    if _exists(db, select(StockDisposal).where(StockDisposal.product_id == pid)):
        raise ValueError("Product in use (stock disposal)")
    if _exists(db, select(BagChange).where(BagChange.product_id == pid)):
        raise ValueError("Product in use (bag change)")


def assert_brand_deletable(db: Session, brand: Brand) -> None:
    bid = brand.id
    if _exists(db, select(Inventory).where(Inventory.brand_id == bid)):
        raise ValueError("Brand in use (inventory)")
    if _exists(db, select(BillLine).where(BillLine.brand_id == bid)):
        raise ValueError("Brand in use (bills)")
    if _exists(db, select(ProcessingJob).where(ProcessingJob.input_brand_id == bid)):
        raise ValueError("Brand in use (processing)")
    if _exists(db, select(ProcessingOutputLine).where(ProcessingOutputLine.brand_id == bid)):
        raise ValueError("Brand in use (processing)")
    if _exists(db, select(ProductTransfer).where(ProductTransfer.brand_id == bid)):
        raise ValueError("Brand in use (transfers)")
    if _exists(db, select(StockDisposal).where(StockDisposal.brand_id == bid)):
        raise ValueError("Brand in use (stock disposal)")
    if _exists(db, select(BagChange).where(BagChange.brand_id == bid)):
        raise ValueError("Brand in use (bag change)")


def assert_location_deletable(db: Session, location: Location) -> None:
    lid = location.id
    if _exists(db, select(Inventory).where(Inventory.location_id == lid)):
        raise ValueError("Location in use (inventory)")
    if _exists(db, select(Bill).where(Bill.location_id == lid)):
        raise ValueError("Location in use (bills)")
    if _exists(db, select(FulfillmentEntry).where(FulfillmentEntry.location_id == lid)):
        raise ValueError("Location in use (fulfillment)")
    if _exists(
        db,
        select(ProductTransfer).where(
            or_(ProductTransfer.from_location_id == lid, ProductTransfer.to_location_id == lid)
        ),
    ):
        raise ValueError("Location in use (transfers)")
    if _exists(db, select(StockDisposal).where(StockDisposal.location_id == lid)):
        raise ValueError("Location in use (stock disposal)")
    if _exists(db, select(BagChange).where(BagChange.location_id == lid)):
        raise ValueError("Location in use (bag change)")
    if _exists(db, select(ProcessingInputLine).where(ProcessingInputLine.location_id == lid)):
        raise ValueError("Location in use (processing)")
    if _exists(db, select(ProcessingOutputLine).where(ProcessingOutputLine.location_id == lid)):
        raise ValueError("Location in use (processing)")
    if _exists(db, select(ProcessingBalanceReturnLine).where(ProcessingBalanceReturnLine.location_id == lid)):
        raise ValueError("Location in use (processing)")


def assert_bag_type_deletable(db: Session, bag_type: BagType) -> None:
    btid = bag_type.id
    if _exists(db, select(Inventory).where(Inventory.bag_type_id == btid)):
        raise ValueError("Bag type in use (inventory)")
    if _exists(db, select(BillLine).where(BillLine.bag_type_id == btid)):
        raise ValueError("Bag type in use (bills)")
    if _exists(db, select(ProcessingInputLine).where(ProcessingInputLine.bag_type_id == btid)):
        raise ValueError("Bag type in use (processing)")
    if _exists(db, select(ProcessingOutputLine).where(ProcessingOutputLine.bag_type_id == btid)):
        raise ValueError("Bag type in use (processing)")
    if _exists(db, select(ProcessingBalanceReturnLine).where(ProcessingBalanceReturnLine.bag_type_id == btid)):
        raise ValueError("Bag type in use (processing)")
    if _exists(db, select(BagChange).where(BagChange.from_bag_type_id == btid)):
        raise ValueError("Bag type in use (bag change)")
    if _exists(db, select(BagChangeToLine).where(BagChangeToLine.to_bag_type_id == btid)):
        raise ValueError("Bag type in use (bag change)")
    if _exists(db, select(ProductTransfer).where(ProductTransfer.bag_type_id == btid)):
        raise ValueError("Bag type in use (transfers)")
    if _exists(db, select(StockDisposal).where(StockDisposal.bag_type_id == btid)):
        raise ValueError("Bag type in use (stock disposal)")
