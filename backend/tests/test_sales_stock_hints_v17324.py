"""Spec v17.3.26 — sales stock hints: other-bill reserved, bags vs kg."""
import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    BagType,
    Bill,
    BillType,
    BookSettings,
    Brand,
    Customer,
    Inventory,
    Location,
    Product,
)
from app.routers.bills import create_finalized_bill
from app.schemas import BillFinalizeCreate, BillLineIn
from app.services.fulfillment import FulfillmentType, create_fulfillment
from app.services.sales_stock_hint import (
    OpenBillRemaining,
    compute_sales_stock_hint,
    list_sales_stock_hint_items,
)
from tests.idempotency_helpers import TEST_USER, ensure_test_user, idem_kwargs


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _hint(on_hand: str, *other_remainings: str, on_hand_bags: int = 0):
    bills = [
        OpenBillRemaining(
            bill_id=i + 1,
            bill_date=date(2026, 1, i + 1),
            remaining_kg=Decimal(kg),
            remaining_bags=int(Decimal(kg)),
        )
        for i, kg in enumerate(other_remainings)
    ]
    return compute_sales_stock_hint(Decimal(on_hand), bills, on_hand_bags=on_hand_bags)


class SalesStockHintMathV17326Tests(unittest.TestCase):
    def test_no_other_bills_reserved_zero(self):
        h = _hint("50", on_hand_bags=50)
        self.assertEqual(h.available_kg, Decimal("50"))
        self.assertEqual(h.available_bags, 50)
        self.assertEqual(h.reserved_kg, Decimal("0"))
        self.assertEqual(h.reserved_bags, 0)

    def test_one_other_bill_100(self):
        h = _hint("50", "100", on_hand_bags=50)
        self.assertEqual(h.available_bags, 50)
        self.assertEqual(h.reserved_bags, 100)
        self.assertEqual(h.reserved_kg, Decimal("100"))

    def test_two_other_bills(self):
        h = _hint("30", "80", "100", on_hand_bags=30)
        self.assertEqual(h.available_bags, 30)
        self.assertEqual(h.reserved_bags, 180)

    def test_current_bill_not_counted(self):
        """Reserved is other bills only — current form qty is omitted."""
        h = compute_sales_stock_hint(Decimal("50"), [], on_hand_bags=50)
        self.assertEqual(h.reserved_bags, 0)
        self.assertEqual(h.available_bags, 50)


