"""Spec v11 / v11.1 — dashboard bill-date aggregation."""
from __future__ import annotations
import csv
import io
from calendar import monthrange
from datetime import date
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.entities import (
    Bill,
    BillLine,
    BillStatus,
    BillType,
    Brand,
    Customer,
    DeliveryStatus,
    Location,
    PaymentStatus,
    Product,
)
MONEY_Q = Decimal("0.01")
KG_Q = Decimal("0.001")
def q_money(value: Decimal | float | int | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_Q)
def q_kg(value: Decimal | float | int | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(KG_Q)
def month_date_range(year: int, month: int) -> tuple[date, date]:
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)
def prev_year_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1
def pct_change(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous == 0:
        if current == 0:
            return q_money(0)
        return None
    return q_money((current - previous) / previous * 100)
def _bill_filters(year: int, month: int, bill_type: BillType, company_id: int = 1):
    start, end = month_date_range(year, month)
    return (
        Bill.company_id == company_id,
        Bill.bill_type == bill_type,
        Bill.status == BillStatus.finalized,
        Bill.bill_date >= start,
        Bill.bill_date <= end,
    )
def _month_bill_totals(db: Session, year: int, month: int, bill_type: BillType, company_id: int = 1) -> dict:
    """Bill-date totals for one bill type (v11.1 primary metrics)."""
    filters = _bill_filters(year, month, bill_type, company_id)
    row = db.execute(
        select(
            func.coalesce(func.sum(Bill.grand_total), 0),
            func.count(Bill.id),
        ).where(*filters)
    ).one()
    bill_amount = q_money(row[0])
    bill_count = int(row[1] or 0)
    qty_row = db.execute(
        select(func.coalesce(func.sum(BillLine.ordered_quantity_kg), 0))
        .select_from(BillLine)
        .join(Bill, BillLine.bill_id == Bill.id)
        .where(*filters)
    ).one()
    qty_ordered_kg = q_kg(qty_row[0])
    bags_row = db.execute(
        select(func.coalesce(func.sum(BillLine.ordered_bags), 0))
        .select_from(BillLine)
        .join(Bill, BillLine.bill_id == Bill.id)
        .where(*filters)
    ).one()
    bags_ordered = int(bags_row[0] or 0)
    return {
        "bill_amount": bill_amount,
        "bill_count": bill_count,
        "qty_ordered_kg": qty_ordered_kg,
        "bags_ordered": bags_ordered,
    }
def _month_sales_legacy_totals(db: Session, year: int, month: int, company_id: int = 1) -> dict:
    """Legacy v11 sales summary including collected/due (sales-summary endpoint only)."""
    start, end = month_date_range(year, month)
    row = db.execute(
        select(
            func.coalesce(func.sum(Bill.grand_total), 0),
            func.count(Bill.id),
            func.coalesce(func.sum(Bill.amount_paid), 0),
        ).where(
            Bill.company_id == company_id,
            Bill.bill_type == BillType.sales,
            Bill.status == BillStatus.finalized,
            Bill.bill_date >= start,
            Bill.bill_date <= end,
        )
    ).one()
    total_sales = q_money(row[0])
    bill_count = int(row[1] or 0)
    total_collected = q_money(row[2])
    qty_row = db.execute(
        select(func.coalesce(func.sum(BillLine.ordered_quantity_kg), 0))
        .select_from(BillLine)
        .join(Bill, BillLine.bill_id == Bill.id)
        .where(
            Bill.company_id == company_id,
            Bill.bill_type == BillType.sales,
            Bill.status == BillStatus.finalized,
            Bill.bill_date >= start,
            Bill.bill_date <= end,
        )
    ).one()
    total_quantity_kg = q_kg(qty_row[0])
    total_due = q_money(total_sales - total_collected)
    avg_bill_value = q_money(total_sales / bill_count) if bill_count else q_money(0)
    return {
        "total_sales": total_sales,
        "bill_count": bill_count,
        "total_quantity_kg": total_quantity_kg,
        "total_collected": total_collected,
        "total_due": total_due,
        "avg_bill_value": avg_bill_value,
    }
def get_business_summary(db: Session, year: int, month: int, company_id: int = 1) -> dict:
    sales = _month_bill_totals(db, year, month, BillType.sales, company_id)
    purchase = _month_bill_totals(db, year, month, BillType.purchase, company_id)
    return {
        "year": year,
        "month": month,
        "sales": sales,
        "purchase": purchase,
    }
def _business_compare_from_totals(
    cur_sales: dict,
    cur_purchase: dict,
    prev_sales: dict,
    prev_purchase: dict,
) -> dict:
    def bucket(sales: dict, purchase: dict) -> dict:
        return {
            "sales_bill_amount": sales["bill_amount"],
            "sales_qty_ordered_kg": sales["qty_ordered_kg"],
            "sales_bags_ordered": sales["bags_ordered"],
            "sales_bill_count": sales["bill_count"],
            "purchase_bill_amount": purchase["bill_amount"],
            "purchase_qty_ordered_kg": purchase["qty_ordered_kg"],
            "purchase_bags_ordered": purchase["bags_ordered"],
            "purchase_bill_count": purchase["bill_count"],
        }
    current = bucket(cur_sales, cur_purchase)
    previous = bucket(prev_sales, prev_purchase)
    return {
        "current": current,
        "previous": previous,
        "change_percent": {
            "sales_bill_amount": pct_change(current["sales_bill_amount"], previous["sales_bill_amount"]),
            "sales_qty_ordered_kg": pct_change(current["sales_qty_ordered_kg"], previous["sales_qty_ordered_kg"]),
            "sales_bags_ordered": pct_change(
                Decimal(current["sales_bags_ordered"]), Decimal(previous["sales_bags_ordered"])
            ),
            "sales_bill_count": pct_change(
                Decimal(current["sales_bill_count"]), Decimal(previous["sales_bill_count"])
            ),
            "purchase_bill_amount": pct_change(
                current["purchase_bill_amount"], previous["purchase_bill_amount"]
            ),
            "purchase_qty_ordered_kg": pct_change(
                current["purchase_qty_ordered_kg"], previous["purchase_qty_ordered_kg"]
            ),
            "purchase_bags_ordered": pct_change(
                Decimal(current["purchase_bags_ordered"]), Decimal(previous["purchase_bags_ordered"])
            ),
            "purchase_bill_count": pct_change(
                Decimal(current["purchase_bill_count"]), Decimal(previous["purchase_bill_count"])
            ),
        },
    }
def get_business_compare(db: Session, year: int, month: int, company_id: int = 1) -> dict:
    cur_sales = _month_bill_totals(db, year, month, BillType.sales, company_id)
    cur_purchase = _month_bill_totals(db, year, month, BillType.purchase, company_id)
    py, pm = prev_year_month(year, month)
    prev_sales = _month_bill_totals(db, py, pm, BillType.sales, company_id)
    prev_purchase = _month_bill_totals(db, py, pm, BillType.purchase, company_id)
    return _business_compare_from_totals(cur_sales, cur_purchase, prev_sales, prev_purchase)
def get_dashboard_bundle(
    db: Session,
    year: int,
    month: int,
    bill_type: BillType,
    group_by: str,
    company_id: int = 1,
) -> dict:
    cur_sales = _month_bill_totals(db, year, month, BillType.sales, company_id)
    cur_purchase = _month_bill_totals(db, year, month, BillType.purchase, company_id)
    summary = {
        "year": year,
        "month": month,
        "sales": cur_sales,
        "purchase": cur_purchase,
    }
    py, pm = prev_year_month(year, month)
    prev_sales = _month_bill_totals(db, py, pm, BillType.sales, company_id)
    prev_purchase = _month_bill_totals(db, py, pm, BillType.purchase, company_id)
    compare = _business_compare_from_totals(cur_sales, cur_purchase, prev_sales, prev_purchase)
    return {
        "summary": summary,
        "compare": compare,
        "daily": get_daily_bill_amounts(db, year, month, company_id),
        "by_product": get_bills_by_product(db, year, month, bill_type, group_by, company_id),
        "by_customer": get_bills_by_customer(db, year, month, bill_type, limit=10, company_id=company_id),
        "by_location": get_bills_by_location(db, year, month, bill_type, company_id),
    }
def get_sales_summary(db: Session, year: int, month: int, company_id: int = 1) -> dict:
    current = _month_sales_legacy_totals(db, year, month, company_id)
    py, pm = prev_year_month(year, month)
    prev = _month_sales_legacy_totals(db, py, pm, company_id)
    mom = pct_change(current["total_sales"], prev["total_sales"])
    return {
        **current,
        "prev_month_sales": prev["total_sales"],
        "mom_change_percent": mom,
    }
def get_sales_compare(db: Session, year: int, month: int, company_id: int = 1) -> dict:
    current = _month_sales_legacy_totals(db, year, month, company_id)
    py, pm = prev_year_month(year, month)
    previous = _month_sales_legacy_totals(db, py, pm, company_id)
    def bucket(data: dict) -> dict:
        return {
            "sales": data["total_sales"],
            "bills": data["bill_count"],
            "kg": data["total_quantity_kg"],
            "collected": data["total_collected"],
        }
    cur = bucket(current)
    prev = bucket(previous)
    return {
        "current": cur,
        "previous": prev,
        "change_percent": {
            "sales": pct_change(cur["sales"], prev["sales"]),
            "bills": pct_change(Decimal(cur["bills"]), Decimal(prev["bills"])),
            "kg": pct_change(cur["kg"], prev["kg"]),
            "collected": pct_change(cur["collected"], prev["collected"]),
        },
    }
def get_bills_by_product(
    db: Session, year: int, month: int, bill_type: BillType, group_by: str, company_id: int = 1
) -> dict:
    filters = _bill_filters(year, month, bill_type, company_id)
    lines_subtotal = q_money(
        db.execute(
            select(func.coalesce(func.sum(BillLine.line_total), 0))
            .select_from(BillLine)
            .join(Bill, BillLine.bill_id == Bill.id)
            .where(*filters)
        ).scalar_one()
    )
    bills_grand_total = q_money(
        db.execute(select(func.coalesce(func.sum(Bill.grand_total), 0)).where(*filters)).scalar_one()
    )
    if group_by == "product":
        stmt = (
            select(
                BillLine.product_id,
                Product.product_name,
                func.coalesce(func.sum(BillLine.ordered_quantity_kg), 0),
                func.coalesce(func.sum(BillLine.ordered_bags), 0),
                func.coalesce(func.sum(BillLine.line_total), 0),
            )
            .join(Bill, BillLine.bill_id == Bill.id)
            .join(Product, BillLine.product_id == Product.id)
            .where(*filters)
            .group_by(BillLine.product_id, Product.product_name)
            .order_by(func.sum(BillLine.line_total).desc())
        )
        rows_raw = db.execute(stmt).all()
        rows = []
        for product_id, product_name, qty, bags, amount in rows_raw:
            amount = q_money(amount)
            qty = q_kg(qty)
            share = q_money(amount / lines_subtotal * 100) if lines_subtotal else q_money(0)
            avg_rate = q_money(amount / qty) if qty else q_money(0)
            rows.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "brand_id": None,
                    "brand_name": None,
                    "quantity_kg": qty,
                    "bag_count": int(bags or 0),
                    "amount": amount,
                    "share_percent": share,
                    "avg_rate_per_kg": avg_rate,
                }
            )
    else:
        stmt = (
            select(
                BillLine.product_id,
                Product.product_name,
                BillLine.brand_id,
                Brand.name,
                func.coalesce(func.sum(BillLine.ordered_quantity_kg), 0),
                func.coalesce(func.sum(BillLine.ordered_bags), 0),
                func.coalesce(func.sum(BillLine.line_total), 0),
            )
            .join(Bill, BillLine.bill_id == Bill.id)
            .join(Product, BillLine.product_id == Product.id)
            .join(Brand, BillLine.brand_id == Brand.id)
            .where(*filters)
            .group_by(BillLine.product_id, Product.product_name, BillLine.brand_id, Brand.name)
            .order_by(func.sum(BillLine.line_total).desc())
        )
        rows_raw = db.execute(stmt).all()
        rows = []
        for product_id, product_name, brand_id, brand_name, qty, bags, amount in rows_raw:
            amount = q_money(amount)
            qty = q_kg(qty)
            share = q_money(amount / lines_subtotal * 100) if lines_subtotal else q_money(0)
            avg_rate = q_money(amount / qty) if qty else q_money(0)
            rows.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "brand_id": brand_id,
                    "brand_name": brand_name,
                    "quantity_kg": qty,
                    "bag_count": int(bags or 0),
                    "amount": amount,
                    "share_percent": share,
                    "avg_rate_per_kg": avg_rate,
                }
            )
    return {
        "rows": rows,
        "lines_subtotal": lines_subtotal,
        "bills_grand_total": bills_grand_total,
        "group_by": group_by,
        "bill_type": bill_type.value,
    }
