from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.auth import get_current_user
from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict, paginate_select
from app.core.permissions import Permission, require_permission
from app.core.tenant import company_id_for_user, require_entity_company, require_for_company, scope_query
from app.core.void_auth import VOID_AUTH_HEADER, verify_void_authorization
from app.database import get_db
from app.models.entities import BagType, Brand, Customer, Inventory, InventoryOwnerType, Location, Product, User
from app.services.idempotency import hash_pydantic_body
from app.services.inventory_usage import inventory_usage_links
from app.schemas import InventoryCreate, InventoryOut, InventoryPageOut, InventoryUsageLinkOut, InventoryUsageOut
from app.utils import recalc_inventory_row, validate_bags_loose

router = APIRouter(tags=["inventory"])

INV_VIEW = [Depends(require_permission(Permission.INVENTORY_VIEW))]
INV_OPEN = [Depends(require_permission(Permission.INVENTORY_OPENING_STOCK))]
INV_EDIT = [Depends(require_permission(Permission.INVENTORY_EDIT_QTY))]

INVENTORY_IDENTITY_MSG = "Inventory row identity cannot be changed."
INVENTORY_DELETE_FORBIDDEN_MSG = (
    "Inventory rows cannot be deleted. Use stock disposal or other operations."
)


def inv_to_out(row: Inventory) -> InventoryOut:
    loc = row.location
    return InventoryOut(
        id=row.id,
        product_id=row.product_id,
        brand_id=row.brand_id,
        location_id=row.location_id,
        bag_type_id=row.bag_type_id,
        owner_type=row.owner_type.value if row.owner_type else "owned",
        customer_id=row.customer_id,
        customer_name=row.customer.name if row.customer else None,
        bag_count=row.bag_count,
        loose_kg=row.loose_kg,
        total_quantity_kg=row.total_quantity_kg,
        product_name=row.product.product_name if row.product else None,
        brand_name=row.brand.name if row.brand else None,
        location_name=loc.name if loc else None,
        location_address_line=loc.address_line if loc else None,
        location_district=loc.district if loc else None,
        location_state=loc.state if loc else None,
        location_pin_code=loc.pin_code if loc else None,
        bag_type_name=row.bag_type.name if row.bag_type else None,
    )


def _load_inventory(db: Session, iid: int, company_id: int | None = None) -> Inventory | None:
    inv = db.scalar(
        select(Inventory)
        .where(Inventory.id == iid)
        .options(
            joinedload(Inventory.product),
            joinedload(Inventory.brand),
            joinedload(Inventory.location),
            joinedload(Inventory.bag_type),
            joinedload(Inventory.customer),
        )
    )
    if company_id is not None:
        require_entity_company(inv, company_id, label="Inventory")
    return inv


@router.get("/inventory", response_model=InventoryPageOut, dependencies=INV_VIEW)
def list_inventory(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    product_id: int | None = None,
    brand_id: int | None = None,
    location_id: int | None = None,
    bag_type_id: int | None = None,
    owner_type: str | None = None,
    customer_id: int | None = None,
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
):
    company_id = company_id_for_user(user)
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = scope_query(
        select(Inventory)
        .join(Inventory.location)
        .join(Inventory.product)
        .join(Inventory.brand)
        .options(
            joinedload(Inventory.product),
            joinedload(Inventory.brand),
            joinedload(Inventory.location),
            joinedload(Inventory.bag_type),
            joinedload(Inventory.customer),
        ),
        Inventory,
        company_id,
    )
    if product_id:
        q = q.where(Inventory.product_id == product_id)
    if brand_id:
        q = q.where(Inventory.brand_id == brand_id)
    if location_id:
        q = q.where(Inventory.location_id == location_id)
    if bag_type_id:
        q = q.where(Inventory.bag_type_id == bag_type_id)
    if owner_type:
        q = q.where(Inventory.owner_type == owner_type)
    if customer_id is not None:
        q = q.where(Inventory.customer_id == customer_id)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(
            or_(
                func.lower(Product.product_name).like(term),
                func.lower(Brand.name).like(term),
                func.lower(Location.name).like(term),
            )
        )
    q = q.order_by(
        Location.name.asc(),
        Product.product_name.asc(),
        Brand.name.asc(),
        Inventory.bag_type_id.asc(),
    )
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    items = [inv_to_out(r) for r in rows]
    return InventoryPageOut(**page_dict(items, total, limit, offset))


