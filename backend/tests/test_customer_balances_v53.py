"""Spec v5.3 — customer opening balances on create only."""
import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Customer
from app.routers.masters import create_customer, get_customer, update_customer
from app.schemas import CustomerCreate, CustomerUpdate


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class CustomerBalancesV53Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()

    def tearDown(self):
        self.db.close()

    def test_create_with_opening_balances_persists(self):
        created = create_customer(
            CustomerCreate(
                name="Opening Bal Co",
                credit_balance=Decimal("5000"),
                debit_balance=Decimal("3000"),
            ),
            db=self.db,
        )
        self.assertEqual(created.credit_balance, Decimal("5000"))
        self.assertEqual(created.debit_balance, Decimal("3000"))

        fetched = get_customer(created.id, db=self.db)
        self.assertEqual(fetched.credit_balance, Decimal("5000"))
        self.assertEqual(fetched.debit_balance, Decimal("3000"))

    def test_update_ignores_balance_fields(self):
        created = create_customer(
            CustomerCreate(
                name="Stable Bal Co",
                credit_balance=Decimal("5000"),
                debit_balance=Decimal("3000"),
            ),
            db=self.db,
        )

        updated = update_customer(
            created.id,
            CustomerUpdate.model_validate(
                {
                    "name": "Stable Bal Co Renamed",
                    "credit_balance": 0,
                    "debit_balance": 0,
                }
            ),
            db=self.db,
        )
        self.assertEqual(updated.name, "Stable Bal Co Renamed")
        self.assertEqual(updated.credit_balance, Decimal("5000"))
        self.assertEqual(updated.debit_balance, Decimal("3000"))

        row = self.db.get(Customer, created.id)
        self.assertEqual(row.credit_balance, Decimal("5000"))
        self.assertEqual(row.debit_balance, Decimal("3000"))


if __name__ == "__main__":
    unittest.main()