def get_sales_by_product(db: Session, year: int, month: int, group_by: str, company_id: int = 1) -> dict:
    return get_bills_by_product(db, year, month, BillType.sales, group_by, company_id)
def get_bills_by_customer(
    db: Session, year: int, month: int, bill_type: BillType, limit: int = 10, *, company_id: int = 1
) -> dict:
    filters = _bill_filters(year, month, bill_type, company_id)
    bill_stmt = (
        select(
            Bill.customer_id,
            Customer.name,
            func.count(Bill.id),
            func.coalesce(func.sum(Bill.grand_total), 0),
        )
        .join(Customer, Bill.customer_id == Customer.id)
        .where(*filters)
        .group_by(Bill.customer_id, Customer.name)
        .order_by(func.sum(Bill.grand_total).desc())
        .limit(limit)
    )
    rows_raw = db.execute(bill_stmt).all()
    if not rows_raw:
        return {"rows": [], "total_amount": q_money(0), "bill_type": bill_type.value}
    customer_ids = [r[0] for r in rows_raw]
    qty_stmt = (
        select(
            Bill.customer_id,
            func.coalesce(func.sum(BillLine.ordered_quantity_kg), 0),
        )
        .join(Bill, BillLine.bill_id == Bill.id)
        .where(
            Bill.customer_id.in_(customer_ids),
            *filters,
        )
        .group_by(Bill.customer_id)
    )
    qty_map = {r[0]: q_kg(r[1]) for r in db.execute(qty_stmt).all()}
    total_amount = q_money(sum(q_money(r[3]) for r in rows_raw))
    rows = []
    for customer_id, customer_name, bill_count, amount in rows_raw:
        amount = q_money(amount)
        share = q_money(amount / total_amount * 100) if total_amount else q_money(0)
        rows.append(
            {
                "customer_id": customer_id,
                "customer_name": customer_name,
                "bill_count": int(bill_count or 0),
                "quantity_kg": qty_map.get(customer_id, q_kg(0)),
                "amount": amount,
                "share_percent": share,
            }
        )
    return {"rows": rows, "total_amount": total_amount, "bill_type": bill_type.value}
