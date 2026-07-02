"""Spec v12.9 — bag type weight and is_loose immutable after creation."""
import unittest
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import BagType, Brand, Inventory, Location, Product
from app.routers.masters import (
    BAG_TYPE_LOOSE_IMMUTABLE_MSG,
    BAG_TYPE_WEIGHT_IMMUTABLE_MSG,
    create_bag_type,
    update_bag_type,
)
from app.schemas import BagTypeCreate


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class BagTypeImmutableV129Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()

    def tearDown(self):
        self.db.close()

    def test_create_bag_type_succeeds(self):
        created = create_bag_type(
            BagTypeCreate(name="40kg", weight_per_bag_kg=Decimal("40"), is_loose=False),
            db=self.db,
        )
        self.assertEqual(created.name, "40kg")
        self.assertEqual(created.weight_per_bag_kg, Decimal("40"))
        self.assertFalse(created.is_loose)

    def test_rename_allowed(self):
        created = create_bag_type(
            BagTypeCreate(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False),
            db=self.db,
        )
        updated = update_bag_type(
            created.id,
            BagTypeCreate(name="50 kg bag", weight_per_bag_kg=Decimal("50"), is_loose=False),
            db=self.db,
        )
        self.assertEqual(updated.name, "50 kg bag")
        self.assertEqual(updated.weight_per_bag_kg, Decimal("50"))
        self.assertFalse(updated.is_loose)

    def test_weight_change_blocked(self):
        created = create_bag_type(
            BagTypeCreate(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False),
            db=self.db,
        )
        with self.assertRaises(HTTPException) as ctx:
            update_bag_type(
                created.id,
                BagTypeCreate(name="50kg", weight_per_bag_kg=Decimal("45"), is_loose=False),
                db=self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, BAG_TYPE_WEIGHT_IMMUTABLE_MSG)

    def test_is_loose_change_blocked(self):
        created = create_bag_type(
            BagTypeCreate(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False),
            db=self.db,
        )
        with self.assertRaises(HTTPException) as ctx:
            update_bag_type(
                created.id,
                BagTypeCreate(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=True),
                db=self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, BAG_TYPE_LOOSE_IMMUTABLE_MSG)

    def test_inventory_unchanged_after_blocked_weight_put(self):
        product = Product(product_name="Wheat")
        brand = Brand(name="Raw")
        location = Location(name="Warehouse")
        self.db.add_all([product, brand, location])
        self.db.flush()

        bag_type = create_bag_type(
            BagTypeCreate(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False),
            db=self.db,
        )
        inv = Inventory(
            product_id=product.id,
            brand_id=brand.id,
            location_id=location.id,
            bag_type_id=bag_type.id,
            bag_count=10,
            loose_kg=Decimal("0"),
            total_quantity_kg=Decimal("500"),
        )
        self.db.add(inv)
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            update_bag_type(
                bag_type.id,
                BagTypeCreate(name="50kg", weight_per_bag_kg=Decimal("40"), is_loose=False),
                db=self.db,
            )
        self.assertEqual(ctx.exception.detail, BAG_TYPE_WEIGHT_IMMUTABLE_MSG)

        self.db.refresh(inv)
        self.db.refresh(bag_type)
        self.assertEqual(bag_type.weight_per_bag_kg, Decimal("50"))
        self.assertEqual(inv.bag_count, 10)
        self.assertEqual(inv.total_quantity_kg, Decimal("500"))


if __name__ == "__main__":
    unittest.main()
