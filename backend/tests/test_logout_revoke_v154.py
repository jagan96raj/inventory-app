"""Spec v15.4 — logout revokes JWT immediately."""
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import COOKIE_NAME, hash_password
from app.database import Base, get_db
from app.main import app
from app.models.entities import RevokedToken, User, UserRole

PASSWORD = "password123"


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class LogoutRevokeV154Tests(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.user_a = User(
            id=1,
            email="usera@test.com",
            password_hash=hash_password(PASSWORD),
            name="User A",
            role=UserRole.owner,
        )
        self.user_b = User(
            id=2,
            email="userb@test.com",
            password_hash=hash_password(PASSWORD),
            name="User B",
            role=UserRole.owner,
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()

    def _login(self, email: str) -> str:
        res = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": PASSWORD},
        )
        self.assertEqual(res.status_code, 200, res.text)
        token = res.cookies.get(COOKIE_NAME)
        self.assertTrue(token)
        return token

    def test_logout_revokes_session_immediately(self):
        token = self._login(self.user_a.email)
        self.client.cookies.set(COOKIE_NAME, token)

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], self.user_a.email)

        logout = self.client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200)

        replay = self.client.get("/api/auth/me")
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.json()["detail"], "Not authenticated")

        claims_jti = self.db.scalars(select(RevokedToken.jti)).all()
        self.assertEqual(len(claims_jti), 1)

    def test_login_again_after_logout_works(self):
        token = self._login(self.user_a.email)
        self.client.cookies.set(COOKIE_NAME, token)
        self.client.post("/api/auth/logout")

        new_token = self._login(self.user_a.email)
        self.client.cookies.set(COOKIE_NAME, new_token)
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)

    def test_logout_user_a_does_not_revoke_user_b(self):
        token_a = self._login(self.user_a.email)
        token_b = self._login(self.user_b.email)

        self.client.cookies.set(COOKIE_NAME, token_a)
        self.client.post("/api/auth/logout")

        self.client.cookies.set(COOKIE_NAME, token_b)
        me_b = self.client.get("/api/auth/me")
        self.assertEqual(me_b.status_code, 200)
        self.assertEqual(me_b.json()["email"], self.user_b.email)

        self.client.cookies.set(COOKIE_NAME, token_a)
        me_a = self.client.get("/api/auth/me")
        self.assertEqual(me_a.status_code, 401)


if __name__ == "__main__":
    unittest.main()