def get_sales_by_customer(db: Session, year: int, month: int, limit: int = 10, *, company_id: int = 1) -> dict:
    return get_bills_by_customer(db, year, month, BillType.sales, limit, company_id=company_id)
def get_bills_by_location(db: Session, year: int, month: int, bill_type: BillType, company_id: int = 1) -> dict:
    filters = _bill_filters(year, month, bill_type, company_id)
    bill_stmt = (
        select(
            Bill.location_id,
            Location.name,
            func.count(Bill.id),
            func.coalesce(func.sum(Bill.grand_total), 0),
        )
        .outerjoin(Location, Bill.location_id == Location.id)
        .where(*filters)
        .group_by(Bill.location_id, Location.name)
        .order_by(func.sum(Bill.grand_total).desc())
    )
    rows_raw = db.execute(bill_stmt).all()
    if not rows_raw:
        return {"rows": [], "bill_type": bill_type.value}
    location_ids = [r[0] for r in rows_raw if r[0] is not None]
    qty_map: dict[int | None, Decimal] = {}
    if location_ids:
        qty_stmt = (
            select(
                Bill.location_id,
                func.coalesce(func.sum(BillLine.ordered_quantity_kg), 0),
            )
            .join(Bill, BillLine.bill_id == Bill.id)
            .where(
                Bill.location_id.in_(location_ids),
                *filters,
            )
            .group_by(Bill.location_id)
        )
        qty_map = {r[0]: q_kg(r[1]) for r in db.execute(qty_stmt).all()}
    rows = []
    for location_id, location_name, bill_count, amount in rows_raw:
        rows.append(
            {
                "location_id": location_id,
                "location_name": location_name or "—",
                "bill_count": int(bill_count or 0),
                "quantity_kg": qty_map.get(location_id, q_kg(0)),
                "amount": q_money(amount),
            }
        )
    return {"rows": rows, "bill_type": bill_type.value}