class SalesStockHintApiV17326Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.product = Product(product_name="Jowar")
        self.zero_product = Product(product_name="Zero SKU")
        self.missing_product = Product(product_name="Missing Row")
        self.brand = Brand(name="CH5")
        self.location = Location(name="Godown")
        self.loose = BagType(name="Loose", weight_per_bag_kg=Decimal("0"), is_loose=True)
        self.bag50 = BagType(name="50kg", weight_per_bag_kg=Decimal("50"), is_loose=False)
        self.customer = Customer(name="Hint Co")
        self.db.add_all(
            [
                self.product,
                self.zero_product,
                self.missing_product,
                self.brand,
                self.location,
                self.loose,
                self.bag50,
                self.customer,
            ]
        )
        self.db.flush()
        if self.db.get(BookSettings, 1) is None:
            self.db.add(
                BookSettings(
                    id=1,
                    company_id=1,
                    cash_opening_balance=Decimal("0"),
                    cash_opening_balance_at=date.today(),
                )
            )
        self.inv = Inventory(
            product_id=self.product.id,
            brand_id=self.brand.id,
            location_id=self.location.id,
            bag_type_id=self.loose.id,
            bag_count=0,
            loose_kg=Decimal("50"),
            total_quantity_kg=Decimal("50"),
        )
        self.packed_inv = Inventory(
            product_id=self.product.id,
            brand_id=self.brand.id,
            location_id=self.location.id,
            bag_type_id=self.bag50.id,
            bag_count=50,
            loose_kg=Decimal("0"),
            total_quantity_kg=Decimal("2500"),
        )
        self.zero_inv = Inventory(
            product_id=self.zero_product.id,
            brand_id=self.brand.id,
            location_id=self.location.id,
            bag_type_id=self.loose.id,
            bag_count=0,
            loose_kg=Decimal("0"),
            total_quantity_kg=Decimal("0"),
        )
        self.db.add_all([self.inv, self.packed_inv, self.zero_inv])
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _loose_line(self, product_id: int, kg: str) -> BillLineIn:
        return BillLineIn(
            product_id=product_id,
            brand_id=self.brand.id,
            bag_type_id=self.loose.id,
            ordered_bags=0,
            ordered_loose_kg=Decimal(kg),
            rate_per_kg=Decimal("10"),
            stock_source="owned",
        )

    def _packed_line(self, bags: int) -> BillLineIn:
        return BillLineIn(
            product_id=self.product.id,
            brand_id=self.brand.id,
            bag_type_id=self.bag50.id,
            ordered_bags=bags,
            ordered_loose_kg=Decimal("0"),
            rate_per_kg=Decimal("10"),
            stock_source="owned",
        )

    def _create_bill(self, line: BillLineIn):
        return create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.sales,
                customer_id=self.customer.id,
                location_id=self.location.id,
                discount_percent=Decimal("0"),
                adjustment=Decimal("0"),
                lines=[line],
            ),
            db=self.db,
            **idem_kwargs(),
        )

    def _hint_item(self, bag_type_id: int, exclude_bill_id: int | None = None):
        items = list_sales_stock_hint_items(
            self.db,
            company_id=1,
            location_id=self.location.id,
            exclude_bill_id=exclude_bill_id,
        )
        return next(
            it
            for it in items
            if it.product_id == self.product.id
            and it.bag_type_id == bag_type_id
            and it.stock_source == "owned"
        )

    def test_zero_qty_row_appears_and_can_be_billed(self):
        stock = self.client.get(f"/api/inventory/stock-at-location?location_id={self.location.id}")
        self.assertEqual(stock.status_code, 200)
        zero = next(r for r in stock.json() if r["product_id"] == self.zero_product.id)
        self.assertEqual(Decimal(str(zero["total_quantity_kg"])), Decimal("0"))

        products = self.client.get("/api/products?limit=30&offset=0")
        names = {p["product_name"] for p in products.json()["items"]}
        self.assertIn("Zero SKU", names)
        self.assertIn("Missing Row", names)

        out = self._create_bill(self._loose_line(self.zero_product.id, "12.5"))
        self.assertGreater(out.id, 0)
        self.db.refresh(self.zero_inv)
        self.assertEqual(self.zero_inv.total_quantity_kg, Decimal("0"))

        missing = self._create_bill(self._loose_line(self.missing_product.id, "8"))
        self.assertGreater(missing.id, 0)
        items = list_sales_stock_hint_items(
            self.db, company_id=1, location_id=self.location.id
        )
        item = next(it for it in items if it.product_id == self.missing_product.id)
        self.assertEqual(item.on_hand_kg, Decimal("0"))

    def test_first_bill_reserved_zero_next_form_sees_other(self):
        a = self._create_bill(self._packed_line(100))
        on_a = compute_sales_stock_hint(
            Decimal("2500"),
            self._hint_item(self.bag50.id, exclude_bill_id=a.id).open_bills,
            on_hand_bags=50,
        )
        self.assertEqual(on_a.available_bags, 50)
        self.assertEqual(on_a.reserved_bags, 0)

        next_form = compute_sales_stock_hint(
            Decimal("2500"),
            self._hint_item(self.bag50.id).open_bills,
            on_hand_bags=50,
        )
        self.assertEqual(next_form.available_bags, 50)
        self.assertEqual(next_form.reserved_bags, 100)

    def test_packed_deliver_then_other_bills(self):
        a = self._create_bill(self._packed_line(100))
        saved = self.db.get(Bill, a.id)
        assert saved is not None
        create_fulfillment(
            self.db,
            bill_line_id=saved.lines[0].id,
            entry_type=FulfillmentType.deliver,
            quantity_kg=Decimal("1000"),
            bag_count=20,
            loose_kg=Decimal("0"),
            expected_version=saved.version,
        )
        self.db.refresh(self.packed_inv)
        self.assertEqual(self.packed_inv.bag_count, 30)

        b_view = compute_sales_stock_hint(
            self.packed_inv.total_quantity_kg,
            self._hint_item(self.bag50.id).open_bills,
            on_hand_bags=self.packed_inv.bag_count,
        )
        self.assertEqual(b_view.available_bags, 30)
        self.assertEqual(b_view.reserved_bags, 80)

        self._create_bill(self._packed_line(100))
        c_view = compute_sales_stock_hint(
            self.packed_inv.total_quantity_kg,
            self._hint_item(self.bag50.id).open_bills,
            on_hand_bags=self.packed_inv.bag_count,
        )
        self.assertEqual(c_view.available_bags, 30)
        self.assertEqual(c_view.reserved_bags, 180)

    def test_does_not_mix_bag_types(self):
        self._create_bill(self._packed_line(100))
        self._create_bill(self._loose_line(self.product.id, "40"))
        packed = self._hint_item(self.bag50.id)
        loose = self._hint_item(self.loose.id)
        packed_h = compute_sales_stock_hint(packed.on_hand_kg, packed.open_bills, on_hand_bags=packed.on_hand_bags)
        loose_h = compute_sales_stock_hint(loose.on_hand_kg, loose.open_bills, on_hand_bags=loose.on_hand_bags)
        self.assertEqual(packed_h.reserved_bags, 100)
        self.assertEqual(loose_h.reserved_kg, Decimal("40"))
        self.assertEqual(packed.on_hand_bags, 50)
        self.assertEqual(loose.on_hand_kg, Decimal("50"))

    def test_create_over_on_hand_does_not_change_inventory(self):
        before = self.inv.total_quantity_kg
        out = self._create_bill(self._loose_line(self.product.id, "100"))
        self.assertGreater(out.id, 0)
        self.db.refresh(self.inv)
        self.assertEqual(self.inv.total_quantity_kg, before)

    def test_deliver_over_on_hand_fails(self):
        bill = self._create_bill(self._loose_line(self.product.id, "100"))
        saved = self.db.get(Bill, bill.id)
        assert saved is not None
        bl = saved.lines[0]
        with self.assertRaises(ValueError) as ctx:
            create_fulfillment(
                self.db,
                bill_line_id=bl.id,
                entry_type=FulfillmentType.deliver,
                quantity_kg=Decimal("100"),
                bag_count=0,
                loose_kg=Decimal("100"),
                expected_version=saved.version,
            )
        self.assertIn("Insufficient stock", str(ctx.exception))
        self.db.refresh(self.inv)
        self.assertEqual(self.inv.total_quantity_kg, Decimal("50"))

        post = self.client.post(
            "/api/fulfillment",
            json={
                "bill_line_id": bl.id,
                "entry_type": "deliver",
                "quantity_kg": "100",
                "bag_count": 0,
                "loose_kg": "100",
                "expected_version": saved.version,
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.assertGreaterEqual(post.status_code, 400)
        self.db.refresh(self.inv)
        self.assertEqual(self.inv.total_quantity_kg, Decimal("50"))


if __name__ == "__main__":
    unittest.main()
