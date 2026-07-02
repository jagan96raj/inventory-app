"""Spec v12.1 — inventory opening quantities; authorized manual correction on edit."""
import unittest
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import BagType, Brand, Inventory, Location, Product, User
from app.routers.inventory import INVENTORY_IDENTITY_MSG, create_inventory, update_inventory
from app.schemas import InventoryCreate
from app.services.operations import subtract_inventory
from tests.idempotency_helpers import TEST_VOID_AUTH_PASSWORD, idem_kwargs


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_masters(db: Session) -> dict:
    product = Product(product_name="Wheat")
    brand = Brand(name="Raw")
    location = Location(name="Warehouse")
    bag_type = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
    user = User(email="test@example.com", password_hash="x", name="Test")
    db.add_all([product, brand, location, bag_type, user])
    db.flush()
    return {
        "product": product,
        "brand": brand,
        "location": location,
        "bag_type": bag_type,
        "user": user,
    }


class InventoryV121Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.masters = _seed_masters(self.db)

    def tearDown(self):
        self.db.close()

    def _create_body(self, *, bag_count: int = 100, loose_kg: Decimal = Decimal("0")) -> InventoryCreate:
        m = self.masters
        return InventoryCreate(
            product_id=m["product"].id,
            brand_id=m["brand"].id,
            location_id=m["location"].id,
            bag_type_id=m["bag_type"].id,
            bag_count=bag_count,
            loose_kg=loose_kg,
        )

    def test_create_opening_qty_persists(self):
        created = create_inventory(self._create_body(bag_count=100), db=self.db, **idem_kwargs())
        self.assertEqual(created.bag_count, 100)
        self.assertEqual(created.total_quantity_kg, Decimal("5000"))

        row = self.db.get(Inventory, created.id)
        self.assertEqual(row.bag_count, 100)
        self.assertEqual(row.total_quantity_kg, Decimal("5000"))

    def test_put_different_qty_requires_authorization(self):
        created = create_inventory(self._create_body(bag_count=100), db=self.db, **idem_kwargs())

        with self.assertRaises(HTTPException) as ctx:
            update_inventory(
                created.id,
                self._create_body(bag_count=50),
                db=self.db,
                void_password=None,
                **idem_kwargs(),
            )
        self.assertEqual(ctx.exception.status_code, 403)

        row = self.db.get(Inventory, created.id)
        self.assertEqual(row.bag_count, 100)

    def test_put_different_qty_with_auth_updates(self):
        created = create_inventory(self._create_body(bag_count=100), db=self.db, **idem_kwargs())

        updated = update_inventory(
            created.id,
            self._create_body(bag_count=50),
            db=self.db,
            void_password=TEST_VOID_AUTH_PASSWORD,
            **idem_kwargs(),
        )
        self.assertEqual(updated.bag_count, 50)
        self.assertEqual(updated.total_quantity_kg, Decimal("2500"))

        row = self.db.get(Inventory, created.id)
        self.assertEqual(row.bag_count, 50)

    def test_put_can_restore_qty_after_subtract_with_auth(self):
        created = create_inventory(self._create_body(bag_count=100), db=self.db, **idem_kwargs())
        m = self.masters

        subtract_inventory(
            self.db,
            m["product"].id,
            m["brand"].id,
            m["location"].id,
            m["bag_type"].id,
            50,
            Decimal("0"),
        )
        self.db.commit()

        row = self.db.get(Inventory, created.id)
        self.assertIsNotNone(row)
        self.assertEqual(row.bag_count, 50)

        updated = update_inventory(
            created.id,
            self._create_body(bag_count=100),
            db=self.db,
            void_password=TEST_VOID_AUTH_PASSWORD,
            **idem_kwargs(),
        )
        self.assertEqual(updated.bag_count, 100)

        row = self.db.get(Inventory, created.id)
        self.assertEqual(row.bag_count, 100)

    def test_put_identity_change_still_blocked(self):
        created = create_inventory(self._create_body(bag_count=100), db=self.db, **idem_kwargs())
        other = Product(product_name="Rice")
        self.db.add(other)
        self.db.flush()
        body = self._create_body(bag_count=100)
        body = body.model_copy(update={"product_id": other.id})

        with self.assertRaises(HTTPException) as ctx:
            update_inventory(
                created.id,
                body,
                db=self.db,
                void_password=TEST_VOID_AUTH_PASSWORD,
                **idem_kwargs(),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, INVENTORY_IDENTITY_MSG)


if __name__ == "__main__":
    unittest.main()
