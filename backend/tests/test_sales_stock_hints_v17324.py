"""Spec v17.3.24 — sales stock hints (display only) and 0-qty SKUs."""
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


def _hint(on_hand: str, *remainings: str) -> tuple[Decimal, Decimal, Decimal]:
    bills = [
        OpenBillRemaining(bill_id=i + 1, bill_date=date(2026, 1, i + 1), remaining_kg=Decimal(kg))
        for i, kg in enumerate(remainings)
    ]
    h = compute_sales_stock_hint(Decimal(on_hand), bills)
    return h.available_kg, h.reserved_kg, h.not_delivered_kg


class SalesStockHintMathV17324Tests(unittest.TestCase):
    def test_50_plus_one_bill_100(self):
        avail, reserved, nd = _hint("50", "100")
        self.assertEqual(avail, Decimal("50"))
        self.assertEqual(reserved, Decimal("0"))
        self.assertEqual(nd, Decimal("100"))

    def test_50_plus_second_100(self):
        avail, reserved, nd = _hint("50", "100", "100")
        self.assertEqual(avail, Decimal("50"))
        self.assertEqual(reserved, Decimal("-50"))
        self.assertEqual(nd, Decimal("200"))

    def test_50_plus_third_100(self):
        avail, reserved, nd = _hint("50", "100", "100", "100")
        self.assertEqual(avail, Decimal("50"))
        self.assertEqual(reserved, Decimal("-150"))
        self.assertEqual(nd, Decimal("300"))

    def test_200_plus_one_bill_100(self):
        avail, reserved, nd = _hint("200", "100")
        self.assertEqual(avail, Decimal("200"))
        self.assertEqual(reserved, Decimal("0"))
        self.assertEqual(nd, Decimal("100"))

    def test_200_plus_second_100(self):
        avail, reserved, nd = _hint("200", "100", "100")
        self.assertEqual(avail, Decimal("200"))
        self.assertEqual(reserved, Decimal("100"))
        self.assertEqual(nd, Decimal("200"))

    def test_zero_open_bills(self):
        avail, reserved, nd = _hint("50")
        self.assertEqual(avail, Decimal("50"))
        self.assertEqual(reserved, Decimal("0"))
        self.assertEqual(nd, Decimal("0"))


class SalesStockHintApiV17324Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.product = Product(product_name="Jowar")
        self.zero_product = Product(product_name="Zero SKU")
        self.missing_product = Product(product_name="Missing Row")
        self.brand = Brand(name="CH5")
        self.location = Location(name="Godown")
        self.loose = BagType(name="Loose", weight_per_bag_kg=Decimal("0"), is_loose=True)
        self.customer = Customer(name="Hint Co")
        self.db.add_all(
            [
                self.product,
                self.zero_product,
                self.missing_product,
                self.brand,
                self.location,
                self.loose,
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
        self.zero_inv = Inventory(
            product_id=self.zero_product.id,
            brand_id=self.brand.id,
            location_id=self.location.id,
            bag_type_id=self.loose.id,
            bag_count=0,
            loose_kg=Decimal("0"),
            total_quantity_kg=Decimal("0"),
        )
        self.db.add_all([self.inv, self.zero_inv])
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _line(self, product_id: int, kg: str) -> BillLineIn:
        return BillLineIn(
            product_id=product_id,
            brand_id=self.brand.id,
            bag_type_id=self.loose.id,
            ordered_bags=0,
            ordered_loose_kg=Decimal(kg),
            rate_per_kg=Decimal("10"),
            stock_source="owned",
        )

    def _create_bill(self, kg: str, product_id: int | None = None):
        return create_finalized_bill(
            BillFinalizeCreate(
                bill_type=BillType.sales,
                customer_id=self.customer.id,
                location_id=self.location.id,
                discount_percent=Decimal("0"),
                adjustment=Decimal("0"),
                lines=[self._line(product_id or self.product.id, kg)],
            ),
            db=self.db,
            **idem_kwargs(),
        )

    def _hint_item(self, product_id: int, exclude_bill_id: int | None = None):
        items = list_sales_stock_hint_items(
            self.db,
            company_id=1,
            location_id=self.location.id,
            exclude_bill_id=exclude_bill_id,
        )
        return next(
            it
            for it in items
            if it.product_id == product_id and it.stock_source == "owned"
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

        out = self._create_bill("12.5", product_id=self.zero_product.id)
        self.assertGreater(out.id, 0)
        self.db.refresh(self.zero_inv)
        self.assertEqual(self.zero_inv.total_quantity_kg, Decimal("0"))

        missing = self._create_bill("8", product_id=self.missing_product.id)
        self.assertGreater(missing.id, 0)
        item = self._hint_item(self.missing_product.id)
        self.assertEqual(item.on_hand_kg, Decimal("0"))

    def test_reserved_examples_via_saved_bills(self):
        self._create_bill("100")
        one = self._hint_item(self.product.id)
        h1 = compute_sales_stock_hint(one.on_hand_kg, one.open_bills)
        self.assertEqual(h1.available_kg, Decimal("50"))
        self.assertEqual(h1.reserved_kg, Decimal("0"))
        self.assertEqual(h1.not_delivered_kg, Decimal("100"))

        self._create_bill("100")
        two = self._hint_item(self.product.id)
        h2 = compute_sales_stock_hint(two.on_hand_kg, two.open_bills)
        self.assertEqual(h2.available_kg, Decimal("50"))
        self.assertEqual(h2.reserved_kg, Decimal("-50"))
        self.assertEqual(h2.not_delivered_kg, Decimal("200"))

        self._create_bill("100")
        three = self._hint_item(self.product.id)
        h3 = compute_sales_stock_hint(three.on_hand_kg, three.open_bills)
        self.assertEqual(h3.available_kg, Decimal("50"))
        self.assertEqual(h3.reserved_kg, Decimal("-150"))
        self.assertEqual(h3.not_delivered_kg, Decimal("300"))

        r = self.client.get(f"/api/bills/sales-stock-hints?location_id={self.location.id}")
        self.assertEqual(r.status_code, 200)
        row = next(i for i in r.json()["items"] if i["product_id"] == self.product.id)
        self.assertEqual(Decimal(str(row["on_hand_kg"])), Decimal("50"))
        self.assertEqual(len(row["open_bills"]), 3)

    def test_200_on_hand_reserved(self):
        self.inv.loose_kg = Decimal("200")
        self.inv.total_quantity_kg = Decimal("200")
        self.db.commit()
        self._create_bill("100")
        one = self._hint_item(self.product.id)
        h1 = compute_sales_stock_hint(one.on_hand_kg, one.open_bills)
        self.assertEqual(h1.available_kg, Decimal("200"))
        self.assertEqual(h1.reserved_kg, Decimal("0"))

        self._create_bill("100")
        two = self._hint_item(self.product.id)
        h2 = compute_sales_stock_hint(two.on_hand_kg, two.open_bills)
        self.assertEqual(h2.available_kg, Decimal("200"))
        self.assertEqual(h2.reserved_kg, Decimal("100"))

    def test_create_over_on_hand_does_not_change_inventory(self):
        before = self.inv.total_quantity_kg
        out = self._create_bill("100")
        self.assertGreater(out.id, 0)
        self.db.refresh(self.inv)
        self.assertEqual(self.inv.total_quantity_kg, before)

    def test_deliver_over_on_hand_fails(self):
        bill = self._create_bill("100")
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
