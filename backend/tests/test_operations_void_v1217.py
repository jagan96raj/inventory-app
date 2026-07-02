"""Spec v12.17 — void bag change / product transfer / stock disposal."""
import unittest
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import BagType, Brand, Inventory, Location, Product
from app.services.idempotency import IDEMPOTENCY_KEY_HEADER
from app.services.operations import (
    OPERATION_ALREADY_VOIDED_MSG,
    OPERATION_VOID_INSUFFICIENT_STOCK_MSG,
    create_bag_change,
    create_product_transfer,
    create_stock_disposal,
    subtract_inventory,
    void_bag_change,
    void_product_transfer,
    void_stock_disposal,
)
from tests.idempotency_helpers import TEST_USER, ensure_test_user, idem_void_headers


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db: Session) -> dict:
    ensure_test_user(db)
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    location_b = Location(name="Store")
    bag_50 = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    bag_25 = BagType(name="25kg", weight_per_bag_kg=Decimal("25"), is_loose=False)
    db.add_all([product, brand, location, location_b, bag_50, bag_25])
    db.flush()
    inv = Inventory(
        product_id=product.id,
        brand_id=brand.id,
        location_id=location.id,
        bag_type_id=bag_50.id,
        bag_count=100,
        loose_kg=Decimal("0"),
        total_quantity_kg=Decimal("5000"),
    )
    db.add(inv)
    db.commit()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "location_b": location_b,
        "bag_50": bag_50,
        "bag_25": bag_25,
    }


def _inv_row(db: Session, m: dict, *, location_id: int, bag_type_id: int) -> Inventory | None:
    return db.scalar(
        select(Inventory).where(
            Inventory.product_id == m["product"].id,
            Inventory.brand_id == m["brand"].id,
            Inventory.location_id == location_id,
            Inventory.bag_type_id == bag_type_id,
        )
    )


class OperationsVoidBagChangeV1217Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)

    def tearDown(self):
        self.db.close()

    def test_bag_change_void_restores_inventory(self):
        m = self.m
        before_from = _inv_row(self.db, m, location_id=m["location"].id, bag_type_id=m["bag_50"].id)
        assert before_from is not None
        self.assertEqual(before_from.bag_count, 100)

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
        )

        after_from = _inv_row(self.db, m, location_id=m["location"].id, bag_type_id=m["bag_50"].id)
        after_to = _inv_row(self.db, m, location_id=m["location"].id, bag_type_id=m["bag_25"].id)
        assert after_from is not None and after_to is not None
        self.assertEqual(after_from.bag_count, 90)
        self.assertEqual(after_to.bag_count, 18)

        voided = void_bag_change(self.db, record.id)
        self.assertIsNotNone(voided.voided_at)

        restored_from = _inv_row(self.db, m, location_id=m["location"].id, bag_type_id=m["bag_50"].id)
        restored_to = _inv_row(self.db, m, location_id=m["location"].id, bag_type_id=m["bag_25"].id)
        assert restored_from is not None
        self.assertEqual(restored_from.bag_count, 100)
        self.assertTrue(restored_to is None or restored_to.bag_count == 0)

    def test_bag_change_double_void_rejected(self):
        m = self.m
        record = create_bag_change(
            self.db,
            location_id=m["location"].id,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            from_bag_type_id=m["bag_50"].id,
            from_bag_count=5,
            from_loose_kg=Decimal("0"),
            quantity_loss_kg=Decimal("0"),
            to_lines=[{"to_bag_type_id": m["bag_25"].id, "bag_count": 10, "loose_kg": Decimal("0")}],
            notes=None,
        )
        void_bag_change(self.db, record.id)
        with self.assertRaises(ValueError) as ctx:
            void_bag_change(self.db, record.id)
        self.assertEqual(str(ctx.exception), OPERATION_ALREADY_VOIDED_MSG)


class OperationsVoidTransferV1217Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)

    def tearDown(self):
        self.db.close()

    def test_transfer_void_restores_inventory(self):
        m = self.m
        record = create_product_transfer(
            self.db,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_50"].id,
            from_location_id=m["location"].id,
            to_location_id=m["location_b"].id,
            bag_count=30,
            loose_kg=Decimal("0"),
            notes=None,
        )

        at_a = _inv_row(self.db, m, location_id=m["location"].id, bag_type_id=m["bag_50"].id)
        at_b = _inv_row(self.db, m, location_id=m["location_b"].id, bag_type_id=m["bag_50"].id)
        assert at_a is not None and at_b is not None
        self.assertEqual(at_a.bag_count, 70)
        self.assertEqual(at_b.bag_count, 30)

        void_product_transfer(self.db, record.id)

        restored_a = _inv_row(self.db, m, location_id=m["location"].id, bag_type_id=m["bag_50"].id)
        restored_b = _inv_row(self.db, m, location_id=m["location_b"].id, bag_type_id=m["bag_50"].id)
        assert restored_a is not None
        self.assertEqual(restored_a.bag_count, 100)
        self.assertTrue(restored_b is None or restored_b.bag_count == 0)

    def test_transfer_void_blocked_when_destination_consumed(self):
        m = self.m
        record = create_product_transfer(
            self.db,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_50"].id,
            from_location_id=m["location"].id,
            to_location_id=m["location_b"].id,
            bag_count=30,
            loose_kg=Decimal("0"),
            notes=None,
        )
        subtract_inventory(
            self.db,
            m["product"].id,
            m["brand"].id,
            m["location_b"].id,
            m["bag_50"].id,
            25,
            Decimal("0"),
        )
        self.db.commit()

        with self.assertRaises(ValueError) as ctx:
            void_product_transfer(self.db, record.id)
        self.assertEqual(str(ctx.exception), OPERATION_VOID_INSUFFICIENT_STOCK_MSG)


class OperationsVoidDisposalV1217Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.m = _seed(self.db)

    def tearDown(self):
        self.db.close()

    def test_disposal_void_restores_inventory(self):
        m = self.m
        record = create_stock_disposal(
            self.db,
            location_id=m["location"].id,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_50"].id,
            bag_count=15,
            loose_kg=Decimal("0"),
            reason="Damaged",
            notes=None,
        )

        after = _inv_row(self.db, m, location_id=m["location"].id, bag_type_id=m["bag_50"].id)
        assert after is not None
        self.assertEqual(after.bag_count, 85)

        void_stock_disposal(self.db, record.id)

        restored = _inv_row(self.db, m, location_id=m["location"].id, bag_type_id=m["bag_50"].id)
        assert restored is not None
        self.assertEqual(restored.bag_count, 100)


class OperationsVoidIdempotencyV1217Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        self.db = _make_session()
        self.m = _seed(self.db)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def test_duplicate_disposal_void_replays_cached_response(self):
        m = self.m
        record = create_stock_disposal(
            self.db,
            location_id=m["location"].id,
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            bag_type_id=m["bag_50"].id,
            bag_count=5,
            loose_kg=Decimal("0"),
            reason=None,
            notes=None,
        )
        key = str(uuid4())
        headers = idem_void_headers(key)
        url = f"/api/operations/stock-disposal/{record.id}/void"

        res1 = self.client.post(url, json={}, headers=headers)
        self.assertEqual(res1.status_code, 200)
        self.assertIsNotNone(res1.json().get("voided_at"))

        res2 = self.client.post(url, json={}, headers=headers)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res1.json()["id"], res2.json()["id"])

        restored = _inv_row(self.db, m, location_id=m["location"].id, bag_type_id=m["bag_50"].id)
        assert restored is not None
        self.assertEqual(restored.bag_count, 100)


if __name__ == "__main__":
    unittest.main()
