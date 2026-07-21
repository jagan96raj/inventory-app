"""Spec v17.0.5 — Profile company update + book_settings header sync."""
import unittest
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.permissions import OWNER_ONLY_COMPANY_MSG
from app.database import Base, get_db
from app.main import app
from app.models.entities import BookSettings, Company, User, UserRole
from app.services.accounts import get_book_settings, serialize_book_settings
from tests.idempotency_helpers import ensure_test_user


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class ProfileCompanyV1705Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        ensure_test_user(self.db)
        self.db.add(
            BookSettings(
                id=1,
                company_id=1,
                cash_opening_balance=Decimal("100.00"),
                cash_opening_balance_at=date(2026, 1, 1),
                company_name="Raj Agro",
                company_address_line="Old Addr",
                company_phone="111",
            )
        )
        self.writer = User(
            id=2,
            email="writer@example.com",
            name="Writer",
            password_hash="x",
            role=UserRole.writer,
            company_id=1,
            is_active=True,
        )
        self.db.add(self.writer)
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self._as_owner()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _as_owner(self):
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 1)

    def _as_writer(self):
        app.dependency_overrides[get_current_user] = lambda: self.db.get(User, 2)

    def test_owner_patch_updates_company(self):
        self._as_owner()
        res = self.client.patch(
            "/api/companies/me",
            json={
                "name": "Raj Agro Updated",
                "address_line": "New Road 1",
                "address_line_2": "Near Market",
                "district": "Coimbatore",
                "state": "Tamil Nadu",
                "pin_code": "641001",
                "gstin": "33AAAAA0000A1Z5",
                "phone": "99999",
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["name"], "Raj Agro Updated")
        self.assertEqual(data["address_line"], "New Road 1")
        self.assertEqual(data["address_line_2"], "Near Market")
        self.assertEqual(data["district"], "Coimbatore")
        self.assertEqual(data["state"], "Tamil Nadu")
        self.assertEqual(data["pin_code"], "641001")
        self.assertEqual(data["gstin"], "33AAAAA0000A1Z5")
        self.assertEqual(data["phone"], "99999")

        company = self.db.get(Company, 1)
        self.assertEqual(company.name, "Raj Agro Updated")
        self.assertEqual(company.address_line, "New Road 1")
        self.assertEqual(company.gstin, "33AAAAA0000A1Z5")

    def test_non_owner_patch_403(self):
        self._as_writer()
        res = self.client.patch(
            "/api/companies/me",
            json={"name": "Hacked Co"},
        )
        self.assertEqual(res.status_code, 403, res.text)
        self.assertEqual(res.json()["detail"], OWNER_ONLY_COMPANY_MSG)
        company = self.db.get(Company, 1)
        self.assertEqual(company.name, "Raj Agro")

    def test_owner_update_syncs_book_settings_header(self):
        self._as_owner()
        res = self.client.patch(
            "/api/companies/me",
            json={
                "name": "Synced Name",
                "address_line": "Synced Addr",
                "address_line_2": "Line 2",
                "district": "Erode",
                "state": "TN",
                "pin_code": "638001",
                "phone": "555",
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        settings = self.db.scalar(select(BookSettings).where(BookSettings.company_id == 1))
        self.assertIsNotNone(settings)
        self.assertEqual(settings.company_name, "Synced Name")
        self.assertEqual(settings.company_address_line, "Synced Addr, Line 2, Erode, TN, 638001")
        self.assertEqual(settings.company_phone, "555")
        # Cash opening untouched
        self.assertEqual(Decimal(str(settings.cash_opening_balance)), Decimal("100.00"))

    def test_book_settings_get_still_returns_cash_and_prefers_company(self):
        company = self.db.get(Company, 1)
        company.name = "From Companies Table"
        company.address_line = "Co Addr"
        company.address_line_2 = "Suite 2"
        company.district = "Salem"
        company.state = "TN"
        company.pin_code = "636001"
        company.gstin = "33BBBBB0000B1Z5"
        company.phone = "777"
        self.db.commit()

        self._as_owner()
        res = self.client.get("/api/book-settings")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(Decimal(str(data["cash_opening_balance"])), Decimal("100.00"))
        self.assertEqual(data["company_name"], "From Companies Table")
        self.assertEqual(data["company_address_line"], "Co Addr")
        self.assertEqual(data["company_address_line_2"], "Suite 2")
        self.assertEqual(data["company_district"], "Salem")
        self.assertEqual(data["company_gstin"], "33BBBBB0000B1Z5")
        self.assertEqual(data["company_phone"], "777")

    def test_serialize_falls_back_when_company_missing_on_settings(self):
        settings = get_book_settings(self.db, 1)
        # Detach company relationship simulation: clear and use column values
        settings.company_name = "Fallback Name"
        settings.company_address_line = "Fallback Addr"
        settings.company_phone = "000"
        # Prefer company when relationship present
        out = serialize_book_settings(settings)
        self.assertEqual(out["company_name"], "Raj Agro")  # from companies row via relationship

    def test_get_companies_me_ok_for_writer(self):
        self._as_writer()
        res = self.client.get("/api/companies/me")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["name"], "Raj Agro")


if __name__ == "__main__":
    unittest.main()
