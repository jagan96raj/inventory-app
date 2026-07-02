"""Spec v14.1 — owner-tagged bag change, transfer, disposal."""
import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    Brand,
    Customer,
    CustomerPartyType,
    Inventory,
    InventoryOwnerType,
    Location,
    Product,
)
from app.services.idempotency import IDEMPOTENCY_KEY_HEADER
from app.services.job_work import create_job_work_order, receive_job_work
from app.services.operations import (
    add_inventory,
    create_bag_change,
    create_product_transfer,
    create_stock_disposal,
)
from tests.idempotency_helpers import TEST_USER, ensure_test_user


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed(db: Session) -> dict:
    ensure_test_user(db)
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    location_b = Location(name="Store")
    bag_50 = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    bag_25 = BagType(name="25kg", weight_per_bag_kg=Decimal("25"), is_loose=False)
    customer = Customer(name="Murugan Traders", party_type=CustomerPartyType.internal)
    db.add_all([product, brand, location, location_b, bag_50, bag_25, customer])
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "location_b": location_b,
        "bag_50": bag_50,
        "bag_25": bag_25,
        "customer": customer,
    }


def _inv(
    db: Session,
    m: dict,
    *,
    location_id: int,
    bag_type_id: int,
    owner_type: InventoryOwnerType = InventoryOwnerType.owned,
    customer_id: int | None = None,
) -> Inventory | None:
    q = select(Inventory).where(
        Inventory.product_id == m["product"].id,
        Inventory.brand_id == m["brand"].id,
        Inventory.location_id == location_id,
        Inventory.bag_type_id == bag_type_id,
        Inventory.owner_type == owner_type,
    )
    if owner_type == InventoryOwnerType.job_work:
        q = q.where(Inventory.customer_id == customer_id)
    else:
        q = q.where(Inventory.customer_id.is_(None))
    return db.scalar(q)


def _receive_jw(db: Session, m: dict, *, bags: int) -> None:
    order = create_job_work_order(
        db,
        customer_id=m["customer"].id,
        job_date=date.today(),
        notes=None,
        lines=[
            {
                "product_id": m["product"].id,
                "brand_id": m["brand"].id,
                "bag_type_id": m["bag_50"].id,
                "ordered_bags": bags,
                "ordered_loose_kg": Decimal("0"),
            }
        ],
    )
    receive_job_work(
        db,
        line_id=order.lines[0].id,
        location_id=m["location"].id,
        bag_count=bags,
        loose_kg=Decimal("0"),
    )