def get_sales_by_location(db: Session, year: int, month: int, company_id: int = 1) -> dict:
    return get_bills_by_location(db, year, month, BillType.sales, company_id)
def get_daily_bill_amounts(db: Session, year: int, month: int, company_id: int = 1) -> dict:
    """Sales + purchase bill amounts per calendar day (v11.1 daily chart)."""
    start, end = month_date_range(year, month)
    last_day = monthrange(year, month)[1]
    def amounts_by_type(bill_type: BillType) -> dict[date, Decimal]:
        rows = db.execute(
            select(
                Bill.bill_date,
                func.coalesce(func.sum(Bill.grand_total), 0),
                func.count(Bill.id),
            )
            .where(
                Bill.company_id == company_id,
                Bill.bill_type == bill_type,
                Bill.status == BillStatus.finalized,
                Bill.bill_date >= start,
                Bill.bill_date <= end,
            )
            .group_by(Bill.bill_date)
        ).all()
        return {r[0]: {"amount": q_money(r[1]), "bill_count": int(r[2] or 0)} for r in rows}
    sales_by_date = amounts_by_type(BillType.sales)
    purchase_by_date = amounts_by_type(BillType.purchase)
    rows = []
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        s = sales_by_date.get(d, {"amount": q_money(0), "bill_count": 0})
        p = purchase_by_date.get(d, {"amount": q_money(0), "bill_count": 0})
        rows.append(
            {
                "day": day,
                "bill_date": d,
                "sales_amount": s["amount"],
                "purchase_amount": p["amount"],
                "sales_bill_count": s["bill_count"],
                "purchase_bill_count": p["bill_count"],
            }
        )
    return {"rows": rows}
