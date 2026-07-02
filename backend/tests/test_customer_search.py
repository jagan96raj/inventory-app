"""Customer search by name and phone."""
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Customer
from app.services.customer_search import apply_customer_search


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class CustomerSearchTests(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.db.add_all(
            [
                Customer(name="Suresh Traders", phone="9876543210", alternate_phone="9123456789"),
                Customer(name="Raj Agro", phone="8011223344"),
                Customer(name="No Phone Co"),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _names(self, search: str | None) -> list[str]:
        q = apply_customer_search(select(Customer).order_by(Customer.name), search)
        return [c.name for c in self.db.scalars(q).all()]

    def test_search_by_name(self):
        self.assertEqual(self._names("suresh"), ["Suresh Traders"])

    def test_search_by_primary_phone(self):
        self.assertEqual(self._names("9876543210"), ["Suresh Traders"])
        self.assertEqual(self._names("8011"), ["Raj Agro"])

    def test_search_by_alternate_phone(self):
        self.assertEqual(self._names("9123456789"), ["Suresh Traders"])

    def test_empty_search_returns_all(self):
        self.assertEqual(len(self._names(None)), 3)
        self.assertEqual(len(self._names("")), 3)


if __name__ == "__main__":
    unittest.main()
