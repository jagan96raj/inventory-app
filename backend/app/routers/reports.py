from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.core.auth import get_current_user
from app.core.permissions import Permission, require_permission
from app.core.tenant import company_id_for_user
from app.database import get_db
from app.models.entities import BillType, User
from app.schemas import DashboardBundleOut, FiscalYearSummaryOut
from app.services import reports
router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_permission(Permission.REPORTS_VIEW))],
)
def validate_year_month(year: int, month: int) -> None:
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="year must be between 2000 and 2100")
def parse_bill_type(bill_type: str) -> BillType:
    try:
        return BillType(bill_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bill_type must be sales or purchase") from exc
@router.get("/business-summary")
def business_summary(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_business_summary(db, year, month, company_id)


@router.get("/fiscal-year-summary", response_model=FiscalYearSummaryOut)
def fiscal_year_summary(
    start_year: int | None = Query(
        None,
        ge=2000,
        le=2100,
        description="FY start calendar year (e.g. 2025 → 1 Apr 2025–31 Mar 2026). Defaults from year/month.",
    ),
    year: int | None = Query(None, description="Optional calendar year to derive FY when start_year omitted"),
    month: int | None = Query(None, ge=1, le=12, description="Optional calendar month to derive FY"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_id = company_id_for_user(user)
    if start_year is None:
        if year is None or month is None:
            raise HTTPException(
                status_code=400,
                detail="Provide start_year, or both year and month to derive the fiscal year",
            )
        validate_year_month(year, month)
        start_year = reports.fiscal_year_start_year(year, month)
    return reports.get_fiscal_year_summary(db, start_year, company_id)


@router.get("/dashboard-bundle", response_model=DashboardBundleOut)
def dashboard_bundle(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    bill_type: str = Query("sales", pattern="^(sales|purchase)$"),
    group_by: str = Query("product_brand", pattern="^(product|product_brand)$"),
    customer_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_dashboard_bundle(
        db,
        year,
        month,
        parse_bill_type(bill_type),
        group_by,
        company_id,
        customer_id=customer_id,
    )
@router.get("/business-compare")
def business_compare(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_business_compare(db, year, month, company_id)
@router.get("/daily-bill-amounts")
def daily_bill_amounts(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_daily_bill_amounts(db, year, month, company_id)
@router.get("/by-product")
def bills_by_product(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    bill_type: str = Query("sales", pattern="^(sales|purchase)$"),
    group_by: str = Query("product_brand", pattern="^(product|product_brand)$"),
    customer_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_bills_by_product(
        db,
        year,
        month,
        parse_bill_type(bill_type),
        group_by,
        company_id,
        customer_id=customer_id,
    )
@router.get("/by-customer")
def bills_by_customer(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    bill_type: str = Query("sales", pattern="^(sales|purchase)$"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_bills_by_customer(db, year, month, parse_bill_type(bill_type), limit, company_id=company_id)
@router.get("/by-location")
def bills_by_location(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    bill_type: str = Query("sales", pattern="^(sales|purchase)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_bills_by_location(db, year, month, parse_bill_type(bill_type), company_id)
@router.get("/bills-export")
def bills_export(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    bill_type: str = Query("sales", pattern="^(sales|purchase)$"),
    group_by: str = Query("product_brand", pattern="^(product|product_brand)$"),
    customer_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    bt = parse_bill_type(bill_type)
    csv_text = reports.get_bills_export_csv(
        db, year, month, bt, group_by, company_id=company_id, customer_id=customer_id
    )
    filename = f"{bill_type}-{year}-{month:02d}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
@router.get("/sales-summary")
def sales_summary(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_sales_summary(db, year, month, company_id)
@router.get("/sales-by-product")
def sales_by_product(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    group_by: str = Query("product_brand", pattern="^(product|product_brand)$"),
    customer_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_sales_by_product(
        db, year, month, group_by, company_id, customer_id=customer_id
    )
@router.get("/sales-by-customer")
def sales_by_customer(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_sales_by_customer(db, year, month, limit, company_id=company_id)
@router.get("/sales-by-location")
def sales_by_location(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_sales_by_location(db, year, month, company_id)
@router.get("/sales-daily")
def sales_daily(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_sales_daily(db, year, month, company_id)
@router.get("/sales-compare")
def sales_compare(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_sales_compare(db, year, month, company_id)
@router.get("/sales-payment-breakdown")
def sales_payment_breakdown(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_sales_payment_breakdown(db, year, month, company_id)
@router.get("/sales-delivery-breakdown")
def sales_delivery_breakdown(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    return reports.get_sales_delivery_breakdown(db, year, month, company_id)
@router.get("/sales-export")
def sales_export(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    group_by: str = Query("product_brand", pattern="^(product|product_brand)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    validate_year_month(year, month)
    company_id = company_id_for_user(user)
    csv_text = reports.get_sales_export_csv(db, year, month, group_by, company_id=company_id)
    filename = f"sales-{year}-{month:02d}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