class OperationsV141JobWorkTests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)
        _receive_jw(self.db, self.m, bags=20)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_job_work_bag_change_moves_owner_bucket(self):
        m = self.m
        before = _inv(
            self.db,
            m,
            location_id=m["location"].id,
            bag_type_id=m["bag_50"].id,
            owner_type=InventoryOwnerType.job_work,
            customer_id=m["customer"].id,
        )
        assert before is not None
        self.assertEqual(before.bag_count, 20)

        record = create_bag_change(
            self.db,
            location_id=m["location"].id,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            from_bag_type_id=m["bag_50"].id,
            from_bag_count=10,
            from_loose_kg=Decimal("0"),
            quantity_loss_kg=Decimal("50"),
            to_lines=[{"to_bag_type_id": m["bag_25"].id, "bag_count": 18, "loose_kg": Decimal("0")}],
            notes=None,
            owner_type=InventoryOwnerType.job_work,
            customer_id=m["customer"].id,
        )
        self.assertEqual(record.owner_type, InventoryOwnerType.job_work)
        self.assertEqual(record.customer_id, m["customer"].id)

        after_from = _inv(
            self.db,
            m,
            location_id=m["location"].id,
            bag_type_id=m["bag_50"].id,
            owner_type=InventoryOwnerType.job_work,
            customer_id=m["customer"].id,
        )
        after_to = _inv(
            self.db,
            m,
            location_id=m["location"].id,
            bag_type_id=m["bag_25"].id,
            owner_type=InventoryOwnerType.job_work,
            customer_id=m["customer"].id,
        )
        assert after_from is not None and after_to is not None
        self.assertEqual(after_from.bag_count, 10)
        self.assertEqual(after_to.bag_count, 18)

    def test_job_work_transfer_preserves_owner(self):
        m = self.m
        record = create_product_transfer(
            self.db,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_50"].id,
            from_location_id=m["location"].id,
            to_location_id=m["location_b"].id,
            bag_count=5,
            loose_kg=Decimal("0"),
            notes=None,
            owner_type=InventoryOwnerType.job_work,
            customer_id=m["customer"].id,
        )
        self.assertEqual(record.owner_type, InventoryOwnerType.job_work)

        src = _inv(
            self.db,
            m,
            location_id=m["location"].id,
            bag_type_id=m["bag_50"].id,
            owner_type=InventoryOwnerType.job_work,
            customer_id=m["customer"].id,
        )
        dst = _inv(
            self.db,
            m,
            location_id=m["location_b"].id,
            bag_type_id=m["bag_50"].id,
            owner_type=InventoryOwnerType.job_work,
            customer_id=m["customer"].id,
        )
        assert src is not None and dst is not None
        self.assertEqual(src.bag_count, 15)
        self.assertEqual(dst.bag_count, 5)

    def test_job_work_disposal_subtracts_owner_only(self):
        m = self.m
        create_stock_disposal(
            self.db,
            location_id=m["location"].id,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_50"].id,
            bag_count=3,
            loose_kg=Decimal("0"),
            reason="damaged",
            notes=None,
            owner_type=InventoryOwnerType.job_work,
            customer_id=m["customer"].id,
        )
        jw = _inv(
            self.db,
            m,
            location_id=m["location"].id,
            bag_type_id=m["bag_50"].id,
            owner_type=InventoryOwnerType.job_work,
            customer_id=m["customer"].id,
        )
        assert jw is not None
        self.assertEqual(jw.bag_count, 17)

    def test_api_bag_change_defaults_owned(self):
        m = self.m
        add_inventory(
            self.db,
            m["product"].id,
            m["brand"].id,
            m["location"].id,
            m["bag_50"].id,
            10,
            Decimal("0"),
        )
        key = str(uuid4())
        res = self.client.post(
            "/api/operations/bag-change",
            json={
                "location_id": m["location"].id,
                "product_id": m["product"].id,
                "brand_id": m["brand"].id,
                "from_bag_type_id": m["bag_50"].id,
                "from_bag_count": 2,
                "from_loose_kg": "0",
                "quantity_loss_kg": "0",
                "to_lines": [
                    {"to_bag_type_id": m["bag_25"].id, "bag_count": 4, "loose_kg": "0"},
                ],
                "notes": None,
            },
            headers={IDEMPOTENCY_KEY_HEADER: key},
        )
        self.assertEqual(res.status_code, 201, res.text)
        body = res.json()
        self.assertEqual(body["owner_type"], "owned")
        self.assertIsNone(body["customer_id"])

        owned = _inv(
            self.db,
            m,
            location_id=m["location"].id,
            bag_type_id=m["bag_50"].id,
            owner_type=InventoryOwnerType.owned,
        )
        assert owned is not None
        self.assertEqual(owned.bag_count, 8)

    def test_job_work_bag_change_does_not_touch_owned(self):
        m = self.m
        add_inventory(
            self.db,
            m["product"].id,
            m["brand"].id,
            m["location"].id,
            m["bag_50"].id,
            5,
            Decimal("0"),
        )
        create_bag_change(
            self.db,
            location_id=m["location"].id,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            from_bag_type_id=m["bag_50"].id,
            from_bag_count=4,
            from_loose_kg=Decimal("0"),
            quantity_loss_kg=Decimal("0"),
            to_lines=[{"to_bag_type_id": m["bag_25"].id, "bag_count": 8, "loose_kg": Decimal("0")}],
            notes=None,
            owner_type=InventoryOwnerType.job_work,
            customer_id=m["customer"].id,
        )
        owned = _inv(
            self.db,
            m,
            location_id=m["location"].id,
            bag_type_id=m["bag_50"].id,
            owner_type=InventoryOwnerType.owned,
        )
        assert owned is not None
        self.assertEqual(owned.bag_count, 5)


if __name__ == "__main__":
    unittest.main()