def get_sales_daily(db: Session, year: int, month: int, company_id: int = 1) -> dict:
    """Legacy sales-only daily endpoint."""
    start, end = month_date_range(year, month)
    bill_rows = db.execute(
        select(
            Bill.bill_date,
            func.coalesce(func.sum(Bill.grand_total), 0),
            func.count(Bill.id),
        )
        .where(
            Bill.company_id == company_id,
            Bill.bill_type == BillType.sales,
            Bill.status == BillStatus.finalized,
            Bill.bill_date >= start,
            Bill.bill_date <= end,
        )
        .group_by(Bill.bill_date)
        .order_by(Bill.bill_date)
    ).all()
    qty_rows = db.execute(
        select(
            Bill.bill_date,
            func.coalesce(func.sum(BillLine.ordered_quantity_kg), 0),
        )
        .select_from(BillLine)
        .join(Bill, BillLine.bill_id == Bill.id)
        .where(
            Bill.company_id == company_id,
            Bill.bill_type == BillType.sales,
            Bill.status == BillStatus.finalized,
            Bill.bill_date >= start,
            Bill.bill_date <= end,
        )
        .group_by(Bill.bill_date)
    ).all()
    qty_by_date = {r[0]: q_kg(r[1]) for r in qty_rows}
    by_date = {
        r[0]: {"amount": q_money(r[1]), "bill_count": int(r[2] or 0), "quantity_kg": qty_by_date.get(r[0], q_kg(0))}
        for r in bill_rows
    }
    last_day = monthrange(year, month)[1]
    rows = []
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        data = by_date.get(d, {"amount": q_money(0), "bill_count": 0, "quantity_kg": q_kg(0)})
        rows.append(
            {
                "day": day,
                "bill_date": d,
                "amount": data["amount"],
                "bill_count": data["bill_count"],
                "quantity_kg": data["quantity_kg"],
            }
        )
    return {"rows": rows}
