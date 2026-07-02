from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.pagination import DEFAULT_LIMIT, clamp_limit, clamp_offset, page_dict, paginate_select
from app.core.permissions import Permission, require_permission
from app.core.void_auth import VOID_AUTH_HEADER, verify_void_authorization
from app.database import get_db
from app.models.entities import BagType, Brand, Customer, Location, Product, User
from app.services.customer_search import apply_customer_search
from app.schemas import (
    BagTypeCreate,
    BagTypeOut,
    BagTypePageOut,
    BrandCreate,
    BrandOut,
    BrandPageOut,
    CustomerCreate,
    CustomerOut,
    CustomerPageOut,
    CustomerUpdate,
    LocationCreate,
    LocationOut,
    LocationPageOut,
    ProductCreate,
    ProductOut,
    ProductPageOut,
)
from app.services import master_delete
from app.utils import normalize_name, validate_bag_type_fields

router = APIRouter(tags=["masters"])

READ = [Depends(require_permission(Permission.MASTERS_READ))]
MANAGE = [Depends(require_permission(Permission.MASTERS_MANAGE))]

BAG_TYPE_WEIGHT_IMMUTABLE_MSG = (
    "Bag type weight cannot be changed after creation. Create a new bag type instead."
)
BAG_TYPE_LOOSE_IMMUTABLE_MSG = (
    "Bagged vs loose setting cannot be changed after creation. Create a new bag type instead."
)


def _delete_master(
    db: Session,
    entity,
    assert_deletable,
    *,
    actor: User,
    entity_type: str,
    entity_label: str,
) -> dict:
    try:
        assert_deletable(db, entity)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    entity_id = entity.id
    try:
        db.delete(entity)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(400, "Cannot delete: record is still in use") from e
    from app.services.audit_log import AuditAction, record_audit_event

    record_audit_event(
        db,
        user=actor,
        action=AuditAction.MASTER_DELETED,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
    )
    return {"ok": True}


def resolve_bag_type_input(name: str, weight_per_bag_kg: Decimal, is_loose: bool) -> tuple[str, Decimal, bool]:
    """Normalize bag type fields; name 'Loose' always maps to loose + weight 0."""
    name = normalize_name(name)
    if name.lower() == "loose":
        return name, Decimal("0"), True
    return name, weight_per_bag_kg, is_loose