@router.get("/inventory/stock-at-location", dependencies=INV_VIEW)
def stock_at_location(
    location_id: int = Query(...),
    product_id: int | None = None,
    brand_id: int | None = None,
    owner_type: str | None = None,
    customer_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_id = company_id_for_user(user)
    q = scope_query(
        select(Inventory).where(Inventory.location_id == location_id).options(
            joinedload(Inventory.product),
            joinedload(Inventory.brand),
            joinedload(Inventory.bag_type),
            joinedload(Inventory.customer),
        ),
        Inventory,
        company_id,
    )
    if product_id:
        q = q.where(Inventory.product_id == product_id)
    if brand_id:
        q = q.where(Inventory.brand_id == brand_id)
    if owner_type:
        q = q.where(Inventory.owner_type == InventoryOwnerType(owner_type))
    if customer_id is not None:
        q = q.where(Inventory.customer_id == customer_id)
    rows = db.scalars(q).unique().all()
    return [inv_to_out(r) for r in rows]


@router.get("/inventory/{iid}/usage", response_model=InventoryUsageOut, dependencies=INV_VIEW)
def get_inventory_usage(
    iid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    inv = require_for_company(db, Inventory, iid, company_id_for_user(user), label="Inventory")
    links = [InventoryUsageLinkOut.model_validate(link) for link in inventory_usage_links(db, inv)]
    return InventoryUsageOut(
        inventory_id=inv.id,
        links=links,
        has_activity=any(link.count > 0 for link in links),
    )


@router.post("/inventory", response_model=InventoryOut, status_code=201, dependencies=INV_OPEN)
def create_inventory(
    body: InventoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/inventory"
    request_hash = hash_pydantic_body(body)

    def execute():
        bt = db.get(BagType, body.bag_type_id)
        if not bt:
            raise HTTPException(400, "Invalid bag type")
        try:
            validate_bags_loose(bt, body.bag_count, body.loose_kg)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        company_id = company_id_for_user(user)
        existing = db.scalar(
            select(Inventory).where(
                Inventory.company_id == company_id,
                Inventory.product_id == body.product_id,
                Inventory.brand_id == body.brand_id,
                Inventory.location_id == body.location_id,
                Inventory.bag_type_id == body.bag_type_id,
                Inventory.owner_type == InventoryOwnerType.owned,
                Inventory.customer_id.is_(None),
            )
        )
        if existing:
            raise HTTPException(400, "Inventory row already exists for this combination")
        inv = Inventory(
            company_id=company_id,
            product_id=body.product_id,
            brand_id=body.brand_id,
            location_id=body.location_id,
            bag_type_id=body.bag_type_id,
            owner_type=InventoryOwnerType.owned,
            customer_id=None,
            bag_count=body.bag_count,
            loose_kg=body.loose_kg,
        )
        recalc_inventory_row(inv, bt)
        db.add(inv)
        db.commit()
        inv = _load_inventory(db, inv.id, company_id)
        out = inv_to_out(inv)
        return out, 201

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.put("/inventory/{iid}", response_model=InventoryOut, dependencies=INV_EDIT)
def update_inventory(
    iid: int,
    body: InventoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str = Depends(require_idempotency_key),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    route_key = f"PUT /api/inventory/{iid}"
    request_hash = hash_pydantic_body(body)

    def execute():
        company_id = company_id_for_user(user)
        inv = require_for_company(db, Inventory, iid, company_id, label="Inventory")
        if (
            body.product_id != inv.product_id
            or body.brand_id != inv.brand_id
            or body.location_id != inv.location_id
            or body.bag_type_id != inv.bag_type_id
        ):
            raise HTTPException(400, INVENTORY_IDENTITY_MSG)

        qty_changed = body.bag_count != inv.bag_count or Decimal(body.loose_kg) != Decimal(inv.loose_kg)
        if qty_changed:
            verify_void_authorization(void_password, user)

        bt = db.get(BagType, body.bag_type_id)
        if not bt:
            raise HTTPException(400, "Invalid bag type")
        try:
            validate_bags_loose(bt, body.bag_count, body.loose_kg)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

        if qty_changed:
            inv.bag_count = body.bag_count
            inv.loose_kg = body.loose_kg
            recalc_inventory_row(inv, bt)
            db.commit()
            from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event

            record_audit_event(
                db,
                user=user,
                action=AuditAction.INVENTORY_QTY_EDITED,
                entity_type=AuditEntityType.INVENTORY,
                entity_id=inv.id,
                entity_label=f"Inventory #{inv.id}",
                metadata={
                    "bag_count": body.bag_count,
                    "loose_kg": str(body.loose_kg),
                },
            )

        inv = _load_inventory(db, iid, company_id)
        out = inv_to_out(inv)
        return out, 200

    return run_idempotent_mutation(db, user, idempotency_key, route_key, request_hash, execute)


@router.delete("/inventory/{iid}")
def delete_inventory(iid: int):  # noqa: ARG001 — route retained; hard-delete disabled (v15.2)
    raise HTTPException(status_code=403, detail=INVENTORY_DELETE_FORBIDDEN_MSG)