def _status_breakdown(db: Session, year: int, month: int, field, company_id: int = 1) -> dict:
    start, end = month_date_range(year, month)
    stmt = (
        select(
            field,
            func.count(Bill.id),
            func.coalesce(func.sum(Bill.grand_total), 0),
        )
        .where(
            Bill.company_id == company_id,
            Bill.bill_type == BillType.sales,
            Bill.status == BillStatus.finalized,
            Bill.bill_date >= start,
            Bill.bill_date <= end,
        )
        .group_by(field)
    )
    rows_raw = db.execute(stmt).all()
    result: dict[str, dict] = {}
    for status, count, amount in rows_raw:
        key = status.value if hasattr(status, "value") else str(status)
        result[key] = {"count": int(count or 0), "amount": q_money(amount)}
    return result
def get_sales_payment_breakdown(db: Session, year: int, month: int, company_id: int = 1) -> dict:
    raw = _status_breakdown(db, year, month, Bill.payment_status, company_id)
    return {
        "paid": raw.get(PaymentStatus.paid.value, {"count": 0, "amount": q_money(0)}),
        "partial": raw.get(PaymentStatus.partial.value, {"count": 0, "amount": q_money(0)}),
        "unpaid": raw.get(PaymentStatus.unpaid.value, {"count": 0, "amount": q_money(0)}),
    }
def get_sales_delivery_breakdown(db: Session, year: int, month: int, company_id: int = 1) -> dict:
    raw = _status_breakdown(db, year, month, Bill.order_delivery_status, company_id)
    return {
        "delivered": raw.get(DeliveryStatus.delivered.value, {"count": 0, "amount": q_money(0)}),
        "partial": raw.get(DeliveryStatus.partial.value, {"count": 0, "amount": q_money(0)}),
        "not_delivered": raw.get(DeliveryStatus.not_delivered.value, {"count": 0, "amount": q_money(0)}),
    }
def get_bills_export_csv(
    db: Session,
    year: int,
    month: int,
    bill_type: BillType,
    group_by: str = "product_brand",
    *,
    company_id: int = 1,
) -> str:
    data = get_bills_by_product(db, year, month, bill_type, group_by, company_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Product", "Brand", "Qty ordered (kg)", "Bags", "Line amount INR", "Share %", "Avg rate/kg"])
    for row in data["rows"]:
        writer.writerow(
            [
                row["product_name"],
                row.get("brand_name") or "",
                str(row["quantity_kg"]),
                row["bag_count"],
                str(row["amount"]),
                str(row["share_percent"]),
                str(row["avg_rate_per_kg"]),
            ]
        )
    return buf.getvalue()
def get_sales_export_csv(db: Session, year: int, month: int, group_by: str = "product_brand", *, company_id: int = 1) -> str:
    return get_bills_export_csv(
        db, year, month, BillType.sales, group_by, company_id=company_id
    )