@router.get("/products", response_model=ProductPageOut, dependencies=READ)
def list_products(
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = select(Product).order_by(Product.product_name)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(func.lower(Product.product_name).like(term))
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    return ProductPageOut(**page_dict(rows, total, limit, offset))


@router.get("/products/{pid}", response_model=ProductOut, dependencies=READ)
def get_product(pid: int, db: Session = Depends(get_db)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Not found")
    return p


@router.post("/products", response_model=ProductOut, status_code=201, dependencies=MANAGE)
def create_product(body: ProductCreate, db: Session = Depends(get_db)):
    name = normalize_name(body.product_name)
    if not name:
        raise HTTPException(400, "Product name required")
    exists = db.scalar(
        select(Product).where(func.lower(func.trim(Product.product_name)) == name.lower())
    )
    if exists:
        raise HTTPException(400, "Product name already exists")
    p = Product(product_name=name)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/products/{pid}", response_model=ProductOut, dependencies=MANAGE)
def update_product(pid: int, body: ProductCreate, db: Session = Depends(get_db)):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Not found")
    name = normalize_name(body.product_name)
    dup = db.scalar(
        select(Product).where(
            func.lower(func.trim(Product.product_name)) == name.lower(), Product.id != pid
        )
    )
    if dup:
        raise HTTPException(400, "Product name already exists")
    p.product_name = name
    db.commit()
    db.refresh(p)
    return p


@router.delete("/products/{pid}", dependencies=MANAGE)
def delete_product(
    pid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    verify_void_authorization(void_password, user)
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Not found")
    return _delete_master(
        db,
        p,
        master_delete.assert_product_deletable,
        actor=user,
        entity_type="product",
        entity_label=p.product_name,
    )


@router.get("/brands", response_model=BrandPageOut, dependencies=READ)
def list_brands(
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = select(Brand).order_by(Brand.name)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(func.lower(Brand.name).like(term))
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    return BrandPageOut(**page_dict(rows, total, limit, offset))


@router.get("/brands/{bid}", response_model=BrandOut, dependencies=READ)
def get_brand(bid: int, db: Session = Depends(get_db)):
    b = db.get(Brand, bid)
    if not b:
        raise HTTPException(404, "Not found")
    return b


@router.post("/brands", response_model=BrandOut, status_code=201, dependencies=MANAGE)
def create_brand(body: BrandCreate, db: Session = Depends(get_db)):
    name = normalize_name(body.name)
    if db.scalar(select(Brand).where(func.lower(func.trim(Brand.name)) == name.lower())):
        raise HTTPException(400, "Brand already exists")
    b = Brand(name=name)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@router.put("/brands/{bid}", response_model=BrandOut, dependencies=MANAGE)
def update_brand(bid: int, body: BrandCreate, db: Session = Depends(get_db)):
    b = db.get(Brand, bid)
    if not b:
        raise HTTPException(404, "Not found")
    name = normalize_name(body.name)
    if db.scalar(select(Brand).where(func.lower(func.trim(Brand.name)) == name.lower(), Brand.id != bid)):
        raise HTTPException(400, "Brand already exists")
    b.name = name
    db.commit()
    db.refresh(b)
    return b


@router.delete("/brands/{bid}", dependencies=MANAGE)
def delete_brand(
    bid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    verify_void_authorization(void_password, user)
    b = db.get(Brand, bid)
    if not b:
        raise HTTPException(404, "Not found")
    return _delete_master(
        db,
        b,
        master_delete.assert_brand_deletable,
        actor=user,
        entity_type="brand",
        entity_label=b.name,
    )


@router.get("/locations", response_model=LocationPageOut, dependencies=READ)
def list_locations(
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = select(Location).order_by(Location.name)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(func.lower(Location.name).like(term))
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    return LocationPageOut(**page_dict(rows, total, limit, offset))


@router.get("/locations/{lid}", response_model=LocationOut, dependencies=READ)
def get_location(lid: int, db: Session = Depends(get_db)):
    loc = db.get(Location, lid)
    if not loc:
        raise HTTPException(404, "Not found")
    return loc


@router.post("/locations", response_model=LocationOut, status_code=201, dependencies=MANAGE)
def create_location(body: LocationCreate, db: Session = Depends(get_db)):
    name = normalize_name(body.name)
    if db.scalar(select(Location).where(func.lower(func.trim(Location.name)) == name.lower())):
        raise HTTPException(400, "Location already exists")
    loc = Location(
        name=name,
        address_line=body.address_line,
        district=body.district,
        state=body.state,
        pin_code=body.pin_code,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@router.put("/locations/{lid}", response_model=LocationOut, dependencies=MANAGE)
def update_location(lid: int, body: LocationCreate, db: Session = Depends(get_db)):
    loc = db.get(Location, lid)
    if not loc:
        raise HTTPException(404, "Not found")
    name = normalize_name(body.name)
    if db.scalar(select(Location).where(func.lower(func.trim(Location.name)) == name.lower(), Location.id != lid)):
        raise HTTPException(400, "Location already exists")
    loc.name = name
    loc.address_line = body.address_line
    loc.district = body.district
    loc.state = body.state
    loc.pin_code = body.pin_code
    db.commit()
    db.refresh(loc)
    return loc


@router.delete("/locations/{lid}", dependencies=MANAGE)
def delete_location(
    lid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    verify_void_authorization(void_password, user)
    loc = db.get(Location, lid)
    if not loc:
        raise HTTPException(404, "Not found")
    return _delete_master(
        db,
        loc,
        master_delete.assert_location_deletable,
        actor=user,
        entity_type="location",
        entity_label=loc.name,
    )


@router.get("/bag-types", response_model=BagTypePageOut, dependencies=READ)
def list_bag_types(
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = select(BagType).order_by(BagType.name)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(func.lower(BagType.name).like(term))
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    return BagTypePageOut(**page_dict(rows, total, limit, offset))


@router.get("/bag-types/{btid}", response_model=BagTypeOut, dependencies=READ)
def get_bag_type(btid: int, db: Session = Depends(get_db)):
    bt = db.get(BagType, btid)
    if not bt:
        raise HTTPException(404, "Not found")
    return bt


@router.post("/bag-types", response_model=BagTypeOut, status_code=201, dependencies=MANAGE)
def create_bag_type(body: BagTypeCreate, db: Session = Depends(get_db)):
    name, weight, is_loose = resolve_bag_type_input(body.name, body.weight_per_bag_kg, body.is_loose)
    try:
        validate_bag_type_fields(name, weight, is_loose)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if db.scalar(select(BagType).where(func.lower(func.trim(BagType.name)) == name.lower())):
        raise HTTPException(400, "Bag type already exists")
    bt = BagType(name=name, weight_per_bag_kg=weight, is_loose=is_loose)
    db.add(bt)
    db.commit()
    db.refresh(bt)
    return bt


@router.put("/bag-types/{btid}", response_model=BagTypeOut, dependencies=MANAGE)
def update_bag_type(btid: int, body: BagTypeCreate, db: Session = Depends(get_db)):
    bt = db.get(BagType, btid)
    if not bt:
        raise HTTPException(404, "Not found")
    name, weight, is_loose = resolve_bag_type_input(body.name, body.weight_per_bag_kg, body.is_loose)
    if weight != bt.weight_per_bag_kg:
        raise HTTPException(400, BAG_TYPE_WEIGHT_IMMUTABLE_MSG)
    if is_loose != bt.is_loose:
        raise HTTPException(400, BAG_TYPE_LOOSE_IMMUTABLE_MSG)
    try:
        validate_bag_type_fields(name, weight, is_loose)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if db.scalar(
        select(BagType).where(func.lower(func.trim(BagType.name)) == name.lower(), BagType.id != btid)
    ):
        raise HTTPException(400, "Bag type already exists")
    bt.name = name
    db.commit()
    db.refresh(bt)
    return bt


@router.delete("/bag-types/{btid}", dependencies=MANAGE)
def delete_bag_type(
    btid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    verify_void_authorization(void_password, user)
    bt = db.get(BagType, btid)
    if not bt:
        raise HTTPException(404, "Not found")
    return _delete_master(
        db,
        bt,
        master_delete.assert_bag_type_deletable,
        actor=user,
        entity_type="bag_type",
        entity_label=bt.name,
    )


@router.get("/customers", response_model=CustomerPageOut, dependencies=READ)
def list_customers(
    search: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)
    q = select(Customer).order_by(Customer.name)
    q = apply_customer_search(q, search)
    rows, total = paginate_select(db, q, limit=limit, offset=offset)
    return CustomerPageOut(**page_dict(rows, total, limit, offset))


@router.get("/customers/{cid}", response_model=CustomerOut, dependencies=READ)
def get_customer(cid: int, db: Session = Depends(get_db)):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(404, "Not found")
    return c


@router.post("/customers", response_model=CustomerOut, status_code=201, dependencies=MANAGE)
def create_customer(body: CustomerCreate, db: Session = Depends(get_db)):
    name = normalize_name(body.name)
    if db.scalar(select(Customer).where(func.lower(func.trim(Customer.name)) == name.lower())):
        raise HTTPException(400, "Customer already exists")
    c = Customer(
        name=name,
        address_line=body.address_line,
        district=body.district,
        state=body.state,
        pin_code=body.pin_code,
        phone=body.phone,
        alternate_phone=body.alternate_phone,
        credit_balance=body.credit_balance,
        debit_balance=body.debit_balance,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.put("/customers/{cid}", response_model=CustomerOut, dependencies=MANAGE)
def update_customer(cid: int, body: CustomerUpdate, db: Session = Depends(get_db)):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(404, "Not found")
    name = normalize_name(body.name)
    if db.scalar(select(Customer).where(func.lower(func.trim(Customer.name)) == name.lower(), Customer.id != cid)):
        raise HTTPException(400, "Customer already exists")
    c.name = name
    c.address_line = body.address_line
    c.district = body.district
    c.state = body.state
    c.pin_code = body.pin_code
    c.phone = body.phone
    c.alternate_phone = body.alternate_phone
    db.commit()
    db.refresh(c)
    return c


@router.delete("/customers/{cid}", dependencies=MANAGE)
def delete_customer(
    cid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    void_password: str | None = Header(None, alias=VOID_AUTH_HEADER),
):
    verify_void_authorization(void_password, user)
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(404, "Not found")
    return _delete_master(
        db,
        c,
        master_delete.assert_customer_deletable,
        actor=user,
        entity_type="customer",
        entity_label=c.name,
    )


@router.post("/seed/bag-types", dependencies=MANAGE)
def seed_bag_types(db: Session = Depends(get_db)):
    seeds = [
        ("50kg", Decimal("50"), False),
        ("30kg", Decimal("30"), False),
        ("25kg", Decimal("25"), False),
        ("Loose", Decimal("0"), True),
    ]
    created = []
    for name, weight, loose in seeds:
        if not db.scalar(select(BagType).where(func.lower(func.trim(BagType.name)) == name.lower())):
            bt = BagType(name=name, weight_per_bag_kg=weight, is_loose=loose)
            db.add(bt)
            created.append(name)
    db.commit()
    return {"created": created}
