"""Linked activity counts for an inventory row (product/brand/location/bag tuple)."""
from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    BagChange,
    BagChangeToLine,
    Bill,
    BillLine,
    BillStatus,
    BillType,
    DeliveryStatus,
    FulfillmentEntry,
    Inventory,
    ProcessingBatch,
    ProcessingInputLine,
    ProcessingJob,
    ProductTransfer,
    StockDisposal,
)


def inventory_usage_links(db: Session, inv: Inventory) -> list[dict[str, str | int]]:
    pid, bid, lid, btid = inv.product_id, inv.brand_id, inv.location_id, inv.bag_type_id

    sales_lines = db.scalar(
        select(func.count(BillLine.id))
        .join(Bill, Bill.id == BillLine.bill_id)
        .where(
            Bill.status == BillStatus.finalized,
            Bill.bill_type == BillType.sales,
            Bill.location_id == lid,
            BillLine.product_id == pid,
            BillLine.brand_id == bid,
            BillLine.bag_type_id == btid,
            Bill.order_delivery_status != DeliveryStatus.delivered,
        )
    ) or 0

    fulfillment = db.scalar(
        select(func.count(FulfillmentEntry.id))
        .join(BillLine, BillLine.id == FulfillmentEntry.bill_line_id)
        .join(Bill, Bill.id == BillLine.bill_id)
        .where(
            FulfillmentEntry.voided_at.is_(None),
            BillLine.product_id == pid,
            BillLine.brand_id == bid,
            BillLine.bag_type_id == btid,
            or_(
                FulfillmentEntry.location_id == lid,
                and_(FulfillmentEntry.location_id.is_(None), Bill.location_id == lid),
            ),
        )
    ) or 0

    bag_changes = db.scalar(
        select(func.count(func.distinct(BagChange.id)))
        .outerjoin(BagChangeToLine, BagChangeToLine.bag_change_id == BagChange.id)
        .where(
            BagChange.voided_at.is_(None),
            BagChange.location_id == lid,
            BagChange.product_id == pid,
            BagChange.brand_id == bid,
            or_(BagChange.from_bag_type_id == btid, BagChangeToLine.to_bag_type_id == btid),
        )
    ) or 0

    transfers = db.scalar(
        select(func.count(ProductTransfer.id)).where(
            ProductTransfer.voided_at.is_(None),
            ProductTransfer.product_id == pid,
            ProductTransfer.brand_id == bid,
            ProductTransfer.bag_type_id == btid,
            or_(ProductTransfer.from_location_id == lid, ProductTransfer.to_location_id == lid),
        )
    ) or 0

    disposals = db.scalar(
        select(func.count(StockDisposal.id)).where(
            StockDisposal.voided_at.is_(None),
            StockDisposal.location_id == lid,
            StockDisposal.product_id == pid,
            StockDisposal.brand_id == bid,
            StockDisposal.bag_type_id == btid,
        )
    ) or 0

    processing = db.scalar(
        select(func.count(ProcessingInputLine.id))
        .join(ProcessingBatch, ProcessingBatch.id == ProcessingInputLine.batch_id)
        .join(ProcessingJob, ProcessingJob.id == ProcessingBatch.job_id)
        .where(
            ProcessingInputLine.location_id == lid,
            ProcessingInputLine.bag_type_id == btid,
            ProcessingJob.input_product_id == pid,
            ProcessingJob.input_brand_id == bid,
        )
    ) or 0

    links: list[dict[str, str | int]] = [
        {
            "key": "sales_bills",
            "label": "Sales bills (undelivered)",
            "count": int(sales_lines),
            "hint": "Bill lines at this location still pending delivery",
        },
        {
            "key": "fulfillment",
            "label": "Fulfillment entries",
            "count": int(fulfillment),
            "hint": "Deliver/receive history for this stock tuple",
        },
        {
            "key": "bag_changes",
            "label": "Bag change operations",
            "count": int(bag_changes),
            "hint": "Repacking that touched this bag type here",
        },
        {
            "key": "transfers",
            "label": "Product transfers",
            "count": int(transfers),
            "hint": "Stock moved to or from this location",
        },
        {
            "key": "disposals",
            "label": "Stock disposals",
            "count": int(disposals),
            "hint": "Written-off quantity at this location",
        },
        {
            "key": "processing",
            "label": "Processing inputs",
            "count": int(processing),
            "hint": "Processing batches that consumed this stock",
        },
    ]
    return links
